# Face Recognition Test Suite

Sprint 2 - Tester-Agent Deliverable

## Quick Start

```bash
# Run all tests
pytest tests/backend/ingestion/ -v

# Run specific category
pytest tests/backend/ingestion/test_face_recognition.py -v
pytest tests/backend/ingestion/test_face_clustering.py -v
pytest tests/backend/ingestion/test_face_metrics.py -v

# Run with coverage (optional)
pytest tests/backend/ingestion/ --cov=backend.ingestion.faces --cov-report=html
```

## Test Overview

| Test File | Tests | Status | Coverage |
|-----------|-------|--------|----------|
| `test_face_recognition.py` | 13 | ✅ 100% | Unit Tests |
| `test_face_clustering.py` | 7 | ⚠️ 71% (2 blocked) | Integration |
| `test_face_metrics.py` | 4 | ✅ 100% | Framework |
| **TOTAL** | **24** | **91.7%** | **All Areas** |

## What's Tested

### Face Detection (MediaPipe)
- ✅ Bounding box validation
- ✅ Confidence scores
- ✅ Edge cases (empty images, invalid data)
- ✅ Multi-face detection
- ✅ Border cases

### Face Embeddings (FaceNet)
- ✅ Dimensionality (512D)
- ✅ Data types (float32/float64)
- ✅ Normalization checks
- ✅ Similarity metrics (same vs different faces)
- ✅ Invalid input handling

### Clustering (DBSCAN)
- ⚠️ Purity (BLOCKED - needs parameter tuning)
- ✅ Consistency (deterministic)
- ✅ False positive detection
- ✅ Noise handling
- ✅ Parameter optimization
- ⚠️ Scalability (BLOCKED - same root cause)

### Metrics Framework
- ✅ Baseline persistence
- ✅ Metric comparison
- ✅ Regression detection
- ✅ Improvement tracking

## Known Issues

### 🔴 BLOCKER: DBSCAN eps Parameter

**Issue:** Current `eps=0.4` is too small for FaceNet embeddings.

**Symptoms:**
- All faces classified as noise
- 0% clustering purity
- No clusters formed

**Fix:** Use `eps=0.6` or implement adaptive parameter selection.

**Test:** `pytest tests/backend/ingestion/test_face_clustering.py::test_optimal_eps_parameter -v` shows `eps=0.6` works for mock data.

See: `TEST_REPORT.md` for detailed analysis and recommendations.

## Test Data

### Current: Synthetic Mocks
- Programmatically generated "faces" (circles with features)
- L2-normalized embeddings in orthogonal dimensions
- Good for unit testing, not for real-world validation

### Needed: Real Test Data
- Public domain face images (e.g., LFW dataset)
- Ground truth from validation UI
- Diverse faces (age, ethnicity, lighting, angles)

See: `tests/fixtures/README.md` for fixture organization.

## Metrics Baseline

Location: `tests/fixtures/baseline_metrics.json`

Current baseline (from synthetic tests):
- Detection Rate: 90%
- Same-Face Similarity: >0.9
- Clustering Purity: 85% (target)
- False Positive Rate: <5% (target)

Update baseline after real data testing:
```python
from tests.backend.ingestion.test_face_metrics import save_baseline, FaceRecognitionMetrics
# ... compute new metrics ...
save_baseline(metrics)
```

## Dependencies

```bash
pip install pytest pytest-asyncio scikit-learn
```

All other dependencies (torch, mediapipe, facenet-pytorch, opencv) are in `requirements.txt`.

## CI Integration

Add to `.github/workflows/test.yml` (or equivalent):

```yaml
- name: Run Face Recognition Tests
  run: |
    pytest tests/backend/ingestion/ -v --tb=short
```

## Documentation

- `TEST_REPORT.md` - Detailed test results and analysis
- `tests/fixtures/README.md` - Fixture organization
- Code comments in test files explain "why" each test matters

## Contact

Issues or questions? Check:
1. `TEST_REPORT.md` for findings
2. Test docstrings for test rationale
3. `.antigravity/tester.md` for agent role definition

---

**Sprint 2 Status:** ✅ Test Suite Complete | ⚠️ 2 Tests Blocked (Parameter Tuning Needed)
