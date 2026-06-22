from psycopg_pool import AsyncConnectionPool

from miniflux_bot.state import StateStore


class PostgresStateStore(StateStore):
    def __init__(self, connection_string: str) -> None:
        self._pool = AsyncConnectionPool(
            connection_string,
            open=False,
            kwargs={"autocommit": True},
            check=AsyncConnectionPool.check_connection,
            min_size=1,
            max_size=2,
        )

    async def init(self) -> None:
        await self._pool.open(wait=True)
        await self._init_db()

    async def close(self) -> None:
        if self._pool.closed:
            return
        await self._pool.close()

    async def _init_db(self) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS miniflux_bot_state (key TEXT PRIMARY KEY, value BIGINT)"
            )
            await conn.execute(
                "INSERT INTO miniflux_bot_state (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                ("processed_id", 0),
            )

    async def get_processed_id(self) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT value FROM miniflux_bot_state WHERE key = %s", ("processed_id",)
            )
            row = await cur.fetchone()

        if row is not None:
            return row[0]
        else:
            raise RuntimeError("Failed to retrieve processed_id")

    async def set_processed_id(self, entry_id: int) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO miniflux_bot_state (key, value)
                VALUES (%s, %s) ON CONFLICT(key) DO
                UPDATE SET value = excluded.value
                """,
                ("processed_id", entry_id),
            )
