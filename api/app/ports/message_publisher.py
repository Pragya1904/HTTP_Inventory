"""Port: messaging publish contract. Implementations live in infrastructure."""
from __future__ import annotations

from typing import Any, Protocol


class MessagePublisher(Protocol):
    """Interface for publishing messages."""

    async def connect(self) -> None: ...
    async def publish(self, message: dict[str, Any]) -> None: ...
    async def close(self) -> None: ...

    @property
    def ready(self) -> bool: ...
