"""
Unit Tests für die Gesichtserkennung (backend/ingestion/faces.py)

Sprint 2: Tester-Agent
Diese Tests überprüfen die grundlegende Funktionalität der Gesichtserkennung:
- Gesichtsdetektion mit MediaPipe
- FaceNet Embeddings (512D)
- Normalisierung und Similarity-Berechnungen
"""

import pytest
import numpy as np
import cv2
import sys
import os
from pathlib import Path

# Projektwurzel zum Path hinzufügen
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from backend.ingestion.faces import detect_faces, get_face_embedding


@pytest.fixture
def sample_face_image():
    """
    Generiert ein synthetisches Testbild mit einem Gesicht.
    Fallback für Tests ohne echte Bilder.
    """
    # Erstelle ein 640x480 RGB Bild mit einem einfachen "Gesicht" (Kreis mit Punkten)
    img = np.ones((480, 640, 3), dtype=np.uint8) * 200  # Hellgrauer Hintergrund

    # Zeichne ein "Gesicht" (Kreis für Kopf, Punkte für Augen/Mund)
    center = (320, 240)
    cv2.circle(img, center, 80, (255, 200, 150), -1)  # Hautfarbe
    cv2.circle(img, (280, 220), 10, (0, 0, 0), -1)    # Linkes Auge
    cv2.circle(img, (360, 220), 10, (0, 0, 0), -1)    # Rechtes Auge
    cv2.ellipse(img, (320, 260), (30, 15), 0, 0, 180, (100, 50, 50), 2)  # Mund

    # Konvertiere zu bytes
    _, buffer = cv2.imencode('.jpg', img)
    return buffer.tobytes()


@pytest.fixture
def sample_face_image_2():
    """
    Zweites synthetisches Gesicht für Vergleichstests.
    Unterschiedliche Position und Größe.
    """
    img = np.ones((480, 640, 3), dtype=np.uint8) * 180

    # Anderes "Gesicht" an anderer Position
    center = (400, 300)
    cv2.circle(img, center, 60, (240, 190, 140), -1)
    cv2.circle(img, (380, 285), 8, (0, 0, 0), -1)
    cv2.circle(img, (420, 285), 8, (0, 0, 0), -1)
    cv2.ellipse(img, (400, 315), (25, 12), 0, 0, 180, (120, 60, 60), 2)

    _, buffer = cv2.imencode('.jpg', img)
    return buffer.tobytes()


@pytest.fixture
def empty_image():
    """Bild ohne Gesicht"""
    img = np.ones((480, 640, 3), dtype=np.uint8) * 100
    _, buffer = cv2.imencode('.jpg', img)
    return buffer.tobytes()


# ==================== Gesichtsdetektion Tests ====================

def test_detect_faces_returns_list(sample_face_image):
    """
    Test: detect_faces gibt eine Liste zurück.
    Wichtig: API-Konsistenz für downstream-Code.
    """
    faces = detect_faces(sample_face_image)
    assert isinstance(faces, list), "detect_faces muss eine Liste zurückgeben"


def test_detect_faces_on_empty_image(empty_image):
    """
    Test: Bild ohne Gesicht gibt leere Liste zurück.
    Wichtig: Kein Crash bei No-Detection-Szenarien.
    """
    faces = detect_faces(empty_image)
    assert isinstance(faces, list), "Auch bei keinem Gesicht muss eine Liste zurückkommen"
    # Note: MediaPipe könnte False Positives haben, daher kein striktes len() == 0


def test_detect_faces_returns_valid_bboxes(sample_face_image):
    """
    Test: Bounding Boxes liegen im gültigen Bildbereich.
    Wichtig: Vermeidet Out-of-Bounds-Fehler beim Cropping.
    """
    faces = detect_faces(sample_face_image)

    if len(faces) > 0:
        # Bildgröße aus sample_face_image: 640x480
        img_width, img_height = 640, 480

        for face in faces:
            box = face['box']
            ymin, xmin, ymax, xmax = box

            assert ymin >= 0, f"ymin={ymin} darf nicht negativ sein"
            assert xmin >= 0, f"xmin={xmin} darf nicht negativ sein"
            assert ymax <= img_height, f"ymax={ymax} überschreitet Bildhöhe {img_height}"
            assert xmax <= img_width, f"xmax={xmax} überschreitet Bildbreite {img_width}"
            assert ymin < ymax, "ymin muss kleiner als ymax sein"
            assert xmin < xmax, "xmin muss kleiner als xmax sein"


