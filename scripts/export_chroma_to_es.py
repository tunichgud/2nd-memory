"""
export_chroma_to_es.py — Exportiert alle ChromaDB-Collections nach Elasticsearch.

Ist idempotent: Nutzt Upsert (_id = ChromaDB-ID), erzeugt keine Duplikate.
Kein Index-Reset — vorhandene Dokumente werden aktualisiert, neue hinzugefügt.

Nutzung (aus dem Projekt-Root):
    python scripts/export_chroma_to_es.py

    # Nur einzelne Collections:
    python scripts/export_chroma_to_es.py --collections messages photos

Voraussetzungen:
    - Elasticsearch läuft (docker compose up -d)
    - config.yaml und .env sind vorhanden
    - Python-Umgebung mit allen Abhängigkeiten aktiviert (.venv)
"""

import argparse
import logging
import sys
from pathlib import Path

# Projekt-Root zum sys.path hinzufügen, damit backend.* importierbar ist
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.rag.store import get_client
from backend.rag.es_store import upsert_documents_es, verify_elasticsearch, _es_available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Collections die nach ES exportiert werden (faces hat kein upsert_documents_es-Mapping,
# wird aber als generischer Bulk-Export trotzdem übertragen).
ALL_COLLECTIONS = ["messages", "photos", "reviews", "saved_places", "faces"]

BATCH_SIZE = 500  # Anzahl Dokumente pro Bulk-Request


def export_collection(collection_name: str) -> int:
    """Exportiert eine ChromaDB-Collection nach Elasticsearch.

    Args:
        collection_name: Name der ChromaDB-Collection.

    Returns:
        Anzahl exportierter Dokumente (0 wenn Collection leer oder nicht vorhanden).
    """
    client = get_client()

    try:
        col = client.get_collection(collection_name)
    except Exception:
        logger.warning("Collection '%s' nicht in ChromaDB gefunden — übersprungen.", collection_name)
        return 0

    # Gesamtzahl ermitteln
    total = col.count()
    if total == 0:
        logger.info("Collection '%s' ist leer — übersprungen.", collection_name)
        return 0

    logger.info("Exportiere '%s': %d Dokumente...", collection_name, total)

    exported = 0
    offset = 0

    while offset < total:
        try:
            data = col.get(
                limit=BATCH_SIZE,
                offset=offset,
                include=["documents", "metadatas", "embeddings"],
            )
        except Exception as batch_err:
            logger.warning(
                "Batch [%d:%d] in '%s' mit Embeddings fehlgeschlagen (%s) — "
                "retry ohne Embeddings...",
                offset, offset + BATCH_SIZE, collection_name, batch_err,
            )
            try:
                data = col.get(
                    limit=BATCH_SIZE,
                    offset=offset,
                    include=["documents", "metadatas"],
                )
            except Exception as retry_err:
                logger.error(
                    "Batch [%d:%d] in '%s' endgültig übersprungen: %s",
                    offset, offset + BATCH_SIZE, collection_name, retry_err,
                )
                offset += BATCH_SIZE
                continue

        ids = data.get("ids", [])
        raw_docs = data.get("documents")
        documents = raw_docs if raw_docs is not None else [""] * len(ids)
        raw_emb = data.get("embeddings")
        # raw_emb kann ein numpy-Array sein → expliziter None-Check statt bool()
        embeddings = raw_emb.tolist() if hasattr(raw_emb, "tolist") else (raw_emb if raw_emb is not None else [])
        raw_meta = data.get("metadatas")
        metadatas = raw_meta if raw_meta is not None else [{}] * len(ids)

        # Fehlende Embeddings auffüllen (z.B. faces-Collection hat andere Embedding-Dims)
        if not embeddings:
            logger.warning(
                "Batch [%d:%d] in '%s' enthält keine Embeddings — wird ohne Vektor exportiert.",
                offset,
                offset + len(ids),
                collection_name,
            )
            # Leere Embedding-Liste → upsert_documents_es überspringt ensure_index-Dim-Check
            embeddings = []

        if ids:
            upsert_documents_es(
                collection_name=collection_name,
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            exported += len(ids)
            logger.info(
                "  '%s': %d/%d Dokumente übertragen.",
                collection_name,
                exported,
                total,
            )

        offset += BATCH_SIZE

    logger.info("Collection '%s' abgeschlossen: %d Dokumente exportiert.", collection_name, exported)
    return exported


def main() -> None:
    """Hauptfunktion: Parsed Argumente und startet den Export."""
    parser = argparse.ArgumentParser(
        description="Exportiert ChromaDB-Collections nach Elasticsearch (idempotent)."
    )
    parser.add_argument(
        "--collections",
        nargs="+",
        default=ALL_COLLECTIONS,
        metavar="COLLECTION",
        help=f"Collections die exportiert werden sollen (Standard: {ALL_COLLECTIONS})",
    )
    args = parser.parse_args()

    # ES-Verbindung prüfen
    verify_elasticsearch()

    # Modul-global _es_available nach verify_elasticsearch() prüfen
    import backend.rag.es_store as es_module
    if es_module._es_available is False:
        logger.error(
            "Elasticsearch ist nicht erreichbar. Bitte 'docker compose up -d' ausführen."
        )
        sys.exit(1)

    logger.info("Starte Export: %s", args.collections)
    total_exported = 0

    for collection_name in args.collections:
        try:
            count = export_collection(collection_name)
            total_exported += count
        except Exception as exc:
            logger.error("Fehler beim Export von '%s': %s", collection_name, exc, exc_info=True)

    logger.info("Export abgeschlossen. Gesamt exportiert: %d Dokumente.", total_exported)


if __name__ == "__main__":
    main()
