from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI

from api.app.infrastructure.messaging.rabbitmq.constants import PublisherState
from api.app.routers.health import health_router
from api.app.routers.metadata import metadata_router


class FakePublisher:
    """Implements MessagePublisher for tests; routers depend only on .ready and .publish()."""

    def __init__(self, state: PublisherState = PublisherState.READY) -> None:
        self.state = state
        self.published: list[dict[str, Any]] = []

    @property
    def ready(self) -> bool:
        return self.state == PublisherState.READY

    async def publish(self, message: dict[str, Any]) -> None:
        self.published.append(message)


class FakeDatabase:
    """Implements DatabaseConnection for tests; routers depend only on .ping()."""
    def __init__(self, ping_ok: bool = True) -> None:
        self._ping_ok = ping_ok

    async def ping(self) -> bool:
        return self._ping_ok


@pytest.fixture()
def test_app() -> FastAPI:
    app = FastAPI()
    app.state.publisher = FakePublisher()
    app.state.database = FakeDatabase()
    app.include_router(health_router)
    app.include_router(metadata_router)
    return app

