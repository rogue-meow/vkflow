from __future__ import annotations

import time
import asyncio
import typing
from collections import defaultdict

from . import BaseStorage


__all__ = ("MemoryStorage",)


class MemoryStorage(BaseStorage):
    """
    In-memory FSM storage implementation.

    Stores FSM state and data in Python dictionaries.
    Data is lost when the bot restarts.

    Features:
    - Thread-safe via asyncio.Lock
    - Optional TTL for automatic state expiration
    - Zero dependencies

    Best for:
    - Development and testing
    - Small bots where persistence isn't critical
    - Stateless deployments

    Examples:
        # Basic usage
        storage = MemoryStorage()

        # With TTL (states expire after 1 hour)
        storage = MemoryStorage(ttl=3600)

        # Use with FSMRouter
        router = FSMRouter(storage)
    """

    def __init__(self, ttl: float | None = None):
        """
        Initialize MemoryStorage.

        Args:
            ttl: Optional time-to-live in seconds for states.
                 If set, states older than TTL will be automatically
                 cleared on next access. None means no expiration.
        """
        self._states: dict[str, str] = {}
        self._data: dict[str, dict[str, typing.Any]] = defaultdict(dict)
        self._timestamps: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl

    async def _check_and_clean_ttl(self, key: str) -> bool:
        """
        Check if key has expired and clean if needed.

        Must be called with lock held.

        Args:
            key: Key to check

        Returns:
            True if key is valid, False if expired/cleaned.
        """
        if self._ttl is None:
            return True

        timestamp = self._timestamps.get(key)
        if timestamp is None:
            return True

        if time.time() - timestamp > self._ttl:
            self._states.pop(key, None)
            self._data.pop(key, None)
            self._timestamps.pop(key, None)
            return False

        return True

    async def get_state(self, key: str) -> str | None:
        async with self._lock:
            if not await self._check_and_clean_ttl(key):
                return None
            return self._states.get(key)

    async def set_state(self, key: str, state: str) -> None:
        async with self._lock:
            self._states[key] = state
            self._timestamps[key] = time.time()

    async def delete_state(self, key: str) -> None:
        async with self._lock:
            self._states.pop(key, None)
            self._timestamps.pop(key, None)

    async def get_data(self, key: str) -> dict[str, typing.Any]:
        async with self._lock:
            if not await self._check_and_clean_ttl(key):
                return {}
            return self._data.get(key, {}).copy()

    async def set_data(self, key: str, data: dict[str, typing.Any]) -> None:
        async with self._lock:
            self._data[key] = data.copy()

    async def update_data(self, key: str, **kwargs: typing.Any) -> dict[str, typing.Any]:
        async with self._lock:
            self._data[key].update(kwargs)
            return self._data[key].copy()

    async def delete_data(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    def get_states_count(self) -> int:
        """
        Get number of active states (for debugging).

        Returns:
            Number of stored states.
        """
        return len(self._states)

    def get_keys(self) -> list[str]:
        """
        Get all stored keys (for debugging).

        Returns:
            List of all keys with active states.
        """
        return list(self._states.keys())
