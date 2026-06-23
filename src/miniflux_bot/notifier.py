from abc import ABC, abstractmethod

from miniflux_bot.models import Entry


class NotifierException(Exception): ...


class TransientNotifierException(NotifierException):
    def __init__(self, *args, retry_after: float | None = None) -> None:
        super().__init__(*args)
        self.retry_after = retry_after


class Notifier(ABC):
    @abstractmethod
    async def notify(self, entry: Entry) -> None: ...
