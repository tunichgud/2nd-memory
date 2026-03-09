import os
import sys
import logging
import asyncio
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.rag.store import get_collection
from backend.ingestion.photos import _find_photo_in_dir, _find_photo_in_zips, _load_config
from backend.ingestion.faces import process_and_store_faces

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def run_reprocessing():
    cfg = _load_config()
    base_dir = Path(__file__).resolve().parents[2]
    photos_dir = base_dir / cfg["paths"]["photos_dir"]
    takeout_root = base_dir / "takeout"
    
    logger.info("Starte Re-Processing der Gesichter für alle vorhandenen Fotos...")
    
    # 1. Alle bereits indexierten Fotos aus ChromaDB laden
    col_photos = get_collection("photos")
    results = col_photos.get(include=["metadatas"])
    
    if not results or not results.get("ids"):
        logger.warning("Keine Fotos in der 'photos' Collection gefunden.")
        return
    
    total = len(results["ids"])
    logger.info(f"Gefundene Fotos: {total}")
    
    success_count = 0
    face_total = 0
    
    for i in range(total):
        photo_id = results["ids"][i]
        meta = results["metadatas"][i]
        filename = meta.get("filename")
        
        if not filename:
            logger.warning(f"Kein Dateiname für ID {photo_id} gefunden, überspringe.")
            continue
            
        logger.info(f"[{i+1}/{total}] Verarbeite {filename}...")
        
        # Bild suchen
        result = _find_photo_in_dir(filename, photos_dir)
        if result is None:
            result = _find_photo_in_zips(filename, takeout_root)
            
        if result is None:
            logger.warning(f"  Bilddatei nicht gefunden: {filename}")
            continue
            
        image_bytes, _ = result
        
        try:
            # Gesichter erkennen und in 'faces' speichern
            num_faces = process_and_store_faces(photo_id, image_bytes, meta)
            face_total += num_faces
            success_count += 1
        except Exception as e:
            logger.error(f"  Fehler bei {filename}: {e}")
            
    logger.info("=" * 50)
    logger.info(f"Re-Processing abgeschlossen!")
    logger.info(f"Fotos erfolgreich verarbeitet: {success_count}/{total}")
    logger.info(f"Gesamtanzahl gefundener Gesichter: {face_total}")
    logger.info("=" * 50)

if __name__ == "__main__":
    asyncio.run(run_reprocessing())
