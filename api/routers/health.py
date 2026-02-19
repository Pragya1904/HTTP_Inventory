import asyncio

from fastapi import APIRouter, Request, Response
from loguru import logger

from api.publisher.constants import PublisherState

router = APIRouter(tags=["health"])

READINESS_PING_TIMEOUT_DEFAULT = 30.0


@router.get("/health/live")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> Response:
    publisher = getattr(request.app.state, "publisher", None)
    database = getattr(request.app.state, "database", None)
    if publisher is None or database is None:
        logger.bind(service_name="api", event="readiness_failed", reason="components_not_initialized").warning("")
        return Response(status_code=503, content="Not ready")
    if publisher.state != PublisherState.READY:
        logger.bind(service_name="api", event="readiness_failed", reason="publisher_not_ready").warning("")
        return Response(status_code=503, content="Publisher not ready")

    timeout_s = READINESS_PING_TIMEOUT_DEFAULT
    settings = getattr(request.app.state, "settings", None)
    if settings is not None:
        timeout_s = getattr(settings, "readiness_ping_timeout_seconds", READINESS_PING_TIMEOUT_DEFAULT)
    try:
        ping_ok = await asyncio.wait_for(database.ping(), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.bind(service_name="api", event="readiness_failed", reason="db_ping_timeout").warning("")
        return Response(status_code=503, content="Database not ready")
    if not ping_ok:
        logger.bind(service_name="api", event="readiness_failed", reason="db_not_ready").warning("")
        return Response(status_code=503, content="Database not ready")
    return Response(status_code=200, content="OK")
