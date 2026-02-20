#!/usr/bin/env bash
# Run test_post_metadata_enqueues_message with worker stopped so the message stays in the queue.
# Usage: from repo root, ./scripts/run_integration_queue_test.sh

set -e
cd "$(dirname "$0")/.."

echo "Stopping worker so it does not consume the message..."
docker compose stop worker

echo "Running test_post_metadata_enqueues_message..."
test_exit=0
docker compose run --rm tests pytest tests/integration/test_compose_api.py::test_post_metadata_enqueues_message -v --tb=short || test_exit=$?

echo "Starting worker again..."
docker compose start worker

exit $test_exit
