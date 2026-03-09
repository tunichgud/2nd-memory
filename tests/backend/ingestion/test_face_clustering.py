"""
Clustering Tests für Gesichtserkennung

Sprint 2: Tester-Agent
Diese Tests überprüfen die Qualität des Gesichts-Clusterings:
- Cluster Purity (Reinheit der Cluster)
- Cluster Consistency (Reproduzierbarkeit)
- False Positive Rate (falsche Zuordnungen)

WICHTIG: Diese Tests benötigen Ground Truth Daten aus dem Validierungs-UI.
Aktuell verwenden wir Mocks, bis echte Validierungsdaten verfügbar sind.
"""

import pytest
import numpy as np
import sys
import os
from typing import List, Dict, Tuple
from sklearn.cluster import DBSCAN
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from backend.ingestion.faces import get_face_embedding


# ==================== Mock Ground Truth ====================

@pytest.fixture
def mock_ground_truth():
    """
    Mock Ground Truth: 3 Personen mit je 5 Gesichtern.
    Simuliert validierte Daten aus dem UI.

    Structure:
    {
        'person_A': [emb1, emb2, emb3, emb4, emb5],
        'person_B': [emb6, emb7, emb8, emb9, emb10],
        'person_C': [emb11, emb12, emb13, emb14, emb15]
    }
    """
    np.random.seed(42)  # Reproduzierbar

    ground_truth = {}

    # Person A: Embeddings um Zentrum [1.0, 0, 0, ...] mit kleiner Varianz
    center_A = np.zeros(512)
    center_A[0] = 1.0
    center_A = center_A / np.linalg.norm(center_A)

    embeddings_A = []
    for _ in range(5):
        noise = np.random.normal(0, 0.1, 512)
        emb = center_A + noise
        emb = emb / np.linalg.norm(emb)  # L2-Normalisierung
        embeddings_A.append(emb)

    ground_truth['person_A'] = embeddings_A

    # Person B: Zentrum [0, 1.0, 0, ...]
    center_B = np.zeros(512)
    center_B[1] = 1.0
    center_B = center_B / np.linalg.norm(center_B)

    embeddings_B = []
    for _ in range(5):
        noise = np.random.normal(0, 0.1, 512)
        emb = center_B + noise
        emb = emb / np.linalg.norm(emb)
        embeddings_B.append(emb)

    ground_truth['person_B'] = embeddings_B

    # Person C: Zentrum [0, 0, 1.0, ...]
    center_C = np.zeros(512)
    center_C[2] = 1.0
    center_C = center_C / np.linalg.norm(center_C)

    embeddings_C = []
    for _ in range(5):
        noise = np.random.normal(0, 0.1, 512)
        emb = center_C + noise
        emb = emb / np.linalg.norm(emb)
        embeddings_C.append(emb)

    ground_truth['person_C'] = embeddings_C

    return ground_truth


def compute_cosine_distance(emb1, emb2):
    """Cosine Distance = 1 - Cosine Similarity"""
    similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
    return 1.0 - similarity


# ==================== Clustering Helper ====================

def perform_clustering(embeddings: List[np.ndarray], eps: float = 0.4, min_samples: int = 2) -> List[int]:
    """
    Führt DBSCAN Clustering durch.

    Args:
        embeddings: Liste von Embeddings
        eps: DBSCAN epsilon (max. Distanz)
        min_samples: Min. Anzahl Samples pro Cluster

    Returns:
        Liste von Cluster-Labels (-1 = Noise)
    """
    if len(embeddings) == 0:
        return []

    # Distanzmatrix berechnen
    n = len(embeddings)
    distances = np.zeros((n, n))

    for i in range(n):
        for j in range(i+1, n):
            dist = compute_cosine_distance(embeddings[i], embeddings[j])
            distances[i, j] = dist
            distances[j, i] = dist

    # DBSCAN anwenden
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='precomputed')
    labels = clustering.fit_predict(distances)

    return labels.tolist()


# ==================== Clustering Tests ====================

