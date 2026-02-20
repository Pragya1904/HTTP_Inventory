from fastapi.testclient import TestClient

from api.app.infrastructure.messaging.inmemory.in_memory_publisher import InMemoryPublisher
from api.app.infrastructure.messaging.rabbitmq.constants import PublisherState
from tests.conftest import FakeDatabase, FakeMetadataRepository, FakePublisher


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


def test_post_metadata_inmemory_stores_message():
    """When app uses InMemoryPublisher (e.g. publisher_backend=inmemory), POST /metadata stores message in .messages."""
    from fastapi import FastAPI

    from api.app.routers.health import health_router
    from api.app.routers.metadata import metadata_router

    from tests.conftest import FakeDatabase

    app = FastAPI()
    publisher = InMemoryPublisher()
    app.state.publisher = publisher
    app.state.database = FakeDatabase()
    app.include_router(health_router)
    app.include_router(metadata_router)

    client = TestClient(app)
    r = client.post("/metadata", json={"url": "https://example.com/foo"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "QUEUED"
    assert body["url"] == "https://example.com/foo"
    assert body["request_id"]

    assert len(publisher.messages) == 1
    assert publisher.messages[0]["url"] == "https://example.com/foo"
    assert publisher.messages[0]["request_id"] == body["request_id"]
    assert "requested_at" in publisher.messages[0]


def test_post_metadata_invalid_url_returns_422(test_app):
    client = TestClient(test_app)
    r = client.post("/metadata", json={"url": "not-a-url"})
    assert r.status_code == 422


def test_get_metadata_missing_url_400(test_app):
    client = TestClient(test_app)
    r = client.get("/metadata")
    assert r.status_code == 400


def test_get_metadata_invalid_url_400(test_app):
    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": "not-a-url"})
    assert r.status_code == 400


def test_get_metadata_not_found_enqueues_and_returns_202(test_app):
    publisher = FakePublisher(state=PublisherState.READY)
    test_app.state.publisher = publisher
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={})

    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": "https://example.com"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "QUEUED"
    assert body["url"] == "https://example.com"
    assert body["request_id"]
    assert len(publisher.published) == 1
    assert publisher.published[0]["url"] == body["url"]
    assert publisher.published[0]["request_id"] == body["request_id"]


def test_get_metadata_found_completed_returns_200_with_metadata(test_app):
    url = "https://example.com"
    record = {
        "url": url,
        "status": "COMPLETED",
        "metadata": {
            "headers": {"content-type": "text/html"},
            "cookies": {"a": "b"},
            "page_source": "<html/>",
            "status_code": 200,
            "final_url": url,
            "additional_details": {"x": 1},
        },
        "processing": {"last_request_id": "req-1", "attempt_number": 0, "error_msg": None},
        "additional_details": None,
    }
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={url: record})

    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": url})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert body["url"] == url
    assert body["metadata"]["headers"]["content-type"] == "text/html"
    assert body["metadata"]["cookies"]["a"] == "b"
    assert body["metadata"]["page_source"] == "<html/>"
    assert body["metadata"]["status_code"] == 200
    assert body["metadata"]["additional_details"]["x"] == 1


def test_get_metadata_completed_with_truncated_additional_details_returns_truncation_info(test_app):
    """When stored record has additional_details with truncated flag and original_length, GET returns them."""
    url = "https://example.com"
    record = {
        "url": url,
        "status": "COMPLETED",
        "metadata": {
            "headers": {},
            "cookies": {},
            "page_source": "<html>" + "x" * 200,
            "status_code": 200,
            "final_url": url,
            "additional_details": {"truncated": True, "original_length": 5000},
        },
        "processing": {"last_request_id": "req-1", "attempt_number": 0, "error_msg": None},
        "additional_details": None,
    }
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={url: record})

    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": url})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert body["metadata"]["additional_details"] is not None
    assert body["metadata"]["additional_details"]["truncated"] is True
    assert body["metadata"]["additional_details"]["original_length"] == 5000


def test_get_metadata_found_in_progress_returns_202_without_enqueue(test_app):
    url = "https://example.com"
    record = {
        "url": url,
        "status": "IN_PROGRESS",
        "metadata": {},
        "processing": {"last_request_id": "req-2"},
    }
    publisher = FakePublisher(state=PublisherState.READY)
    test_app.state.publisher = publisher
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={url: record})

    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": url})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["url"] == url
    assert body["request_id"] == "req-2"
    assert publisher.published == []


def test_get_metadata_found_pending_returns_202_without_enqueue(test_app):
    url = "https://example.com"
    record = {"url": url, "status": "PENDING", "processing": {"last_request_id": "req-p"}}
    publisher = FakePublisher(state=PublisherState.READY)
    test_app.state.publisher = publisher
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={url: record})

    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": url})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["request_id"] == "req-p"
    assert publisher.published == []


