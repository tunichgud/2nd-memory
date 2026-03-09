"""
Metrics Framework für Face Recognition

Sprint 2: Tester-Agent
Dieses Modul stellt ein Framework bereit um:
- Baseline-Metriken zu speichern
- Metriken über Zeit zu tracken
- Regressionen zu erkennen

Metriken:
- Detection Rate (wie viele Gesichter werden erkannt)
- Embedding Quality (Dimensionalität, Normalisierung)
- Clustering Purity
- False Positive Rate
- Processing Time
"""

import pytest
import json
import numpy as np
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from backend.ingestion.faces import detect_faces, get_face_embedding


# ==================== Metrics Dataclass ====================

@dataclass
class FaceRecognitionMetrics:
    """
    Speichert alle relevanten Metriken für Face Recognition.

    Verwendung:
    1. Baseline erstellen: Metriken bei Sprint 2 Start
    2. Nach jeder Änderung: Neue Metriken berechnen
    3. Vergleich: Regression Detection
    """
    # Detection Metrics
    detection_rate: float  # % der Test-Bilder wo Gesichter erkannt wurden
    avg_faces_per_image: float  # Durchschnitt Gesichter pro Bild
    avg_confidence: float  # Durchschnittlicher Detection Score

    # Embedding Metrics
    embedding_dimensions: int  # Sollte 512 sein
    avg_embedding_norm: float  # Durchschnittliche L2-Norm
    embedding_std: float  # Standardabweichung der Norms

    # Similarity Metrics
    same_face_similarity: float  # Similarity für gleiches Gesicht
    diff_face_similarity: float  # Similarity für verschiedene Gesichter
    similarity_margin: float  # Abstand zwischen same/diff

    # Clustering Metrics
    clustering_purity: float  # % korrekt zugeordnete Gesichter
    false_positive_rate: float  # % falsche Zuordnungen
    n_clusters: int  # Anzahl gefundener Cluster
    n_noise_points: int  # Outliers

    # Performance Metrics
    avg_detection_time_ms: float  # Zeit für detect_faces
    avg_embedding_time_ms: float  # Zeit für get_face_embedding

    # Metadata
    timestamp: str  # Wann wurden Metriken erstellt
    git_commit: Optional[str] = None  # Welcher Code-Stand
    notes: Optional[str] = None  # Freitext


def metrics_to_dict(metrics: FaceRecognitionMetrics) -> Dict:
    """Konvertiert Metrics zu Dict für JSON-Serialisierung"""
    return asdict(metrics)


def dict_to_metrics(data: Dict) -> FaceRecognitionMetrics:
    """Lädt Metrics aus Dict"""
    return FaceRecognitionMetrics(**data)


# ==================== Baseline Management ====================

BASELINE_PATH = Path(__file__).parent / "../../fixtures/baseline_metrics.json"


def save_baseline(metrics: FaceRecognitionMetrics):
    """
    Speichert Baseline-Metriken in JSON.

    Aufgerufen bei Sprint 2 Start um initialen Zustand festzuhalten.
    """
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(BASELINE_PATH, 'w') as f:
        json.dump(metrics_to_dict(metrics), f, indent=2)

    print(f"Baseline gespeichert: {BASELINE_PATH}")


def load_baseline() -> Optional[FaceRecognitionMetrics]:
    """
    Lädt Baseline-Metriken aus JSON.

    Returns None wenn keine Baseline existiert.
    """
    if not BASELINE_PATH.exists():
        return None

    with open(BASELINE_PATH, 'r') as f:
        data = json.load(f)

    return dict_to_metrics(data)


