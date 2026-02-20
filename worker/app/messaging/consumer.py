"""RabbitMQ consumer: message handler and consumption loop."""
from __future__ import annotations

import asyncio
from typing import Any

from aio_pika import IncomingMessage as AioPikaIncomingMessage
from aio_pika.abc import AbstractQueue
from loguru import logger

from worker.app.application.processing_service import ProcessingService
from worker.app.core import SERVICE_NAME
from worker.app.infrastructure.messaging.rabbitmq.aio_pika_message_adapter import AioPikaMessageAdapter


def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


def create_message_handler(
    processing_service: ProcessingService,
    message_handler_errors: asyncio.Queue[Exception],
    processing_lock: asyncio.Lock,
):
    """Create an async message handler that processes messages and records errors."""

    async def on_message(raw_message: AioPikaIncomingMessage) -> None:
        async with processing_lock:
            try:
                message = AioPikaMessageAdapter(raw_message)
                await processing_service.process_message(message)
            except Exception as e:
                logger.exception("message handling failed: {}", e)
                try:
                    if not raw_message.processed:
                        await raw_message.reject(requeue=False)
                finally:
                    await message_handler_errors.put(e)

    return on_message
