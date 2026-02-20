from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI

from api.app.infrastructure.messaging.rabbitmq.constants import PublisherState
from api.app.routers.health import health_router
from api.app.routers.metadata import metadata_router


class FakePublisher:
    """Implements MessagePublisher for tests; routers depend only on .ready and .publish()."""

    def __init__(
        self,
        state: PublisherState = PublisherState.READY,
        *,
        raise_on_publish: Exception | None = None,
    ) -> None:
        self.state = state
        self.published: list[dict[str, Any]] = []
        self._raise_on_publish = raise_on_publish

    @property
    def ready(self) -> bool:
        return self.state == PublisherState.READY

    async def publish(self, message: dict[str, Any]) -> None:
        if self._raise_on_publish is not None:
            raise self._raise_on_publish
        self.published.append(message)


class FakeDatabase:
    """Implements DatabaseConnection for tests. Full protocol so connect/close/ready won't break callers."""

    def __init__(self, ping_ok: bool = True) -> None:
        self._ping_ok = ping_ok
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def connect(self) -> None:
        self._ready = True

    async def ping(self) -> bool:
        return self._ping_ok

    async def close(self) -> None:
        self._ready = False


class FakeMetadataRepository:
    """Implements API MetadataRepository for tests; routers depend only on .get_by_url()."""

    def __init__(
        self,
        records_by_url: dict[str, dict[str, Any]] | None = None,
        *,
        raise_on_get: Exception | None = None,
    ) -> None:
        self._records_by_url = records_by_url or {}
        self._raise_on_get = raise_on_get

    async def get_by_url(self, url: str) -> dict[str, Any] | None:
        if self._raise_on_get is not None:
            raise self._raise_on_get
        return self._records_by_url.get(url)

    def set_record(self, url: str, record: dict[str, Any]) -> None:
        self._records_by_url[url] = record

    def delete_record(self, url: str) -> None:
        self._records_by_url.pop(url, None)


@pytest.fixture()
def test_app() -> FastAPI:
    app = FastAPI()
    app.state.publisher = FakePublisher()
    app.state.database = FakeDatabase()
    app.state.metadata_repository = FakeMetadataRepository()
    app.include_router(health_router)
    app.include_router(metadata_router)
    return app

