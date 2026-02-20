import asyncio
import signal

from loguru import logger

from worker.app.composition import create_worker_dependencies
from worker.app.messaging.consumer import create_message_handler
from worker.app.core import SERVICE_NAME


# Max time to wait for in-flight message handler to finish during shutdown.
SHUTDOWN_LOCK_WAIT_SECONDS = 60.0


def _log(event: str, **kwargs) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


async def run_worker() -> None:
    deps = create_worker_dependencies()
    consumer_tag: str | None = None
    processing_lock: asyncio.Lock | None = None
    message_handler_errors: asyncio.Queue[Exception] | None = None
    run_error: Exception | None = None

    try:
        await deps.connect()

        _log(
            "worker_bootstrap_complete",
            repository_backend=deps.settings.repository_backend,
            consumer_backend=deps.settings.consumer_backend,
            queue_name=deps.settings.queue_name,
            prefetch_count=deps.settings.prefetch_count,
        )

        shutdown = asyncio.Event()
        processing_lock = asyncio.Lock()
        message_handler_errors = asyncio.Queue()

        handler = create_message_handler(
            deps.processing_service, message_handler_errors, processing_lock
        )
        consumer_tag = await deps.message_consumer.start_consuming(handler)

        def request_shutdown() -> None:
            if not shutdown.is_set():
                _log("shutdown_signal")
                shutdown.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, request_shutdown)
            except NotImplementedError:
                logger.warning("signal handler not implemented for {}", sig)

        _log("worker_started")
        await shutdown.wait()
    except Exception as e:
        run_error = e
    finally:
        if consumer_tag is not None:
            try:
                await deps.message_consumer.cancel(consumer_tag)
            except Exception as e:
                logger.warning("consumer cancel failed: {}", e)

        if processing_lock is not None:
            try:
                await asyncio.wait_for(
                    processing_lock.acquire(),
                    timeout=SHUTDOWN_LOCK_WAIT_SECONDS,
                )
                processing_lock.release()
            except asyncio.TimeoutError:
                _log("shutdown_lock_timeout", timeout_s=SHUTDOWN_LOCK_WAIT_SECONDS)

        await deps.close()

        _log("worker_stopped")

    if run_error is not None:
        raise run_error
    if message_handler_errors is not None:
        # drain and surface all
        errors: list[Exception] = []
        try:
            while True:
                errors.append(message_handler_errors.get_nowait())
        except asyncio.QueueEmpty:
            pass
        if errors:
            for i, err in enumerate(errors):
                if i > 0:
                    logger.warning("handler_error_during_run", index=i + 1, total=len(errors), error=str(err))
            raise errors[0]


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        _log("worker_interrupted")
    except Exception as e:
        raise RuntimeError(f"Worker failed: {e}") from e


if __name__ == "__main__":
    main()