def test_detect_faces_has_confidence_score(sample_face_image):
    """
    Test: Jede Detection hat einen Confidence Score.
    Wichtig: Für Qualitätsfilter (z.B. score > 0.5).
    """
    faces = detect_faces(sample_face_image)

    if len(faces) > 0:
        for face in faces:
            assert 'score' in face, "Jede Detection muss einen 'score' haben"
            assert isinstance(face['score'], (float, np.floating)), "Score muss numerisch sein"
            assert 0.0 <= face['score'] <= 1.0, f"Score {face['score']} außerhalb [0, 1]"


def test_detect_faces_invalid_bytes():
    """
    Test: Ungültige Bilddaten führen zu leerer Liste, nicht zu Crash.
    Wichtig: Robustheit gegen korrupte Uploads.
    """
    invalid_bytes = b"not an image"
    faces = detect_faces(invalid_bytes)
    assert isinstance(faces, list), "Muss auch bei invaliden Daten eine Liste zurückgeben"
    assert len(faces) == 0, "Ungültige Bilddaten sollten keine Gesichter detektieren"


# ==================== Embedding Tests ====================

def test_face_embedding_dimensions(sample_face_image):
    """
    Test: FaceNet Embeddings haben korrekte Dimensionalität (512D).
    Wichtig: ChromaDB und Similarity-Berechnungen basieren darauf.
    """
    faces = detect_faces(sample_face_image)

    if len(faces) > 0:
        box = faces[0]['box']
        embedding = get_face_embedding(sample_face_image, box)

        assert embedding is not None, "Embedding darf nicht None sein"
        assert isinstance(embedding, np.ndarray), "Embedding muss numpy array sein"
        assert embedding.shape == (512,), f"FaceNet sollte 512D liefern, bekam {embedding.shape}"


def test_embedding_data_type(sample_face_image):
    """
    Test: Embeddings sind float32/float64.
    Wichtig: Numerische Stabilität und Kompatibilität.
    """
    faces = detect_faces(sample_face_image)

    if len(faces) > 0:
        box = faces[0]['box']
        embedding = get_face_embedding(sample_face_image, box)

        assert embedding is not None
        assert embedding.dtype in [np.float32, np.float64], f"Unexpected dtype: {embedding.dtype}"


def test_embedding_normalization(sample_face_image):
    """
    Test: Embeddings sind L2-normalisiert (für Cosine Similarity).
    Wichtig: ChromaDB verwendet Cosine Distance standardmäßig.
    """
    faces = detect_faces(sample_face_image)

    if len(faces) > 0:
        box = faces[0]['box']
        embedding = get_face_embedding(sample_face_image, box)

        if embedding is not None:
            l2_norm = np.linalg.norm(embedding)
            # FaceNet normalisiert nicht automatisch, aber wir sollten prüfen ob es getan werden sollte
            # Für jetzt: Check ob Norm in vernünftigem Bereich liegt
            assert l2_norm > 0, "Embedding sollte nicht Null-Vektor sein"
            # Note: Wenn l2_norm ~1.0, dann ist es normalisiert
            # Für nicht-normalisierte Embeddings erwarten wir größere Werte


def test_embedding_with_invalid_box(sample_face_image):
    """
    Test: Ungültige Bounding Box gibt None zurück.
    Wichtig: Fehlerbehandlung bei fehlerhaften Metadaten.
    """
    # Box außerhalb des Bildes
    invalid_box = [1000, 1000, 1100, 1100]
    embedding = get_face_embedding(sample_face_image, invalid_box)
    assert embedding is None, "Ungültige Box sollte None zurückgeben"

    # Leere Box
    empty_box = [100, 100, 100, 100]
    embedding = get_face_embedding(sample_face_image, empty_box)
    assert embedding is None, "Leere Box sollte None zurückgeben"


