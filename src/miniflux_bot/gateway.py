import asyncio
import logging
from typing import Literal

import miniflux
import requests

from miniflux_bot.models import Entry

logger = logging.getLogger(__name__)


class GatewayException(Exception): ...


class TransientGatewayException(GatewayException):
    def __init__(self, *args, retry_after: float | None = None) -> None:
        super().__init__(*args)
        self.retry_after = retry_after


async def _run_guarded(func, /, *args, **kwargs):
    try:
        result = await asyncio.to_thread(func, *args, **kwargs)
    except (
        miniflux.ServerError,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    ) as exc:
        raise TransientGatewayException(str(exc)) from exc
    except miniflux.ClientError as exc:
        raise GatewayException(str(exc)) from exc
    return result


class MinifluxGateway:
    def __init__(self, client: miniflux.Client) -> None:
        self._client = client

    async def get_unread_since(self, entry_id: int) -> list[Entry]:
        logger.debug("Fetching unread since %d", entry_id)
        response = await _run_guarded(
            self._client.get_entries,
            status="unread",
            order="id",
            direction="asc",
            after_entry_id=entry_id,
        )
        return [Entry(raw_entry) for raw_entry in response["entries"]]

    async def _mark(self, entry_id: int, status: Literal["read", "unread"]) -> None:
        logger.debug("Marking %d as %s", entry_id, status)
        await _run_guarded(
            self._client.update_entries, entry_ids=[entry_id], status=status
        )

    async def mark_read(self, entry_id: int) -> None:
        await self._mark(entry_id=entry_id, status="read")

    async def mark_unread(self, entry_id: int) -> None:
        await self._mark(entry_id=entry_id, status="unread")
