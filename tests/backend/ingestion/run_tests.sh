#!/bin/bash
# Face Recognition Test Suite Runner
# Sprint 2 - Tester-Agent

set -e

echo "========================================"
echo "Face Recognition Test Suite - Sprint 2"
echo "========================================"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Installing..."
    pip install pytest pytest-asyncio scikit-learn
fi

echo "📊 Running Test Suite..."
echo ""

# Run tests with detailed output
pytest tests/backend/ingestion/ -v --tb=short --color=yes

echo ""
echo "========================================"
echo "✅ Test Suite Completed"
echo "========================================"
echo ""
echo "📄 Full Report: tests/backend/ingestion/TEST_REPORT.md"
echo "📊 Baseline Metrics: tests/fixtures/baseline_metrics.json"
echo ""
echo "Next Steps:"
echo "  1. Review TEST_REPORT.md for detailed findings"
echo "  2. Fix DBSCAN eps parameter (see recommendations)"
echo "  3. Test with real face images"
echo ""
