# Testing Guidelines -- HTTP Inventory

---

## Executive Summary

**For reviewers (tech and non-tech):** This document describes how the HTTP Inventory system is tested. The suite has **66 test cases** across 10 modules, covering API behavior, worker processing, database persistence, and failure scenarios. All tests run in Docker; no local Python setup is required. (One failure-path test is skipped when services are running.)

**To verify everything works:** Run `docker compose up -d` (start services), then `docker compose run --rm tests pytest -v --tb=short`. All tests should pass. Unit tests run without external services; integration tests require RabbitMQ and MongoDB.

---

## 1. Test Coverage Overview

| Module | Tests | Type | What Gets Tested |
|--------|-------|------|------------------|
| `test_metadata_endpoints.py` | 22 | Unit | POST/GET /metadata: success, 503, 422, 400, all status flows, sequences |
| `test_health_endpoints.py` | 5 | Unit | /health/live, /health/ready (200/503 based on publisher and DB) |
| `test_publisher_unit.py` | 4 | Unit | RabbitMQ publisher: connect, publish rejection, failure recovery, close |
| `test_worker_processing_service_retry_failure.py` | 6 | Unit | Retry logic, permanent failure, malformed messages |
| `test_worker_processing_service_truncation.py` | 5 | Unit | Page source truncation, helper behavior |
| `test_compose_api.py` | 3 | Integration | API probes, POST enqueue to RabbitMQ, failure when deps down |
| `test_worker_integration.py` | 1 | Integration | Worker consume→fetch→persist; truncation covered by unit tests + metadata_endpoints |
| `test_metadata_fetcher_integration.py` | 15 | Integration | Real HTTP: 2xx, 4xx/5xx, redirects, cookies, non-HTML (needs internet) |
| `test_worker_mongo_repository_integration.py` | 4 | Integration | Mongo ping, indexes, write/read, fetch by created_at |
| `test_e2e_metadata_post_get.py` | 1 | Integration | Full pipeline: POST + GET for curated URLs, step-by-step logs |

**Markers:** `integration` = needs RabbitMQ/Mongo; `failure_path` = expects 503 when deps are stopped.

---

## 2. Test Strategy

### Unit Tests

Unit tests run without external dependencies. They use fake/mock implementations of ports (publishers, repositories, database connections) to test routing logic, service behavior, and state transitions in isolation.

**Markers:** Tests not marked `integration` or `failure_path`.

### Integration Tests

Integration tests require running infrastructure (RabbitMQ, MongoDB). They run inside the `tests` Docker container via `docker compose run`. Some (metadata fetcher) require internet access.

**Marker:** `@pytest.mark.integration`.

### Containerized Test Environment

All tests run inside a Docker container defined by `Dockerfile.tests`. The container installs both API and dev dependencies, sets `PYTHONPATH=/workspace`, and runs pytest against the `tests/` directory.

```bash
docker compose run --rm tests pytest -v --tb=short
```

### In-Memory Publisher Option

The API supports `PUBLISHER_BACKEND=inmemory` for testing without RabbitMQ. The `InMemoryPublisher` stores messages in a list and is always ready. Unit tests cover this path; no consumer exists for this publisher.

---

## 3. API Testing

### POST /metadata

| Scenario | Status | Coverage |
|----------|--------|----------|
| Valid URL, publisher ready | 202 QUEUED | Unit + integration |
| Publisher missing (startup failure) | 503 | Unit |
| Publisher not ready (RECONNECTING) | 503 | Unit |
| Invalid URL (malformed) | 422 | Unit |
| InMemoryPublisher stores in .messages | 202 | Unit |

### GET /metadata

| Scenario | Status | Coverage |
|----------|--------|----------|
| Missing `url` query param | 400 | Unit |
| Invalid `url` format | 400 | Unit |
| Record not found → enqueue and return | 202 QUEUED | Unit + E2E |
| Record COMPLETED → return full metadata | 200 | Unit + E2E |
| Record COMPLETED with truncation → return `additional_details` | 200 | Unit + integration |
| Record PENDING / IN_PROGRESS / FAILED_RETRYABLE / QUEUED → no re-enqueue | 202 IN_PROGRESS | Unit |
| Record unknown status → re-enqueue | 202 | Unit |
| Record FAILED_PERMANENT → return failure metadata | 200 | Unit |
| Not found + publisher failure / not ready / publish raises | 503 | Unit |
| Not found + DB down (repo missing or raises) | 503 | Unit |

### Sequence Tests

- **GET new URL → GET again while in progress:** Does not re-enqueue.
- **POST URL → wait for completion → GET:** Returns 200 without re-enqueue.

---

## 4. Worker Testing

### Message Consumption

Worker connects to RabbitMQ, consumes a message, fetches metadata via HTTP, and persists to MongoDB. Integration tests verify the full flow and document schema.

### Large Response Truncation (Integration)

When a URL returns a response exceeding `MAX_PAGE_SOURCE_LENGTH`, the worker truncates `page_source`, stores `additional_details` with `truncated: true` and `original_length`, and GET /metadata returns this info.

### Retry Logic (Unit)

- **Retryable error** (`MetadataFetchError`, `MetadataFetchTimeoutError`): `mark_retryable_failure`, nack with requeue.
- **Retries exhausted:** `mark_permanent_failure`, ack.
- **Non-retryable error:** Immediate permanent failure, ack.
- **Malformed message** (missing or empty `url`): Raises `ValueError`.

