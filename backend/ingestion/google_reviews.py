"""
google_reviews.py – Google Maps Bewertungen Ingestion für memosaur.

Liest Bewertungen.json aus dem Google Takeout und indexiert alle 47 Einträge.
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
    """Erstellt den Dokumenttext für eine Bewertung."""
    props = feature.get("properties", {})
    loc = props.get("location", {})
    coords = feature.get("geometry", {}).get("coordinates", [0, 0])

    parts = []

    name = loc.get("name", "")
    if name:
        parts.append(f"Bewertung: {name}")

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
            parts.append(f"Datum: {dt.strftime('%d.%m.%Y')}")
        except ValueError:
            parts.append(f"Datum: {date_str}")

    rating = props.get("five_star_rating_published", 0)
    if rating:
        parts.append(f"Bewertung: {rating}/5 Sterne")

    review_text = props.get("review_text_published", "")
    if review_text:
        parts.append(f"Rezension: {review_text}")

    # Strukturierte Unterfragen (Essen, Service, Ambiente etc.)
    questions = props.get("questions", [])
    if questions:
        q_parts = []
        for q in questions:
            q_name = q.get("question", "")
            q_option = q.get("selected_option", "")
            q_rating = q.get("rating", 0)
            if q_option:
                q_parts.append(f"{q_name}: {q_option}")
            elif q_rating:
                q_parts.append(f"{q_name}: {q_rating}/5")
        if q_parts:
            parts.append("Details: " + ", ".join(q_parts))

    return "\n".join(parts)


def ingest_reviews(
    progress_callback: Callable[[int, int, str], None] | None = None,
    reset: bool = False,
) -> dict:
    """Liest alle Google Maps Bewertungen und speichert sie in Elasticsearch."""
    from backend.rag.embedder import embed_single
    from backend.rag.store_es import upsert_documents_v2
    from backend.rag.es_store import reset_es_index

    cfg = _load_config()
    reviews_path = BASE_DIR / cfg["paths"]["reviews_file"]

    if not reviews_path.exists():
        logger.error("Bewertungen.json nicht gefunden: %s", reviews_path)
        return {"total": 0, "success": 0, "errors": 1}

    data = json.loads(reviews_path.read_text(encoding="utf-8"))
    features = data.get("features", [])
    total = len(features)
    logger.info("%d Bewertungen gefunden.", total)

    if reset:
        reset_es_index("reviews")

    stats = {"total": total, "success": 0, "errors": 0}
    ids, documents, embeddings, metadatas = [], [], [], []

    for idx, feature in enumerate(features, start=1):
        props = feature.get("properties", {})
        loc = props.get("location", {})
        coords = feature.get("geometry", {}).get("coordinates", [0, 0])

        name = loc.get("name", f"Ort_{idx}")
        status = f"Bewertung [{idx}/{total}]: {name}"
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

        # Koordinaten (GeoJSON: [lon, lat])
        lat = coords[1] if len(coords) >= 2 else 0.0
        lon = coords[0] if len(coords) >= 2 else 0.0

        try:
            embedding = embed_single(doc_text)
        except Exception as exc:
            logger.error("Embedding-Fehler für Bewertung '%s': %s", name, exc)
            stats["errors"] += 1
            continue

        chroma_meta = {
            "source": "google_reviews",
            "name": name,
            "address": loc.get("address", ""),
            "country": loc.get("country_code", ""),
            "date_ts": date_ts,
            "date_iso": date_str,
            "lat": lat,
            "lon": lon,
            "rating": props.get("five_star_rating_published", 0),
            "maps_url": props.get("google_maps_url", ""),
        }

        ids.append(f"review_{idx:03d}_{name[:30].replace(' ', '_')}")
        documents.append(doc_text)
        embeddings.append(embedding)
        metadatas.append(chroma_meta)
        stats["success"] += 1

    if ids:
        upsert_documents_v2("reviews", ids, documents, embeddings, metadatas)

    logger.info("Bewertungs-Ingestion abgeschlossen: %s", stats)
    return stats
