"""Adapter: wrap aio_pika.IncomingMessage to implement ports.IncomingMessage."""
from __future__ import annotations

from aio_pika import IncomingMessage as AioPikaIncomingMessage


class AioPikaMessageAdapter:
    """Implements worker.app.ports.incoming_message.IncomingMessage for aio_pika."""

    def __init__(self, message: AioPikaIncomingMessage) -> None:
        self._message = message

    @property
    def body(self) -> bytes:
        return self._message.body

    async def ack(self) -> None:
        await self._message.ack()

    async def nack(self, *, requeue: bool = True) -> None:
        await self._message.nack(requeue=requeue)
