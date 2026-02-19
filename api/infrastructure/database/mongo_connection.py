from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient

from api.app.core.backoff import exponential_backoff
from api.infrastructure.database.base import DatabaseConnection
from api.infrastructure.database.constants import ConnectionState

SERVICE_NAME = "api"


def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


class MongoConnection(DatabaseConnection):
    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._state = ConnectionState.DISCONNECTED
        self._client: AsyncIOMotorClient | None = None

    @property
    def ready(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    async def connect(self) -> None:
        self._state = ConnectionState.CONNECTING
        attempt = 0
        backoff = exponential_backoff(
            self._settings.initial_backoff_seconds,
            self._settings.max_backoff_seconds,
            2.0,
            self._settings.max_connection_attempts,
        )
        async for delay in backoff:
            attempt += 1
            _log("db_connect_attempt", attempt=attempt, delay=delay)
            try:
                u, p = self._settings.database_user, self._settings.database_password
                if u and p:
                    uri = f"mongodb://{u}:{p}@{self._settings.database_host}:{self._settings.database_port}"
                else:
                    uri = f"mongodb://{self._settings.database_host}:{self._settings.database_port}"
                self._client = AsyncIOMotorClient(
                    uri,
                    serverSelectionTimeoutMS=5000,
                )
                await self._client.admin.command("ping")
                self._state = ConnectionState.CONNECTED
                _log("db_connected")
                return
            except Exception as e:
                logger.warning("db connect failed: {}", e)
                if attempt >= self._settings.max_connection_attempts:
                    self._state = ConnectionState.DISCONNECTED
                    _log("db_connect_failed", attempt=attempt)
                    raise
        self._state = ConnectionState.DISCONNECTED

    async def ping(self) -> bool:
        if not self._client:
            return False
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
        self._state = ConnectionState.DISCONNECTED

