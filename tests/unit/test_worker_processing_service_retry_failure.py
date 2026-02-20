"""Unit tests for ProcessingService retry/failure paths and malformed messages."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from worker.app.application.processing_service import ProcessingService
from worker.app.domain.metadata_fetcher import MetadataFetchError, MetadataFetchTimeoutError
from worker.app.domain.models import FetchResult, MetadataBlock


class FakeMessage:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.body = json.dumps(payload).encode()
        self.acked = False
        self.nacked = False
        self.nack_requeue: bool | None = None

    @property
    def processed(self) -> bool:
        return self.acked or self.nacked

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, *, requeue: bool) -> None:
        self.nacked = True
        self.nack_requeue = requeue


class CapturingRepo:
    """Records all repository calls for assertions."""

    def __init__(self, get_by_url_return: dict[str, Any] | None = None) -> None:
        self.get_by_url_return = get_by_url_return or {"processing": {"attempt_number": 0}}
        self.ensure_record_calls: list[tuple[str, Any]] = []
        self.mark_in_progress_calls: list[tuple[str, Any]] = []
        self.mark_completed_calls: list[tuple[str, Any, Any]] = []
        self.mark_retryable_failure_calls: list[tuple[str, Any, str]] = []
        self.mark_permanent_failure_calls: list[tuple[str, Any, str]] = []

    async def ensure_record(self, url: str, ctx: Any) -> None:
        self.ensure_record_calls.append((url, ctx))

    async def mark_in_progress(self, url: str, ctx: Any) -> None:
        self.mark_in_progress_calls.append((url, ctx))

    async def mark_completed(self, url: str, ctx: Any, metadata: MetadataBlock) -> None:
        self.mark_completed_calls.append((url, ctx, metadata))

    async def mark_retryable_failure(self, url: str, ctx: Any, error: str) -> int:
        self.mark_retryable_failure_calls.append((url, ctx, error))
        return 1

    async def mark_permanent_failure(self, url: str, ctx: Any, error: str) -> None:
        self.mark_permanent_failure_calls.append((url, ctx, error))

    async def get_by_url(self, url: str) -> dict[str, Any] | None:
        return self.get_by_url_return


class FailingFetcher:
    """Fetcher that raises a given exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def fetch(self, url: str) -> FetchResult:
        raise self._exc


class _SuccessFetcher:
    async def fetch(self, url: str) -> FetchResult:
        return FetchResult(headers={}, cookies={}, page_source="", status_code=200, final_url=url)


def test_malformed_message_missing_url_raises_value_error():
    """Process_message raises ValueError when message has no url."""
    repo = CapturingRepo()
    svc = ProcessingService(repo, _SuccessFetcher(), max_retries=3)
    msg = FakeMessage({"request_id": "r1"})  # no url

    with pytest.raises(ValueError, match="missing required field: url"):
        asyncio.run(svc.process_message(msg))  # type: ignore[arg-type]

    assert msg.acked is False
    assert msg.nacked is False
    assert len(repo.mark_completed_calls) == 0
    assert len(repo.mark_permanent_failure_calls) == 0


def test_malformed_message_empty_url_raises_value_error():
    """Process_message raises ValueError when url is empty string."""
    repo = CapturingRepo()
    svc = ProcessingService(repo, _SuccessFetcher(), max_retries=3)
    msg = FakeMessage({"url": "   ", "request_id": "r1"})

    with pytest.raises(ValueError, match="missing required field: url"):
        asyncio.run(svc.process_message(msg))  # type: ignore[arg-type]

    assert msg.acked is False
    assert msg.nacked is False


def test_retryable_failure_with_retries_left_nack_requeue():
    """On retryable fetch error with attempts left: mark_retryable_failure, then nack(requeue=True)."""
    repo = CapturingRepo(get_by_url_return={"processing": {"attempt_number": 0}})
    svc = ProcessingService(repo, FailingFetcher(MetadataFetchTimeoutError("timeout")), max_retries=3)
    msg = FakeMessage({"url": "https://example.com", "request_id": "req-1"})

    asyncio.run(svc.process_message(msg))  # type: ignore[arg-type]

    assert msg.nacked is True
    assert msg.nack_requeue is True
    assert msg.acked is False
    assert len(repo.mark_retryable_failure_calls) == 1
    assert repo.mark_retryable_failure_calls[0][2] == "timeout"
    assert repo.mark_retryable_failure_calls[0][1].attempt_number == 1
    assert len(repo.mark_permanent_failure_calls) == 0
    assert len(repo.mark_completed_calls) == 0


def test_retryable_failure_exhaust_retries_then_permanent_ack():
    """On retryable fetch error when next_attempt >= max_retries: mark_retryable_failure, mark_permanent_failure, ack."""
    repo = CapturingRepo(get_by_url_return={"processing": {"attempt_number": 1}})  # attempt 2 will be 2 >= 2
    svc = ProcessingService(repo, FailingFetcher(MetadataFetchError("fetch failed")), max_retries=2)
    msg = FakeMessage({"url": "https://example.com", "request_id": "req-1"})

    asyncio.run(svc.process_message(msg))  # type: ignore[arg-type]

    assert msg.acked is True
    assert msg.nacked is False
    assert len(repo.mark_retryable_failure_calls) == 1
    assert repo.mark_retryable_failure_calls[0][1].attempt_number == 2
    assert len(repo.mark_permanent_failure_calls) == 1
    assert repo.mark_permanent_failure_calls[0][2] == "fetch failed"
    assert len(repo.mark_completed_calls) == 0


def test_non_retryable_failure_immediate_permanent_ack():
    """On non-retryable exception (e.g. generic): mark_permanent_failure, ack (no nack, no mark_retryable)."""
    repo = CapturingRepo(get_by_url_return={"processing": {"attempt_number": 0}})
    svc = ProcessingService(repo, FailingFetcher(RuntimeError("something else")), max_retries=3)
    msg = FakeMessage({"url": "https://example.com", "request_id": "req-1"})

    asyncio.run(svc.process_message(msg))  # type: ignore[arg-type]

    assert msg.acked is True
    assert msg.nacked is False
    assert len(repo.mark_permanent_failure_calls) == 1
    assert repo.mark_permanent_failure_calls[0][2] == "something else"
    assert len(repo.mark_retryable_failure_calls) == 0
    assert len(repo.mark_completed_calls) == 0


def test_retryable_failure_metadata_fetch_error_nack_requeue():
    """MetadataFetchError is retryable; we nack+requeue when retries left."""
    repo = CapturingRepo(get_by_url_return={"processing": {"attempt_number": 0}})
    svc = ProcessingService(repo, FailingFetcher(MetadataFetchError("connection refused")), max_retries=5)
    msg = FakeMessage({"url": "https://example.com", "request_id": "req-1"})

    asyncio.run(svc.process_message(msg))  # type: ignore[arg-type]

    assert msg.nacked is True
    assert msg.nack_requeue is True
    assert len(repo.mark_retryable_failure_calls) == 1
    assert len(repo.mark_permanent_failure_calls) == 0
