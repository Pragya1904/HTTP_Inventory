"""Message consumer factory: selects implementation from config. Only place that imports concrete consumers."""
from __future__ import annotations

from worker.app.config.settings import Settings
from worker.app.ports.message_consumer import MessageConsumer
from worker.app.infrastructure.messaging.rabbitmq.rabbitmq_consumer import RabbitMQConsumer


def create_message_consumer(settings: Settings) -> MessageConsumer:
    backend = settings.consumer_backend.strip().lower()

    if backend == "rabbitmq":
        return RabbitMQConsumer(settings)

    raise ValueError(f"Unsupported consumer backend: {backend}")
