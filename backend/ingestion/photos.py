"""
photos.py – Google Fotos Ingestion für memosaur.

Ablauf:
  1. Sample-Liste (sample/photo_sample.json) laden
  2. Fotos aus ZIP-Archiven oder extrahiertem Ordner lesen
  3. Sidecar-JSON auslesen (GPS, Datum, People-Tags)
  4. Bildbeschreibung via Vision-LLM generieren
  5. Dokument in ChromaDB speichern

Fortschritt wird via Callback gemeldet (für SSE-Streaming im API).
"""

from __future__ import annotations

import json
import logging
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
SAMPLE_FILE = BASE_DIR / "sample" / "photo_sample.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# ---------------------------------------------------------------------------
# Reverse Geocoding (GPS → Ortsname via Nominatim, gecacht)
# ---------------------------------------------------------------------------

_geo_cache: dict[tuple, str] = {}


def _reverse_geocode(lat: float, lon: float) -> str:
    """Löst GPS-Koordinaten in einen lesbaren Ortsnamen auf (Nominatim/OSM).

    Koordinaten werden auf 2 Dezimalstellen gerundet für Cache-Effizienz
    (~1km Genauigkeit, reicht für Ortsnamen).
    Gibt leeren String zurück falls kein Ergebnis oder Fehler.
    """
    if not lat or not lon or (lat == 0.0 and lon == 0.0):
        return ""

    key = (round(lat, 2), round(lon, 2))
    if key in _geo_cache:
        return _geo_cache[key]

    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError

        geolocator = Nominatim(user_agent="memosaur/1.0")
        location = geolocator.reverse(
            (lat, lon),
            language="de",
            zoom=12,          # Stadtebene
            timeout=5,
        )
        if location and location.raw:
            addr = location.raw.get("address", {})
            # Ortsnamen in Prioritätsreihenfolge
            name = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("municipality")
                or addr.get("county")
                or addr.get("state")
                or ""
            )
            country = addr.get("country", "")
            state = addr.get("state", "")

            if name and country:
                # z.B. "München, Bayern, Deutschland"
                parts = [name]
                if state and state != name:
                    parts.append(state)
                parts.append(country)
                result = ", ".join(parts)
            elif name:
                result = name
            else:
                result = ""

            _geo_cache[key] = result
            # Nominatim Policy: max 1 Request/Sekunde
            time.sleep(1.1)
            return result

    except Exception as exc:
        logger.debug("Reverse Geocoding fehlgeschlagen für %.4f,%.4f: %s", lat, lon, exc)

    _geo_cache[key] = ""
    return ""


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    import yaml
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _find_photo_in_zips(filename: str, takeout_dir: Path) -> tuple[bytes, dict] | None:
    """Sucht ein Foto in allen ZIP-Archiven und gibt (bytes, sidecar_meta) zurück."""
    for zip_path in sorted(takeout_dir.glob("*.zip")):
        try:
            with zipfile.ZipFile(zip_path) as zf:
                name_set = set(zf.namelist())
                # Suche nach dem Dateinamen irgendwo im ZIP
                matches = [e for e in name_set if Path(e).name == filename]
                if not matches:
                    continue
                entry = matches[0]

                # Bildbytes laden
                image_bytes = zf.read(entry)

                # Sidecar-Metadaten laden
                meta = {}
                meta_entry = entry + ".supplemental-metadata.json"
                if meta_entry in name_set:
                    try:
                        meta = json.loads(zf.read(meta_entry))
                    except (json.JSONDecodeError, KeyError):
                        pass

                return image_bytes, meta
        except Exception as exc:
            logger.warning("Fehler beim Lesen von %s: %s", zip_path.name, exc)
            continue
    return None


def _find_photo_in_dir(filename: str, photos_dir: Path) -> tuple[bytes, dict] | None:
    """Sucht ein Foto im extrahierten Verzeichnis."""
    photo_path = photos_dir / filename
    if not photo_path.exists():
        return None

    image_bytes = photo_path.read_bytes()

    # Sidecar laden
    meta = {}
    meta_path = photos_dir / (filename + ".supplemental-metadata.json")
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return image_bytes, meta


