"""
End-to-end test: half of TEST_URLs via POST /metadata, half via GET /metadata.

Verifies API enqueue (POST and GET), publisher, consumer, and DB behaviour.
Logs every step and documents results. Requires full stack (API, RabbitMQ, Mongo)
and starts the worker in-process so one run exercises the full pipeline.

Run: docker compose run --rm tests pytest tests/integration/test_e2e_metadata_post_get.py -v -s
     (-s shows print logs)
"""
from __future__ import annotations

import inspect
import asyncio
import signal
import time
import uuid

import httpx
import pytest

from tests.test_data import TEST_URLS
from worker.app.constants import PROCESSING_STATUS


API_BASE = "http://api:6577"
MONGO_URI = "mongodb://mongo:27017"
DB_NAME = "metadata_inventory"
COLLECTION_NAME = "metadata_records"
WAIT_POLL_INTERVAL_S = 2.0
WAIT_TIMEOUT_TOTAL_S = 600  # 10 min for all URLs to reach terminal state


def _log(step: str, **kwargs: object) -> None:
    parts = [f"[E2E] {step}"]
    for k, v in kwargs.items():
        parts.append(f" {k}={v}")
    print("".join(parts))


def _wait_api_ready(timeout_s: float = 90.0) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            r = httpx.get(f"{API_BASE}/health/ready", timeout=5.0)
            if r.status_code == 200:
                _log("api_ready", status=200)
                return
        except Exception as e:
            _log("api_wait", error=str(e))
        time.sleep(1.0)
    raise AssertionError(f"API not ready within {timeout_s}s")


async def _get_record(url: str):
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        coll = client[DB_NAME][COLLECTION_NAME]
        return await coll.find_one({"url": url})
    finally:
        res = client.close()
        if inspect.isawaitable(res):
            await res


async def _wait_terminal_state(url: str, timeout_s: float) -> dict | None:
    terminal = {PROCESSING_STATUS.COMPLETED, PROCESSING_STATUS.FAILED_PERMANENT}
    start = time.time()
    while time.time() - start < timeout_s:
        record = await _get_record(url)
        if record:
            status = record.get("status")
            if status in terminal:
                return record
        await asyncio.sleep(WAIT_POLL_INTERVAL_S)
    return None


async def _run_e2e() -> None:
    urls = list(TEST_URLS)
    if not urls:
        pytest.skip("TEST_URLS is empty")
    n = len(urls)
    half = n // 2
    post_urls = urls[:half]
    get_urls = urls[half:]
    _log("split", total=n, post_count=len(post_urls), get_count=len(get_urls))

    _wait_api_ready()

    # Start worker so messages are consumed
    proc = await asyncio.create_subprocess_exec("python", "-m", "worker.app.main")
    _log("worker_started", pid=proc.pid)

    results: list[dict] = []
    timeout_per_url = max(30.0, WAIT_TIMEOUT_TOTAL_S / n)

    try:
        # ---- Enqueue via POST ----
        for i, url in enumerate(post_urls):
            r = httpx.post(f"{API_BASE}/metadata", json={"url": url}, timeout=10.0)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            request_id = body.get("request_id", "")
            _log("enqueue_post", index=i + 1, url=url[:60], status_code=r.status_code, request_id=request_id)
            if r.status_code == 202:
                results.append({"url": url, "method": "POST", "request_id": request_id, "enqueued": True})
            else:
                results.append({"url": url, "method": "POST", "request_id": "", "enqueued": False, "status_code": r.status_code})

        # ---- Enqueue via GET ----
        for i, url in enumerate(get_urls):
            r = httpx.get(f"{API_BASE}/metadata", params={"url": url}, timeout=10.0)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            request_id = body.get("request_id", "")
            _log("enqueue_get", index=i + 1, url=url[:60], status_code=r.status_code, request_id=request_id)
            if r.status_code in (200, 202):
                results.append({"url": url, "method": "GET", "request_id": request_id, "enqueued": True})
            else:
                results.append({"url": url, "method": "GET", "request_id": "", "enqueued": False, "status_code": r.status_code})

        # ---- Wait for terminal state in DB for each URL ----
        all_urls = [r["url"] for r in results]
        _log("wait_db", message="Waiting for terminal state (COMPLETED or FAILED_PERMANENT) for all URLs")
        for i, url in enumerate(all_urls):
            record = await _wait_terminal_state(url, timeout_per_url)
            if record:
                status = record.get("status", "UNKNOWN")
                processing = record.get("processing") or {}
                attempt_number = processing.get("attempt_number", 0)
                error_msg = processing.get("error_msg")
                _log("db_result", url=url[:60], status=status, attempt_number=attempt_number, error_msg=(error_msg or "")[:80])
                for r in results:
                    if r["url"] == url:
                        r["status"] = status
                        r["attempt_number"] = attempt_number
                        r["error_msg"] = error_msg
                        break
            else:
                _log("db_timeout", url=url[:60])
                for r in results:
                    if r["url"] == url:
                        r["status"] = "TIMEOUT"
                        r["attempt_number"] = None
                        r["error_msg"] = None
                        break

    finally:
        if proc.returncode is None:
            proc.send_signal(signal.SIGTERM)
            _log("worker_stop", message="SIGTERM sent")
            try:
                await asyncio.wait_for(proc.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

    # ---- Document results ----
    completed = sum(1 for r in results if r.get("status") == PROCESSING_STATUS.COMPLETED)
    failed = sum(1 for r in results if r.get("status") == PROCESSING_STATUS.FAILED_PERMANENT)
    timeout_count = sum(1 for r in results if r.get("status") == "TIMEOUT")
    other = len(results) - completed - failed - timeout_count

    _log("summary", completed=completed, failed_permanent=failed, timeout=timeout_count, other=other, total=len(results))
    print("\n[E2E] --- Results by URL ---")
    for r in results:
        print(f"  {r['method']:4} | {r.get('status', '?'):20} | {r['url'][:70]}")
    print("[E2E] --- End results ---\n")

    # Store for documentation / assertions
    assert len(results) == n, f"Expected {n} results, got {len(results)}"
    # At least one completed so pipeline worked
    assert completed >= 1, f"No URL reached COMPLETED; completed={completed}, failed={failed}, timeout={timeout_count}"


@pytest.mark.integration
def test_e2e_metadata_half_post_half_get():
    """E2E: half URLs via POST /metadata, half via GET /metadata; verify API, publisher, consumer, DB; log every step."""
    asyncio.run(_run_e2e())