def compare_metrics(current: FaceRecognitionMetrics, baseline: FaceRecognitionMetrics) -> Dict[str, float]:
    """
    Vergleicht aktuelle Metriken mit Baseline.

    Returns:
        Dict mit relativen Änderungen (positive = Verbesserung)
    """
    comparison = {}

    # Detection Rate: Höher = besser
    comparison['detection_rate_change'] = current.detection_rate - baseline.detection_rate

    # Confidence: Höher = besser
    comparison['confidence_change'] = current.avg_confidence - baseline.avg_confidence

    # Same Face Similarity: Höher = besser
    comparison['same_similarity_change'] = current.same_face_similarity - baseline.same_face_similarity

    # Diff Face Similarity: Niedriger = besser
    comparison['diff_similarity_change'] = baseline.diff_face_similarity - current.diff_face_similarity

    # Similarity Margin: Höher = besser
    comparison['margin_change'] = current.similarity_margin - baseline.similarity_margin

    # Clustering Purity: Höher = besser
    comparison['purity_change'] = current.clustering_purity - baseline.clustering_purity

    # False Positive Rate: Niedriger = besser
    comparison['fp_rate_change'] = baseline.false_positive_rate - current.false_positive_rate

    # Performance: Schneller = besser
    comparison['detection_time_change'] = baseline.avg_detection_time_ms - current.avg_detection_time_ms
    comparison['embedding_time_change'] = baseline.avg_embedding_time_ms - current.avg_embedding_time_ms

    return comparison


# ==================== Metric Computation ====================

def compute_detection_metrics(test_images: List[bytes]) -> Dict:
    """
    Berechnet Detection-Metriken für eine Liste von Test-Bildern.
    """
    import time

    n_images = len(test_images)
    n_detected = 0
    total_faces = 0
    total_confidence = 0.0
    face_count = 0
    total_time = 0.0

    for image_bytes in test_images:
        start = time.time()
        faces = detect_faces(image_bytes)
        duration = (time.time() - start) * 1000  # ms

        total_time += duration

        if len(faces) > 0:
            n_detected += 1
            total_faces += len(faces)

            for face in faces:
                total_confidence += face['score']
                face_count += 1

    detection_rate = n_detected / n_images if n_images > 0 else 0.0
    avg_faces = total_faces / n_images if n_images > 0 else 0.0
    avg_confidence = total_confidence / face_count if face_count > 0 else 0.0
    avg_time = total_time / n_images if n_images > 0 else 0.0

    return {
        'detection_rate': detection_rate,
        'avg_faces_per_image': avg_faces,
        'avg_confidence': avg_confidence,
        'avg_detection_time_ms': avg_time
    }


def compute_embedding_metrics(test_images: List[bytes]) -> Dict:
    """
    Berechnet Embedding-Metriken.
    """
    import time

    embeddings = []
    total_time = 0.0
    n_embeddings = 0

    for image_bytes in test_images:
        faces = detect_faces(image_bytes)

        for face in faces:
            start = time.time()
            emb = get_face_embedding(image_bytes, face['box'])
            duration = (time.time() - start) * 1000  # ms

            if emb is not None:
                embeddings.append(emb)
                total_time += duration
                n_embeddings += 1

    if len(embeddings) == 0:
        return {
            'embedding_dimensions': 0,
            'avg_embedding_norm': 0.0,
            'embedding_std': 0.0,
            'avg_embedding_time_ms': 0.0
        }

    norms = [np.linalg.norm(emb) for emb in embeddings]
    avg_time = total_time / n_embeddings if n_embeddings > 0 else 0.0

    return {
        'embedding_dimensions': embeddings[0].shape[0],
        'avg_embedding_norm': np.mean(norms),
        'embedding_std': np.std(norms),
        'avg_embedding_time_ms': avg_time
    }


