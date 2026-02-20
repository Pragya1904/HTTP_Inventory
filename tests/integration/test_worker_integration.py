import asyncio
import random
import signal
import time
import uuid

import pytest

from tests.test_data import TEST_URLS
from worker.app.constants import PROCESSING_STATUS


AMQP_URL = "amqp://guest:guest@rabbitmq:5672/"
MONGO_URI = "mongodb://mongo:27017"
QUEUE_NAME = "metadata_queue"
QUEUE_ARGS = {"x-max-length": 1000, "x-overflow": "reject-publish"}


async def _clear_queue() -> None:
    import aio_pika

    conn = await aio_pika.connect_robust(AMQP_URL)
    ch = await conn.channel()
    q = await ch.declare_queue(QUEUE_NAME, durable=True, arguments=QUEUE_ARGS)
    while True:
        msg = await q.get(fail=False, timeout=1)
        if msg is None:
            break
        await msg.ack()
    await ch.close()
    await conn.close()


async def _publish_message(url: str, request_id: str) -> None:
    import aio_pika

    conn = await aio_pika.connect_robust(AMQP_URL)
    ch = await conn.channel()
    await ch.declare_queue(QUEUE_NAME, durable=True, arguments=QUEUE_ARGS)
    await ch.default_exchange.publish(
        aio_pika.Message(
            body=f'{{"url":"{url}","request_id":"{request_id}"}}'.encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=QUEUE_NAME,
    )
    await ch.close()
    await conn.close()


async def _delete_existing_record(url: str) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        coll = mongo["metadata_inventory"]["metadata_records"]
        await coll.delete_many({"url": url})
    finally:
        mongo.close()


async def _wait_for_completed(url: str, timeout_s: float = 45.0) -> dict:
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        coll = mongo["metadata_inventory"]["metadata_records"]
        start = time.time()
        while time.time() - start < timeout_s:
            record = await coll.find_one({"url": url})
            if record and record.get("status") == PROCESSING_STATUS.COMPLETED:
                return record
            await asyncio.sleep(1.0)
    finally:
        mongo.close()
    raise AssertionError(
        f"Timed out waiting for {PROCESSING_STATUS.COMPLETED} status for {url}"
    )


@pytest.mark.integration
def test_worker_processes_message_and_persists_metadata():
    """Worker processes a message for a URL from the curated TEST_URLS (random pick)."""
    async def _run() -> None:
        test_id = str(uuid.uuid4())
        # Use a URL that returns 2xx (avoid 404/500 for this flow)
        success_urls = [u for u in TEST_URLS if "status/404" not in u and "status/500" not in u]
        target_url = random.choice(success_urls) if success_urls else f"http://api:6577/health/live?worker_test_id={test_id}"
        request_id = f"req-{test_id}"

        await _clear_queue()
        await _delete_existing_record(target_url)

        proc = await asyncio.create_subprocess_exec("python", "-m", "worker.app.main")
        try:
            await _publish_message(target_url, request_id)
            record = await _wait_for_completed(target_url)
            assert record["status"] == PROCESSING_STATUS.COMPLETED
            assert record["url"] == target_url
            assert "metadata" in record
            assert isinstance(record["metadata"].get("headers"), dict)
            assert isinstance(record["metadata"].get("cookies"), dict)
            assert isinstance(record["metadata"].get("page_source"), str)
            assert isinstance(record["metadata"].get("status_code"), int)
            assert isinstance(record["metadata"].get("final_url"), str)

            processing = record.get("processing", {})
            assert isinstance(processing, dict)
            assert isinstance(processing.get("retry_count"), int)
            assert processing.get("error_msg") is None
            assert processing.get("last_attempt_at") is not None

            assert record.get("additional_details") is None
            assert record.get("created_at") is not None
            assert record.get("updated_at") is not None
        finally:
            if proc.returncode is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()

    asyncio.run(_run())

