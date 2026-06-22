import asyncio
import logging
from typing import Never

import miniflux
import requests

from miniflux_bot.gateway import MinifluxGateway
from miniflux_bot.models import Entry
from miniflux_bot.notifier import Notifier, TransientNotifierException
from miniflux_bot.state import StateStore


class MinifluxBot:
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

    async def _set_processed_id(self, entry_id: int) -> None:
        if entry_id > self._processed_id:
            await self._store.set_processed_id(entry_id)
            self._processed_id = entry_id

    async def _poll_loop(self) -> Never:
        try:
            logging.info("Poll loop started")
            while True:
                try:
                    unprocessed_entries = await self._gateway.get_unread_since(
                        self._enqueued_id
                    )

                    if unprocessed_entries:
                        logging.info(
                            "Unprocessed entries: %d", len(unprocessed_entries)
                        )

                    for entry in unprocessed_entries:
                        await self._queue.put(entry)
                        self._enqueued_id = entry.id

                except (
                    miniflux.ClientError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                ) as exc:
                    logging.exception(
                        "Fetch failed with: %s; will retry next interval", exc
                    )

                await asyncio.sleep(delay=self._poll_interval)
        except asyncio.CancelledError:
            logging.info("Poll loop cancelled")
            raise

    async def _process_loop(self) -> Never:
        loop = asyncio.get_running_loop()
        try:
            logging.info("Process loop started")
            while True:
                entry: Entry = await self._queue.get()
                try:
                    await self._notifier.notify(entry)
                    logging.info("Notified: %d", entry.id)
                    await self._set_processed_id(entry.id)
                    logging.info("Saved: %d", entry.id)
                except TransientNotifierException as exc:
                    entry.attempt += 1
                    if exc.retry_after is not None:
                        delay = exc.retry_after
                    else:
                        delay = min(self._retry_cap, 2 ** min(entry.attempt, 16))

                    logging.warning(
                        "Transient failure on %d (attempt %d), re-queuing in %.0fs: %s",
                        entry.id,
                        entry.attempt,
                        delay,
                        exc,
                    )

                    loop.call_later(delay, self._queue.put_nowait, entry)
                except Exception as exc:
                    logging.exception(
                        "Dropping %d on non-transient error: %s", entry.id, exc
                    )
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            logging.info("Process loop cancelled")
            raise

    async def run(self) -> None:
        self._processed_id = await self._store.get_processed_id()
        self._enqueued_id = self._processed_id
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._poll_loop(), name="poll_loop")
                tg.create_task(self._process_loop(), name="process_loop")
        finally:
            logging.info("Shutting down")