def test_clustering_purity(mock_ground_truth):
    """
    Test: Cluster Purity - wie viele Gesichter werden korrekt zugeordnet?

    Target: >85% Purity
    Wichtig: Hauptmetrik für Clustering-Qualität.
    BLOCKING: Wenn <70% → Face Recognition unbrauchbar.
    """
    # Alle Embeddings sammeln mit Ground Truth Labels
    all_embeddings = []
    true_labels = []

    for person_id, embeddings in mock_ground_truth.items():
        all_embeddings.extend(embeddings)
        true_labels.extend([person_id] * len(embeddings))

    # Clustering durchführen
    predicted_labels = perform_clustering(all_embeddings, eps=0.4, min_samples=2)

    # Purity berechnen: Für jeden Cluster, wie viele gehören zur häufigsten Klasse?
    cluster_ids = set(predicted_labels)
    if -1 in cluster_ids:
        cluster_ids.remove(-1)  # Noise ignorieren

    total_correct = 0
    total_samples = len([l for l in predicted_labels if l != -1])

    for cluster_id in cluster_ids:
        # Welche True Labels sind in diesem Cluster?
        indices = [i for i, l in enumerate(predicted_labels) if l == cluster_id]
        cluster_true_labels = [true_labels[i] for i in indices]

        # Häufigste Klasse
        most_common = Counter(cluster_true_labels).most_common(1)[0][1]
        total_correct += most_common

    purity = total_correct / total_samples if total_samples > 0 else 0

    print(f"\nClustering Purity: {purity:.2%}")
    print(f"Predicted Clusters: {len(cluster_ids)}")
    print(f"Noise Points: {predicted_labels.count(-1)}")

    assert purity >= 0.85, (
        f"Clustering Purity {purity:.2%} unter Target (85%). "
        f"BLOCKING: Clustering-Qualität unzureichend!"
    )

    # Warnung bei niedriger Purity
    if purity < 0.70:
        pytest.fail(f"CRITICAL: Purity {purity:.2%} < 70% - Face Recognition unbrauchbar!")


def test_clustering_consistency(mock_ground_truth):
    """
    Test: Clustering Consistency - mehrfaches Ausführen liefert gleiche Ergebnisse.

    Wichtig: DBSCAN ist deterministisch bei gleichen Parametern.
    Problem: Wenn Embeddings instabil sind, variieren Cluster.
    """
    all_embeddings = []
    for embeddings in mock_ground_truth.values():
        all_embeddings.extend(embeddings)

    # Clustering 3x durchführen
    labels_1 = perform_clustering(all_embeddings, eps=0.4, min_samples=2)
    labels_2 = perform_clustering(all_embeddings, eps=0.4, min_samples=2)
    labels_3 = perform_clustering(all_embeddings, eps=0.4, min_samples=2)

    # Sollten identisch sein
    assert labels_1 == labels_2, "Clustering ist nicht konsistent (Run 1 vs 2)"
    assert labels_2 == labels_3, "Clustering ist nicht konsistent (Run 2 vs 3)"

    print(f"\nClustering ist konsistent über 3 Runs")


def test_no_false_positives(mock_ground_truth):
    """
    Test: False Positive Rate < 5%

    False Positive = Gesicht von Person A wird in Cluster von Person B zugeordnet.
    Wichtig: Privacy - falsche Zuordnungen sind kritisch!
    """
    all_embeddings = []
    true_labels = []

    for person_id, embeddings in mock_ground_truth.items():
        all_embeddings.extend(embeddings)
        true_labels.extend([person_id] * len(embeddings))

    predicted_labels = perform_clustering(all_embeddings, eps=0.4, min_samples=2)

    # Cluster analysieren: Für jeden Cluster, sind verschiedene Personen drin?
    cluster_ids = set(predicted_labels)
    if -1 in cluster_ids:
        cluster_ids.remove(-1)

    false_positives = 0
    total_pairs = 0

    for cluster_id in cluster_ids:
        indices = [i for i, l in enumerate(predicted_labels) if l == cluster_id]
        cluster_true_labels = [true_labels[i] for i in indices]

        # Zähle Paare mit unterschiedlichen True Labels
        for i in range(len(cluster_true_labels)):
            for j in range(i+1, len(cluster_true_labels)):
                total_pairs += 1
                if cluster_true_labels[i] != cluster_true_labels[j]:
                    false_positives += 1

    fp_rate = false_positives / total_pairs if total_pairs > 0 else 0

    print(f"\nFalse Positive Rate: {fp_rate:.2%}")
    print(f"False Positives: {false_positives} / {total_pairs} Paare")

    assert fp_rate < 0.05, (
        f"False Positive Rate {fp_rate:.2%} über Target (5%). "
        f"PRIVACY RISK: Falsche Zuordnungen zu häufig!"
    )


