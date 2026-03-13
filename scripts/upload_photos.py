#!/usr/bin/env python3
"""
upload_photos.py — Fotos manuell in 2nd Memory importieren

Standard-Verzeichnis wird aus config.yaml (paths.upload_dir) gelesen.
Kann relativ (zum Projektwurzel) oder absolut angegeben werden.

Priorität für das Upload-Verzeichnis:
  1. --dir Argument (CLI)
  2. paths.upload_dir in config.yaml
  3. Fallback: uploads/ (relativ zur Projektwurzel)

Verwendung:
    python3 scripts/upload_photos.py [--dry-run]
    python3 scripts/upload_photos.py --dir /mnt/c/Users/Alex/Pictures/Jazz [--dry-run]

Beispiel meta.yaml (im Upload-Verzeichnis):
    defaults:
        persons: ["Jazz"]           # Standard-Personen für alle Fotos
        user_id: "00000000-0000-0000-0000-000000000001"

    files:
        Jazz_2019_Park.jpg:
            date: "2019-10-31"      # YYYY-MM-DD
            persons: ["Jazz", "Alex"]
            place: "Hamburg"
            description: "Jazz im Park, Herbst 2019. Sie ist sehr mobil und fröhlich."

        Jazz_Winningen_2014.jpg:
            date: "2014-07-15"
            persons: ["Jazz", "Monika Schmidt"]
            place: "Winningen"
"""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def _load_meta(upload_dir: Path) -> dict:
    """Lädt optionale meta.yaml aus dem Upload-Verzeichnis."""
    meta_file = upload_dir / "meta.yaml"
    if meta_file.exists():
        with open(meta_file, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _make_doc_id(filename: str) -> str:
    return f"photo_{hashlib.md5(filename.encode()).hexdigest()[:12]}"


def _build_document(filename: str, date_iso: str, persons: list[str],
                    place: str, description: str) -> str:
    """Erstellt den Dokumenttext für ChromaDB (kompatibel mit ingest_photos Format)."""
    parts = [f"Foto: {filename}"]
    if date_iso:
        parts.append(f"Datum: {date_iso[:10]}")
    if place:
        parts.append(f"Ort: {place}")
    if persons:
        parts.append(f"Personen: {', '.join(persons)}")
    if description:
        parts.append(f"Beschreibung: {description}")
    return "\n".join(parts)


def _parse_date(date_str: str) -> tuple[int, str]:
    """Parst YYYY-MM-DD zu (timestamp, iso_string)."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp()), dt.isoformat()
    except ValueError:
        return 0, ""


def upload_photos(
    upload_dir: Path,
    user_id: str = "00000000-0000-0000-0000-000000000001",
    dry_run: bool = False,
) -> dict:
    """Importiert Fotos aus upload_dir in ChromaDB."""
    from backend.llm.connector import describe_image
    from backend.rag.embedder import embed_single
    from backend.rag.store import upsert_documents, get_indexed_ids

    meta_cfg = _load_meta(upload_dir)
    defaults = meta_cfg.get("defaults", {})
    file_meta = meta_cfg.get("files", {})

    default_persons = defaults.get("persons", [])
    uid = defaults.get("user_id", user_id)

    # Bereits indexierte IDs
    indexed_ids = get_indexed_ids("photos")
    logger.info(f"Bereits {len(indexed_ids)} Fotos in DB")

    # Fotos einlesen
    photo_files = sorted([
        f for f in upload_dir.iterdir()
        if f.suffix.lower() in IMAGE_EXTENSIONS
    ])

    if not photo_files:
        logger.warning(f"Keine Fotos in {upload_dir} gefunden")
        return {"total": 0, "success": 0, "skipped": 0, "errors": 0}

    logger.info(f"Gefundene Fotos: {len(photo_files)}")

    stats = {"total": len(photo_files), "success": 0, "skipped": 0, "errors": 0}

    ids, documents, embeddings_list, metadatas = [], [], [], []

    for photo_path in photo_files:
        filename = photo_path.name
        doc_id = _make_doc_id(filename)

        if doc_id in indexed_ids:
            logger.info(f"  SKIP (bereits indexiert): {filename}")
            stats["skipped"] += 1
            continue

        # Metadaten aus meta.yaml
        fmeta = file_meta.get(filename, {})
        persons = fmeta.get("persons", default_persons)
        place = fmeta.get("place", "")
        manual_desc = fmeta.get("description", "")
        date_str = fmeta.get("date", "")

        date_ts, date_iso = _parse_date(date_str) if date_str else (0, "")

        logger.info(f"  Verarbeite: {filename} (Datum: {date_str or '?'}, Ort: {place or '?'})")

        try:
            # KI-Beschreibung (oder manuelle)
            if manual_desc:
                description = manual_desc
                logger.info(f"    Nutze manuelle Beschreibung")
            else:
                if dry_run:
                    description = f"[DRY-RUN] Foto von {filename}"
                else:
                    image_bytes = photo_path.read_bytes()
                    description = describe_image(image_bytes, filename)
                    logger.info(f"    KI-Beschreibung: {description[:80]}...")

            document = _build_document(filename, date_iso, persons, place, description)

            if dry_run:
                logger.info(f"    [DRY-RUN] Dokument:\n{document}")
                stats["success"] += 1
                continue

            # Embedding
            embedding = embed_single(document)

            metadata = {
                "user_id": uid,
                "source": "manual_upload",
                "filename": filename,
                "date_ts": date_ts,
                "date_iso": date_iso,
                "lat": fmeta.get("lat", 0.0),
                "lon": fmeta.get("lon", 0.0),
                "persons": ", ".join(persons),
                "place_name": place,
                "cluster": place,
                "has_face": bool(persons),
            }

            ids.append(doc_id)
            documents.append(document)
            embeddings_list.append(embedding)
            metadatas.append(metadata)

            stats["success"] += 1
            logger.info(f"    ✓ Bereit zum Import")

        except Exception as e:
            logger.error(f"    ❌ Fehler bei {filename}: {e}")
            stats["errors"] += 1

    # Batch-Import
    if ids and not dry_run:
        upsert_documents("photos", ids, documents, embeddings_list, metadatas)
        logger.info(f"\n✅ {len(ids)} Fotos importiert in ChromaDB")
    elif dry_run:
        logger.info(f"\n[DRY-RUN] Würde {stats['success']} Fotos importieren")

    return stats


def _resolve_upload_dir(cli_dir: str | None) -> Path:
    """Löst das Upload-Verzeichnis auf.

    Priorität:
      1. --dir CLI-Argument (absolut oder relativ zur Projektwurzel)
      2. paths.upload_dir in config.yaml (absolut oder relativ)
      3. Fallback: uploads/ relativ zur Projektwurzel
    """
    if cli_dir is not None:
        p = Path(cli_dir)
        resolved = p if p.is_absolute() else BASE_DIR / p
        logger.info(f"Upload-Verzeichnis (--dir): {resolved}")
        return resolved

    # Versuche config.yaml
    cfg_path = BASE_DIR / "config.yaml"
    if cfg_path.exists():
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            upload_dir_cfg = cfg.get("paths", {}).get("upload_dir")
            if upload_dir_cfg:
                p = Path(upload_dir_cfg)
                resolved = p if p.is_absolute() else BASE_DIR / p
                logger.info(f"Upload-Verzeichnis (config.yaml): {resolved}")
                return resolved
        except Exception as e:
            logger.warning(f"config.yaml konnte nicht gelesen werden: {e}")

    # Fallback
    resolved = BASE_DIR / "uploads"
    logger.info(f"Upload-Verzeichnis (Fallback): {resolved}")
    return resolved


def main():
    parser = argparse.ArgumentParser(description="Fotos manuell in 2nd Memory importieren")
    parser.add_argument(
        "--dir",
        default=None,
        help=(
            "Upload-Verzeichnis. Absoluter oder relativer Pfad. "
            "Default: paths.upload_dir aus config.yaml (oder uploads/)"
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur simulieren, nichts schreiben")
    parser.add_argument("--user-id", default="00000000-0000-0000-0000-000000000001")
    args = parser.parse_args()

    upload_dir = _resolve_upload_dir(args.dir)
    if not upload_dir.exists():
        upload_dir.mkdir(parents=True)
        logger.info(f"Verzeichnis erstellt: {upload_dir}")
        logger.info(f"Lege Fotos in {upload_dir} ab und starte das Script erneut.")
        logger.info(f"Optionale Metadaten: {upload_dir}/meta.yaml")
        sys.exit(0)

    stats = upload_photos(upload_dir, user_id=args.user_id, dry_run=args.dry_run)

    print(f"\nErgebnis: {stats['success']}/{stats['total']} importiert, "
          f"{stats['skipped']} übersprungen, {stats['errors']} Fehler")


if __name__ == "__main__":
    main()
