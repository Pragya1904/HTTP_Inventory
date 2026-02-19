from fastapi.testclient import TestClient

from api.publisher.constants import PublisherState
from tests.conftest import FakeDatabase, FakePublisher


def test_post_metadata_503_when_publisher_missing(test_app):
    test_app.state.publisher = None
    client = TestClient(test_app)
    r = client.post("/metadata", json={"url": "https://example.com"})
    assert r.status_code == 503


def test_post_metadata_503_when_publisher_not_ready(test_app):
    test_app.state.publisher = FakePublisher(state=PublisherState.RECONNECTING)
    test_app.state.database = FakeDatabase(ping_ok=True)
    client = TestClient(test_app)
    r = client.post("/metadata", json={"url": "https://example.com"})
    assert r.status_code == 503


def test_post_metadata_202_and_enqueues_message(test_app):
    publisher = FakePublisher(state=PublisherState.READY)
    test_app.state.publisher = publisher
    client = TestClient(test_app)
    r = client.post("/metadata", json={"url": "https://example.com"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "QUEUED"
    assert body["url"] 
    assert isinstance(body["request_id"], str) and body["request_id"]
    assert len(publisher.published) == 1
    assert publisher.published[0]["url"] == body["url"]
    assert publisher.published[0]["request_id"] == body["request_id"]


def test_post_metadata_invalid_url_returns_422(test_app):
    client = TestClient(test_app)
    r = client.post("/metadata", json={"url": "not-a-url"})
    assert r.status_code == 422


def test_get_metadata_placeholder_202(test_app):
    client = TestClient(test_app)
    r = client.get("/metadata")
    assert r.status_code == 202
    assert r.json()["message"]

