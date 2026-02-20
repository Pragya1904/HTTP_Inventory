"""RabbitMQ consumer lifecycle states."""
from enum import Enum


class ConsumerState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    CHANNEL_OPEN = "CHANNEL_OPEN"
    QUEUE_DECLARED = "QUEUE_DECLARED"
    READY = "READY"
    RECONNECTING = "RECONNECTING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