def test_clustering_handles_noise():
    """
    Test: Outlier/Noise werden korrekt als Noise (-1) markiert.

    Wichtig: Ein einzelnes unbekanntes Gesicht sollte keinen eigenen Cluster bilden.
    """
    np.random.seed(42)

    # 3 Cluster + 2 Outliers
    embeddings = []

    # Cluster A (3 Samples)
    center_A = np.zeros(512)
    center_A[0] = 1.0
    center_A = center_A / np.linalg.norm(center_A)
    for _ in range(3):
        noise = np.random.normal(0, 0.05, 512)
        emb = center_A + noise
        emb = emb / np.linalg.norm(emb)
        embeddings.append(emb)

    # Cluster B (3 Samples)
    center_B = np.zeros(512)
    center_B[1] = 1.0
    center_B = center_B / np.linalg.norm(center_B)
    for _ in range(3):
        noise = np.random.normal(0, 0.05, 512)
        emb = center_B + noise
        emb = emb / np.linalg.norm(emb)
        embeddings.append(emb)

    # 2 Outliers (weit weg von allen)
    outlier_1 = np.random.normal(0, 1, 512)
    outlier_1 = outlier_1 / np.linalg.norm(outlier_1)
    embeddings.append(outlier_1)

    outlier_2 = np.random.normal(0, 1, 512)
    outlier_2 = outlier_2 / np.linalg.norm(outlier_2)
    embeddings.append(outlier_2)

    # Clustering
    labels = perform_clustering(embeddings, eps=0.3, min_samples=2)

    noise_count = labels.count(-1)
    print(f"\nNoise Points: {noise_count} / {len(labels)}")

    # Mindestens 1 Outlier sollte als Noise erkannt werden
    assert noise_count > 0, "Outliers sollten als Noise (-1) markiert werden"


def test_optimal_eps_parameter():
    """
    Test: Finde optimalen eps-Parameter für DBSCAN.

    Wichtig: eps beeinflusst Cluster-Anzahl stark.
    Zu klein → zu viele Cluster
    Zu groß → alles ein Cluster
    """
    np.random.seed(42)

    # 3 klar getrennte Personen
    embeddings = []
    true_labels = []

    centers = [
        np.array([1, 0, 0] + [0]*509),
        np.array([0, 1, 0] + [0]*509),
        np.array([0, 0, 1] + [0]*509)
    ]

    for idx, center in enumerate(centers):
        center = center / np.linalg.norm(center)
        for _ in range(5):
            noise = np.random.normal(0, 0.05, 512)
            emb = center + noise
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)
            true_labels.append(f"person_{idx}")

    # Teste verschiedene eps-Werte
    eps_values = [0.2, 0.3, 0.4, 0.5, 0.6]
    results = []

    for eps in eps_values:
        labels = perform_clustering(embeddings, eps=eps, min_samples=2)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = labels.count(-1)
        results.append((eps, n_clusters, n_noise))

    print(f"\nEps Parameter Test:")
    for eps, n_clusters, n_noise in results:
        print(f"  eps={eps}: {n_clusters} Cluster, {n_noise} Noise")

    # Idealerweise: 3 Cluster bei einem der eps-Werte
    cluster_counts = [r[1] for r in results]
    assert 3 in cluster_counts, (
        f"Kein eps-Wert erzeugt 3 Cluster (erwartet für 3 Personen). "
        f"Gefunden: {cluster_counts}. Benötigt eps-Tuning!"
    )


# ==================== Integration Tests ====================

def test_clustering_scalability():
    """
    Test: Clustering skaliert mit großer Anzahl von Gesichtern.

    Wichtig: Performance bei 100+ Gesichtern.
    """
    np.random.seed(42)

    # 10 Personen mit je 10 Gesichtern = 100 total
    embeddings = []
    n_persons = 10
    faces_per_person = 10

    for person_id in range(n_persons):
        # Zentrum für Person
        center = np.random.normal(0, 1, 512)
        center = center / np.linalg.norm(center)

        for _ in range(faces_per_person):
            noise = np.random.normal(0, 0.1, 512)
            emb = center + noise
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)

    # Clustering (sollte nicht zu lange dauern)
    import time
    start = time.time()
    labels = perform_clustering(embeddings, eps=0.4, min_samples=3)
    duration = time.time() - start

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

    print(f"\nScalability Test: 100 Gesichter")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Clusters: {n_clusters}")

    assert duration < 10.0, f"Clustering zu langsam: {duration:.2f}s (Target: <10s)"
    assert 5 <= n_clusters <= 15, f"Unerwartete Cluster-Anzahl: {n_clusters} (Target: ~10)"


def test_clustering_empty_input():
    """
    Test: Leere Embedding-Liste crasht nicht.

    Wichtig: Edge Case bei Fotos ohne Gesichter.
    """
    embeddings = []
    labels = perform_clustering(embeddings)
    assert labels == [], "Leere Input sollte leere Output liefern"
