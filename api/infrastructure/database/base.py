from abc import ABC, abstractmethod


class DatabaseConnection(ABC):
    @property
    @abstractmethod
    def ready(self) -> bool: ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...

