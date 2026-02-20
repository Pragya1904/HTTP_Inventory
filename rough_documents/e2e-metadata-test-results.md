# E2E metadata test – results and interpretation

The test **`tests/integration/test_e2e_metadata_post_get.py`** runs an end-to-end flow:

1. **Split URLs** – Uses all entries from `tests/test_data.TEST_URLS`. Half are sent via **POST /metadata** (JSON body), half via **GET /metadata?url=...**.
2. **Enqueue** – Logs each enqueue (method, URL, status code, request_id).
3. **Worker** – Starts the worker in-process so messages are consumed and persisted.
4. **DB wait** – For each URL, polls Mongo until status is **COMPLETED** or **FAILED_PERMANENT** (or timeout).
5. **Summary** – Prints counts (completed, failed_permanent, timeout, other) and a table: method | status | url.

## How to run

```bash
docker compose run --rm tests pytest tests/integration/test_e2e_metadata_post_get.py -m integration -v -s --tb=short
```

Use **`-s`** so `[E2E]` logs and the result table are visible.

## Log steps you’ll see

| Step           | Meaning |
|----------------|--------|
| `split`        | Total URLs and how many go to POST vs GET. |
| `api_ready`    | API /health/ready returned 200. |
| `worker_started` | Worker subprocess PID. |
| `enqueue_post` | One line per POST; url, status_code, request_id. |
| `enqueue_get`  | One line per GET; url, status_code, request_id. |
| `wait_db`      | Start waiting for terminal state for all URLs. |
| `db_result`    | For each URL: final status, attempt_number, error_msg (if any). |
| `db_timeout`   | URL did not reach COMPLETED/FAILED_PERMANENT in time. |
| `worker_stop`  | Worker received SIGTERM. |
| `summary`      | Counts: completed, failed_permanent, timeout, other, total. |
| **Results table** | One line per URL: POST/GET | status | url. |

## Status values

- **COMPLETED** – Metadata fetched and stored.
- **FAILED_PERMANENT** – Worker gave up after retries (e.g. 404/500 or fetch error).
- **TIMEOUT** – Test did not see COMPLETED or FAILED_PERMANENT within the wait window.
- **Other** – Any other DB status (e.g. QUEUED, IN_PROGRESS, FAILED_RETRYABLE) still present at end of wait.

## Documenting a run

After a run, you can:

- Copy the printed **summary** and **Results table** into a report or ticket.
- Use the **summary** counts to track how many URLs completed vs failed vs timed out across runs.
- Inspect **db_result** / **db_timeout** lines for specific URLs that failed or timed out.

The test **asserts** that at least one URL reaches **COMPLETED** (so the pipeline is working) and that the number of results matches the number of URLs.
