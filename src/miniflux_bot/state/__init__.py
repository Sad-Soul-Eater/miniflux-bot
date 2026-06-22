from abc import ABC, abstractmethod


class StateStore(ABC):
    @abstractmethod
    async def get_processed_id(self) -> int: ...

    @abstractmethod
    async def set_processed_id(self, entry_id: int) -> None: ...

    @abstractmethod
    async def init(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...
