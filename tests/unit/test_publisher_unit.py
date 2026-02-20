import asyncio

import pytest

from api.app.infrastructure.messaging.rabbitmq.constants import PublisherState
from api.app.infrastructure.messaging.rabbitmq.rabbitmq_publisher import RabbitMQPublisher


class _FakeChannel:
    def __init__(self, publish_raises: Exception | None = None) -> None:
        self._publish_raises = publish_raises
        self.default_exchange = self

    async def publish(self, *args, **kwargs):
        if self._publish_raises:
            raise self._publish_raises

    async def declare_queue(self, *args, **kwargs):
        return None

    async def close(self):
        return None


class _FakeConnection:
    def __init__(self, channel: _FakeChannel) -> None:
        self._channel = channel
        self.connection = self
        self._callbacks = []

    async def channel(self, publisher_confirms: bool = True):
        return self._channel

    def add_close_callback(self, cb):
        self._callbacks.append(cb)

    async def close(self):
        return None


class _Settings:
    broker_user = "guest"
    broker_password = "guest"
    broker_host = "localhost"
    broker_port = 5672
    queue_name = "metadata_queue"
    queue_max_length = 1000
    initial_backoff_seconds = 0.0
    max_backoff_seconds = 0.0
    max_connection_attempts = 1
    backoff_multiplier = 2.0
    publish_timeout_seconds = 10.0


@pytest.mark.asyncio
async def test_connect_sets_ready(monkeypatch):
    channel = _FakeChannel()
    conn = _FakeConnection(channel)

    async def _connect_robust(url):
        return conn

    import api.app.infrastructure.messaging.rabbitmq.rabbitmq_publisher as mod

    monkeypatch.setattr(mod.aio_pika, "connect_robust", _connect_robust)
    pub = RabbitMQPublisher(_Settings())
    await pub.connect()
    assert pub.state == PublisherState.READY
    assert pub.ready is True


@pytest.mark.asyncio
async def test_publish_rejected_when_not_ready(monkeypatch):
    pub = RabbitMQPublisher(_Settings())
    with pytest.raises(RuntimeError):
        await pub.publish({"x": 1})


@pytest.mark.asyncio
async def test_publish_failure_sets_reconnecting_and_schedules_reconnect(monkeypatch):
    channel = _FakeChannel(publish_raises=RuntimeError("boom"))
    conn = _FakeConnection(channel)

    async def _connect_robust(url):
        return conn

    import api.app.infrastructure.messaging.rabbitmq.rabbitmq_publisher as mod

    monkeypatch.setattr(mod.aio_pika, "connect_robust", _connect_robust)
    pub = RabbitMQPublisher(_Settings())
    await pub.connect()
    assert pub.state == PublisherState.READY

    with pytest.raises(RuntimeError):
        await pub.publish({"url": "https://example.com", "request_id": "r"})
    assert pub.state == PublisherState.RECONNECTING
    assert pub._reconnect_task is not None  # internal check for scheduling


@pytest.mark.asyncio
async def test_close_transitions_to_closed(monkeypatch):
    channel = _FakeChannel()
    conn = _FakeConnection(channel)

    async def _connect_robust(url):
        return conn

    import api.app.infrastructure.messaging.rabbitmq.rabbitmq_publisher as mod

    monkeypatch.setattr(mod.aio_pika, "connect_robust", _connect_robust)
    pub = RabbitMQPublisher(_Settings())
    await pub.connect()
    await pub.close()
    assert pub.state == PublisherState.CLOSED

