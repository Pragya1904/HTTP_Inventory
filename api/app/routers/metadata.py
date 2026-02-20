from __future__ import annotations

from fastapi import APIRouter, Request, Response
from loguru import logger
from typing import Any

from api.app.routers.metadata_serializers import response_from_record
from api.app.routers.utils import enqueue_or_503, is_minimally_valid_url
from api.app.schemas.metadata import MetadataPostRequest

def _log(event: str, **kwargs: Any) -> None:
    logger.info(f"{event}: {kwargs}")


metadata_router = APIRouter(prefix="/metadata", tags=["metadata"])

@metadata_router.post("")
async def post_metadata(request: Request, body: MetadataPostRequest) -> Response:
    url_str = str(body.url)
    return await enqueue_or_503(request, url=url_str)


@metadata_router.get("")
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
