"""
RabbitMQ publisher: connection lifecycle and publish with confirm.

Lifecycle:
  DISCONNECTED -> CONNECTING (backoff) -> CONNECTED -> CHANNEL_OPEN ->
  CONFIRM_ENABLED -> QUEUE_DECLARED -> READY.
  On broker disconnect or channel error: READY -> RECONNECTING (backoff) -> CONNECTED -> ... -> READY.
  On shutdown: READY/RECONNECTING -> CLOSING (wait in-flight) -> close channel/connection -> CLOSED.
"""
import asyncio
import json
import time
from typing import Any

import aio_pika
from aio_pika import Message, DeliveryMode
from loguru import logger

from api.app.core.backoff import exponential_backoff
from api.publisher.constants import PublisherState
from api.publisher.publisher import MessagePublisher

SERVICE_NAME = "api"


def _log(event: str, **kwargs: Any) -> None:
    """
    Structured log. bind() attaches key-value context (event, service_name, attempt, ...) to the
    log record for filtering in aggregators; .info() / .warning() set severity level.
    We use .info("") because the payload is in the bound kwargs, not the message body.
    """
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


class RabbitMQPublisher(MessagePublisher):
    """
    Lifecycle: CONNECTING -> CONNECTED -> channel/open -> QUEUE_DECLARED -> READY.
    On broker disconnect (or channel error): RECONNECTING -> backoff -> CONNECTED -> READY.
    On close(): CLOSING -> wait in-flight -> CLOSED.
    """

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._state = PublisherState.DISCONNECTED
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.Channel | None = None
        self._lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task | None = None
        self._closing = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def _on_connection_closed(self, *args: Any, **kwargs: Any) -> None:
        if self._closing:
            return
        self._set_state(PublisherState.RECONNECTING)
        _log("broker_disconnect_detected")
        if (self._reconnect_task is None or self._reconnect_task.done()) and self._loop:
            def schedule() -> None:
                asyncio.create_task(self._reconnect_loop())
            self._loop.call_soon_threadsafe(schedule)

    @property
    def state(self) -> PublisherState:
        return self._state

    @property
    def ready(self) -> bool:
        return self._state == PublisherState.READY

    def _set_state(self, state: PublisherState) -> None:
        self._state = state

    async def connect(self) -> None:
        self._set_state(PublisherState.CONNECTING)
        attempt = 0
        async for delay in exponential_backoff(
            self._settings.initial_backoff_seconds,
            self._settings.max_backoff_seconds,
            2.0,
            self._settings.max_connection_attempts,
        ):
            attempt += 1
            _log("rmq_connect_attempt", attempt=attempt, delay=delay)
            try:
                url = (
                    f"amqp://{self._settings.broker_user}:{self._settings.broker_password}"
                    f"@{self._settings.broker_host}:{self._settings.broker_port}/"
                )
                self._connection = await aio_pika.connect_robust(url)
                self._loop = asyncio.get_running_loop()
                conn = getattr(self._connection, "connection", self._connection)
                if callable(getattr(conn, "add_close_callback", None)):
                    conn.add_close_callback(self._on_connection_closed)
                break
            except Exception as e:
                logger.exception("rmq_connect_attempt failed: {}", e)
                if attempt >= self._settings.max_connection_attempts:
                    _log("rmq_connect_failed", attempt=attempt)
                    self._set_state(PublisherState.DISCONNECTED)
                    raise
        self._set_state(PublisherState.CONNECTED)
        _log("rmq_connected")
        await self._open_channel_and_declare()

    async def _open_channel_and_declare(self) -> None:
        if not self._connection:
            return
        try:
            self._set_state(PublisherState.CHANNEL_OPEN)
            self._channel = await self._connection.channel(publisher_confirms=True)
            self._set_state(PublisherState.CONFIRM_ENABLED)
            await self._channel.declare_queue(
                self._settings.queue_name,
                durable=True,
                arguments={
                    "x-max-length": self._settings.queue_max_length,
                    "x-overflow": "reject-publish",
                },
            )
            self._set_state(PublisherState.QUEUE_DECLARED)
            self._set_state(PublisherState.READY)
        except aio_pika.exceptions.ChannelNotFoundEntity as e:
            logger.exception("Queue declaration mismatch: {}", e)
            raise
        except Exception:
            self._set_state(PublisherState.RECONNECTING)
            await self._close_channel_and_connection()
            raise

    async def _close_channel_and_connection(self) -> None:
        if self._channel:
            try:
                await self._channel.close()
            except Exception:
                pass
            self._channel = None
        if self._connection:
            try:
                await self._connection.close()
            except Exception:
                pass
            self._connection = None

    async def publish(self, message: dict[str, Any]) -> None:
        if self._state != PublisherState.READY:
            _log("publish_rejected", reason="publisher_not_ready")
            raise RuntimeError("publisher_not_ready")
        start = time.perf_counter()
        async with self._lock:
            if not self._channel:
                _log("publish_failed", reason="connection_lost")
                raise RuntimeError("connection_lost")
            body = json.dumps(message).encode()
            msg = Message(body, delivery_mode=DeliveryMode.PERSISTENT)
            try:
                await self._channel.default_exchange.publish(
                    msg,
                    routing_key=self._settings.queue_name,
                    timeout=10.0,
                )
            except Exception as e:
                _log("publish_failed", reason="connection_lost")
                self._set_state(PublisherState.RECONNECTING)
                if self._reconnect_task is None or self._reconnect_task.done():
                    self._reconnect_task = asyncio.create_task(self._reconnect_loop())
                raise
        latency_ms = (time.perf_counter() - start) * 1000
        request_id = message.get("request_id", "")
        url = message.get("url", "")
        _log("publish_success", request_id=request_id, url=url, latency_ms=round(latency_ms, 2))

    async def _reconnect_loop(self) -> None:
        self._set_state(PublisherState.RECONNECTING)
        attempt = 0
        async for delay in exponential_backoff(
            self._settings.initial_backoff_seconds,
            self._settings.max_backoff_seconds,
            2.0,
            self._settings.max_connection_attempts,
        ):
            if self._closing:
                return
            attempt += 1
            _log("rmq_reconnect_attempt", attempt=attempt)
            try:
                url = (
                    f"amqp://{self._settings.broker_user}:{self._settings.broker_password}"
                    f"@{self._settings.broker_host}:{self._settings.broker_port}/"
                )
                self._connection = await aio_pika.connect_robust(url)
                if self._loop is None:
                    self._loop = asyncio.get_running_loop()
                conn = getattr(self._connection, "connection", self._connection)
                if callable(getattr(conn, "add_close_callback", None)):
                    conn.add_close_callback(self._on_connection_closed)
                self._set_state(PublisherState.CONNECTED)
                await self._open_channel_and_declare()
                _log("rmq_reconnected")
                return
            except Exception as e:
                logger.warning("reconnect failed: {}", e)
        self._set_state(PublisherState.DISCONNECTED)

    async def close(self) -> None:
        self._closing = True
        self._set_state(PublisherState.CLOSING)
        _log("publisher_shutdown")
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            await self._close_channel_and_connection()
        self._set_state(PublisherState.CLOSED)
