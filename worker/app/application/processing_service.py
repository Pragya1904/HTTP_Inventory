from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from worker.app.domain.processing_context import ProcessingContext
from worker.app.constants import PROCESSING_STATUS
from worker.app.ports.incoming_message import IncomingMessage
from worker.app.domain.metadata_fetcher import (
    MetadataFetcher,
    MetadataFetchError,
    MetadataFetchTimeoutError,
)
from worker.app.domain.models import FetchResult, MetadataBlock, MetadataMessage
from worker.app.ports.metadata_repository import MetadataRepository
from worker.app.core import SERVICE_NAME

MAX_PAGE_SOURCE_LENGTH = 1_000_000  # 1 MB


def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


class ProcessingService:
    """
    Processes metadata fetch messages: ensure record, fetch, persist or mark failure.

    max_retries is the maximum number of fetch attempts (not "retries after the first").
    With max_retries=3, attempts are 0, 1, 2; after the third failure we mark FAILED_PERMANENT
    and ack (no fourth fetch). On each failure before that we nack+requeue.
    """

    def __init__(
        self,
        repository: MetadataRepository,
        fetcher: MetadataFetcher,
        max_retries: int,
        *,
        max_page_source_length: int = MAX_PAGE_SOURCE_LENGTH,
    ) -> None:
        self._repository = repository
        self._fetcher = fetcher
        self._max_retries = max_retries
        self._max_page_source_length = int(max_page_source_length)

    def _truncate_page_source_if_needed(self, result: FetchResult) -> FetchResult:
        max_len = self._max_page_source_length
        if max_len <= 0:
            return result
        page_source = result.page_source or ""
        if len(page_source) <= max_len:
            return result

        details = dict(result.additional_details) if result.additional_details else {}
        details["truncated"] = True
        details["original_length"] = len(page_source)
        return FetchResult(
            headers=dict(result.headers),
            cookies=dict(result.cookies),
            page_source=page_source[:max_len],
            status_code=int(result.status_code),
            final_url=str(result.final_url),
            additional_details=details,
        )

    async def process_message(self, message: IncomingMessage) -> None:
        payload = self._deserialize_message(message.body)
        url = payload.url
        request_id = payload.request_id
        ctx = ProcessingContext(request_id=request_id, started_at=datetime.now(timezone.utc))
        _log("message_received", url=url, request_id=request_id)

        await self._repository.ensure_record(url, ctx)
        ctx = ProcessingContext(
            request_id=ctx.request_id,
            started_at=ctx.started_at,
            attempt_number=await self._get_attempt_number(url),
        )
        await self._repository.mark_in_progress(url, ctx)
        _log("message_in_progress", url=url, request_id=request_id)

        try:
            result = await self._fetcher.fetch(url)
            result = self._truncate_page_source_if_needed(result)
            await self._repository.mark_completed(
                url,
                ctx,
                MetadataBlock.from_fetch_result(result),
            )
            await message.ack()
            final_status, final_attempt_number = await self._log_final_state(url)
            _log(
                "metadata_persisted",
                url=url,
                request_id=request_id,
                status=final_status,
                attempt_number=final_attempt_number,
            )
        except Exception as exc:
            error_text = str(exc)
            is_retryable = self._is_retryable_fetch_error(exc)

            if is_retryable:
                next_attempt = ctx.attempt_number + 1
                ctx_next = ProcessingContext(
                    request_id=ctx.request_id,
                    started_at=ctx.started_at,
                    attempt_number=next_attempt,
                )
                await self._repository.mark_retryable_failure(url, ctx_next, error_text)
                if next_attempt >= self._max_retries:
                    await self._repository.mark_permanent_failure(url, ctx_next, error_text)
                    final_status, final_attempt_number = await self._log_final_state(url)
                    await message.ack()
                    _log(
                        "metadata_permanent_failure",
                        url=url,
                        request_id=request_id,
                        attempt_number=next_attempt,
                        status=final_status,
                        error=error_text,
                    )
                    return

                final_status, final_attempt_number = await self._log_final_state(url)
                await message.nack(requeue=True)
                _log(
                    "metadata_retryable_failure",
                    url=url,
                    request_id=request_id,
                    attempt_number=next_attempt,
                    status=final_status,
                    error=error_text,
                )
                return

            await self._repository.mark_permanent_failure(url, ctx, error_text)
            final_status, final_attempt_number = await self._log_final_state(url)
            await message.ack()
            _log(
                "metadata_permanent_failure",
                url=url,
                request_id=request_id,
                attempt_number=final_attempt_number,
                status=final_status,
                error=error_text,
            )

    def _deserialize_message(self, raw_body: bytes) -> MetadataMessage:
        body = json.loads(raw_body.decode())
        url = str(body.get("url", "")).strip()
        request_id = str(body.get("request_id", "")).strip()
        if not url:
            raise ValueError("message missing required field: url")
        return MetadataMessage(url=url, request_id=request_id)

    async def _get_attempt_number(self, url: str) -> int:
        doc = await self._repository.get_by_url(url)
        if not doc:
            return 0
        return int(doc.get("processing", {}).get("attempt_number", 0))

    def _is_retryable_fetch_error(self, exc: Exception) -> bool:
        return isinstance(exc, (MetadataFetchTimeoutError, MetadataFetchError))

    async def _log_final_state(self, url: str) -> tuple[str, int]:
        try:
            doc = await self._repository.get_by_url(url)
            if not doc:
                _log("metadata_final_state", url=url, status=PROCESSING_STATUS.UNKNOWN, attempt_number=0)
                return (PROCESSING_STATUS.UNKNOWN, 0)

            status = str(doc.get("status", PROCESSING_STATUS.UNKNOWN))
            attempt_number = int(doc.get("processing", {}).get("attempt_number", 0))
            _log(
                "metadata_final_state",
                url=url,
                status=status,
                attempt_number=attempt_number,
            )
            return (status, attempt_number)
        except Exception:
            _log("metadata_final_state", url=url, status=PROCESSING_STATUS.UNKNOWN, attempt_number=0)
            return (PROCESSING_STATUS.UNKNOWN, 0)
