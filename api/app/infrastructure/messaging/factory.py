"""Publisher factory: selects implementation from config."""
from __future__ import annotations

from api.app.config.settings import Settings
from api.app.ports.message_publisher import MessagePublisher
from api.app.infrastructure.messaging.rabbitmq.rabbitmq_publisher import RabbitMQPublisher
from api.app.infrastructure.messaging.inmemory.in_memory_publisher import InMemoryPublisher


def create_publisher(settings: Settings) -> MessagePublisher:
    backend = settings.publisher_backend.strip().lower()

    if backend == "rabbitmq":
        return RabbitMQPublisher(settings)

    if backend == "inmemory":
        return InMemoryPublisher()

    raise ValueError(f"Unsupported publisher backend: {backend}")
