"""
google_saved.py – Google Maps Gespeicherte Orte Ingestion für memosaur.

Liest Gespeicherte Orte.json aus dem Google Takeout und indexiert alle 210 Einträge.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]


def _load_config() -> dict:
    import yaml
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_document(feature: dict) -> str:
    """Erstellt den Dokumenttext für einen gespeicherten Ort."""
    props = feature.get("properties", {})
    loc = props.get("location", {})
    coords = feature.get("geometry", {}).get("coordinates", [0, 0])

    # Koordinaten aus URL extrahieren falls [0,0]
    if (not coords or coords == [0, 0]) and props.get("google_maps_url", ""):
        import re
        match = re.search(r"[?&]q=([-\d.]+),([-\d.]+)", props["google_maps_url"])
        if match:
            coords = [float(match.group(2)), float(match.group(1))]  # [lon, lat]

    parts = []

    name = loc.get("name", "")
    if name:
        parts.append(f"Gespeicherter Ort: {name}")

    addr = loc.get("address", "")
    if addr:
        parts.append(f"Adresse: {addr}")

    country = loc.get("country_code", "")
    if country:
        parts.append(f"Land: {country}")

    if coords and len(coords) >= 2 and (coords[0] or coords[1]):
        parts.append(f"Koordinaten: {coords[1]:.5f}°N, {coords[0]:.5f}°E")

    date_str = props.get("date", "")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            parts.append(f"Gespeichert am: {dt.strftime('%d.%m.%Y')}")
        except ValueError:
            parts.append(f"Datum: {date_str}")

    comment = props.get("Comment", "")
    # Generischen Standardkommentar weglassen
    if comment and "keine Informationen verfügbar" not in comment:
        parts.append(f"Kommentar: {comment}")

    return "\n".join(parts)


def ingest_saved_places(
    progress_callback: Callable[[int, int, str], None] | None = None,
    reset: bool = False,
) -> dict:
    """Liest alle gespeicherten Google Maps Orte und speichert sie in Elasticsearch."""
    from backend.rag.embedder import embed_single
    from backend.rag.store_es import upsert_documents_v2
    from backend.rag.es_store import reset_es_index

    cfg = _load_config()
    saved_path = BASE_DIR / cfg["paths"]["saved_places_file"]

    if not saved_path.exists():
        logger.error("Gespeicherte Orte.json nicht gefunden: %s", saved_path)
        return {"total": 0, "success": 0, "errors": 1}

    data = json.loads(saved_path.read_text(encoding="utf-8"))
    features = data.get("features", [])
    total = len(features)
    logger.info("%d gespeicherte Orte gefunden.", total)

    if reset:
        reset_es_index("saved_places")

    stats = {"total": total, "success": 0, "errors": 0}
    ids, documents, embeddings, metadatas = [], [], [], []

    for idx, feature in enumerate(features, start=1):
        props = feature.get("properties", {})
        loc = props.get("location", {})
        coords = feature.get("geometry", {}).get("coordinates", [0, 0])

        # Koordinaten aus URL wenn nötig
        if (not coords or coords == [0, 0]) and props.get("google_maps_url", ""):
            import re
            match = re.search(r"[?&]q=([-\d.]+),([-\d.]+)", props.get("google_maps_url", ""))
            if match:
                coords = [float(match.group(2)), float(match.group(1))]

        name = loc.get("name", f"Ort_{idx}")
        status = f"Gespeicherter Ort [{idx}/{total}]: {name}"
        logger.info(status)
        if progress_callback:
            progress_callback(idx, total, status)

        doc_text = _build_document(feature)

        # Datum als Timestamp
        date_ts = 0
        date_str = props.get("date", "")
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_ts = int(dt.timestamp())
            except ValueError:
                pass

        lat = coords[1] if coords and len(coords) >= 2 else 0.0
        lon = coords[0] if coords and len(coords) >= 2 else 0.0

        try:
            embedding = embed_single(doc_text)
        except Exception as exc:
            logger.error("Embedding-Fehler für Ort '%s': %s", name, exc)
            stats["errors"] += 1
            continue

        chroma_meta = {
            "source": "google_saved",
            "name": name,
            "address": loc.get("address", ""),
            "country": loc.get("country_code", ""),
            "date_ts": date_ts,
            "date_iso": date_str,
            "lat": lat,
            "lon": lon,
            "maps_url": props.get("google_maps_url", ""),
        }

        ids.append(f"saved_{idx:03d}_{name[:30].replace(' ', '_')}")
        documents.append(doc_text)
        embeddings.append(embedding)
        metadatas.append(chroma_meta)
        stats["success"] += 1

    if ids:
        upsert_documents_v2("saved_places", ids, documents, embeddings, metadatas)

    logger.info("Gespeicherte-Orte-Ingestion abgeschlossen: %s", stats)
    return stats
