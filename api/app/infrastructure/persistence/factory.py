"""Database connection factory: selects implementation from config. Only place that imports concrete connections."""
from __future__ import annotations

from api.app.config.settings import Settings
from api.app.ports.database_connection import DatabaseConnection
from api.app.infrastructure.persistence.mongo.mongo_connection import MongoConnection

def create_database_connection(settings: Settings) -> DatabaseConnection:
    backend = settings.database_backend.strip().lower()

    if backend == "mongo":
        return MongoConnection(settings)

    raise ValueError(f"Unsupported database backend: {backend}")
