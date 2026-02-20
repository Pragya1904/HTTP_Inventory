import asyncio

from fastapi import APIRouter, Request, Response
from loguru import logger

from api.app.routers.utils import _readiness_ping_timeout_seconds

health_router = APIRouter(tags=["health"])


@health_router.get("/health/live")
async def live() -> dict:
    return {"status": "ok"}


@health_router.get("/health/ready")
async def ready(request: Request) -> Response:
    publisher = getattr(request.app.state, "publisher", None)
    database = getattr(request.app.state, "database", None)
    if publisher is None or database is None:
        logger.bind(service_name="api", event="readiness_failed", reason="components_not_initialized").warning("")
        return Response(status_code=503, content="Not ready")
    if not publisher.ready:
        logger.bind(service_name="api", event="readiness_failed", reason="publisher_not_ready").warning("")
        return Response(status_code=503, content="Publisher not ready")

    timeout_s = _readiness_ping_timeout_seconds(request)
    try:
        ping_ok = await asyncio.wait_for(database.ping(), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.bind(service_name="api", event="readiness_failed", reason="db_ping_timeout").warning("")
        return Response(status_code=503, content="Database not ready")
    if not ping_ok:
        logger.bind(service_name="api", event="readiness_failed", reason="db_not_ready").warning("")
        return Response(status_code=503, content="Database not ready")
    return Response(status_code=200, content="OK")
