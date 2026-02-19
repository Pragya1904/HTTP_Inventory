# API contracts — curl for Postman

Base URL when running locally: `http://localhost:6577`

---

## 1. GET /health/live

Liveness probe. Always 200 when the process is up.

```bash
curl -X GET "http://localhost:6577/health/live"
```

**Example response (200):**
```json
{"status":"ok"}
```

---

## 2. GET /health/ready

Readiness probe. 200 only when publisher is READY and database ping succeeds; otherwise 503.

```bash
curl -X GET "http://localhost:6577/health/ready"
```

**Example response (200):** empty body, status 200.

**Example response (503):** body `Not ready` / `Publisher not ready` / `Database not ready`.

---

## 3. POST /metadata

Enqueue a URL for metadata processing. Body must be JSON with a valid `url` (HTTP/HTTPS).

```bash
curl -X POST "http://localhost:6577/metadata" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://example.com\"}"
```

**Example response (202):**
```json
{"status":"QUEUED","url":"https://example.com/","request_id":"550e8400-e29b-41d4-a716-446655440000"}
```

**Example response (503):** when publisher not ready, queue rejected, or broker down.

**Example response (422):** when body is invalid or `url` is not a valid URL.

---

## 4. GET /metadata

Placeholder. Returns 202 with a message.

```bash
curl -X GET "http://localhost:6577/metadata"
```

**Example response (202):**
```json
{"message": "Processing or retrieval not yet implemented"}
```

---

## Summary for Postman

| Contract        | Method | Path         | Body (optional)           | Success |
|----------------|--------|--------------|---------------------------|---------|
| Liveness       | GET    | /health/live | —                         | 200     |
| Readiness      | GET    | /health/ready| —                         | 200     |
| Post metadata  | POST   | /metadata    | `{"url": "https://example.com"}` | 202 |
| Get metadata   | GET    | /metadata    | —                         | 202     |

Use **Base URL** `http://localhost:6577` (or your API host) and the paths above.
