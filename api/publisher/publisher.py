from abc import ABC, abstractmethod
from typing import Any


class MessagePublisher(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def publish(self, message: dict[str, Any]) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @property
    @abstractmethod
    def ready(self) -> bool: ...

