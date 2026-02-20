"""Port: abstraction for an incoming queue message. Implementations live in infrastructure."""
from __future__ import annotations

from typing import Protocol


class IncomingMessage(Protocol):
    """Transport-agnostic incoming message. Application uses this; broker adapters implement it."""

    @property
    def body(self) -> bytes: ...

    async def ack(self) -> None: ...

    async def nack(self, *, requeue: bool = True) -> None: ...
