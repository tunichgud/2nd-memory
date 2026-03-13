#!/usr/bin/env bash
set -e

echo "========================================="
echo "Running 2nd Memory Test Suite"
echo "========================================="

# Run backend unit tests
echo "[1/2] Running Backend Unit Tests (pytest)..."
.venv/bin/pytest tests/test_connector.py -v

# Run frontend E2E tests
echo "[2/2] Running Frontend UI E2E Tests (Selenium)..."
.venv/bin/pytest tests/frontend/test_streaming_ui.py -v

echo "========================================="
echo "All tests passed successfully! 🎉"
echo "========================================="
