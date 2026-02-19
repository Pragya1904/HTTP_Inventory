import asyncio
import json
import signal
import sys
from pathlib import Path

from loguru import logger

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.core.backoff import exponential_backoff
from config.settings import Settings

SERVICE_NAME = "worker"


def _log(event: str, **kwargs) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


async def run_worker() -> None:
    import aio_pika
    from motor.motor_asyncio import AsyncIOMotorClient

    settings = Settings()

    _log("mongo_connecting")
    attempt = 0
    async for delay in exponential_backoff(
        settings.initial_backoff_seconds,
        settings.max_backoff_seconds,
        2.0,
        settings.max_connection_attempts,
    ):
        attempt += 1
        _log("mongo_connect_attempt", attempt=attempt, delay=delay)
        try:
            u, p = settings.database_user, settings.database_password
            if u and p:
                uri = f"mongodb://{u}:{p}@{settings.database_host}:{settings.database_port}"
            else:
                uri = f"mongodb://{settings.database_host}:{settings.database_port}"
            mongo_client = AsyncIOMotorClient(
                uri,
                serverSelectionTimeoutMS=5000,
            )
            await mongo_client.admin.command("ping")
            _log("mongo_connected")
            break
        except Exception as e:
            logger.warning("mongo connect failed: {}", e)
            if attempt >= settings.max_connection_attempts:
                raise
    else:
        raise RuntimeError("mongo connect failed")

    _log("rmq_connecting")
    attempt = 0
    async for delay in exponential_backoff(
        settings.initial_backoff_seconds,
        settings.max_backoff_seconds,
        2.0,
        settings.max_connection_attempts,
    ):
        attempt += 1
        _log("rmq_connect_attempt", attempt=attempt, delay=delay)
        try:
            url = (
                f"amqp://{settings.broker_user}:{settings.broker_password}"
                f"@{settings.broker_host}:{settings.broker_port}/"
            )
            connection = await aio_pika.connect_robust(url)
            break
        except Exception as e:
            logger.warning("rmq connect failed: {}", e)
            if attempt >= settings.max_connection_attempts:
                raise
    else:
        raise RuntimeError("rmq connect failed")

    _log("rmq_connected")
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=settings.prefetch_count)
    queue = await channel.declare_queue(
        settings.queue_name,
        durable=True,
        arguments={
            "x-max-length": settings.queue_max_length,
            "x-overflow": "reject-publish",
        },
    )

    shutdown = asyncio.Event()

    async def on_message(message: "aio_pika.IncomingMessage") -> None:
        async with message.process():
            try:
                body = json.loads(message.body.decode())
                url = body.get("url", "")
                request_id = body.get("request_id", "")
                _log("message_received", url=url, request_id=request_id)
            except Exception as e:
                logger.exception("message handling failed: {}", e)

    consumer_task = asyncio.create_task(
        queue.consume(on_message, no_ack=False),
    )

    def request_shutdown() -> None:
        if not shutdown.is_set():
            _log("shutdown_signal")
            shutdown.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_shutdown)
        except NotImplementedError:
            pass

    _log("worker_started")
    await shutdown.wait()
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await channel.close()
    await connection.close()
    await mongo_client.close()
    _log("worker_stopped")


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        _log("worker_interrupted")
    except Exception as e:
        logger.exception("worker failed: {}", e)
        raise


if __name__ == "__main__":
    main()