def compute_similarity_metrics(test_images: List[bytes]) -> Dict:
    """
    Berechnet Similarity-Metriken.

    Same-Face: Gleiches Bild zweimal → Similarity
    Diff-Face: Verschiedene Bilder → Similarity
    """
    same_similarities = []
    diff_similarities = []

    # Same-Face: Erstes Bild mit sich selbst
    if len(test_images) > 0:
        image_bytes = test_images[0]
        faces = detect_faces(image_bytes)

        if len(faces) > 0:
            box = faces[0]['box']
            emb1 = get_face_embedding(image_bytes, box)
            emb2 = get_face_embedding(image_bytes, box)

            if emb1 is not None and emb2 is not None:
                sim = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
                same_similarities.append(sim)

    # Diff-Face: Verschiedene Bilder vergleichen
    embeddings = []
    for image_bytes in test_images[:5]:  # Max 5 Bilder
        faces = detect_faces(image_bytes)
        if len(faces) > 0:
            emb = get_face_embedding(image_bytes, faces[0]['box'])
            if emb is not None:
                embeddings.append(emb)

    for i in range(len(embeddings)):
        for j in range(i+1, len(embeddings)):
            sim = np.dot(embeddings[i], embeddings[j]) / (
                np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
            )
            diff_similarities.append(sim)

    same_sim = np.mean(same_similarities) if len(same_similarities) > 0 else 0.0
    diff_sim = np.mean(diff_similarities) if len(diff_similarities) > 0 else 0.0
    margin = same_sim - diff_sim

    return {
        'same_face_similarity': same_sim,
        'diff_face_similarity': diff_sim,
        'similarity_margin': margin
    }


# ==================== Tests ====================

def test_metrics_dataclass_serialization():
    """
    Test: Metrics können zu JSON serialisiert und deserialisiert werden.

    Wichtig: Persistierung der Baseline.
    """
    from datetime import datetime

    metrics = FaceRecognitionMetrics(
        detection_rate=0.95,
        avg_faces_per_image=2.3,
        avg_confidence=0.87,
        embedding_dimensions=512,
        avg_embedding_norm=1.05,
        embedding_std=0.02,
        same_face_similarity=0.92,
        diff_face_similarity=0.38,
        similarity_margin=0.54,
        clustering_purity=0.88,
        false_positive_rate=0.03,
        n_clusters=5,
        n_noise_points=2,
        avg_detection_time_ms=45.2,
        avg_embedding_time_ms=12.8,
        timestamp=datetime.now().isoformat(),
        git_commit="abc123",
        notes="Initial baseline"
    )

    # Zu Dict
    data = metrics_to_dict(metrics)
    assert isinstance(data, dict)
    assert data['detection_rate'] == 0.95

    # Von Dict
    restored = dict_to_metrics(data)
    assert isinstance(restored, FaceRecognitionMetrics)
    assert restored.detection_rate == 0.95
    assert restored.git_commit == "abc123"


def test_save_and_load_baseline():
    """
    Test: Baseline kann gespeichert und geladen werden.
    """
    from datetime import datetime

    metrics = FaceRecognitionMetrics(
        detection_rate=0.90,
        avg_faces_per_image=2.0,
        avg_confidence=0.85,
        embedding_dimensions=512,
        avg_embedding_norm=1.0,
        embedding_std=0.01,
        same_face_similarity=0.90,
        diff_face_similarity=0.40,
        similarity_margin=0.50,
        clustering_purity=0.85,
        false_positive_rate=0.05,
        n_clusters=3,
        n_noise_points=1,
        avg_detection_time_ms=50.0,
        avg_embedding_time_ms=15.0,
        timestamp=datetime.now().isoformat(),
        notes="Test baseline"
    )

    # Speichern
    save_baseline(metrics)
    assert BASELINE_PATH.exists(), "Baseline-Datei wurde nicht erstellt"

    # Laden
    loaded = load_baseline()
    assert loaded is not None, "Baseline konnte nicht geladen werden"
    assert loaded.detection_rate == 0.90
    assert loaded.notes == "Test baseline"


