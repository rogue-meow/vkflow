from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import typing
import warnings

from . import BaseStorage


__all__ = ("SQLiteStorage",)


try:
    import aiosqlite

    _HAS_AIOSQLITE = True
except ImportError:
    _HAS_AIOSQLITE = False


class _SyncCursorWrapper:
    """Async-обёртка над синхронным sqlite3.Cursor."""

    def __init__(self, cursor: sqlite3.Cursor):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    async def fetchone(self):
        return self._cursor.fetchone()

    async def fetchall(self):
        return self._cursor.fetchall()


class _SyncConnectionWrapper:
    """Async-обёртка над синхронным sqlite3.Connection через to_thread."""

    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection
        self._lock = asyncio.Lock()

    async def execute(self, sql: str, parameters: tuple = ()) -> _SyncCursorWrapper:
        async with self._lock:
            cursor = await asyncio.to_thread(self._conn.execute, sql, parameters)
            return _SyncCursorWrapper(cursor)

    async def commit(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._conn.commit)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS fsm_states (
    key        TEXT PRIMARY KEY,
    state      TEXT,
    data       TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL
)
"""


class SQLiteStorage(BaseStorage):
    """
    FSM-хранилище на основе SQLite.

    Сохраняет состояния и данные FSM в файле базы данных SQLite.
    Данные переживают перезапуск бота.

    Возможности:
    - Персистентное хранение через SQLite
    - Опциональный TTL для автоматического истечения состояний
    - WAL-режим журнала для лучшей производительности
    - Ленивое подключение (создаётся при первом обращении)
    - Поддержка context manager

    Зависимости:
        При наличии ``aiosqlite`` (``pip install aiosqlite``) используется
        асинхронный драйвер. При отсутствии — синхронный ``sqlite3``
        из стандартной библиотеки через ``asyncio.to_thread``.

    Examples:
        # Базовое использование
        storage = SQLiteStorage()

        # Свой путь и TTL
        storage = SQLiteStorage("bot_states.db", ttl=3600)

        # В памяти (как MemoryStorage, но через SQL)
        storage = SQLiteStorage(":memory:")

        # Context manager
        async with SQLiteStorage("fsm.db") as storage:
            router = FSMRouter(storage)
    """

    def __init__(self, path: str = "fsm.db", ttl: float | None = None):
        """
        Инициализация SQLiteStorage.

        Args:
            path: Путь к файлу БД или ":memory:" для хранения
                  в оперативной памяти. По умолчанию "fsm.db".
            ttl: Опциональное время жизни состояний в секундах.
                 При установке просроченные состояния автоматически
                 удаляются при следующем обращении. None — без ограничений.
        """
        if not _HAS_AIOSQLITE:
            warnings.warn(
                "aiosqlite не установлен, SQLiteStorage будет использовать "
                "синхронный sqlite3 через asyncio.to_thread. "
                "Для лучшей производительности: pip install aiosqlite",
                stacklevel=2,
            )
        self._path = path
        self._ttl = ttl
        self._connection = None

    async def _ensure_connection(self):
        if self._connection is not None:
            return

        if _HAS_AIOSQLITE:
            self._connection = await aiosqlite.connect(self._path)
        else:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            self._connection = _SyncConnectionWrapper(conn)

        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute(_CREATE_TABLE)
        await self._connection.commit()

    async def _is_expired(self, updated_at: float) -> bool:
        if self._ttl is None:
            return False
        return time.time() - updated_at > self._ttl

    async def get_state(self, key: str) -> str | None:
        await self._ensure_connection()
        cursor = await self._connection.execute(
            "SELECT state, updated_at FROM fsm_states WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        if await self._is_expired(row[1]):
            await self._delete_row(key)
            return None

        return row[0]

    async def set_state(self, key: str, state: str) -> None:
        await self._ensure_connection()
        now = time.time()
        await self._connection.execute(
            "INSERT INTO fsm_states (key, state, data, updated_at) VALUES (?, ?, '{}', ?)"
            " ON CONFLICT(key) DO UPDATE SET state = ?, updated_at = ?",
            (key, state, now, state, now),
        )
        await self._connection.commit()

    async def delete_state(self, key: str) -> None:
        await self._ensure_connection()
        await self._connection.execute(
            "UPDATE fsm_states SET state = NULL WHERE key = ?",
            (key,),
        )
        await self._connection.commit()

    async def get_data(self, key: str) -> dict[str, typing.Any]:
        await self._ensure_connection()
        cursor = await self._connection.execute(
            "SELECT data, updated_at FROM fsm_states WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()

        if row is None:
            return {}

        if await self._is_expired(row[1]):
            await self._delete_row(key)
            return {}

        return json.loads(row[0])

    async def set_data(self, key: str, data: dict[str, typing.Any]) -> None:
        await self._ensure_connection()
        now = time.time()
        serialized = json.dumps(data)
        await self._connection.execute(
            "INSERT INTO fsm_states (key, state, data, updated_at) VALUES (?, NULL, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET data = ?, updated_at = ?",
            (key, serialized, now, serialized, now),
        )
        await self._connection.commit()

    async def update_data(self, key: str, **kwargs: typing.Any) -> dict[str, typing.Any]:
        await self._ensure_connection()
        data = await self.get_data(key)
        data.update(kwargs)
        await self.set_data(key, data)
        return data

    async def delete_data(self, key: str) -> None:
        await self._ensure_connection()
        await self._connection.execute(
            "UPDATE fsm_states SET data = '{}' WHERE key = ?",
            (key,),
        )
        await self._connection.commit()

    async def close(self) -> None:
        """Закрывает соединение с SQLite."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def cleanup(self) -> int:
        """
        Удаляет все просроченные записи из базы данных.

        Работает только при настроенном TTL.

        Returns:
            Количество удалённых записей.
        """
        if self._ttl is None:
            return 0

        await self._ensure_connection()
        threshold = time.time() - self._ttl
        cursor = await self._connection.execute(
            "DELETE FROM fsm_states WHERE updated_at < ?",
            (threshold,),
        )
        await self._connection.commit()
        return cursor.rowcount

    async def get_states_count(self) -> int:
        """
        Количество активных состояний (для отладки).

        Returns:
            Число хранимых состояний.
        """
        await self._ensure_connection()
        cursor = await self._connection.execute(
            "SELECT COUNT(*) FROM fsm_states WHERE state IS NOT NULL",
        )
        row = await cursor.fetchone()
        return row[0]

    async def get_keys(self) -> list[str]:
        """
        Все хранимые ключи (для отладки).

        Returns:
            Список ключей с активными состояниями.
        """
        await self._ensure_connection()
        cursor = await self._connection.execute(
            "SELECT key FROM fsm_states WHERE state IS NOT NULL",
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def _delete_row(self, key: str) -> None:
        await self._connection.execute(
            "DELETE FROM fsm_states WHERE key = ?",
            (key,),
        )
        await self._connection.commit()

    async def __aenter__(self):
        await self._ensure_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
