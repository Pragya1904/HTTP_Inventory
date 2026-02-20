import asyncio
import os
import random
import signal
import time
import uuid

import httpx
import pytest

from tests.test_data import TEST_URLS
from worker.app.constants import PROCESSING_STATUS


AMQP_URL = "amqp://guest:guest@rabbitmq:5672/"
MONGO_URI = "mongodb://mongo:27017"
API_BASE = "http://api:6577"
QUEUE_NAME = "metadata_queue"
QUEUE_ARGS = {"x-max-length": 1000, "x-overflow": "reject-publish"}

# URL that returns a large HTML body so we can trigger page_source truncation
TRUNCATION_TEST_URL = "https://httpbin.org/html"
TRUNCATION_MAX_LENGTH = 300


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
    import inspect
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        coll = mongo["metadata_inventory"]["metadata_records"]
        await coll.delete_many({"url": url})
    finally:
        res = mongo.close()
        if inspect.isawaitable(res):
            await res


async def _wait_for_completed(url: str, timeout_s: float = 45.0) -> dict:
    import inspect
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
        res = mongo.close()
        if inspect.isawaitable(res):
            await res
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
            assert isinstance(processing.get("attempt_number"), int)
            assert processing.get("error_msg") is None
            assert processing.get("last_attempt_at") is not None
            assert processing.get("last_request_id") == request_id

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


def _wait_api_ready(timeout_s: float = 60.0) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            r = httpx.get(f"{API_BASE}/health/ready", timeout=5.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1.0)
    raise AssertionError(f"API not ready within {timeout_s}s")


@pytest.mark.integration
def test_large_response_truncated_additional_details_returned_via_get():
    """
    One URL with response exceeding payload size: worker truncates page_source, stores
    additional_details with truncated flag and original_length; GET /metadata returns them.
    """
    async def _run() -> None:
        _wait_api_ready()
        await _clear_queue()
        await _delete_existing_record(TRUNCATION_TEST_URL)

        # Enqueue via API
        r_post = httpx.post(
            f"{API_BASE}/metadata",
            json={"url": TRUNCATION_TEST_URL},
            timeout=10.0,
        )
        assert r_post.status_code == 202, f"POST failed: {r_post.status_code} {r_post.text}"

        # Start worker with small max_page_source_length so response is truncated
        env = os.environ.copy()
        env["MAX_PAGE_SOURCE_LENGTH"] = str(TRUNCATION_MAX_LENGTH)
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "worker.app.main",
            env=env,
        )
        try:
            record = await _wait_for_completed(TRUNCATION_TEST_URL, timeout_s=60.0)
            assert record["status"] == PROCESSING_STATUS.COMPLETED
            meta = record.get("metadata") or {}
            assert isinstance(meta.get("page_source"), str)
            assert len(meta["page_source"]) <= TRUNCATION_MAX_LENGTH
            add = meta.get("additional_details")
            assert add is not None, "expected additional_details with truncation info"
            assert add.get("truncated") is True
            assert isinstance(add.get("original_length"), int)
            assert add["original_length"] >= TRUNCATION_MAX_LENGTH

            # GET and assert API returns additional_details
            r_get = httpx.get(
                f"{API_BASE}/metadata",
                params={"url": TRUNCATION_TEST_URL},
                timeout=10.0,
            )
            assert r_get.status_code == 200, f"GET failed: {r_get.status_code} {r_get.text}"
            body = r_get.json()
            assert body.get("status") == "COMPLETED"
            assert body.get("metadata") is not None
            add_get = body["metadata"].get("additional_details")
            assert add_get is not None
            assert add_get.get("truncated") is True
            assert add_get.get("original_length") == add["original_length"]
        finally:
            if proc.returncode is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()

    asyncio.run(_run())

