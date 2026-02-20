from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import Request, Response
from loguru import logger

from api.app.constants import ProcessingStatus
from api.app.core import SERVICE_NAME
from api.app.schemas.metadata import MetadataPostResponse
from api.app.services.enqueue_metadata import enqueue_metadata

READINESS_PING_TIMEOUT_DEFAULT = 30.0


def readiness_ping_timeout_seconds(request: Request) -> float:
    """Read readiness DB ping timeout from app.state.settings or default."""
    settings = getattr(request.app.state, "settings", None)
    if settings is not None:
        return getattr(settings, "readiness_ping_timeout_seconds", READINESS_PING_TIMEOUT_DEFAULT)
    return READINESS_PING_TIMEOUT_DEFAULT


def is_minimally_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).warning("")


async def enqueue_or_503(request: Request, *, url: str) -> Response:
    """Shared enqueue logic for POST and GET-not-found paths."""
    publisher = getattr(request.app.state, "publisher", None)
    if publisher is None:
        _log("publish_rejected", reason="publisher_not_ready")
        return Response(status_code=503, content="Publisher not available")

    outcome = await enqueue_metadata(url, publisher)

    if outcome.success:
        return Response(
            status_code=202,
            media_type="application/json",
            content=MetadataPostResponse(
                status=ProcessingStatus.QUEUED,
                url=outcome.url or url,
                request_id=outcome.request_id or "",
            ).model_dump_json(),
        )

    _log(
        "publish_failed",
        reason=outcome.error,
        url=outcome.url or url,
        request_id=outcome.request_id or "",
    )
    content = "Queue rejected" if outcome.is_queue_rejected else (outcome.error or "Publish failed")
    return Response(status_code=503, content=content)


__all__ = [
    "readiness_ping_timeout_seconds",
    "is_minimally_valid_url",
    "enqueue_or_503",
]