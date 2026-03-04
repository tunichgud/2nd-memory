"""
main.py – Memosaur Hauptworkflow (Takeout-Variante).

Ablauf:
1. Alle ZIP-Dateien im takeout/-Ordner scannen
2. Foto-Dateien (.jpg / .jpeg / .png / .webp) zusammen mit ihren
   supplemental-metadata.json-Sidecar-Dateien einlesen
3. Die 10 neuesten Fotos (nach photoTakenTime) auswählen
4. Bilddaten direkt aus dem ZIP in den RAM laden (keine Extraktion)
5. Jedes Bild von qwen3:8b beschreiben lassen (vision.py)
6. Ergebnisse als results.json speichern
"""

import json
import sys
import zipfile
from pathlib import Path
from datetime import datetime, timezone

# Sicherstellen, dass src/ im Python-Pfad ist
sys.path.insert(0, str(Path(__file__).resolve().parent))

from vision import describe_image

BASE_DIR = Path(__file__).resolve().parent.parent
TAKEOUT_DIR = BASE_DIR / "takeout"
OUTPUT_FILE = BASE_DIR / "results.json"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
TOP_N = 10


def _metadata_name(image_zip_path: str) -> str:
    """Leitet den Namen der Sidecar-Metadaten-Datei ab.

    Google Takeout legt Metadaten als '<name>.supplemental-metadata.json'
    neben die Bilddatei. Bei langen Dateinamen wird der Name manchmal
    abgeschnitten – daher prüfen wir beide Varianten.
    """
    return image_zip_path + ".supplemental-metadata.json"


def collect_photos(takeout_dir: Path) -> list[dict]:
    """Scannt alle ZIPs und sammelt Fotos mit Metadaten.

    Returns:
        Liste von Dicts mit den Schlüsseln:
        - zip_path: Path zum ZIP-Archiv
        - zip_entry: interner Pfad im ZIP
        - filename: Dateiname ohne Pfad
        - taken_ts: Unix-Timestamp (int) des Aufnahmezeitpunkts
        - taken_fmt: Lesbare Datumsangabe
        - geo: dict mit latitude/longitude oder None
    """
    zip_files = sorted(takeout_dir.glob("*.zip"))
    if not zip_files:
        raise FileNotFoundError(f"Keine ZIP-Dateien in {takeout_dir} gefunden.")

    photos: list[dict] = []

    for zip_path in zip_files:
        print(f"  Scanne {zip_path.name} …")
        with zipfile.ZipFile(zip_path) as zf:
            name_set = set(zf.namelist())

            for entry in zf.namelist():
                ext = Path(entry).suffix.lower()
                if ext not in IMAGE_EXTENSIONS:
                    continue

                # Metadaten-Sidecar laden (optional)
                meta: dict = {}
                meta_entry = _metadata_name(entry)
                if meta_entry in name_set:
                    try:
                        meta = json.loads(zf.read(meta_entry))
                    except (json.JSONDecodeError, KeyError):
                        pass

                # Aufnahmezeit ermitteln (Fallback: Erstellungszeit, dann 0)
                taken_ts = 0
                taken_fmt = "unbekannt"
                for time_key in ("photoTakenTime", "creationTime"):
                    if time_key in meta:
                        try:
                            taken_ts = int(meta[time_key]["timestamp"])
                            taken_fmt = meta[time_key].get("formatted", "")
                            break
                        except (KeyError, ValueError):
                            pass

                # Geo-Daten (bevorzugt geoData, sonst geoDataExif)
                geo = None
                for geo_key in ("geoData", "geoDataExif"):
                    g = meta.get(geo_key, {})
                    if g.get("latitude") or g.get("longitude"):
                        geo = {
                            "latitude": g.get("latitude"),
                            "longitude": g.get("longitude"),
                            "altitude": g.get("altitude"),
                        }
                        break

                photos.append(
                    {
                        "zip_path": zip_path,
                        "zip_entry": entry,
                        "filename": Path(entry).name,
                        "taken_ts": taken_ts,
                        "taken_fmt": taken_fmt,
                        "geo": geo,
                    }
                )

    return photos


def select_newest(photos: list[dict], n: int) -> list[dict]:
    """Gibt die n neuesten Fotos zurück (absteigend nach Aufnahmezeit)."""
    return sorted(photos, key=lambda p: p["taken_ts"], reverse=True)[:n]


def process_photos(photos: list[dict]) -> list[dict]:
    """Lädt Bildbytes aus dem ZIP und beschreibt jedes Bild per KI."""
    results = []

    for idx, photo in enumerate(photos, start=1):
        filename = photo["filename"]
        taken_fmt = photo["taken_fmt"]

        print(f"[{idx}/{len(photos)}] {filename}  ({taken_fmt})")

        try:
            with zipfile.ZipFile(photo["zip_path"]) as zf:
                image_bytes = zf.read(photo["zip_entry"])

            print(f"  {len(image_bytes):,} Bytes geladen, analysiere …")
            description = describe_image(image_bytes)
            print(
                f"  Beschreibung: "
                f"{description[:80]}{'…' if len(description) > 80 else ''}"
            )

            entry: dict = {
                "filename": filename,
                "date": taken_fmt,
                "description": description,
            }
            if photo["geo"]:
                entry["geo"] = photo["geo"]

            results.append(entry)

        except Exception as exc:  # noqa: BLE001
            print(f"  Fehler: {exc}")
            results.append(
                {
                    "filename": filename,
                    "date": taken_fmt,
                    "description": f"Fehler: {exc}",
                }
            )

    return results


def main() -> None:
    print("=== Memosaur – Digitales Gedächtnis ===\n")

    # 1. Fotos aus allen ZIPs einsammeln
    print(f"Scanne Takeout-Archiv in {TAKEOUT_DIR} …\n")
    all_photos = collect_photos(TAKEOUT_DIR)
    print(f"\n{len(all_photos)} Fotos insgesamt gefunden.")

    # 2. Die 10 neuesten auswählen
    newest = select_newest(all_photos, TOP_N)
    print(f"Verarbeite die {len(newest)} neuesten Fotos.\n")

    # 3. Bilder beschreiben
    results = process_photos(newest)

    # 4. Ergebnisse speichern
    OUTPUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nFertig! {len(results)} Einträge gespeichert in: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