def _parse_metadata(meta: dict, filename: str) -> dict:
    """Extrahiert relevante Felder aus dem Sidecar-JSON."""
    # Aufnahmezeit
    taken_ts = 0
    taken_iso = ""
    for key in ("photoTakenTime", "creationTime"):
        if key in meta:
            try:
                taken_ts = int(meta[key]["timestamp"])
                taken_iso = datetime.fromtimestamp(taken_ts, tz=timezone.utc).isoformat()
                break
            except (KeyError, ValueError, OSError):
                pass

    # Fallback: Datum aus Dateiname (YYYYMMDD_HHMMSS)
    if not taken_iso and len(filename) >= 15:
        try:
            dt = datetime.strptime(filename[:15], "%Y%m%d_%H%M%S")
            taken_ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
            taken_iso = dt.isoformat()
        except ValueError:
            pass

    # GPS
    lat, lon, alt = None, None, None
    for geo_key in ("geoData", "geoDataExif"):
        g = meta.get(geo_key, {})
        if g.get("latitude") or g.get("longitude"):
            lat = g.get("latitude")
            lon = g.get("longitude")
            alt = g.get("altitude")
            break

    # Personen
    people = [p["name"] for p in meta.get("people", []) if p.get("name")]

    return {
        "date_ts": taken_ts,
        "date_iso": taken_iso,
        "lat": lat,
        "lon": lon,
        "alt": alt,
        "people": people,
    }


