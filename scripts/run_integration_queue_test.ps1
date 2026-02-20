# Run test_post_metadata_enqueues_message with worker stopped so the message stays in the queue.
# Usage: from repo root, .\scripts\run_integration_queue_test.ps1
# Or: pwsh -File scripts/run_integration_queue_test.ps1

$ErrorActionPreference = "Stop"
$projectRoot = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { Get-Location }
Push-Location $projectRoot
try {
    Write-Host "Stopping worker so it does not consume the message..."
    docker compose stop worker
    Write-Host "Running test_post_metadata_enqueues_message..."
    docker compose run --rm tests pytest tests/integration/test_compose_api.py::test_post_metadata_enqueues_message -v --tb=short
    $testExit = $LASTEXITCODE
} finally {
    Write-Host "Starting worker again..."
    docker compose start worker
    Pop-Location
}
exit $testExit
