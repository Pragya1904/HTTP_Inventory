"""Database connection factory: selects implementation from config. Only place that imports concrete connections."""
from __future__ import annotations

from api.app.config.settings import Settings
from api.app.ports.database_connection import DatabaseConnection
from api.app.ports.metadata_repository import MetadataRepository
from api.app.infrastructure.persistence.mongo.mongo_connection import MongoConnection
from api.app.infrastructure.persistence.mongo.mongo_metadata_repository import MongoMetadataRepository


def create_database_connection(settings: Settings) -> DatabaseConnection:
    backend = settings.database_backend.strip().lower()

    if backend in ("mongo",):
        return MongoConnection(settings)

    raise ValueError(f"Unsupported database backend: {backend}")


def create_metadata_repository(settings: Settings, database: DatabaseConnection) -> MetadataRepository:
    """Build MetadataRepository for the current database backend. Repository shares the same connection as readiness."""
    backend = settings.database_backend.strip().lower()

    if backend == "mongo":
        if not isinstance(database, MongoConnection):
            raise ValueError(
                f"Metadata repository for backend 'mongo' requires MongoConnection, got {type(database).__name__}"
            )
        return MongoMetadataRepository(database)

    raise ValueError(f"Unsupported database backend for metadata repository: {backend}")