### Mongo Persistence

Integration tests verify:

- Mongo connection and ping.
- Index creation: `uq_metadata_url`, `idx_metadata_created_at`.
- Write/read roundtrip.
- `fetch_records_created_in_past_24_hours`.

Document schema: `url`, `status`, `metadata` (headers, cookies, page_source, status_code, final_url, additional_details), `processing`, `created_at`, `updated_at`.

---

## 5. Metadata Fetcher (Integration, Requires Internet)

| Scenario | Coverage |
|----------|----------|
| Success URLs (2xx): Wikipedia, Python.org, httpbin, etc. | Parametrized (8 URLs) |
| Redirects: final_url reflects resolution, headers present | 1 test |
| Non-HTML content (JSON, XML): stored in page_source | 1 test |
| Error status (404, 500): raises `MetadataFetchError` | Parametrized (2 URLs) |
| Cookie-set endpoints: returns result with cookies dict | Parametrized (2 URLs) |
| Random URL from full TEST_URLS list | 1 test |

---

## 6. Failure Simulation

| Scenario | How to Test |
|----------|-------------|
| Broker (RabbitMQ) unavailable | Stop rabbitmq, run `pytest -m failure_path --no-deps` |
| Mongo unavailable | Stop mongo; readiness returns 503 |
| HTTP timeout | Configurable via `FETCH_CONNECT_TIMEOUT_SECONDS`, `FETCH_READ_TIMEOUT_SECONDS`; raises retryable error |
| Non-200 HTTP (4xx/5xx) | Metadata fetcher integration; retryable error flow |
| Large page source | Truncation unit + worker integration |

---

## 7. Deterministic Testing Approach

- **Idempotent queue declaration:** Publisher and consumer declare the queue with identical args; RabbitMQ no-op if already exists.
- **Prefetch = 1:** One message at a time; prevents out-of-order processing and simplifies retry logic.
- **Locks:** Worker and publisher use `asyncio.Lock` for in-flight operations and graceful shutdown.

---

## 8. Local Test Execution

### Quick Reference (Docker Commands)

| # | Purpose | Command |
|---|---------|---------|
| 1 | **All tests** | `docker compose run --rm tests pytest -v --tb=short` |
| 2 | Unit tests only | `docker compose run --rm tests pytest -m "not integration" -v --tb=short` |
| 3 | Integration tests only | `docker compose run --rm tests pytest -m integration -v --tb=short` |
| 4 | Failure path (stop deps first) | `docker compose stop rabbitmq mongo` then `docker compose run --rm --no-deps tests pytest -m failure_path -v --tb=short` |
| 5 | API integration | `docker compose run --rm tests pytest tests/integration/test_compose_api.py -m integration -v --tb=short` |
| 6 | Worker integration | `docker compose run --rm tests pytest tests/integration/test_worker_integration.py -m integration -v --tb=short` |
| 7 | Metadata fetcher (needs internet) | `docker compose run --rm tests pytest tests/integration/test_metadata_fetcher_integration.py -m integration -v --tb=short` |
| 8 | Mongo integration | `docker compose run --rm tests pytest tests/integration/test_worker_mongo_repository_integration.py -m integration -v --tb=short` |
| 9 | E2E POST + GET (use -s for logs) | `docker compose run --rm tests pytest tests/integration/test_e2e_metadata_post_get.py -m integration -v -s --tb=short` |
| 10 | Queue test (stop worker first) | `.\scripts\run_integration_queue_test.ps1` (Windows) or `./scripts/run_integration_queue_test.sh` (Linux/macOS) |

**Note for `test_post_metadata_enqueues_message`:** Worker must be stopped so the message remains in the queue for verification. Use the script or: `docker compose stop worker` → run test → `docker compose start worker`.

### Docker Test Container

```yaml
tests:
  build:
    context: .
    dockerfile: Dockerfile.tests
  depends_on:
    - api
    - rabbitmq
    - mongo
  env_file:
    - .env
```

### Pytest Configuration

```ini
[pytest]
addopts = -q
testpaths = tests
markers =
  integration: tests that require docker compose and real services
  failure_path: tests that expect 503 when rabbitmq/mongo are down
asyncio_mode = auto
```

### Flag Reference

| Flag | Scope | Description |
|------|-------|-------------|
| `--rm` | Docker | Remove container after exit |
| `-m` | pytest | Run tests matching marker |
| `-v` | pytest | Verbose output |
| `--tb=short` | pytest | Short traceback on failure |
| `-s` | pytest | Don't capture stdout (E2E step logs) |
| `--no-deps` | Docker | Don't start linked services (failure path) |

---

## 9. Verification Checklist (For Reviewers)

1. **Prerequisites:** Docker and Docker Compose installed.
2. **Start services:** `docker compose up -d` (api, rabbitmq, mongo, worker).
3. **Run all tests:** `docker compose run --rm tests pytest -v --tb=short`.
4. **Expected:** All tests pass. Integration tests may take 1–2 minutes; metadata fetcher needs internet.
5. **Failure path (optional):** `docker compose stop rabbitmq mongo` → `docker compose run --rm --no-deps tests pytest -m failure_path -v` → `docker compose start rabbitmq mongo`.
6. **E2E with logs:** `docker compose run --rm tests pytest tests/integration/test_e2e_metadata_post_get.py -m integration -v -s` to see step-by-step output.