def _build_document(filename: str, parsed: dict, description: str, place_name: str = "") -> str:
    """Erstellt den Dokumenttext für ChromaDB."""
    parts = [f"Foto: {filename}"]

    if parsed["date_iso"]:
        try:
            dt = datetime.fromisoformat(parsed["date_iso"])
            parts.append(f"Datum: {dt.strftime('%d.%m.%Y um %H:%M Uhr')}")
        except ValueError:
            parts.append(f"Datum: {parsed['date_iso']}")

    if place_name:
        parts.append(f"Ort: {place_name}")

    if parsed["lat"] and parsed["lon"]:
        parts.append(f"Koordinaten: {parsed['lat']:.5f}°N, {parsed['lon']:.5f}°E")

    if parsed["people"]:
        parts.append(f"Personen: {', '.join(parsed['people'])}")

    if description:
        parts.append(f"Bildbeschreibung: {description}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Haupt-Ingestion
# ---------------------------------------------------------------------------

def ingest_photos(
    progress_callback: Callable[[int, int, str], None] | None = None,
    reset: bool = False,
    user_id: str = "00000000-0000-0000-0000-000000000001",
    limit: int | None = None,
) -> dict:
    """Liest Fotos ein, beschreibt sie per KI und speichert sie in ChromaDB & ES.

    Args:
        progress_callback: Wird mit (aktuell, gesamt, status_text) aufgerufen.
        reset: Falls True, wird die Collection vorher geleert.
        user_id: Die ID des Nutzers.
        limit: Maximale Anzahl an neuen Fotos (zusätzlich zum Sample falls konfiguriert).

    Returns:
        Dict mit Statistiken: total, success, skipped, errors
    """
    from backend.llm.connector import describe_image
    from backend.rag.embedder import embed_single
    from backend.rag.es_store import reset_es_index

    cfg = _load_config()
    photos_dir = BASE_DIR / cfg["paths"]["photos_dir"]
    takeout_root = BASE_DIR / "takeout"

    # 1. Bereits indexierte IDs laden (falls kein Reset)
    indexed_ids = set()
    if not reset:
        try:
            from backend.rag.es_store import get_all_documents_es
            hits = get_all_documents_es(collection_name="photos", user_id=user_id)
            indexed_ids = {h["id"] for h in hits}
            logger.info("Bereits %d Fotos in DB vorhanden (Skip-Modus aktiv).", len(indexed_ids))
        except Exception:
            pass
    
    # 1. Sample-Liste laden (Basis-Set)
    sample_list: list[dict] = []
    if SAMPLE_FILE.exists():
        sample_list = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    
    sample_filenames = {s["filename"] for s in sample_list}
    
    # 2. Ordner scannen für zusätzliche Bilder (falls gewünscht)
    target_count = cfg.get("ingestion", {}).get("photo_sample_size", 50)
    if limit:
        target_count = limit
        
    all_files = sorted([f.name for f in photos_dir.glob("*") if f.suffix.lower() in IMAGE_EXTENSIONS])
    
    # Kombinierte Liste erstellen: erst Samples, dann neue
    final_list = []
    # Zuerst Sample-Einträge
    for s in sample_list:
        final_list.append(s)
        
    # Dann restliche Dateien auffüllen bis target_count oder alle
    for fname in all_files:
        if fname not in sample_filenames:
            final_list.append({"filename": fname})
        
        if len(final_list) >= target_count and target_count > 0:
            break

    total = len(final_list)
    if reset:
        reset_es_index("photos")
        logger.info("Photos-Index zurückgesetzt.")

    stats = {"total": total, "success": 0, "skipped": 0, "errors": 0}
    ids, documents, embeddings, metadatas = [], [], [], []

    for idx, entry in enumerate(final_list, start=1):
        filename = entry["filename"]
        
        # Skip falls bereits indexiert
        if f"photo_{filename}" in indexed_ids:
            # logger.debug("Überspringe bereits indexiertes Foto: %s", filename)
            stats["skipped"] += 1
            continue

        status = f"Verarbeite [{idx}/{total}]: {filename}"
        logger.info(status)
        if progress_callback:
            progress_callback(idx, total, status)

        # Foto laden
        result = _find_photo_in_dir(filename, photos_dir)
        if result is None:
            result = _find_photo_in_zips(filename, takeout_root)

        if result is None:
            logger.warning("Foto nicht gefunden: %s", filename)
            stats["skipped"] += 1
            continue

        image_bytes, meta = result
        parsed = _parse_metadata(meta, filename)

        # Fallback auf Koordinaten aus der Liste (falls vorhanden und Sidecar leer)
        if (not parsed["lat"] or parsed["lat"] == 0.0) and "lat" in entry:
            parsed["lat"] = entry["lat"]
            parsed["lon"] = entry["lon"]
            logger.info("  Nutze Fallback-Koordinaten: %.4f, %.4f", parsed["lat"], parsed["lon"])
        
        # Personen aus Liste ergänzen
        sample_people = entry.get("persons", [])
        if isinstance(sample_people, str):
            sample_people = [p.strip() for p in sample_people.split(",") if p.strip()]
        for p in sample_people:
            if p not in parsed["people"]:
                parsed["people"].append(p)

        # Reverse Geocoding
        place_name = ""
        if parsed["lat"] and parsed["lon"]:
            place_name = _reverse_geocode(parsed["lat"], parsed["lon"])
            if place_name:
                logger.info("  Ort: %s", place_name)

        # KI-Beschreibung
        try:
            description = describe_image(image_bytes)
            # Kurze Pause für VRAM
            time.sleep(1)
        except Exception as exc:
            logger.warning("Vision-Fehler für %s: %s", filename, exc)
            description = ""
            time.sleep(2)

        doc_text = _build_document(filename, parsed, description, place_name=place_name)

        try:
            embedding = embed_single(doc_text)
        except Exception as exc:
            logger.error("Embedding-Fehler für %s: %s", filename, exc)
            stats["errors"] += 1
            continue

        # Metadaten
        from backend.rag.query_parser import _person_field
        from backend.ingestion.persons import get_known_persons
        known = get_known_persons()
        persons_str = ",".join(parsed["people"])
        person_flags = {
            _person_field(n): (n.split()[0].lower() in persons_str.lower() or n.lower() in persons_str.lower())
            for n in known
        }

        chroma_meta = {
            "source": "google_photos",
            "filename": filename,
            "date_ts": parsed["date_ts"] or 0,
            "date_iso": parsed["date_iso"] or "",
            "lat": parsed["lat"] or 0.0,
            "lon": parsed["lon"] or 0.0,
            "alt": parsed["alt"] or 0.0,
            "persons": persons_str,
            "cluster": entry.get("cluster", ""),
            "place_name": place_name,
            "user_id": user_id,
            **person_flags,
        }

        ids.append(f"photo_{filename}")
        documents.append(doc_text)
        embeddings.append(embedding)
        metadatas.append(chroma_meta)
        stats["success"] += 1

        # 🚀 Echtzeit-Gesichtserkennung
        try:
            from backend.ingestion.faces import process_and_store_faces
            process_and_store_faces(f"photo_{filename}", image_bytes, chroma_meta)
        except Exception as exc:
            logger.warning("Gesichtserkennung fehlgeschlagen für %s: %s", filename, exc)

        # Regelmäßiger Checkpoint-Upsert (Batching)
        if len(ids) >= 10:
            _flush_to_stores(ids, documents, embeddings, metadatas, reset and idx <= 10)
            ids, documents, embeddings, metadatas = [], [], [], []

    # Finaler Flush
    if ids:
        _flush_to_stores(ids, documents, embeddings, metadatas, reset and total <= 10)

    logger.info("Foto-Ingestion abgeschlossen: %s", stats)
    return stats


def _flush_to_stores(ids, documents, embeddings, metadatas, first_batch_reset):
    from backend.rag.store_es import upsert_documents_v2
    upsert_documents_v2("photos", ids, documents, embeddings, metadatas)
