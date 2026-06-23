import asyncio
import logging
import sqlite3

from miniflux_bot.state import StateStore

logger = logging.getLogger(__name__)


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
        logger.info("SQLite state store ready at %s", self._path)

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

    def _write_processed_id(self, entry_id: int) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO state (key, value)
                VALUES (?, ?) ON CONFLICT(key) DO
                UPDATE SET value = excluded.value
                """,
                ("processed_id", entry_id),
            )

    def _read_processed_id(self) -> int:
        return self._connection.execute(
            "SELECT value FROM state WHERE key = ?", ("processed_id",)
        ).fetchone()[0]

    async def get_processed_id(self) -> int:
        return await asyncio.to_thread(self._read_processed_id)

    async def set_processed_id(self, entry_id: int):
        await asyncio.to_thread(self._write_processed_id, entry_id)
