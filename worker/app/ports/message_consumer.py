"""Port: message consumer for queue. Implementations live in infrastructure."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol


class MessageConsumer(Protocol):
    async def connect(self) -> None: ...

    async def start_consuming(
        self,
        handler: Callable[[Any], Awaitable[None]],
    ) -> str:
        """Start consuming; call handler for each message. Returns consumer tag for cancellation."""
        ...

    async def cancel(self, consumer_tag: str) -> None: ...

    async def close(self) -> None: ...
