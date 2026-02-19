from fastapi.testclient import TestClient

from api.publisher.constants import PublisherState
from tests.conftest import FakeDatabase, FakePublisher


def test_live_is_always_200(test_app):
    client = TestClient(test_app)
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_503_when_components_missing():
    from fastapi import FastAPI
    from api.routers.health import router as health_router

    app = FastAPI()
    app.include_router(health_router)
    client = TestClient(app)
    r = client.get("/health/ready")
    assert r.status_code == 503


def test_ready_503_when_publisher_not_ready(test_app):
    test_app.state.publisher = FakePublisher(state=PublisherState.RECONNECTING)
    test_app.state.database = FakeDatabase(ping_ok=True)
    client = TestClient(test_app)
    r = client.get("/health/ready")
    assert r.status_code == 503


def test_ready_503_when_db_ping_fails(test_app):
    test_app.state.publisher = FakePublisher(state=PublisherState.READY)
    test_app.state.database = FakeDatabase(ping_ok=False)
    client = TestClient(test_app)
    r = client.get("/health/ready")
    assert r.status_code == 503


def test_ready_200_when_ready(test_app):
    test_app.state.publisher = FakePublisher(state=PublisherState.READY)
    test_app.state.database = FakeDatabase(ping_ok=True)
    client = TestClient(test_app)
    r = client.get("/health/ready")
    assert r.status_code == 200

