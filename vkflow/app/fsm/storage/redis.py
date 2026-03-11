from __future__ import annotations

import json
import typing

from . import BaseStorage


__all__ = ("RedisStorage",)


try:
    import redis.asyncio as aioredis

    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False


class RedisStorage(BaseStorage):
    """
    FSM-хранилище на основе Redis.

    Сохраняет состояния и данные FSM в Redis с использованием
    хэшей (HSET/HGET). Каждый ключ FSM хранится как Redis hash
    с полями ``state`` и ``data``.

    Возможности:
    - Персистентное хранение через Redis
    - Нативный TTL через ``EXPIRE`` — автоматическое истечение без ручных проверок
    - Настраиваемый префикс ключей для изоляции данных
    - Ленивое подключение (создаётся при первом обращении)
    - Поддержка context manager

    Зависимости:
        Требуется ``redis`` (``pip install redis``).
        При отсутствии пакета будет выброшено ``RuntimeError``.

    Examples:
        # Базовое использование
        storage = RedisStorage()

        # С настройками
        storage = RedisStorage("redis://localhost:6379/1", ttl=3600)

        # Свой префикс для изоляции
        storage = RedisStorage(prefix="mybot:fsm:")

        # Существующий клиент Redis
        import redis.asyncio as aioredis
        client = aioredis.Redis(host="redis.example.com")
        storage = RedisStorage(client=client)

        # Context manager
        async with RedisStorage() as storage:
            router = FSMRouter(storage)
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        *,
        ttl: int | None = None,
        prefix: str = "vkflow:fsm:",
        client: typing.Any | None = None,
    ):
        """
        Инициализация RedisStorage.

        Args:
            url: URL подключения к Redis. Игнорируется, если передан ``client``.
                 По умолчанию ``"redis://localhost:6379/0"``.
            ttl: Опциональное время жизни состояний в секундах.
                 Использует нативный Redis TTL (``EXPIRE``).
                 None — без ограничений.
            prefix: Префикс для всех ключей в Redis.
                    По умолчанию ``"vkflow:fsm:"``.
            client: Существующий экземпляр ``redis.asyncio.Redis``.
                    Если передан, ``url`` игнорируется, и при ``close()``
                    соединение НЕ закрывается (управление — на вызывающей стороне).
        """
        if not _HAS_REDIS and client is None:
            raise RuntimeError(
                "Для использования RedisStorage необходим пакет redis. "
                "Установите его: pip install redis или pip install vkflow[redis]"
            )
        self._url = url
        self._ttl = ttl
        self._prefix = prefix
        self._client = client
        self._owns_client = client is None

    def _make_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def _ensure_connection(self) -> None:
        if self._client is not None:
            return
        if not _HAS_REDIS:
            raise RuntimeError(
                "Для использования RedisStorage необходим пакет redis. "
                "Установите его: pip install redis или pip install vkflow[redis]"
            )
        self._client = aioredis.from_url(self._url)

    async def _refresh_ttl(self, redis_key: str) -> None:
        if self._ttl is not None and self._client is not None:
            await self._client.expire(redis_key, self._ttl)

    async def get_state(self, key: str) -> str | None:
        await self._ensure_connection()
        redis_key = self._make_key(key)
        value = await self._client.hget(redis_key, "state")  # type: ignore[union-attr]
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

    async def set_state(self, key: str, state: str) -> None:
        await self._ensure_connection()
        redis_key = self._make_key(key)
        await self._client.hset(redis_key, "state", state)  # type: ignore[union-attr]
        await self._refresh_ttl(redis_key)

    async def delete_state(self, key: str) -> None:
        await self._ensure_connection()
        redis_key = self._make_key(key)
        await self._client.hdel(redis_key, "state")  # type: ignore[union-attr]

    async def get_data(self, key: str) -> dict[str, typing.Any]:
        await self._ensure_connection()
        redis_key = self._make_key(key)
        value = await self._client.hget(redis_key, "data")  # type: ignore[union-attr]
        if value is None:
            return {}
        raw = value.decode() if isinstance(value, bytes) else value
        return json.loads(raw)

    async def set_data(self, key: str, data: dict[str, typing.Any]) -> None:
        await self._ensure_connection()
        redis_key = self._make_key(key)
        await self._client.hset(redis_key, "data", json.dumps(data))  # type: ignore[union-attr]
        await self._refresh_ttl(redis_key)

    async def update_data(self, key: str, **kwargs: typing.Any) -> dict[str, typing.Any]:
        data = await self.get_data(key)
        data.update(kwargs)
        await self.set_data(key, data)
        return data

    async def delete_data(self, key: str) -> None:
        await self._ensure_connection()
        redis_key = self._make_key(key)
        await self._client.hdel(redis_key, "data")  # type: ignore[union-attr]

    async def close(self) -> None:
        """Закрывает соединение с Redis (если оно создано этим хранилищем)."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def get_states_count(self) -> int:
        """
        Количество активных состояний (для отладки).

        Выполняет ``SCAN`` по ключам с префиксом и проверяет наличие
        поля ``state`` в каждом хэше.

        Returns:
            Число хранимых состояний.
        """
        await self._ensure_connection()
        count = 0
        async for redis_key in self._client.scan_iter(match=f"{self._prefix}*"):  # type: ignore[union-attr]
            if await self._client.hexists(redis_key, "state"):  # type: ignore[union-attr]
                count += 1
        return count

    async def get_keys(self) -> list[str]:
        """
        Все хранимые ключи с активными состояниями (для отладки).

        Returns:
            Список ключей (без префикса) с активными состояниями.
        """
        await self._ensure_connection()
        keys = []
        prefix_len = len(self._prefix)
        async for redis_key in self._client.scan_iter(match=f"{self._prefix}*"):  # type: ignore[union-attr]
            if await self._client.hexists(redis_key, "state"):  # type: ignore[union-attr]
                raw = redis_key.decode() if isinstance(redis_key, bytes) else redis_key
                keys.append(raw[prefix_len:])
        return keys

    async def __aenter__(self):
        await self._ensure_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
