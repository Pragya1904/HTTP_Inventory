"""Mongo client connection helper (provider-specific infrastructure)."""
from __future__ import annotations

import inspect
from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient

from worker.app.config.settings import Settings
from worker.app.core import SERVICE_NAME
from worker.app.core.backoff import exponential_backoff


def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


def _build_mongo_uri(settings: Settings) -> str:
    user, password = settings.database_user, settings.database_password
    if user and password:
        return f"mongodb://{user}:{password}@{settings.database_host}:{settings.database_port}"
    return f"mongodb://{settings.database_host}:{settings.database_port}"


async def create_mongo_client(settings: Settings) -> AsyncIOMotorClient:
    """Connect to Mongo with retry/backoff and return a live client."""
    _log("mongo_connecting")
    attempt = 0
    async for delay in exponential_backoff(
        settings.initial_backoff_seconds,
        settings.max_backoff_seconds,
        settings.backoff_multiplier,
        settings.max_connection_attempts,
    ):
        attempt += 1
        _log("mongo_connect_attempt", attempt=attempt, delay=delay)
        mongo_client: AsyncIOMotorClient | None = None
        try:
            mongo_client = AsyncIOMotorClient(
                _build_mongo_uri(settings),
                serverSelectionTimeoutMS=settings.database_connection_timeout_ms,
            )
            await mongo_client.admin.command("ping")
            _log("mongo_connected")
            return mongo_client
        except Exception as exc:
            logger.warning("mongo connect failed: {}", exc)
            if mongo_client is not None:
                res = mongo_client.close()
                if inspect.isawaitable(res):
                    await res
            if attempt >= settings.max_connection_attempts:
                raise
    raise RuntimeError("mongo connect failed")
