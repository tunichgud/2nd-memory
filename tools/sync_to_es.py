"""
sync_to_es.py – Synchronisiert Daten von ChromaDB nach Elasticsearch.

Vorteil: Nutzt bereits vorhandene Embeddings und Bildbeschreibungen aus ChromaDB,
ohne die Vision-API oder sentence-transformers erneut zu bemühen.
"""

import sys
import os
from pathlib import Path

# Projekt-Root zum Pfad hinzufügen
sys.path.insert(0, os.path.abspath("."))

import logging
from backend.rag.store import get_all_documents
from backend.rag.es_store import upsert_documents_es, reset_es_index

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def sync_collection(name: str):
    logger.info("Synchronisiere Collection '%s' von ChromaDB nach Elasticsearch...", name)
    
    # Alle Daten aus ChromaDB laden (inkl. Embeddings)
    # Hinweis: Bei sehr großen Datenmengen müsste man hier via get() mit Offsets arbeiten,
    # für das Sample reicht get_all_documents.
    from backend.rag.store import get_client
    client = get_client()
    col = client.get_collection(name)
    
    data = col.get(include=["documents", "metadatas", "embeddings"])
    
    ids = data.get("ids", [])
    documents = data.get("documents", [])
    embeddings = data.get("embeddings", [])
    metadatas = data.get("metadatas", [])
    
    if not ids:
        logger.info("Keine Daten in ChromaDB Collection '%s' gefunden.", name)
        return

    logger.info("Übertrage %d Dokumente nach Elasticsearch...", len(ids))
    
    # ES Index zurücksetzen (optional, hier für sauberen Sync)
    reset_es_index(name)
    
    # In Elasticsearch speichern
    upsert_documents_es(
        collection_name=name,
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )
    logger.info("Sync für '%s' erfolgreich.", name)

if __name__ == "__main__":
    for col in ["photos", "messages", "reviews", "saved_places"]:
        try:
            sync_collection(col)
        except Exception as e:
            logger.error("Fehler beim Sync von '%s': %s", col, e)
