from __future__ import annotations

from fastapi import APIRouter, Request, Response
from loguru import logger
from typing import Any

from api.app.routers.metadata_serializers import response_from_record
from api.app.routers.utils import enqueue_or_503, is_minimally_valid_url
from api.app.schemas.metadata import MetadataPostRequest

def _log(event: str, **kwargs: Any) -> None:
    logger.info(f"{event}: {kwargs}")


metadata_router = APIRouter(prefix="/metadata", tags=["Inventory"])

@metadata_router.post(
    "",
    summary="Enqueue URL for metadata processing",
    description="Submits a URL for asynchronous metadata fetch. The request is enqueued to a worker; returns immediately with 202 and a request_id. Processing happens in the background.",
    responses={
        202: {"description": "URL accepted and queued for processing."},
        422: {"description": "Invalid request body or URL validation failed."},
        503: {"description": "Publisher or queue unavailable; try again later."},
    },
)
async def post_metadata(request: Request, body: MetadataPostRequest) -> Response:
    url_str = str(body.url)
    return await enqueue_or_503(request, url=url_str)


@metadata_router.get(
    "",
    summary="Lookup URL metadata",
    description="Returns the metadata record if it exists (COMPLETED or FAILED_PERMANENT). If the URL is not found, it is enqueued and 202 is returned. If the record is PENDING/IN_PROGRESS, returns 202 without re-enqueuing.",
    responses={
        200: {"description": "Metadata found and returned (COMPLETED or FAILED_PERMANENT)."},
        202: {"description": "URL enqueued or processing in progress."},
        400: {"description": "Missing or invalid URL query parameter."},
        503: {"description": "Database or publisher unavailable."},
    },
)
async def get_metadata(request: Request, url: str | None = None) -> Response:
    if not url:
        return Response(status_code=400, content="Missing required query parameter: url")
    if not is_minimally_valid_url(url):
        return Response(status_code=400, content="Invalid URL")

    repo = getattr(request.app.state, "metadata_repository", None)
    if repo is None:
        return Response(status_code=503, content="Database not available")

    try:
        record = await repo.get_by_url(url)
    except Exception as e:
        _log("get_metadata_error", url=url, error=str(e))
        return Response(status_code=503)

    if record is not None:
        response = response_from_record(record, requested_url=url)
        if response is not None:
            return response

    # Not found → enqueue (same as POST contract).
    return await enqueue_or_503(request, url=url)
