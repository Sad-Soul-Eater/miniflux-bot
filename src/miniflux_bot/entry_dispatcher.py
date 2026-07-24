import asyncio
import logging
from typing import Never

from miniflux_bot.gateway import (
    GatewayException,
    MinifluxGateway,
)
from miniflux_bot.models import Entry
from miniflux_bot.notifier import Notifier, TransientNotifierException
from miniflux_bot.state import StateStore

logger = logging.getLogger(__name__)


class EntryDispatcher:
    def __init__(
        self,
        state_store: StateStore,
        gateway: MinifluxGateway,
        poll_interval: int,
        notifier: Notifier,
    ) -> None:
        self._store = state_store
        self._gateway = gateway
        self._poll_interval = poll_interval
        self._notifier = notifier

        self._processed_id = 0
        self._enqueued_id = 0
        self._retry_cap = 300

        self._queue = asyncio.Queue()

    async def _advance_processed_id(self, entry_id: int) -> None:
        if entry_id > self._processed_id:
            await self._store.set_processed_id(entry_id)
            self._processed_id = entry_id

    async def _poll_loop(self) -> Never:
        try:
            logger.info("Poll loop started")
            while True:
                try:
                    unprocessed_entries = await self._gateway.get_unread_since(
                        self._enqueued_id
                    )

                    if unprocessed_entries:
                        logger.info("Unprocessed entries: %d", len(unprocessed_entries))

                    for entry in unprocessed_entries:
                        await self._queue.put(entry)
                        self._enqueued_id = entry.id

                except GatewayException:
                    logger.exception("Fetch failed with: %s; will retry next interval")

                await asyncio.sleep(delay=self._poll_interval)
        except asyncio.CancelledError:
            logger.info("Poll loop cancelled")
            raise

    async def _deliver_loop(self) -> Never:
        loop = asyncio.get_running_loop()
        try:
            logger.info("Deliver loop started")
            while True:
                entry: Entry = await self._queue.get()
                try:
                    await self._notifier.notify(entry)
                    logger.info("Notified: %d", entry.id)
                    await self._advance_processed_id(entry.id)
                    logger.info("Saved: %d", entry.id)
                except TransientNotifierException as exc:
                    entry.attempt += 1
                    if exc.retry_after is not None:
                        delay = exc.retry_after
                    else:
                        delay = min(self._retry_cap, 2 ** min(entry.attempt, 16))

                    logger.warning(
                        "Transient failure on %d (attempt %d), re-queuing in %.0fs: %s",
                        entry.id,
                        entry.attempt,
                        delay,
                        exc,
                    )

                    loop.call_later(delay, self._queue.put_nowait, entry)
                except Exception:
                    logger.exception("Dropping %d on non-transient error:", entry.id)
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            logger.info("Deliver loop cancelled")
            raise

    async def run(self) -> None:
        self._processed_id = await self._store.get_processed_id()
        logger.info("Resuming from processed_id=%d", self._processed_id)
        self._enqueued_id = self._processed_id
        try:
            async with asyncio.TaskGroup() as task_group:
                task_group.create_task(self._poll_loop(), name="poll_loop")
                task_group.create_task(self._deliver_loop(), name="deliver_loop")
        finally:
            logger.info("Shutting down")
