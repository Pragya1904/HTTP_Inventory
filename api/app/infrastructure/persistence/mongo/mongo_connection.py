import inspect
from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from api.app.config.settings import Settings
from api.app.core import SERVICE_NAME
from api.app.core.backoff import exponential_backoff
from api.app.infrastructure.persistence.mongo.constants import ConnectionState


def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


class MongoConnection:
    """DatabaseConnection implementation using MongoDB."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._state = ConnectionState.DISCONNECTED
        self._client: AsyncIOMotorClient | None = None

    @property
    def ready(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def client(self) -> AsyncIOMotorClient:
        if not self._client:
            raise RuntimeError("db_not_connected")
        return self._client

    @property
    def metadata_collection(self) -> AsyncIOMotorCollection:
        """Mongo collection used for metadata records."""
        client = self.client
        return client[self._settings.database_name][self._settings.database_collection]

    async def connect(self) -> None:
        self._state = ConnectionState.CONNECTING
        attempt = 0
        backoff = exponential_backoff(
            self._settings.initial_backoff_seconds,
            self._settings.max_backoff_seconds,
            self._settings.backoff_multiplier,
            self._settings.max_connection_attempts,
        )
        async for delay in backoff:
            attempt += 1
            _log("db_connect_attempt", attempt=attempt, delay=delay)
            try:
                db_user, db_password = self._settings.database_user, self._settings.database_password
                if db_user and db_password:
                    uri = f"mongodb://{db_user}:{db_password}@{self._settings.database_host}:{self._settings.database_port}"
                else:
                    uri = f"mongodb://{self._settings.database_host}:{self._settings.database_port}"
                self._client = AsyncIOMotorClient(
                    uri,
                    serverSelectionTimeoutMS=self._settings.database_connection_timeout_ms,
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
        """Return True if the database responds to ping; False if not connected or any error."""
        if not self._client:
            return False
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            res = self._client.close()
            if inspect.isawaitable(res):
                await res
            self._client = None
        self._state = ConnectionState.DISCONNECTED
