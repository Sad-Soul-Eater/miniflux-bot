import asyncio
import logging
import logging.config
import os
import signal
from importlib.metadata import version

import miniflux
from dotenv import load_dotenv

from miniflux_bot.action_dispatcher import ActionDispatcher
from miniflux_bot.config import require_env
from miniflux_bot.entry_dispatcher import EntryDispatcher
from miniflux_bot.gateway import MinifluxGateway
from miniflux_bot.state import StateStore
from miniflux_bot.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


async def main() -> None:
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(name)s] [%(taskName)s] %(levelname)s: %(message)s"
                }
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "default"}
            },
            "root": {"level": log_level, "handlers": ["console"]},
            "loggers": {
                "aiogram": {"level": log_level},
                "aiosqlite": {"level": log_level},
                "psycopg": {"level": log_level},
            },
        }
    )
    logger.info("Starting miniflux-bot %s", version("miniflux-bot"))

    url = require_env("MINIFLUX_URL")
    api_key = require_env("MINIFLUX_API_KEY")
    poll_interval = int(os.getenv("POLL_INTERVAL", 60))
    tg_bot_token = require_env("TELEGRAM_BOT_TOKEN")
    tg_chat_id = int(require_env("TELEGRAM_CHAT_ID"))
    state_backend = os.getenv("STATE_BACKEND", "sqlite")

    logger.info(
        "Config: store=%s poll_interval=%ds chat_id=%s miniflux_url=%s",
        state_backend,
        poll_interval,
        tg_chat_id,
        url,
    )

    state_store: StateStore

    match state_backend:
        case "memory":
            from miniflux_bot.state.sqlite import SqliteStateStore

            state_store = SqliteStateStore(path=":memory:")
        case "sqlite":
            from miniflux_bot.state.sqlite import SqliteStateStore

            state_sqlite_path = os.getenv("STATE_SQLITE_PATH", "/data")
            state_store = SqliteStateStore(
                path=os.path.join(state_sqlite_path, "bot.sqlite")
            )
        case "postgres":
            from miniflux_bot.state.postgres import PostgresStateStore

            state_postgres_dsn = require_env("STATE_POSTGRES_DSN")
            state_store = PostgresStateStore(state_postgres_dsn)
        case _:
            raise RuntimeError(f"Unknown store backend: {state_backend!r}")

    miniflux_client = miniflux.Client(base_url=url, api_key=api_key)
    miniflux_gateway = MinifluxGateway(miniflux_client)
    action_dispatcher = ActionDispatcher(miniflux_gateway)

    telegram_notifier = TelegramNotifier(
        token=tg_bot_token,
        chat_id=tg_chat_id,
        action_dispatcher=action_dispatcher,
    )

    entry_dispatcher = EntryDispatcher(
        state_store=state_store,
        gateway=miniflux_gateway,
        poll_interval=poll_interval,
        notifier=telegram_notifier,
    )

    try:
        await state_store.init()
        async with asyncio.TaskGroup() as task_group:
            task_group.create_task(action_dispatcher.run(), name="action_dispatcher")
            task_group.create_task(telegram_notifier.run(), name="telegram_notifier")
            task_group.create_task(entry_dispatcher.run(), name="entry_dispatcher")
    finally:
        await state_store.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
