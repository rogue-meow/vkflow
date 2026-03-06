from __future__ import annotations

import asyncio
import functools

import time

import hashlib

from dataclasses import dataclass
from collections import OrderedDict

from typing import (
    Any,
    Generic,
    TypeVar,
    ParamSpec,
    overload,
)
from collections.abc import Callable, Coroutine


__all__ = (
    "APICache",
    "CacheConfig",
    "CachedFunction",
    "cached",
    "clear_all_caches",
)


P = ParamSpec("P")
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


_cached_functions: list[CachedFunction] = []


@dataclass
class CacheConfig:
    ttl: float = 300
    max_size: int = 1000
    include_api_in_key: bool = False
    hash_large_values: bool = True
    large_value_threshold: int = 100


@dataclass
class CacheEntry(Generic[T]):
    value: T
    created_at: float
    ttl: float
    hits: int = 0

    def is_expired(self) -> bool:
        if self.ttl <= 0:
            return False
        return time.time() - self.created_at > self.ttl

    def touch(self) -> None:
        self.hits += 1


class APICache(Generic[T]):
    def __init__(self, config: CacheConfig | None = None):
        self.config = config or CacheConfig()
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = asyncio.Lock()

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        key_parts = []

        for arg in args:
            if self.config.hash_large_values and isinstance(arg, (str, bytes)):  # noqa: SIM102
                if len(arg) > self.config.large_value_threshold:
                    arg = hashlib.md5(str(arg).encode()).hexdigest()

            key_parts.append(repr(arg))

        for k, v in sorted(kwargs.items()):
            if self.config.hash_large_values and isinstance(v, (str, bytes)):  # noqa: SIM102
                if len(v) > self.config.large_value_threshold:
                    v = hashlib.md5(str(v).encode()).hexdigest()

            key_parts.append(f"{k}={v!r}")

        return ":".join(key_parts)

    async def get(self, key: str) -> T | None:
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            if entry.is_expired():
                del self._cache[key]
                return None

            self._cache.move_to_end(key)
            entry.touch()

            return entry.value

    async def set(self, key: str, value: T) -> None:
        async with self._lock:
            if self.config.max_size > 0:
                while len(self._cache) >= self.config.max_size:
                    self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(
                value=value,
                created_at=time.time(),
                ttl=self.config.ttl,
            )

    async def invalidate(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]

                return True
            return False

    def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()

        return count

    async def cleanup_expired(self) -> int:
        async with self._lock:
            expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]

            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    @property
    def size(self) -> int:
        return len(self._cache)

    def stats(self) -> dict[str, Any]:
        total_hits = sum(entry.hits for entry in self._cache.values())

        return {
            "size": self.size,
            "max_size": self.config.max_size,
            "ttl": self.config.ttl,
            "total_hits": total_hits,
        }


class CachedFunction(Generic[P, T]):
    def __init__(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        cache: APICache[T],
        config: CacheConfig,
    ):
        self._func = func
        self._cache = cache
        self._config = config

        functools.update_wrapper(self, func)
        _cached_functions.append(self)

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self._config.include_api_in_key and args:
            cache_args = args[1:] if len(args) > 1 else ()
        else:
            cache_args = args

        key = self._cache._make_key(*cache_args, **kwargs)
        cached_value = await self._cache.get(key)

        if cached_value is not None:
            return cached_value

        result = await self._func(*args, **kwargs)

        await self._cache.set(key, result)
        return result

    async def invalidate(self, *args: Any, **kwargs: Any) -> bool:
        key = self._cache._make_key(*args, **kwargs)
        return await self._cache.invalidate(key)

    def clear_cache(self) -> int:
        return self._cache.clear()

    async def refresh(self, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self._config.include_api_in_key and args:
            cache_args = args[1:] if len(args) > 1 else ()
        else:
            cache_args = args

        key = self._cache._make_key(*cache_args, **kwargs)
        await self._cache.invalidate(key)

        result = await self._func(*args, **kwargs)

        await self._cache.set(key, result)
        return result

    def stats(self) -> dict[str, Any]:
        stats = self._cache.stats()
        stats["function"] = self._func.__name__

        return stats

    @property
    def cache(self) -> APICache[T]:
        return self._cache


@overload
def cached(
    func: F,
) -> CachedFunction[..., Any]: ...


@overload
def cached(
    *,
    ttl: float = 300,
    max_size: int = 1000,
    config: CacheConfig | None = None,
) -> Callable[[F], CachedFunction[..., Any]]: ...


def cached(
    func: F | None = None,
    *,
    ttl: float = 300,
    max_size: int = 1000,
    config: CacheConfig | None = None,
) -> CachedFunction[..., Any] | Callable[[F], CachedFunction[..., Any]]:
    if config is None:
        config = CacheConfig(ttl=ttl, max_size=max_size)

    def decorator(f: F) -> CachedFunction[..., Any]:
        cache = APICache(config)
        return CachedFunction(f, cache, config)

    if func is not None:
        return decorator(func)
    return decorator


def clear_all_caches() -> int:
    total = 0

    for cached_func in _cached_functions:
        total += cached_func.clear_cache()

    return total


def cached_user(ttl: float = 300) -> Callable[[F], CachedFunction[..., Any]]:
    return cached(ttl=ttl, max_size=5000)


def cached_group(ttl: float = 600) -> Callable[[F], CachedFunction[..., Any]]:
    return cached(ttl=ttl, max_size=2000)


def cached_message(ttl: float = 60) -> Callable[[F], CachedFunction[..., Any]]:
    return cached(ttl=ttl, max_size=500)
