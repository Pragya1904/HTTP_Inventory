"""
Composition root: single place where concrete implementations are wired.

Builds settings, publisher, and database from config; provides connect/close
lifecycle. Used by lifespan to populate app.state. No DI container library —
explicit wiring only. Uses app config and infrastructure factories so backend
selection (e.g. publisher_backend=inmemory) is driven by settings.
"""

from api.app.config.settings import Settings
from api.app.ports.database_connection import DatabaseConnection
from api.app.ports.message_publisher import MessagePublisher
from api.app.infrastructure.messaging.factory import create_publisher
from api.app.infrastructure.persistence.factory import create_database_connection


class AppDependencies:
    """Holds wired dependencies and their lifecycle. Built only in composition root."""

    def __init__(
        self,
        *,
        settings: Settings,
        publisher: MessagePublisher,
        database: DatabaseConnection,
    ) -> None:
        self._settings = settings
        self._publisher = publisher
        self._database = database
        self._publisher_connected = False
        self._database_connected = False

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def publisher(self) -> MessagePublisher:
        return self._publisher

    @property
    def database(self) -> DatabaseConnection:
        return self._database

    async def connect(self) -> None:
        await self._publisher.connect()
        self._publisher_connected = True
        try:
            await self._database.connect()
            self._database_connected = True
        except Exception:
            await self._publisher.close()
            self._publisher_connected = False
            raise

    async def close(self) -> None:
        if self._publisher_connected and self._publisher is not None:
            await self._publisher.close()
            self._publisher_connected = False
        if self._database_connected and self._database is not None:
            await self._database.close()
            self._database_connected = False


def create_app_dependencies(settings: Settings | None = None) -> AppDependencies:
    """
    Composition root: build all app dependencies in one place.
    Caller owns lifecycle (connect/close). Publisher and database backends
    are selected from settings (publisher_backend, database_backend).
    """
    _settings = settings or Settings()
    return AppDependencies(
        settings=_settings,
        publisher=create_publisher(_settings),
        database=create_database_connection(_settings),
    )
