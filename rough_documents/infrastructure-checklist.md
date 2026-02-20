# Infrastructure checklist — Worker + API

Execution blueprint status, now including Worker Phase 1 (processing + metadata fetch + DB persistence).

## Phase Update

- Worker processing + metadata fetch + Mongo repository integration is now in progress.

---

## 1. API — RabbitMQ Publisher

| Item | Status | Notes |
|------|--------|--------|
| Publisher states (DISCONNECTED → READY, RECONNECTING, CLOSING, CLOSED) | ✅ | `PublisherState` in `publisher/constants.py`; `RabbitMQPublisher` implements `MessagePublisher` |
| Startup: CONNECTING with exponential backoff (1s, 30s max, 2x, 10 attempts) | ✅ | Uses settings `initial_backoff_seconds`, `max_backoff_seconds`, `max_connection_attempts` |
| Log `event=rmq_connect_attempt` (attempt, delay) | ✅ | |
| Fail fast after max attempts | ✅ | Raises after `max_connection_attempts` |
| CONNECTED → CHANNEL_OPEN → CONFIRM_ENABLED → QUEUE_DECLARED → READY | ✅ | `_open_channel_and_declare()` |
| Queue: durable, x-max-length=1000, x-overflow=reject-publish | ✅ | `declare_queue(..., arguments={...})` |
| Publish: async lock, delivery_mode=2, await confirm | ✅ | `_lock`, `DeliveryMode.PERSISTENT`, `publish(..., timeout=10)` |
| 503 if not READY; log `event=publish_rejected` reason=publisher_not_ready | ✅ | Router + publisher |
| On ACK: 202, log `event=publish_success` request_id, url, latency_ms | ✅ | |
| On NACK/overflow: 503, log `event=publish_failed` reason=queue_rejected | ✅ | Router logs publish_failed; 503 on publish error |
| On connection lost: RECONNECTING, 503, log reason=connection_lost | ✅ | Publisher sets RECONNECTING, raises; router 503 |
| Reconnect loop with backoff; log rmq_reconnect_attempt, rmq_reconnected | ✅ | `_reconnect_loop()` |
| Graceful shutdown: CLOSING → wait in-flight → close channel → close connection → CLOSED | ✅ | `close()` uses lock then closes channel/connection |
| Log `event=publisher_shutdown` | ✅ | |

---

## 2. API — Health & DB

| Item | Status | Notes |
|------|--------|--------|
| `/health/live` always 200 | ✅ | Returns `{"status": "ok"}` |
| `/health/ready` 200 only if Publisher READY + DB ping OK | ✅ | Uses `database.ping()` (app.state.database); provider-agnostic |
| DB connect on startup, exponential backoff, fail fast | ✅ | `MongoConnection.connect()` in `infrastructure/database/mongo_connection.py` |
| DB states: DISCONNECTED, CONNECTING, CONNECTED | ✅ | `ConnectionState` in `infrastructure/database/constants.py` (provider-agnostic) |
| Log readiness failures | ✅ | `event=readiness_failed`, reason=... |

---

## 3. API — Contracts

| Item | Status | Notes |
|------|--------|--------|
| POST /metadata: body `{ "url": "..." }`, respond 202/503/400/500 | ✅ | 202/503 implemented |
| Response 202: `{ "status": "QUEUED", "url", "request_id" }` | ✅ | `MetadataPostResponse` |
| empty / Invalid URL → 400 | ⬜ | Pydantic `HttpUrl` yields 422 for invalid URL; map to 400 if required |
| publisher not ready / queue overflow / broker down → 503 | ✅ | |
| unexpected exception → 500 | ⬜ | Route currently returns 503 on any exception; add 500 for unhandled if desired |
| GET /metadata?url=... reads DB; enqueues on miss; never blocks | ✅ | 200 COMPLETED/FAILED_PERMANENT; 202 IN_PROGRESS/QUEUED; 503 on publish failure |

---

## 4. Worker

| Item | Status | Notes |
|------|--------|--------|
| Mongo connect with backoff | ✅ | `worker/app/main.py` uses exponential backoff + configurable timeout |
| RabbitMQ connect with backoff | ✅ | `worker/app/main.py` uses exponential backoff |
| Declare queue (idempotent), QoS prefetch=1 | ✅ | Queue declare + `set_qos(prefetch_count=settings.prefetch_count)` |
| Start consuming, manual ACK/NACK, process URL payload | ✅ | `ProcessingService.process_message()` controls ACK/NACK after DB writes |
| Log `event=worker_started` | ✅ | `worker/app/main.py` |
| SIGTERM: stop consuming, wait in-flight, close channel, close Mongo, exit | ✅ | `queue.cancel(...)`, processing lock drain, then close resources |
| Metadata fetcher (headers/cookies/page source with timeouts) | ✅ | `worker/app/services/metadata_fetcher.py` |
| Mongo repository (upsert/status transitions/retry persistence) | ✅ | `worker/app/repository/mongo_repository.py` |
| Processing orchestrator (retry policy + delivery guarantees) | ✅ | `worker/app/services/processing_service.py` |

---

## 5. Logging

| Item | Status | Notes |
|------|--------|--------|
| Logs include timestamp, service_name, event | ✅ | `logger.bind(service_name=..., event=...)`; loguru adds timestamp |
| Where applicable: request_id, url | ✅ | publish_success, publish_failed |
| Publisher: latency_ms on success | ✅ | |

---

## 6. Verification (ready for testing)

| Item | Status | Notes |
|------|--------|--------|
| `docker compose up` — API starts | ⬜ | Manual: ensure .env has DATABASE_* and BROKER_* |
| http://localhost:6577/docs loads | ⬜ | Manual |
| POST /metadata → 202, message in RabbitMQ UI | ⬜ | Manual |
| Worker logs show message received, URL logged | ⬜ | After worker enabled |
| Stop RabbitMQ → POST returns 503; restart → ready 200 again | ⬜ | Manual |
| Graceful shutdown (SIGTERM) — no crashes | ⬜ | Manual |

---

## Summary

**Scope: API enqueuing + API GET read-through + Worker Phase 1 processing integration.**

- **Done (code-level):** API enqueuing and GET read-through are implemented, and Worker section 4 is implemented with fetcher, processing service, Mongo repository, manual ACK/NACK flow, and graceful shutdown path.
- **Optional (API contracts):** Invalid URL → 400 (currently 422 via Pydantic); unexpected exception → 500 (currently 503). Can add later if contract demands it.
- **Pending verification:** Section 6 manual runtime checks in Docker environment.

*Update status: ⬜ → ✅ when done and verified.*

---

## Milestone: Worker Metadata Persistence

Status: Completed

- [x] Mongo schema defined (includes `processing.last_request_id` by consent)
- [x] Unique index on URL
- [x] Index on created_at
- [x] Atomic upsert logic implemented
- [x] Retryable failure handling implemented
- [x] Permanent failure handling implemented
- [x] Structured persistence logs added
- [x] Final state verification log added
