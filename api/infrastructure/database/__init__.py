from typing import Any

try:
    from api.infrastructure.database.base import DatabaseConnection
    from api.infrastructure.database.mongo_connection import MongoConnection
except ImportError:
    from infrastructure.database.base import DatabaseConnection
    from infrastructure.database.mongo_connection import MongoConnection


def get_database_connection(settings: Any) -> DatabaseConnection:
    return MongoConnection(settings)

