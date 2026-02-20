from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncio
import pytest

from worker.app.application.processing_service import ProcessingService
from worker.app.domain.models import FetchResult, MetadataBlock


class FakeMessage:
    def __init__(self, payload: dict[str, Any]) -> None:
        import json

        self.body = json.dumps(payload).encode()
        self.acked = False
        self.nacked = False
        self.nack_requeue: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, *, requeue: bool) -> None:
        self.nacked = True
        self.nack_requeue = requeue


@dataclass
class CapturingRepo:
    completed_block: MetadataBlock | None = None

    async def ensure_record(self, url: str, ctx) -> None:  # noqa: ANN001
        return

    async def mark_in_progress(self, url: str, ctx) -> None:  # noqa: ANN001
        return

    async def mark_completed(self, url: str, ctx, metadata: MetadataBlock) -> None:  # noqa: ANN001
        self.completed_block = metadata

    async def mark_retryable_failure(self, url: str, ctx, error: str) -> int:  # noqa: ANN001
        return 1

    async def mark_permanent_failure(self, url: str, ctx, error: str) -> None:  # noqa: ANN001
        return

    async def get_by_url(self, url: str) -> dict[str, Any] | None:
        return {"processing": {"attempt_number": 0}}


class FakeFetcher:
    def __init__(self, result: FetchResult) -> None:
        self._result = result

    async def fetch(self, url: str) -> FetchResult:
        return self._result


def test_processing_service_truncates_page_source_and_sets_flags():
    original = "x" * 25
    result = FetchResult(
        headers={"a": "b"},
        cookies={},
        page_source=original,
        status_code=200,
        final_url="https://example.com",
    )
    repo = CapturingRepo()
    svc = ProcessingService(repo, FakeFetcher(result), max_retries=1, max_page_source_length=10)
    msg = FakeMessage({"url": "https://example.com", "request_id": "req-1"})

    asyncio.run(svc.process_message(msg))  # type: ignore[arg-type]

    assert msg.acked is True
    assert repo.completed_block is not None
    assert repo.completed_block.page_source == "x" * 10
    assert repo.completed_block.additional_details is not None
    assert repo.completed_block.additional_details["truncated"] is True
    assert repo.completed_block.additional_details["original_length"] == 25


def test_processing_service_does_not_set_truncated_flag_when_not_needed():
    original = "hello"
    result = FetchResult(
        headers={},
        cookies={},
        page_source=original,
        status_code=200,
        final_url="https://example.com",
    )
    repo = CapturingRepo()
    svc = ProcessingService(repo, FakeFetcher(result), max_retries=1, max_page_source_length=10)
    msg = FakeMessage({"url": "https://example.com", "request_id": "req-1"})

    asyncio.run(svc.process_message(msg))  # type: ignore[arg-type]

    assert repo.completed_block is not None
    assert repo.completed_block.page_source == original
    assert repo.completed_block.additional_details in (None, {})
    if isinstance(repo.completed_block.additional_details, dict):
        assert "truncated" not in repo.completed_block.additional_details
        assert "original_length" not in repo.completed_block.additional_details


def test_truncate_page_source_helper_truncates_and_sets_flags():
    repo = CapturingRepo()
    svc = ProcessingService(repo, FakeFetcher(FetchResult(headers={}, cookies={}, page_source="", status_code=200, final_url="x")), max_retries=1, max_page_source_length=5)

    original = "a" * 12
    result = FetchResult(
        headers={"h": "v"},
        cookies={"c": "1"},
        page_source=original,
        status_code=200,
        final_url="https://example.com",
        additional_details={"some_key": "some_val"},
    )

    out = svc._truncate_page_source_if_needed(result)
    assert out is not result
    assert out.page_source == "a" * 5
    assert out.additional_details["truncated"] is True
    assert out.additional_details["original_length"] == 12
    assert out.additional_details["some_key"] == "some_val"


def test_truncate_page_source_helper_returns_same_object_when_no_truncation_needed():
    repo = CapturingRepo()
    svc = ProcessingService(repo, FakeFetcher(FetchResult(headers={}, cookies={}, page_source="", status_code=200, final_url="x")), max_retries=1, max_page_source_length=100)

    result = FetchResult(
        headers={},
        cookies={},
        page_source="short",
        status_code=200,
        final_url="https://example.com",
        additional_details={"k": "v"},
    )
    out = svc._truncate_page_source_if_needed(result)
    assert out is result


def test_truncate_page_source_helper_returns_same_object_when_max_len_disabled():
    repo = CapturingRepo()
    svc = ProcessingService(repo, FakeFetcher(FetchResult(headers={}, cookies={}, page_source="", status_code=200, final_url="x")), max_retries=1, max_page_source_length=0)

    result = FetchResult(
        headers={},
        cookies={},
        page_source="a" * 1000,
        status_code=200,
        final_url="https://example.com",
    )
    out = svc._truncate_page_source_if_needed(result)
    assert out is result

