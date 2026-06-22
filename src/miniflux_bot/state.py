import asyncio
import sqlite3
from abc import ABC, abstractmethod

import psycopg


class StateStore(ABC):
    @abstractmethod
    async def get_processed_id(self) -> int: ...

    @abstractmethod
    async def set_processed_id(self, entry_id: int) -> None: ...

    @abstractmethod
    async def init(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class SqliteStateStore(StateStore):
    def __init__(self, path: str) -> None:
        self._conn: sqlite3.Connection | None = None
        self._path = path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(database=self._path, check_same_thread=False)

    @property
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("StateStore not initialized - call init() first")
        return self._conn

    async def init(self) -> None:
        self._conn = await asyncio.to_thread(self._connect)

        await asyncio.to_thread(self._init_db)

    async def close(self) -> None:
        if self._conn is None:
            return
        await asyncio.to_thread(self._connection.close)

    def _init_db(self) -> None:
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER)"
            )
            self._connection.execute(
                "INSERT or IGNORE INTO state (key, value) VALUES (?, ?)",
                ("processed_id", 0),
            )

    def _set(self, entry_id: int) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO state (key, value)
                VALUES (?, ?) ON CONFLICT(key) DO
                UPDATE SET value = excluded.value
                """,
                ("processed_id", entry_id),
            )

    def _get(self) -> int:
        return self._connection.execute(
            "SELECT value FROM state WHERE key = ?", ("processed_id",)
        ).fetchone()[0]

    async def get_processed_id(self) -> int:
        return await asyncio.to_thread(self._get)

    async def set_processed_id(self, entry_id: int):
        await asyncio.to_thread(self._set, entry_id)


class PostgresStateStore(StateStore):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string
        self._conn: psycopg.AsyncConnection | None = None

    async def init(self) -> None:
        self._conn = await psycopg.AsyncConnection.connect(
            self._connection_string, autocommit=True
        )
        await self._init_db()

    async def close(self) -> None:
        if self._conn is None:
            return
        await self._conn.close()

    @property
    def _connection(self) -> psycopg.AsyncConnection:
        if self._conn is None:
            raise RuntimeError("StateStore not initialized - call init() first")
        return self._conn

    async def _init_db(self) -> None:
        await self._connection.execute(
            "CREATE TABLE IF NOT EXISTS miniflux_bot_state (key TEXT PRIMARY KEY, value BIGINT)"
        )
        await self._connection.execute(
            "INSERT INTO miniflux_bot_state (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
            ("processed_id", 0),
        )

    async def get_processed_id(self) -> int:
        result = await (
            await self._connection.execute(
                "SELECT value FROM miniflux_bot_state WHERE key = %s", ("processed_id",)
            )
        ).fetchone()

        if result is not None:
            return result[0]
        raise RuntimeError("Failed to retrieve processed_id")

    async def set_processed_id(self, entry_id: int) -> None:
        await self._connection.execute(
            """
            INSERT INTO miniflux_bot_state (key, value)
            VALUES (%s, %s) ON CONFLICT(key) DO
            UPDATE SET value = excluded.value
            """,
            ("processed_id", entry_id),
        )
