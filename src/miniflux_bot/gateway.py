import asyncio

import miniflux

from miniflux_bot.models import Entry


class MinifluxGateway:
    def __init__(self, client: miniflux.Client) -> None:
        self._client = client

    async def get_latest_unread(self) -> Entry | None:
        latest_response = await asyncio.to_thread(
            self._client.get_entries,
            status="unread",
            order="id",
            direction="desc",
            limit=1,
        )
        if latest_response["total"] > 0:
            return Entry(latest_response["entries"][0])
        else:
            return None

    async def get_unread_since(self, entry_id: int) -> list[Entry]:
        response = await asyncio.to_thread(
            self._client.get_entries,
            status="unread",
            order="id",
            direction="asc",
            after_entry_id=entry_id,
        )
        return [Entry(raw_entry) for raw_entry in response["entries"]]

    async def mark_read(self, entry_id: int) -> None:
        await asyncio.to_thread(
            self._client.update_entries, entry_ids=[entry_id], status="read"
        )

    async def mark_unread(self, entry_id: int) -> None:
        await asyncio.to_thread(
            self._client.update_entries, entry_ids=[entry_id], status="unread"
        )
