"""
RabbitMQ consumer: connection lifecycle, queue declaration, and consume loop.

Lifecycle:
  DISCONNECTED -> CONNECTING (backoff) -> CONNECTED -> CHANNEL_OPEN ->
  QUEUE_DECLARED -> READY.
  On broker disconnect: READY -> RECONNECTING (backoff) -> CONNECTED -> ... -> READY
  (re-subscribes with stored handler).
  On shutdown: READY/RECONNECTING -> CLOSING -> cancel consumer, close channel/connection -> CLOSED.

Concurrency:
  - Connection close callback may run from another thread; we schedule _reconnect_loop
    on the event loop via call_soon_threadsafe(create_task(...)).
  - close() and _reconnect_loop both acquire _lock around teardown and re-subscribe
    respectively, so we never close the channel while consume() is in progress, and
    reconnect re-checks _closing under the lock before subscribing.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable
import aio_pika
from loguru import logger

from worker.app.config.settings import Settings
from worker.app.core import SERVICE_NAME
from worker.app.core.backoff import exponential_backoff
from worker.app.infrastructure.messaging.rabbitmq.constants import ConsumerState


def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


class RabbitMQConsumer:
    """MessageConsumer implementation"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._state = ConsumerState.DISCONNECTED
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.Channel | None = None
        self._queue: aio_pika.Queue | None = None
        self._lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._closing = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._handler: Callable[[Any], Awaitable[None]] | None = None
        self._consumer_tag: str | None = None

    def _set_state(self, state: ConsumerState) -> None:
        self._state = state

    def _build_amqp_url(self) -> str:
        return (
            f"amqp://{self._settings.broker_user}:{self._settings.broker_password}"
            f"@{self._settings.broker_host}:{self._settings.broker_port}/"
        )

    def _register_close_callback(self, connection: aio_pika.RobustConnection) -> None:
        conn = getattr(connection, "connection", connection)
        if callable(getattr(conn, "add_close_callback", None)):
            conn.add_close_callback(self._on_connection_closed)

    def _on_connection_closed(self, *args: Any, **kwargs: Any) -> None:
        if self._closing:
            return
        self._set_state(ConsumerState.RECONNECTING)
        _log("broker_disconnect_detected")
        if (self._reconnect_task is None or self._reconnect_task.done()) and self._loop:
            def schedule() -> None:
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())
            self._loop.call_soon_threadsafe(schedule)

    async def _open_channel_and_declare(self) -> None:
        if not self._connection:
            return
        self._set_state(ConsumerState.CHANNEL_OPEN)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self._settings.prefetch_count)
        self._queue = await self._channel.declare_queue(
            self._settings.queue_name,
            durable=True,
            arguments={
                "x-max-length": self._settings.queue_max_length,
                "x-overflow": "reject-publish",
            },
        )
        self._set_state(ConsumerState.QUEUE_DECLARED)
        self._set_state(ConsumerState.READY)

    async def _close_channel_and_connection(self) -> None:
        self._queue = None
        self._consumer_tag = None
        if self._channel:
            try:
                await self._channel.close()
            except Exception as e:
                logger.warning("channel close failed (continuing to close connection): {}", e)
            self._channel = None
        if self._connection:
            try:
                await self._connection.close()
            except Exception as e:
                logger.warning("connection close failed: {}", e)
            self._connection = None

    async def connect(self) -> None:
        self._set_state(ConsumerState.CONNECTING)
        _log("rmq_connecting")
        attempt = 0
        async for delay in exponential_backoff(
            self._settings.initial_backoff_seconds,
            self._settings.max_backoff_seconds,
            self._settings.backoff_multiplier,
            self._settings.max_connection_attempts,
        ):
            attempt += 1
            _log("rmq_connect_attempt", attempt=attempt, delay=delay)
            try:
                self._connection = await aio_pika.connect_robust(self._build_amqp_url())
                self._loop = asyncio.get_running_loop()
                self._register_close_callback(self._connection)
                break
            except Exception as e:
                logger.warning("rmq connect failed: {}", e)
                if attempt >= self._settings.max_connection_attempts:
                    _log("rmq_connect_failed", attempt=attempt)
                    self._set_state(ConsumerState.DISCONNECTED)
                    raise
        self._set_state(ConsumerState.CONNECTED)
        _log("rmq_connected")
        await self._open_channel_and_declare()

    async def start_consuming(
        self,
        handler: Callable[[Any], Awaitable[None]],
    ) -> str:
        if self._queue is None:
            raise RuntimeError("consumer not connected")
        async with self._lock:
            if self._queue is None:
                raise RuntimeError("consumer not connected")
            self._handler = handler
            self._consumer_tag = await self._queue.consume(handler, no_ack=False)
            return self._consumer_tag

    async def cancel(self, consumer_tag: str) -> None:
        async with self._lock:
            if self._queue is not None and self._consumer_tag is not None:
                await self._queue.cancel(self._consumer_tag)
                self._consumer_tag = None

    async def _reconnect_loop(self) -> None:
        self._set_state(ConsumerState.RECONNECTING)
        attempt = 0
        async for delay in exponential_backoff(
            self._settings.initial_backoff_seconds,
            self._settings.max_backoff_seconds,
            self._settings.backoff_multiplier,
            self._settings.max_connection_attempts,
        ):
            if self._closing:
                return
            attempt += 1
            _log("rmq_reconnect_attempt", attempt=attempt)
            try:
                self._connection = await aio_pika.connect_robust(self._build_amqp_url())
                if self._loop is None:
                    self._loop = asyncio.get_running_loop()
                self._register_close_callback(self._connection)
                self._set_state(ConsumerState.CONNECTED)
                await self._open_channel_and_declare()
                async with self._lock:
                    if self._closing:
                        return
                    if self._handler is not None and self._queue is not None:
                        self._consumer_tag = await self._queue.consume(self._handler, no_ack=False)
                _log("rmq_reconnected")
                return
            except Exception as e:
                logger.warning("reconnect failed: {}", e)
        _log("rmq_reconnect_exhausted", max_attempts=self._settings.max_connection_attempts)
        self._set_state(ConsumerState.DISCONNECTED)

    async def close(self) -> None:
        self._closing = True
        self._set_state(ConsumerState.CLOSING)
        _log("consumer_shutdown")
        if self._reconnect_task is not None and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            await self._close_channel_and_connection()
        self._set_state(ConsumerState.CLOSED)
