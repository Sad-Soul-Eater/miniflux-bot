import asyncio
import sqlite3
from abc import ABC, abstractmethod


class StateStore(ABC):
    @abstractmethod
    async def get_processed_id(self) -> int: ...

    @abstractmethod
    async def set_processed_id(self, entry_id: int): ...

    @abstractmethod
    async def init(self): ...

    @abstractmethod
    async def close(self): ...


class SqliteStateStore(StateStore):
    def __init__(self, path: str):
        self._conn: sqlite3.Connection | None = None
        self._path = path

    @property
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("StateStore not initialized - call init() first")
        return self._conn

    async def init(self):
        self._conn = await asyncio.to_thread(
            sqlite3.connect, self._path, check_same_thread=False
        )

        await asyncio.to_thread(self._init_db)

    async def close(self):
        if self._conn is None:
            return
        await asyncio.to_thread(self._connection.close)

    def _init_db(self):
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER)"
            )
            self._connection.execute(
                "INSERT or IGNORE INTO state (key, value) VALUES (?, ?)",
                ("processed_id", 0),
            )

    def _set(self, entry_id: int):
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
