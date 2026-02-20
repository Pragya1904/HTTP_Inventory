import json
import random
import time

import pytest
import httpx

from tests.test_data import TEST_URLS


API_BASE = "http://api:6577"
RMQ_URL = "amqp://guest:guest@rabbitmq:5672/"
RMQ_MGMT = "http://guest:guest@rabbitmq:15672"
QUEUE_NAME = "metadata_queue"
QUEUE_ARGS = {"x-max-length": 1000, "x-overflow": "reject-publish"}


def _queue_consumer_count() -> int | None:
    """Return consumer_count for metadata_queue from RabbitMQ management API, or None if unavailable."""
    try:
        r = httpx.get(f"{RMQ_MGMT}/api/queues/%2F/{QUEUE_NAME}", timeout=5.0)
        if r.status_code != 200:
            return None
        return r.json().get("consumer_count", 0)
    except Exception:
        return None


def _wait_http(url: str, timeout_s: float = 60.0) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                return
        except Exception:
            pass
        time.sleep(1.0)
    raise AssertionError(f"Timed out waiting for {url}")


@pytest.mark.integration
def test_api_live_and_ready_endpoints():
    _wait_http(f"{API_BASE}/health/live", timeout_s=90)
    r = httpx.get(f"{API_BASE}/health/live")
    assert r.status_code == 200

    # ready may take a bit until broker + db are reachable
    start = time.time()
    while time.time() - start < 90:
        rr = httpx.get(f"{API_BASE}/health/ready")
        if rr.status_code == 200:
            break
        time.sleep(1.0)
    assert rr.status_code == 200


@pytest.mark.integration
def test_post_metadata_enqueues_message():
    """POST /metadata enqueues a message; we drain the queue to find it. Requires no consumer on the queue
    (worker must be stopped), otherwise the worker may consume the message before we read it.
    Run with worker stopped: docker compose stop worker && docker compose run --rm tests pytest tests/integration/test_compose_api.py::test_post_metadata_enqueues_message -v && docker compose start worker
    Or use scripts/run_integration_queue_test.ps1 (Windows) or scripts/run_integration_queue_test.sh (Linux/macOS).
    """
    consumers = _queue_consumer_count()
    if consumers is not None and consumers > 0:
        pytest.skip(
            "Queue has active consumer(s); worker must be stopped so the message stays in the queue. "
            "Run: docker compose stop worker && docker compose run --rm tests pytest tests/integration/test_compose_api.py::test_post_metadata_enqueues_message -v && docker compose start worker "
            "(or use scripts/run_integration_queue_test.ps1 / run_integration_queue_test.sh)"
        )

    import aio_pika
    import asyncio

    async def _drain_and_check(req_id: str, expected_url: str) -> None:
        conn = await aio_pika.connect_robust(RMQ_URL)
        ch = await conn.channel()
        q = await ch.declare_queue(QUEUE_NAME, durable=True, arguments=QUEUE_ARGS)
        
        while True:
            msg = await q.get(fail=False, timeout=10)
            if msg is None:
                break
            payload = json.loads(msg.body.decode())
            if payload.get("request_id") == req_id:
                assert payload["url"] == expected_url
                await msg.ack()
                await ch.close()
                await conn.close()
                return
            await msg.ack()
        await ch.close()
        await conn.close()
        raise AssertionError(f"No message with request_id {req_id!r} in queue")

    # Pick a URL from the curated test list for variety in integration runs
    url = random.choice(TEST_URLS)
    r = httpx.post(f"{API_BASE}/metadata", json={"url": url})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "QUEUED"
    req_id = body["request_id"]
    expected_url = body["url"]
    assert expected_url == url

    # Allow broker a moment to receive the message (publish is awaited, but delivery can be slightly delayed)
    time.sleep(1.0)
    asyncio.run(_drain_and_check(req_id, expected_url))


@pytest.mark.failure_path
@pytest.mark.integration
def test_failure_when_deps_down():
    """Expect 503 when RabbitMQ/Mongo are stopped. Run: docker compose stop rabbitmq mongo; docker compose run --no-deps tests pytest -m failure_path -v"""
    r_ready = httpx.get(f"{API_BASE}/health/ready", timeout=35.0)
    if r_ready.status_code == 200:
        pytest.skip("Dependencies are up (ready=200). Run with deps stopped: docker compose stop rabbitmq mongo; docker compose run --no-deps tests pytest -m failure_path -v")
    assert r_ready.status_code == 503, f"Expected 503 when deps down, got {r_ready.status_code}"

    url = random.choice(TEST_URLS)
    r_post = httpx.post(f"{API_BASE}/metadata", json={"url": url}, timeout=10.0)
    assert r_post.status_code == 503, f"Expected 503 when broker down, got {r_post.status_code}"