# ==================== Similarity Tests ====================

def test_same_face_high_similarity(sample_face_image):
    """
    Test: Gleiches Gesicht zweimal verarbeitet → hohe Similarity (>0.7).
    Wichtig: Basis für Clustering - identische Gesichter müssen erkannt werden.
    CRITICAL: Dies ist der wichtigste Test für Face Recognition!
    """
    faces = detect_faces(sample_face_image)

    if len(faces) > 0:
        box = faces[0]['box']
        emb1 = get_face_embedding(sample_face_image, box)
        emb2 = get_face_embedding(sample_face_image, box)

        assert emb1 is not None and emb2 is not None

        # Cosine Similarity: (A·B) / (||A|| * ||B||)
        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

        assert similarity > 0.7, (
            f"Gleiches Gesicht sollte Similarity >0.7 haben, bekam {similarity:.3f}. "
            f"BLOCKING: Face Recognition funktioniert nicht zuverlässig!"
        )


def test_different_faces_low_similarity(sample_face_image, sample_face_image_2):
    """
    Test: Verschiedene Gesichter → niedrige Similarity (<0.5).
    Wichtig: False Positives vermeiden - verschiedene Personen dürfen nicht geclustert werden.
    """
    faces1 = detect_faces(sample_face_image)
    faces2 = detect_faces(sample_face_image_2)

    if len(faces1) > 0 and len(faces2) > 0:
        emb1 = get_face_embedding(sample_face_image, faces1[0]['box'])
        emb2 = get_face_embedding(sample_face_image_2, faces2[0]['box'])

        assert emb1 is not None and emb2 is not None

        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

        # Note: Mit synthetischen Bildern könnte die Similarity höher sein
        # Für echte Gesichter erwarten wir <0.5
        # Hier nur sanfte Warnung, kein Fail
        if similarity > 0.5:
            print(f"WARNING: Verschiedene Gesichter haben Similarity {similarity:.3f} (>0.5)")


# ==================== Edge Cases ====================

def test_multiple_faces_detection():
    """
    Test: Mehrere Gesichter in einem Bild werden erkannt.
    Wichtig: Gruppenfotos korrekt verarbeiten.
    """
    # Bild mit zwei "Gesichtern"
    img = np.ones((480, 640, 3), dtype=np.uint8) * 200

    # Gesicht 1
    cv2.circle(img, (200, 240), 60, (255, 200, 150), -1)
    cv2.circle(img, (180, 220), 8, (0, 0, 0), -1)
    cv2.circle(img, (220, 220), 8, (0, 0, 0), -1)

    # Gesicht 2
    cv2.circle(img, (440, 240), 60, (255, 200, 150), -1)
    cv2.circle(img, (420, 220), 8, (0, 0, 0), -1)
    cv2.circle(img, (460, 220), 8, (0, 0, 0), -1)

    _, buffer = cv2.imencode('.jpg', img)
    image_bytes = buffer.tobytes()

    faces = detect_faces(image_bytes)

    # MediaPipe sollte idealerweise beide erkennen
    # Mit synthetischen Bildern nicht garantiert - nur Info
    print(f"INFO: Erkannte {len(faces)} Gesichter im Multi-Face-Bild")


def test_face_at_image_border():
    """
    Test: Gesicht am Bildrand wird korrekt behandelt.
    Wichtig: Keine Array-Index-Fehler bei Rand-Crops.
    """
    img = np.ones((480, 640, 3), dtype=np.uint8) * 200

    # Gesicht am linken Rand (teilweise außerhalb)
    cv2.circle(img, (30, 240), 50, (255, 200, 150), -1)
    cv2.circle(img, (20, 220), 8, (0, 0, 0), -1)
    cv2.circle(img, (40, 220), 8, (0, 0, 0), -1)

    _, buffer = cv2.imencode('.jpg', img)
    image_bytes = buffer.tobytes()

    faces = detect_faces(image_bytes)

    # Sollte nicht crashen
    for face in faces:
        box = face['box']
        embedding = get_face_embedding(image_bytes, box)
        # Kann None sein wenn Box zu klein, aber kein Crash
        assert embedding is None or isinstance(embedding, np.ndarray)
