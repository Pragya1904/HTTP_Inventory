from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI

from api.publisher.constants import PublisherState
from api.routers.health import router as health_router
from api.routers.metadata import metadata_router


class FakePublisher:
    def __init__(self, state: PublisherState = PublisherState.READY) -> None:
        self.state = state
        self.published: list[dict[str, Any]] = []

    async def publish(self, message: dict[str, Any]) -> None:
        self.published.append(message)


class FakeDatabase:
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

