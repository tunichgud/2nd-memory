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
) -> dict:
    """Liest alle 50 Sample-Fotos ein, beschreibt sie per KI und speichert sie in ChromaDB.

    Args:
        progress_callback: Wird mit (aktuell, gesamt, status_text) aufgerufen.
        reset: Falls True, wird die Collection vorher geleert.

    Returns:
        Dict mit Statistiken: total, success, skipped, errors
    """
    from backend.llm.connector import describe_image
    from backend.rag.embedder import embed_single
    from backend.rag.store import upsert_documents, reset_collection

    cfg = _load_config()
    takeout_base = BASE_DIR / cfg["paths"]["takeout_dir"]
    photos_dir = BASE_DIR / cfg["paths"]["photos_dir"]
    takeout_root = BASE_DIR / "takeout"  # für ZIP-Suche

    # Sample-Liste laden
    sample_list: list[dict] = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    total = len(sample_list)

    if reset:
        reset_collection("photos")
        logger.info("Photos-Collection zurückgesetzt.")

    stats = {"total": total, "success": 0, "skipped": 0, "errors": 0}

    ids, documents, embeddings, metadatas = [], [], [], []

    for idx, entry in enumerate(sample_list, start=1):
        filename = entry["filename"]
        status = f"Verarbeite [{idx}/{total}]: {filename}"
        logger.info(status)
        if progress_callback:
            progress_callback(idx, total, status)

        # Foto laden (erst extrahiertes Verzeichnis, dann ZIPs)
        result = _find_photo_in_dir(filename, photos_dir)
        if result is None:
            result = _find_photo_in_zips(filename, takeout_root)

        if result is None:
            logger.warning("Foto nicht gefunden: %s", filename)
            stats["skipped"] += 1
            continue

        image_bytes, meta = result

        # Metadaten parsen
        parsed = _parse_metadata(meta, filename)

        # KI-Bildbeschreibung
        # Reverse Geocoding (vor Vision, damit Ortsname im Log erscheint)
        place_name = ""
        if parsed["lat"] and parsed["lon"]:
            place_name = _reverse_geocode(parsed["lat"], parsed["lon"])
            if place_name:
                logger.info("  Ort: %s", place_name)

        try:
            description = describe_image(image_bytes)
            # Kurze Pause damit der VRAM nach keep_alive=0 entladen werden kann
            time.sleep(2)
        except Exception as exc:
            logger.warning("Vision-Fehler für %s: %s", filename, exc)
            description = ""
            time.sleep(5)  # Längere Pause nach Fehler

        # Dokument aufbauen (mit Ortsname)
        doc_text = _build_document(filename, parsed, description, place_name=place_name)

        # Embedding
        try:
            embedding = embed_single(doc_text)
        except Exception as exc:
            logger.error("Embedding-Fehler für %s: %s", filename, exc)
            stats["errors"] += 1
            continue

        # Boolean-Personen-Flags für ChromaDB-Filter
        from backend.rag.query_parser import _person_field
        from backend.ingestion.persons import get_known_persons
        known = get_known_persons()
        persons_str = ",".join(parsed["people"])
        person_flags = {
            _person_field(n): (n.split()[0].lower() in persons_str.lower() or n.lower() in persons_str.lower())
            for n in known
        }

        # Metadaten für ChromaDB (nur skalare Typen erlaubt)
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
            **person_flags,
        }

        ids.append(f"photo_{filename}")
        documents.append(doc_text)
        embeddings.append(embedding)
        metadatas.append(chroma_meta)
        stats["success"] += 1

    # Batch-Upsert
    if ids:
        upsert_documents("photos", ids, documents, embeddings, metadatas)

    logger.info("Foto-Ingestion abgeschlossen: %s", stats)
    return stats
