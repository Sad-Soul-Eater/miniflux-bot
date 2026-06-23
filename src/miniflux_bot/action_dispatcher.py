import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from miniflux_bot.gateway import MinifluxGateway, TransientGatewayException

logger = logging.getLogger(__name__)


@dataclass
class MarkRequest:
    entry_id: int
    status: Literal["read", "unread"]
    attempt: int = 0


class ActionDispatcher:
    def __init__(self, gateway: MinifluxGateway):
        self._gateway = gateway
        self._queue = asyncio.Queue()
        self._retry_cap = 300

    async def mark_read(self, entry_id: int) -> None:
        self._queue.put_nowait(MarkRequest(entry_id=entry_id, status="read"))

    async def mark_unread(self, entry_id: int) -> None:
        self._queue.put_nowait(MarkRequest(entry_id=entry_id, status="unread"))

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            logger.info("Action worker started")
            while True:
                action: MarkRequest = await self._queue.get()
                try:
                    match action.status:
                        case "read":
                            await self._gateway.mark_read(action.entry_id)
                        case "unread":
                            await self._gateway.mark_unread(action.entry_id)
                    logger.info("Applied %s to %d", action.status, action.entry_id)
                except TransientGatewayException as exc:
                    action.attempt += 1
                    if exc.retry_after is not None:
                        delay = exc.retry_after
                    else:
                        delay = min(self._retry_cap, 2 ** min(action.attempt, 16))

                    logger.warning(
                        "Miniflux %s on %d failed (attempt %d), retrying in %.0fs: %s",
                        action.status,
                        action.entry_id,
                        action.attempt,
                        delay,
                        exc,
                    )

                    loop.call_later(delay, self._queue.put_nowait, action)
                except Exception as exc:
                    logger.exception(
                        "Dropping %s on %d (non-transient): %s",
                        action.status,
                        action.entry_id,
                        exc,
                    )
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            logger.info("Action worker cancelled")
            raise
