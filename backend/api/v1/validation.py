"""
validation.py – Label-Validierungs-API für Gesichtserkennung

Ermöglicht Human-in-the-Loop Validierung von Clustern:
- Cluster-Vorschläge mit Qualitätsmetriken abrufen
- Validierungen speichern (Ground Truth)
- Ground Truth als JSON exportieren
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sklearn.cluster import DBSCAN
from scipy.spatial.distance import cosine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/validation", tags=["v1/validation"])

# Ground Truth Storage
BASE_DIR = Path(__file__).resolve().parents[3]
GROUND_TRUTH_DIR = BASE_DIR / "data" / "ground_truth"
GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
GROUND_TRUTH_FILE = GROUND_TRUTH_DIR / "validated_clusters.json"


# ==============================================================================
# Pydantic Schemas
# ==============================================================================

class QualityMetrics(BaseModel):
    avg_intra_similarity: float = Field(..., description="Durchschnittliche Cosine Similarity innerhalb des Clusters")
    min_intra_similarity: float = Field(..., description="Minimale Ähnlichkeit innerhalb des Clusters")
    std_intra_similarity: float = Field(..., description="Standardabweichung der Ähnlichkeit")
    avg_detection_conf: float = Field(..., description="Durchschnittliche MediaPipe Detection Confidence")
    size: int = Field(..., description="Anzahl Gesichter im Cluster")

class ClusterPreview(BaseModel):
    cluster_id: str
    images: List[str] = Field(..., description="Pfade zu repräsentativen Bildern")
    suggested_label: Optional[str] = Field(None, description="Bereits verknüpfter Name (falls vorhanden)")
    quality_metrics: QualityMetrics
    face_ids: List[str] = Field(..., description="IDs aller Gesichter in diesem Cluster")

class StartValidationRequest(BaseModel):
    user_id: str
    sample_size: int = Field(50, description="Max. Anzahl Cluster zum Validieren")
    min_cluster_size: int = Field(2, description="Minimale Cluster-Größe")

class StartValidationResponse(BaseModel):
    clusters: List[ClusterPreview]
    total_unvalidated: int
    dbscan_eps: float = Field(..., description="Verwendeter DBSCAN epsilon-Wert")

class ValidationSubmission(BaseModel):
    cluster_id: str
    action: str = Field(..., description="validate | reject | split | merge")
    label: Optional[str] = None
    confidence: int = Field(..., ge=1, le=5, description="User-Confidence (1-5 Sterne)")
    notes: Optional[str] = None
    face_ids: List[str] = Field(..., description="Face-IDs, die validiert werden")

class ValidationResponse(BaseModel):
    success: bool
    message: str
    total_validated: int = Field(..., description="Gesamtanzahl validierter Cluster")

class ExportGroundTruthResponse(BaseModel):
    file_path: str
    total_clusters: int
    total_faces: int
    version: str

class PersonFaceInfo(BaseModel):
    face_id: str
    filename: str
    bbox: Optional[str] = None
    confidence: float
    cluster_id: str

class PersonOverviewResponse(BaseModel):
    person_name: str
    total_faces: int
    faces: List[PersonFaceInfo]

class UnlinkFaceFromPersonRequest(BaseModel):
    person_name: str
    face_id: str


# ==============================================================================
# Helper Functions
# ==============================================================================

def calculate_cluster_quality(embeddings: np.ndarray, confidences: List[float]) -> QualityMetrics:
    """
    Berechnet Qualitätsmetriken für einen Cluster.

    Args:
        embeddings: Face-Embeddings (N x 512)
        confidences: MediaPipe Detection Confidences pro Gesicht

    Returns:
        QualityMetrics mit Intra-Cluster-Metriken
    """
    # Alle paarweisen Cosine Similarities berechnen
    similarities = []
    n = len(embeddings)

    if n < 2:
        return QualityMetrics(
            avg_intra_similarity=1.0,
            min_intra_similarity=1.0,
            std_intra_similarity=0.0,
            avg_detection_conf=confidences[0] if confidences else 0.0,
            size=n
        )

    for i in range(n):
        for j in range(i+1, n):
            sim = 1.0 - cosine(embeddings[i], embeddings[j])
            similarities.append(sim)

    return QualityMetrics(
        avg_intra_similarity=float(np.mean(similarities)),
        min_intra_similarity=float(np.min(similarities)),
        std_intra_similarity=float(np.std(similarities)),
        avg_detection_conf=float(np.mean(confidences)) if confidences else 0.0,
        size=n
    )


def load_ground_truth() -> Dict[str, Any]:
    """Lädt vorhandene Ground Truth aus JSON-Datei."""
    if not GROUND_TRUTH_FILE.exists():
        return {
            "dataset_version": "1.0",
            "created_at": datetime.now().isoformat(),
            "total_clusters": 0,
            "total_faces": 0,
            "clusters": []
        }

    with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_ground_truth(data: Dict[str, Any]) -> None:
    """Speichert Ground Truth in JSON-Datei."""
    with open(GROUND_TRUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ==============================================================================
# API Endpoints
# ==============================================================================

@router.post("/start", response_model=StartValidationResponse)
async def start_validation(req: StartValidationRequest):
    """
    Startet eine Validierungs-Session und gibt Cluster-Vorschläge zurück.

    Workflow:
    1. Alle unzugeordneten Gesichter aus ChromaDB laden
    2. DBSCAN Clustering durchführen
    3. Top-N Cluster mit Qualitätsmetriken zurückgeben
    """
    from backend.rag.store import get_collection

    # Config laden für DBSCAN-Parameter
    import yaml
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    dbscan_eps = config.get("face_recognition", {}).get("dbscan_eps", 0.4)
    dbscan_min_samples = config.get("face_recognition", {}).get("dbscan_min_samples", 2)

    logger.info(f"Starting validation session for user {req.user_id} with eps={dbscan_eps}")

    # 1. Gesichter laden
    col = get_collection("faces")
    all_faces = col.get(include=["embeddings", "metadatas"])

    if not all_faces or not all_faces.get("ids"):
        return StartValidationResponse(
            clusters=[],
            total_unvalidated=0,
            dbscan_eps=dbscan_eps
        )

    # 2. Nur unzugeordnete Gesichter filtern
    embeddings, metadata_list, face_ids = [], [], []

    for i in range(len(all_faces["ids"])):
        meta = all_faces["metadatas"][i]
        entity_id = meta.get("entity_id", "")

        # Filter: Keine Zuordnung ODER nur in ground_truth validiert
        if entity_id in [None, "", "unassigned"] or meta.get("validation_status") == "pending":
            embeddings.append(all_faces["embeddings"][i])
            metadata_list.append(meta)
            face_ids.append(all_faces["ids"][i])

    if not embeddings:
        return StartValidationResponse(
            clusters=[],
            total_unvalidated=0,
            dbscan_eps=dbscan_eps
        )

    # 3. DBSCAN Clustering
    X = np.array(embeddings)
    clustering = DBSCAN(eps=dbscan_eps, min_samples=dbscan_min_samples, metric='cosine').fit(X)
    labels = clustering.labels_

    # 4. Cluster organisieren
    clusters_data = {}

    for idx, label in enumerate(labels):
        if label == -1:  # Noise ignorieren
            continue

        cluster_id = f"cluster_{label}"
        if cluster_id not in clusters_data:
            clusters_data[cluster_id] = {
                "face_ids": [],
                "embeddings": [],
                "images": [],
                "confidences": [],
                "suggested_label": None
            }

        meta = metadata_list[idx]
        clusters_data[cluster_id]["face_ids"].append(face_ids[idx])
        clusters_data[cluster_id]["embeddings"].append(embeddings[idx])
        clusters_data[cluster_id]["images"].append(meta.get("filename", ""))
        clusters_data[cluster_id]["confidences"].append(meta.get("confidence", 0.5))

        # Suggested Label (falls bereits entity_id gesetzt)
        if meta.get("entity_id") and meta["entity_id"] not in ["", "unassigned"]:
            clusters_data[cluster_id]["suggested_label"] = meta["entity_id"]

    # 5. Filter nach Mindestgröße und sortieren
    valid_clusters = [
        (cid, data) for cid, data in clusters_data.items()
        if len(data["face_ids"]) >= req.min_cluster_size
    ]
    valid_clusters.sort(key=lambda x: len(x[1]["face_ids"]), reverse=True)

    # 6. Top-N Cluster mit Metriken vorbereiten
    cluster_previews = []

    for cluster_id, data in valid_clusters[:req.sample_size]:
        # Qualitätsmetriken berechnen
        quality = calculate_cluster_quality(
            np.array(data["embeddings"]),
            data["confidences"]
        )

        # Diverse repräsentative Bilder auswählen (max 5)
        num_samples = min(len(data["images"]), 5)
        if len(data["images"]) <= num_samples:
            sample_images = data["images"]
        else:
            indices = np.linspace(0, len(data["images"]) - 1, num_samples, dtype=int)
            sample_images = [data["images"][i] for i in indices]

        cluster_previews.append(ClusterPreview(
            cluster_id=cluster_id,
            images=sample_images,
            suggested_label=data["suggested_label"],
            quality_metrics=quality,
            face_ids=data["face_ids"]
        ))

    logger.info(f"Found {len(cluster_previews)} clusters for validation (total unvalidated: {len(embeddings)})")

    return StartValidationResponse(
        clusters=cluster_previews,
        total_unvalidated=len(embeddings),
        dbscan_eps=dbscan_eps
    )


@router.post("/submit", response_model=ValidationResponse)
async def submit_validation(submission: ValidationSubmission):
    """
    Speichert eine Cluster-Validierung als Ground Truth.

    Actions:
    - validate: Cluster ist korrekt, Label speichern
    - reject: Cluster ist falsch, keine Aktion
    - split: Cluster muss aufgeteilt werden (TODO)
    - merge: Cluster sollen zusammengeführt werden (TODO)
    """
    from backend.rag.store import get_collection

    logger.info(f"Validation submission: {submission.action} for cluster {submission.cluster_id}")

    if submission.action not in ["validate", "reject", "split", "merge"]:
        raise HTTPException(status_code=400, detail="Invalid action")

    # 1. Ground Truth laden
    gt_data = load_ground_truth()

    # 2. Neue Validierung hinzufügen (nur bei "validate")
    if submission.action == "validate":
        if not submission.label:
            raise HTTPException(status_code=400, detail="Label required for validation")

        # Gesichter-Daten aus ChromaDB holen
        col = get_collection("faces")
        faces = col.get(ids=submission.face_ids, include=["embeddings", "metadatas"])

        if not faces or not faces["ids"]:
            raise HTTPException(status_code=404, detail="Face IDs not found in database")

        # Embeddings sammeln
        embeddings_list = [faces["embeddings"][i] for i in range(len(faces["ids"]))]
        image_paths = [faces["metadatas"][i].get("filename", "") for i in range(len(faces["ids"]))]
        confidences = [faces["metadatas"][i].get("confidence", 0.0) for i in range(len(faces["ids"]))]

        # Qualitätsmetriken berechnen
        quality = calculate_cluster_quality(np.array(embeddings_list), confidences)

        # Neuer Ground Truth Cluster
        gt_cluster = {
            "cluster_id": f"gt_{submission.cluster_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "original_cluster_id": submission.cluster_id,
            "label": submission.label,
            "face_count": len(submission.face_ids),
            "face_ids": submission.face_ids,
            "embeddings": [emb.tolist() for emb in embeddings_list],  # Serialize numpy arrays
            "image_paths": image_paths,
            "validation_status": "validated",
            "validated_at": datetime.now().isoformat(),
            "confidence": submission.confidence,
            "notes": submission.notes or "",
            "quality_metrics": quality.dict()
        }

        gt_data["clusters"].append(gt_cluster)
        gt_data["total_clusters"] = len(gt_data["clusters"])
        gt_data["total_faces"] = sum(c["face_count"] for c in gt_data["clusters"])
        gt_data["last_updated"] = datetime.now().isoformat()

        # 3. Ground Truth speichern
        save_ground_truth(gt_data)

        # 4. Metadaten in ChromaDB updaten (validation_status markieren + entity_id setzen)
        # WICHTIG: Kopien erstellen, nicht Referenzen ändern!
        updated_metas = []
        for i, face_id in enumerate(submission.face_ids):
            meta = faces["metadatas"][i]
            # Kopie erstellen
            new_meta = dict(meta)
            new_meta["validation_status"] = "validated"
            new_meta["gt_label"] = submission.label
            new_meta["gt_cluster_id"] = gt_cluster["cluster_id"]
            # NEU: Entity-Verknüpfung direkt setzen
            new_meta["entity_id"] = submission.label
            new_meta["cluster_id"] = submission.cluster_id
            updated_metas.append(new_meta)

        # Batch-Update
        col.update(ids=submission.face_ids, metadatas=updated_metas)
        logger.info(f"Updated {len(submission.face_ids)} faces with entity_id='{submission.label}' (validation)")

        # 5. Entity Graph in Elasticsearch aktualisieren
        from backend.rag.es_store import get_es_client, get_index_name
        es = get_es_client()
        index_name = get_index_name("entities")

        if not es.indices.exists(index=index_name):
            es.indices.create(index=index_name)

        try:
            res = es.get(index=index_name, id=submission.label)
            entity = res["_source"]
            if gt_cluster["cluster_id"] not in entity.setdefault("vision_clusters", []):
                entity["vision_clusters"].append(gt_cluster["cluster_id"])
        except Exception:
            entity = {
                "entity_id": submission.label,
                "chat_aliases": [],
                "vision_clusters": [gt_cluster["cluster_id"]]
            }

        es.index(index=index_name, id=submission.label, document=entity)
        es.indices.refresh(index=index_name)

        # 6. Fotos aktualisieren (Sync)
        from backend.api.v1.entities import _sync_photo_persons
        for face_id in submission.face_ids:
            _sync_photo_persons(face_id)

        logger.info(f"✅ Validated cluster {submission.cluster_id} as '{submission.label}' with {len(submission.face_ids)} faces")

    elif submission.action == "reject":
        # Rejected Cluster markieren (optional logging)
        logger.info(f"❌ Rejected cluster {submission.cluster_id}")

    return ValidationResponse(
        success=True,
        message=f"Validation '{submission.action}' processed successfully",
        total_validated=gt_data["total_clusters"]
    )


@router.get("/export", response_model=ExportGroundTruthResponse)
async def export_ground_truth():
    """
    Exportiert validierte Ground Truth als JSON-Datei.

    Returns:
        Pfad zur Datei und Statistiken
    """
    gt_data = load_ground_truth()

    return ExportGroundTruthResponse(
        file_path=str(GROUND_TRUTH_FILE),
        total_clusters=gt_data["total_clusters"],
        total_faces=gt_data["total_faces"],
        version=gt_data["dataset_version"]
    )


@router.post("/repair/migrate-ground-truth")
async def repair_migrate_ground_truth():
    """
    REPARATUR: Migriert alte Ground-Truth-Daten nach ChromaDB und Elasticsearch.

    Nutze diesen Endpunkt, wenn Personen in den Statistiken erscheinen,
    aber nicht in der Personen-Liste.

    WICHTIG: Überspringt Multi-Person-Labels (z.B. "Sarah, Nora, Frieda")
    """
    from backend.rag.store import get_collection
    from backend.rag.es_store import get_es_client, get_index_name
    from backend.api.v1.entities import _sync_photo_persons

    gt_data = load_ground_truth()

    if not gt_data.get("clusters"):
        return {"success": False, "message": "Keine Ground Truth Daten gefunden"}

    col = get_collection("faces")
    es = get_es_client()
    index_name = get_index_name("entities")

    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name)

    migrated_persons = {}
    skipped_multi_person = []
    processed_face_ids = set()  # Duplikate vermeiden

    for cluster in gt_data["clusters"]:
        label = cluster["label"]
        face_ids = cluster["face_ids"]

        # SKIP: Multi-Person-Labels (enthalten Komma)
        if "," in label:
            skipped_multi_person.append(f"{label} ({len(face_ids)} Gesichter)")
            logger.warning(f"Skipping multi-person label: '{label}'")
            continue

        # SKIP: Gesichter die bereits verarbeitet wurden (Duplikate)
        new_face_ids = [fid for fid in face_ids if fid not in processed_face_ids]
        if not new_face_ids:
            logger.info(f"Skipping duplicate cluster for '{label}'")
            continue

        logger.info(f"Migrating '{label}': {len(new_face_ids)} faces")

        # 1. ChromaDB updaten
        faces = col.get(ids=new_face_ids, include=["metadatas"])

        if faces and faces["ids"]:
            updated_metas = []
            for i, face_id in enumerate(faces["ids"]):
                meta = faces["metadatas"][i]
                new_meta = dict(meta)
                new_meta["entity_id"] = label
                new_meta["validation_status"] = "validated"
                new_meta["gt_label"] = label
                new_meta["gt_cluster_id"] = cluster["cluster_id"]
                updated_metas.append(new_meta)
                processed_face_ids.add(face_id)

            col.update(ids=faces["ids"], metadatas=updated_metas)
            migrated_persons[label] = migrated_persons.get(label, 0) + len(faces["ids"])

        # 2. Elasticsearch updaten
        try:
            res = es.get(index=index_name, id=label)
            entity = res["_source"]
            if cluster["cluster_id"] not in entity.setdefault("vision_clusters", []):
                entity["vision_clusters"].append(cluster["cluster_id"])
        except Exception:
            entity = {
                "entity_id": label,
                "chat_aliases": [],
                "vision_clusters": [cluster["cluster_id"]]
            }

        es.index(index=index_name, id=label, document=entity)

        # 3. Fotos syncen (nur für neue Gesichter)
        for face_id in new_face_ids:
            try:
                _sync_photo_persons(face_id)
            except Exception as e:
                logger.warning(f"Photo sync failed for {face_id}: {e}")

    es.indices.refresh(index=index_name)

    result = {
        "success": True,
        "message": f"Ground Truth migriert: {len(migrated_persons)} Personen",
        "persons": migrated_persons
    }

    if skipped_multi_person:
        result["warnings"] = {
            "skipped_multi_person_labels": skipped_multi_person,
            "message": "Multi-Person-Labels können nicht automatisch migriert werden. Bitte einzeln im Personen-Tab zuordnen."
        }

    return result


@router.get("/stats")
async def get_validation_stats():
    """
    Gibt Statistiken über validierte Cluster zurück.
    """
    gt_data = load_ground_truth()

    # Metriken aggregieren
    if gt_data["clusters"]:
        avg_quality = np.mean([c["quality_metrics"]["avg_intra_similarity"] for c in gt_data["clusters"]])
        avg_size = np.mean([c["face_count"] for c in gt_data["clusters"]])

        # Label-Verteilung
        label_counts = {}
        for cluster in gt_data["clusters"]:
            label = cluster["label"]
            label_counts[label] = label_counts.get(label, 0) + 1
    else:
        avg_quality = 0.0
        avg_size = 0.0
        label_counts = {}

    return {
        "total_clusters": gt_data["total_clusters"],
        "total_faces": gt_data["total_faces"],
        "avg_cluster_quality": float(avg_quality),
        "avg_cluster_size": float(avg_size),
        "label_distribution": label_counts,
        "last_updated": gt_data.get("last_updated", "never")
    }


@router.get("/persons")
async def list_validated_persons():
    """
    Listet alle Personen auf, die durch Validierung erstellt wurden.
    """
    from backend.rag.store import get_collection

    col = get_collection("faces")
    all_faces = col.get(
        where={"validation_status": "validated"},
        include=["metadatas"]
    )

    if not all_faces or not all_faces.get("ids"):
        return {"persons": []}

    # Personen gruppieren
    persons_map = {}
    for i, face_id in enumerate(all_faces["ids"]):
        meta = all_faces["metadatas"][i]
        entity_id = meta.get("entity_id") or meta.get("gt_label")

        if not entity_id or entity_id == "unassigned":
            continue

        if entity_id not in persons_map:
            persons_map[entity_id] = {
                "name": entity_id,
                "face_count": 0,
                "preview_image": meta.get("filename", "")
            }

        persons_map[entity_id]["face_count"] += 1

    persons = sorted(persons_map.values(), key=lambda x: x["face_count"], reverse=True)

    return {"persons": persons}


@router.get("/persons/{person_name}", response_model=PersonOverviewResponse)
async def get_person_faces(person_name: str):
    """
    Gibt alle Gesichter einer Person zurück (für Validierungs-Review).
    """
    from backend.rag.store import get_collection

    col = get_collection("faces")

    # Suche nach entity_id ODER gt_label
    faces_by_entity = col.get(
        where={"entity_id": person_name},
        include=["metadatas"]
    )

    faces_by_label = col.get(
        where={"gt_label": person_name},
        include=["metadatas"]
    )

    # Merge beide Ergebnisse
    all_face_ids = set()
    face_data = []

    for result in [faces_by_entity, faces_by_label]:
        if result and result.get("ids"):
            for i, face_id in enumerate(result["ids"]):
                if face_id in all_face_ids:
                    continue

                all_face_ids.add(face_id)
                meta = result["metadatas"][i]

                face_data.append(PersonFaceInfo(
                    face_id=face_id,
                    filename=meta.get("filename", ""),
                    bbox=meta.get("bbox"),
                    confidence=meta.get("confidence", 0.0),
                    cluster_id=meta.get("cluster_id", "")
                ))

    return PersonOverviewResponse(
        person_name=person_name,
        total_faces=len(face_data),
        faces=face_data
    )


@router.post("/persons/unlink-face")
async def unlink_face_from_person(req: UnlinkFaceFromPersonRequest):
    """
    Entfernt ein Gesicht aus einer Person (markiert es als unassigned).
    """
    from backend.rag.store import get_collection
    from backend.api.v1.entities import _sync_photo_persons

    col = get_collection("faces")

    # Gesicht laden
    face_data = col.get(ids=[req.face_id], include=["metadatas"])

    if not face_data or not face_data.get("ids"):
        raise HTTPException(status_code=404, detail="Face not found")

    meta = face_data["metadatas"][0]

    # Validierung: Gehört es zur angegebenen Person?
    current_entity = meta.get("entity_id") or meta.get("gt_label")
    if current_entity != req.person_name:
        raise HTTPException(
            status_code=400,
            detail=f"Face belongs to '{current_entity}', not '{req.person_name}'"
        )

    # Zurücksetzen
    meta["entity_id"] = "unassigned"
    meta["cluster_id"] = ""
    meta["validation_status"] = "pending"
    meta["gt_label"] = ""
    meta["gt_cluster_id"] = ""

    col.update(ids=[req.face_id], metadatas=[meta])

    # Foto-Sync
    _sync_photo_persons(req.face_id)

    logger.info(f"Unlinked face {req.face_id} from person '{req.person_name}'")

    return {
        "success": True,
        "message": f"Face removed from '{req.person_name}'"
    }
