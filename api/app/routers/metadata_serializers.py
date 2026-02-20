"""Helpers to serialize metadata DB records into API responses."""
from __future__ import annotations

from typing import Any

from fastapi import Response

from api.app.constants import ProcessingStatus
from api.app.schemas.metadata import (
    MetadataGetFailedResponse,
    MetadataGetSuccessResponse,
    MetadataPayload,
    MetadataPostResponse,
)


_IN_PROGRESS_STATUSES = {
    ProcessingStatus.QUEUED,
    ProcessingStatus.PENDING,
    ProcessingStatus.IN_PROGRESS,
    ProcessingStatus.FAILED_RETRYABLE,
}


def response_from_record(record: dict[str, Any], *, requested_url: str) -> Response | None:
    """
    Map a persisted record (written by worker) to an HTTP response.

    Rules:
    - COMPLETED -> 200 with full metadata (nested under `metadata`, no request_id)
    - FAILED_PERMANENT -> 200 with failure metadata (flat: error_msg, attempt_number; no request_id)
    - PENDING/IN_PROGRESS/FAILED_RETRYABLE/QUEUED -> 202 IN_PROGRESS (do not enqueue again)
    - unknown/malformed status -> None (caller may choose to enqueue)
    """
    status = str(record.get("status", "") or "")
    processing = record.get("processing") or {}
    request_id = str(processing.get("last_request_id") or "")
    url = str(record.get("url") or requested_url)

    if status == ProcessingStatus.COMPLETED:
        meta = record.get("metadata") or {}

        additional = meta.get("additional_details")
        if not isinstance(additional, dict):
            additional = record.get("additional_details")
        if not isinstance(additional, dict):
            additional = None

        return Response(
            status_code=200,
            media_type="application/json",
            content=MetadataGetSuccessResponse(
                status=ProcessingStatus.COMPLETED,
                url=url,
                metadata=MetadataPayload(
                    headers=dict(meta.get("headers") or {}),
                    cookies=dict(meta.get("cookies") or {}),
                    status_code=int(meta.get("status_code") or 0),
                    page_source=str(meta.get("page_source") or ""),
                    additional_details=additional,
                ),
            ).model_dump_json(),
        )

    if status == ProcessingStatus.FAILED_PERMANENT:
        return Response(
            status_code=200,
            media_type="application/json",
            content=MetadataGetFailedResponse(
                status=ProcessingStatus.FAILED_PERMANENT,
                url=url,
                error_msg=processing.get("error_msg"),
                attempt_number=processing.get("attempt_number"),
            ).model_dump_json(),
        )

    if status in _IN_PROGRESS_STATUSES:
        return Response(
            status_code=202,
            media_type="application/json",
            content=MetadataPostResponse(
                status=ProcessingStatus.IN_PROGRESS,
                url=url,
                request_id=request_id,
            ).model_dump_json(),
        )

    return None