def test_get_metadata_found_failed_retryable_returns_202_without_enqueue(test_app):
    url = "https://example.com"
    record = {"url": url, "status": "FAILED_RETRYABLE", "processing": {"last_request_id": "req-r"}}
    publisher = FakePublisher(state=PublisherState.READY)
    test_app.state.publisher = publisher
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={url: record})

    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": url})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["request_id"] == "req-r"
    assert publisher.published == []


def test_get_metadata_found_queued_returns_202_without_enqueue(test_app):
    url = "https://example.com"
    record = {"url": url, "status": "QUEUED", "processing": {"last_request_id": "req-q"}}
    publisher = FakePublisher(state=PublisherState.READY)
    test_app.state.publisher = publisher
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={url: record})

    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": url})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["request_id"] == "req-q"
    assert publisher.published == []


def test_get_metadata_unknown_status_enqueues_again(test_app):
    url = "https://example.com"
    record = {"url": url, "status": "UNKNOWN", "processing": {"last_request_id": "req-u"}}
    publisher = FakePublisher(state=PublisherState.READY)
    test_app.state.publisher = publisher
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={url: record})

    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": url})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "QUEUED"
    assert body["url"] == url
    assert len(publisher.published) == 1


def test_get_metadata_found_failed_permanent_returns_200_with_failure_metadata(test_app):
    url = "https://example.com"
    record = {
        "url": url,
        "status": "FAILED_PERMANENT",
        "metadata": {},
        "processing": {"last_request_id": "req-f", "attempt_number": 3, "error_msg": "boom"},
    }
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={url: record})
    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": url})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILED_PERMANENT"
    assert body["url"] == url
    assert "request_id" not in body
    assert body["error_msg"] == "boom"
    assert body["attempt_number"] == 3


def test_get_metadata_not_found_publisher_failure_returns_503(test_app):
    test_app.state.publisher = None
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={})
    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": "https://example.com"})
    assert r.status_code == 503


def test_get_metadata_db_down_when_repo_missing_returns_503(test_app):
    test_app.state.metadata_repository = None
    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": "https://example.com"})
    assert r.status_code == 503


def test_get_metadata_db_down_when_repo_raises_returns_503(test_app):
    """When repo.get_by_url raises (e.g. DB down), API returns 503."""
    test_app.state.metadata_repository = FakeMetadataRepository(raise_on_get=RuntimeError("db_down"))
    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": "https://example.com"})
    assert r.status_code == 503


def test_get_metadata_not_found_when_publisher_not_ready_returns_503(test_app):
    test_app.state.publisher = FakePublisher(state=PublisherState.RECONNECTING)
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={})
    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": "https://example.com"})
    assert r.status_code == 503


def test_get_metadata_not_found_when_publish_raises_returns_503(test_app):
    test_app.state.publisher = FakePublisher(
        state=PublisherState.READY,
        raise_on_publish=RuntimeError("connection_lost"),
    )
    test_app.state.metadata_repository = FakeMetadataRepository(records_by_url={})
    client = TestClient(test_app)
    r = client.get("/metadata", params={"url": "https://example.com"})
    assert r.status_code == 503


def test_sequence_get_new_url_then_get_in_progress_does_not_reenqueue(test_app):
    url = "https://example.com"
    publisher = FakePublisher(state=PublisherState.READY)
    repo = FakeMetadataRepository(records_by_url={})
    test_app.state.publisher = publisher
    test_app.state.metadata_repository = repo

    client = TestClient(test_app)

    r1 = client.get("/metadata", params={"url": url})
    assert r1.status_code == 202
    body1 = r1.json()
    assert body1["status"] == "QUEUED"
    assert len(publisher.published) == 1

    # simulate worker created a record after consuming
    repo.set_record(url, {"url": url, "status": "IN_PROGRESS", "processing": {"last_request_id": body1["request_id"]}})

    r2 = client.get("/metadata", params={"url": url})
    assert r2.status_code == 202
    body2 = r2.json()
    assert body2["status"] == "IN_PROGRESS"
    assert body2["request_id"] == body1["request_id"]
    assert len(publisher.published) == 1  # no second publish


def test_sequence_post_url_then_get_completed_returns_200_without_reenqueue(test_app):
    url = "https://example.com"
    publisher = FakePublisher(state=PublisherState.READY)
    repo = FakeMetadataRepository(records_by_url={})
    test_app.state.publisher = publisher
    test_app.state.metadata_repository = repo
    client = TestClient(test_app)

    r_post = client.post("/metadata", json={"url": url})
    assert r_post.status_code == 202
    req_id = r_post.json()["request_id"]
    assert len(publisher.published) == 1

    repo.set_record(
        url,
        {
            "url": url,
            "status": "COMPLETED",
            "metadata": {
                "headers": {},
                "cookies": {},
                "page_source": "<html/>",
                "status_code": 200,
                "final_url": url,
            },
            "processing": {"last_request_id": req_id},
        },
    )

    r_get = client.get("/metadata", params={"url": url})
    assert r_get.status_code == 200
    body = r_get.json()
    assert body["status"] == "COMPLETED"
    assert "request_id" not in body
    assert len(publisher.published) == 1  # no second publish