def test_compare_metrics_detects_improvements():
    """
    Test: Verbesserungen werden korrekt erkannt.
    """
    from datetime import datetime

    baseline = FaceRecognitionMetrics(
        detection_rate=0.80,
        avg_faces_per_image=2.0,
        avg_confidence=0.80,
        embedding_dimensions=512,
        avg_embedding_norm=1.0,
        embedding_std=0.01,
        same_face_similarity=0.80,
        diff_face_similarity=0.50,
        similarity_margin=0.30,
        clustering_purity=0.75,
        false_positive_rate=0.10,
        n_clusters=3,
        n_noise_points=1,
        avg_detection_time_ms=100.0,
        avg_embedding_time_ms=30.0,
        timestamp=datetime.now().isoformat()
    )

    # Verbesserte Metriken
    current = FaceRecognitionMetrics(
        detection_rate=0.90,  # +0.10
        avg_faces_per_image=2.0,
        avg_confidence=0.85,  # +0.05
        embedding_dimensions=512,
        avg_embedding_norm=1.0,
        embedding_std=0.01,
        same_face_similarity=0.90,  # +0.10
        diff_face_similarity=0.40,  # -0.10 (besser!)
        similarity_margin=0.50,  # +0.20
        clustering_purity=0.88,  # +0.13
        false_positive_rate=0.03,  # -0.07 (besser!)
        n_clusters=3,
        n_noise_points=1,
        avg_detection_time_ms=50.0,  # -50ms (besser!)
        avg_embedding_time_ms=15.0,  # -15ms (besser!)
        timestamp=datetime.now().isoformat()
    )

    comparison = compare_metrics(current, baseline)

    # Alle sollten Verbesserungen zeigen (positive Werte)
    assert comparison['detection_rate_change'] > 0, "Detection Rate sollte besser sein"
    assert comparison['confidence_change'] > 0, "Confidence sollte besser sein"
    assert comparison['same_similarity_change'] > 0, "Same-Face Similarity sollte höher sein"
    assert comparison['diff_similarity_change'] > 0, "Diff-Face Similarity sollte niedriger sein"
    assert comparison['purity_change'] > 0, "Purity sollte besser sein"
    assert comparison['fp_rate_change'] > 0, "FP Rate sollte niedriger sein"
    assert comparison['detection_time_change'] > 0, "Detection sollte schneller sein"


def test_compare_metrics_detects_regressions():
    """
    Test: Regressionen werden erkannt.
    """
    from datetime import datetime

    baseline = FaceRecognitionMetrics(
        detection_rate=0.90,
        avg_faces_per_image=2.0,
        avg_confidence=0.85,
        embedding_dimensions=512,
        avg_embedding_norm=1.0,
        embedding_std=0.01,
        same_face_similarity=0.90,
        diff_face_similarity=0.40,
        similarity_margin=0.50,
        clustering_purity=0.88,
        false_positive_rate=0.03,
        n_clusters=3,
        n_noise_points=1,
        avg_detection_time_ms=50.0,
        avg_embedding_time_ms=15.0,
        timestamp=datetime.now().isoformat()
    )

    # Verschlechterte Metriken
    current = FaceRecognitionMetrics(
        detection_rate=0.70,  # -0.20 (Regression!)
        avg_faces_per_image=2.0,
        avg_confidence=0.75,  # -0.10 (Regression!)
        embedding_dimensions=512,
        avg_embedding_norm=1.0,
        embedding_std=0.01,
        same_face_similarity=0.70,  # -0.20 (Regression!)
        diff_face_similarity=0.55,  # +0.15 (Regression!)
        similarity_margin=0.15,  # -0.35 (Regression!)
        clustering_purity=0.65,  # -0.23 (Regression!)
        false_positive_rate=0.15,  # +0.12 (Regression!)
        n_clusters=3,
        n_noise_points=1,
        avg_detection_time_ms=100.0,  # +50ms (Regression!)
        avg_embedding_time_ms=30.0,  # +15ms (Regression!)
        timestamp=datetime.now().isoformat()
    )

    comparison = compare_metrics(current, baseline)

    # Alle sollten Verschlechterungen zeigen (negative Werte)
    assert comparison['detection_rate_change'] < 0, "Regression: Detection Rate schlechter"
    assert comparison['purity_change'] < 0, "Regression: Purity schlechter"
    assert comparison['fp_rate_change'] < 0, "Regression: FP Rate höher"

    print("\nREGRESSION DETECTED:")
    for key, value in comparison.items():
        if value < 0:
            print(f"  {key}: {value:.3f}")
