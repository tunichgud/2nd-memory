#!/usr/bin/env python3
"""
migrate_ground_truth.py
=======================
Wartungsskript: Migriert alte Ground-Truth-Validierungen nach ChromaDB und Elasticsearch.

Problem:
    Wenn Personen in den Validierungs-Statistiken erscheinen, aber nicht in der
    Personen-Liste, dann wurden sie nur in der Ground-Truth-JSON gespeichert,
    aber nicht in ChromaDB/Elasticsearch.

Lösung:
    Dieses Skript liest die Ground-Truth-Datei und schreibt alle Zuordnungen
    in ChromaDB und Elasticsearch.

Verwendung:
    python tools/migrate_ground_truth.py

    Oder via API:
    curl -X POST http://localhost:8000/api/v1/validation/repair/migrate-ground-truth
"""

import sys
import json
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.rag.store import get_collection
from backend.rag.es_store import get_es_client, get_index_name

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def load_ground_truth():
    """Lädt die Ground Truth JSON-Datei."""
    gt_file = Path(__file__).parent.parent / "data" / "ground_truth" / "validated_clusters.json"

    if not gt_file.exists():
        logger.error(f"Ground Truth Datei nicht gefunden: {gt_file}")
        return None

    with open(gt_file, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate():
    """Führt die Migration durch."""
    logger.info("Starte Ground Truth Migration...")

    # 1. Ground Truth laden
    gt_data = load_ground_truth()

    if not gt_data or not gt_data.get("clusters"):
        logger.warning("Keine Ground Truth Daten gefunden")
        return

    logger.info(f"Gefunden: {len(gt_data['clusters'])} Cluster, {gt_data.get('total_faces', 0)} Gesichter")

    # 2. ChromaDB und Elasticsearch initialisieren
    col = get_collection("faces")
    es = get_es_client()
    index_name = get_index_name("entities")

    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name)
        logger.info(f"Elasticsearch Index erstellt: {index_name}")

    # 3. Migration durchführen
    migrated_persons = {}
    skipped_multi_person = []
    processed_face_ids = set()  # Duplikate vermeiden

    for cluster in gt_data["clusters"]:
        label = cluster["label"]
        face_ids = cluster["face_ids"]

        # SKIP: Multi-Person-Labels (enthalten Komma)
        if "," in label:
            skipped_multi_person.append(f"{label} ({len(face_ids)} Gesichter)")
            logger.warning(f"⚠️  SKIP: Multi-Person-Label '{label}'")
            continue

        # SKIP: Duplikate
        new_face_ids = [fid for fid in face_ids if fid not in processed_face_ids]
        if not new_face_ids:
            logger.info(f"⏭️  SKIP: Duplicate cluster for '{label}'")
            continue

        logger.info(f"Migriere Cluster '{label}' mit {len(new_face_ids)} Gesichtern...")

        # ChromaDB updaten
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
            logger.info(f"  ✓ ChromaDB: {len(faces['ids'])} Gesichter aktualisiert")

        # Elasticsearch updaten
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
        logger.info(f"  ✓ Elasticsearch: Entity '{label}' aktualisiert")

    es.indices.refresh(index=index_name)

    # 4. Zusammenfassung
    logger.info("\n" + "="*70)
    logger.info("✅ Migration abgeschlossen!")
    logger.info(f"   Migrierte Personen: {len(migrated_persons)}")
    for person, count in sorted(migrated_persons.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"   - {person}: {count} Gesichter")

    if skipped_multi_person:
        logger.info("\n⚠️  Übersprungene Multi-Person-Labels:")
        for entry in skipped_multi_person:
            logger.info(f"   - {entry}")
        logger.info("\n   → Diese müssen manuell im Personen-Tab einzeln zugeordnet werden.")

    logger.info("="*70)


if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        logger.error(f"Fehler bei der Migration: {e}", exc_info=True)
        sys.exit(1)
