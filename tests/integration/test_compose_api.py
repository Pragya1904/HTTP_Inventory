import json
import time

import pytest
import httpx


API_BASE = "http://api:6577"
RMQ_URL = "amqp://guest:guest@rabbitmq:5672/"
QUEUE_NAME = "metadata_queue"
QUEUE_ARGS = {"x-max-length": 1000, "x-overflow": "reject-publish"}


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
    import aio_pika
    import asyncio

    async def _drain_and_check(req_id: str, expected_url: str) -> None:
        conn = await aio_pika.connect_robust(RMQ_URL)
        ch = await conn.channel()
        q = await ch.declare_queue(QUEUE_NAME, durable=True, arguments=QUEUE_ARGS)
        
        while True:
            msg = await q.get(fail=False, timeout=2)
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

    r = httpx.post(f"{API_BASE}/metadata", json={"url": "https://example.com"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "QUEUED"
    req_id = body["request_id"]
    expected_url = body["url"] 

    asyncio.run(_drain_and_check(req_id, expected_url))


@pytest.mark.failure_path
@pytest.mark.integration
def test_failure_when_deps_down():
    """Expect 503 when RabbitMQ/Mongo are stopped. Run: docker compose stop rabbitmq mongo; docker compose run --no-deps tests pytest -m failure_path -v"""
    r_ready = httpx.get(f"{API_BASE}/health/ready", timeout=35.0)
    assert r_ready.status_code == 503, f"Expected 503 when deps down, got {r_ready.status_code}"

    r_post = httpx.post(f"{API_BASE}/metadata", json={"url": "https://example.com"}, timeout=10.0)
    assert r_post.status_code == 503, f"Expected 503 when broker down, got {r_post.status_code}"

