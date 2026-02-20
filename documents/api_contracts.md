# API Contract — HTTP Inventory

Base URL:

```
http://localhost:6577
```

---

# Overview

The HTTP Inventory service provides asynchronous metadata ingestion and retrieval for external URLs.

Core principles:

* Asynchronous processing (via RabbitMQ)
* Immediate API responsiveness
* Deterministic state transitions
* At-least-once delivery semantics
* MongoDB as single source of truth

---

# POST `/metadata`

Enqueue a URL for asynchronous metadata processing.

---

## Request

| Field  | Value                            |
| ------ | -------------------------------- |
| Method | POST                             |
| Path   | `/metadata`                      |
| Header | `Content-Type: application/json` |
| Body   | JSON                             |

---

## Request Body Schema

```json
{
  "url": "https://example.com"
}
```

### Validation

* Must be a valid HTTP or HTTPS URL.
* Validated via Pydantic `HttpUrl`.
* Scheme must be `http` or `https`.

---

## Example cURL

```bash
curl -X POST http://localhost:6577/metadata \
  -H "Content-Type: application/json" \
  -d '{
        "url": "https://example.com"
      }'
```

---

## Success Response — 202 Accepted

The URL has been successfully enqueued.

```json
{
  "status": "QUEUED",
  "url": "https://example.com/",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| Field        | Type   | Description                         |
| ------------ | ------ | ----------------------------------- |
| `status`     | string | Always `"QUEUED"`                   |
| `url`        | string | Normalized URL                      |
| `request_id` | string | UUID v4 identifying enqueue request |

---

## Failure Responses

### 422 — Invalid URL

```json
{
  "detail": [
    {
      "loc": ["body", "url"],
      "msg": "Input should be a valid URL",
      "type": "url_parsing"
    }
  ]
}
```

---

### 503 — Publisher Not Ready

```json
{
  "error": "Publisher not ready"
}
```

Occurs when:

* Broker unavailable
* Publisher reconnecting
* Startup not complete

---

### 503 — Queue Overflow

```json
{
  "error": "Queue rejected (x-max-length reached)"
}
```

Occurs when queue reaches configured max length.

---

### 503 — Broker Connection Failure

```json
{
  "error": "Broker connection failure"
}
```

---

# GET `/metadata`

Retrieve metadata for a URL.

This endpoint performs a read-through operation:

* If metadata exists → return it.
* If not → enqueue and return 202.

---

## Request

| Field  | Value            |
| ------ | ---------------- |
| Method | GET              |
| Path   | `/metadata`      |
| Query  | `url` (required) |

---

## Query Parameter

| Parameter | Type   | Required | Description          |
| --------- | ------ | -------- | -------------------- |
| `url`     | string | Yes      | Valid HTTP/HTTPS URL |

URL must be URL-encoded if it contains special characters.

---

## Example cURL

```bash
curl -X GET \
  "http://localhost:6577/metadata?url=https%3A%2F%2Fexample.com"
```

---

# Responses

---

## 200 OK — COMPLETED

Metadata successfully fetched and stored.

```json
{
  "status": "COMPLETED",
  "url": "https://example.com",
  "metadata": {
    "headers": {
      "content-type": "text/html; charset=UTF-8",
      "content-length": "1256",
      "server": "nginx"
    },
    "cookies": {},
    "status_code": 200,
    "page_source": "<!doctype html><html>...</html>",
    "additional_details": null
  }
}
```

---

## 200 OK — FAILED_PERMANENT

All retries exhausted or non-retryable error occurred.

```json
{
  "status": "FAILED_PERMANENT",
  "url": "https://example.com/broken",
  "error_msg": "http status 500",
  "attempt_number": 3
}
```

---

## 202 Accepted — IN_PROGRESS

Metadata exists but processing is not yet complete.

```json
{
  "status": "IN_PROGRESS",
  "url": "https://example.com"
}
```

---

## 202 Accepted — Not Found (Enqueued)

No record exists. URL has been enqueued for processing.

```json
{
  "status": "QUEUED",
  "url": "https://example.com",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

# Failure Responses

---

## 400 — Missing Query Parameter

```json
{
  "error": "Missing required query parameter: url"
}
```

---

## 400 — Invalid URL

```json
{
  "error": "Invalid URL"
}
```

---

## 503 — Publisher Failure (When Enqueue Required)

```json
{
  "error": "Publisher not available"
}
```

---

## 503 — Database Not Available

```json
{
  "error": "Database not available"
}
```

---

# Health Endpoints

---

## GET `/health/live`

Liveness probe.

```bash
curl http://localhost:6577/health/live
```

**200 OK**

```json
{
  "status": "ok"
}
```

---

## GET `/health/ready`

Readiness probe.

Returns 200 only when:

* Publisher state is READY
* Database ping succeeds

```bash
curl http://localhost:6577/health/ready
```

### 200 OK

```json
{
  "status": "ready"
}
```

### 503 Not Ready

```json
{
  "status": "not_ready",
  "reason": "Publisher not ready"
}
```

---

# Status Model

---

## Allowed States

| Status             | Description                         |
| ------------------ | ----------------------------------- |
| `PENDING`          | Record created, not yet processed   |
| `QUEUED`           | API-level acknowledgment of enqueue |
| `IN_PROGRESS`      | Worker actively processing          |
| `COMPLETED`        | Metadata fetched successfully       |
| `FAILED_RETRYABLE` | Temporary failure, will retry       |
| `FAILED_PERMANENT` | Terminal failure                    |

---

## State Transition Diagram

```
PENDING
   |
   v
IN_PROGRESS
   |------------ success ------------> COMPLETED
   |
   |-- retryable error --> FAILED_RETRYABLE
   |                             |
   |                             v
   |----------------------- requeue
   |
   |-- non-retryable error --> FAILED_PERMANENT
```

