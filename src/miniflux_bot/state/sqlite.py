import logging

import aiosqlite

from miniflux_bot.state import StateStore

logger = logging.getLogger(__name__)


class SqliteStateStore(StateStore):
    def __init__(self, path: str) -> None:
        self._conn: aiosqlite.Connection | None = None
        self._path = path

    @property
    def _connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("StateStore not initialized - call init() first")
        return self._conn

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(database=self._path, autocommit=True)
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")
        await self._connection.execute(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER)"
        )
        await self._connection.execute(
            "INSERT or IGNORE INTO state (key, value) VALUES (?, ?)",
            ("processed_id", 0),
        )
        logger.info("SQLite state store ready at %s", self._path)

    async def close(self) -> None:
        if self._conn is None:
            return
        await self._connection.close()

    async def get_processed_id(self) -> int:
        async with await self._connection.execute(
            "SELECT value FROM state WHERE key = ?", ("processed_id",)
        ) as cur:
            row = await cur.fetchone()
            if row is not None:
                return row[0]
            else:
                raise RuntimeError("Failed to retrieve processed_id")

    async def set_processed_id(self, entry_id: int) -> None:
        await self._connection.execute(
            """
            INSERT INTO state (key, value)
            VALUES (?, ?) ON CONFLICT(key) DO
                UPDATE SET value = excluded.value
            """,
            ("processed_id", entry_id),
        )
