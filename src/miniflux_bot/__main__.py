import asyncio
import logging
import os
from importlib.metadata import version

import miniflux
from dotenv import load_dotenv

from miniflux_bot.bot import MinifluxBot
from miniflux_bot.config import require_env
from miniflux_bot.gateway import MinifluxGateway
from miniflux_bot.state import SqliteStateStore, StateStore
from miniflux_bot.telegram import TelegramBot


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(taskName)s] %(levelname)s %(message)s",
    )
    logging.info("Starting miniflux-bot %s", version("miniflux-bot"))

    load_dotenv()

    url = require_env("MINIFLUX_URL")
    api_key = require_env("MINIFLUX_API_KEY")
    poll_interval = int(os.getenv("MINIFLUX_POLL_INTERVAL", 60))
    tg_bot_token = require_env("TELEGRAM_BOT_TOKEN")
    tg_chat_id = int(require_env("TELEGRAM_CHAT_ID"))
    store_backend = os.getenv("MINIFLUX_STORE_BACKEND", "sqlite")

    state_store: StateStore

    match store_backend:
        case "memory":
            state_store = SqliteStateStore(path=":memory:")
        case "sqlite":
            sqlite_store_path = os.getenv("MINIFLUX_SQLITE_STORE_PATH", "/data")
            state_store = SqliteStateStore(
                path=os.path.join(sqlite_store_path, "bot.sqlite")
            )
        case _:
            raise RuntimeError(f"Unknown store backend: {store_backend!r}")

    miniflux_client = miniflux.Client(base_url=url, api_key=api_key)
    miniflux_gateway = MinifluxGateway(miniflux_client)

    telegram_bot = TelegramBot(
        token=tg_bot_token,
        chat_id=tg_chat_id,
        gateway=miniflux_gateway,
    )

    miniflux_bot = MinifluxBot(
        state_store=state_store,
        gateway=miniflux_gateway,
        poll_interval=poll_interval,
        notifier=telegram_bot,
    )

    try:
        await state_store.init()
        async with asyncio.TaskGroup() as tg:
            tg.create_task(telegram_bot.run(), name="telegram_bot")
            tg.create_task(miniflux_bot.run(), name="miniflux_bot")
    finally:
        await state_store.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
