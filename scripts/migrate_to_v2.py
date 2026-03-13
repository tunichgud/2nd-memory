#!/usr/bin/env python3
"""
migrate_to_v2.py – Migriert bestehende ChromaDB-Daten auf das v2-Schema.

Was wird gemacht:
  1. SQLite-Datenbank anlegen + Default-User "ManfredMustermann"
  2. Alle ChromaDB-Dokumente lesen
  3. user_id = DEFAULT_USER_ID zu allen Metadaten hinzufügen
  4. Klarnamen aus Metadaten (persons, place_name) extrahieren
     und ein Token-Wörterbuch aufbauen
  5. Dokument-Text und Metadaten-Felder durch Tokens ersetzen
  6. Embeddings neu berechnen (tokenisierter Text)
  7. Dokumente zurückschreiben
  8. Token-Wörterbuch als JSON exportieren (für Browser-Import)

Ausführen: python scripts/migrate_to_v2.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Projektpfad
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("migrate_v2")

DEFAULT_USER_ID   = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_NAME = "ManfredMustermann"

# ---------------------------------------------------------------------------
# Token-Dictionary (lokales Objekt, wird am Ende exportiert)
# ---------------------------------------------------------------------------

_token_dict: dict[str, dict] = {}  # cleartext_lc → {token_id, cleartext, type}
_counters = {"PER": 0, "LOC": 0, "ORG": 0}


def _get_or_create_token(cleartext: str, ner_type: str) -> str:
    """Gibt Token zurück, legt neuen an falls nicht vorhanden."""
    lc = cleartext.lower().strip()
    prefix = ner_type.upper()

    # Bereits bekannt?
    for entry in _token_dict.values():
        if entry["cleartext_lc"] == lc and entry["type"] == prefix:
            return f"[{entry['token_id']}]"

    # Neu anlegen
    _counters[prefix] = _counters.get(prefix, 0) + 1
    token_id = f"{prefix}_{_counters[prefix]}"
    _token_dict[token_id] = {
        "token_id":    token_id,
        "cleartext":   cleartext,
        "cleartext_lc": lc,
        "type":        prefix,
        "first_seen":  time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count":       1,
    }
    logger.info("Neuer Token: [%s] = '%s'", token_id, cleartext)
    return f"[{token_id}]"


def _tokenize_persons(persons_str: str) -> str:
    """Ersetzt kommaseparierte Personennamen durch Tokens."""
    if not persons_str:
        return ""
    names = [n.strip() for n in persons_str.split(",") if n.strip()]
    return ",".join(_get_or_create_token(n, "PER") for n in names)


def _tokenize_place(place: str) -> str:
    """Ersetzt einen Ortsnamen durch einen LOC-Token."""
    if not place:
        return ""
    # Bei zusammengesetzten Ortsnamen (z.B. "München, Bayern, Deutschland")
    # nur den ersten Teil (Hauptort) als Token verwenden
    main = place.split(",")[0].strip()
    return _get_or_create_token(main, "LOC")


def _tokenize_document(doc: str, persons_map: dict, place_map: dict) -> str:
    """Ersetzt Klarnamen in Dokumenttext durch Tokens."""
    result = doc
    # Personennamen ersetzen
    for cleartext, token in persons_map.items():
        result = result.replace(cleartext, token)
    # Ortsnamen ersetzen
    for cleartext, token in place_map.items():
        result = result.replace(cleartext, token)
    return result


# ---------------------------------------------------------------------------
# Haupt-Migration
# ---------------------------------------------------------------------------

async def run_migration():
    from backend.db.database import init_db, DEFAULT_USER_ID, DEFAULT_USER_NAME
    from backend.rag.store import get_all_documents, upsert_documents, COLLECTIONS
    from backend.rag.embedder import embed_single

    logger.info("=" * 60)
    logger.info("2nd-memory v2 Migration startet")
    logger.info("=" * 60)

    # Schritt 1: SQLite initialisieren
    logger.info("Schritt 1: SQLite-Datenbank initialisieren…")
    await init_db()
    logger.info("SQLite OK (User: %s / %s)", DEFAULT_USER_NAME, DEFAULT_USER_ID)

    # Schritt 2–7: ChromaDB-Dokumente migrieren
    total_migrated = 0

    for col_name in COLLECTIONS:
        logger.info("Migriere Collection '%s'…", col_name)
        data = get_all_documents(col_name)

        if not data["ids"]:
            logger.info("  Leer, überspringe.")
            continue

        count = len(data["ids"])
        logger.info("  %d Dokumente gefunden.", count)

        ids, documents, embeddings, metadatas = [], [], [], []

        for i, (doc_id, doc, meta) in enumerate(
            zip(data["ids"], data["documents"], data["metadatas"]), start=1
        ):
            logger.info("  [%d/%d] %s", i, count, doc_id)

            new_meta = dict(meta)

            # user_id hinzufügen
            new_meta["user_id"] = DEFAULT_USER_ID

            # Personen tokenisieren
            persons_map = {}
            if meta.get("persons"):
                original_persons = meta["persons"]
                tokenized_persons = _tokenize_persons(original_persons)
                new_meta["persons"] = tokenized_persons
                # Mapping für Dokument-Ersetzung
                for name in original_persons.split(","):
                    name = name.strip()
                    if name:
                        tok = _get_or_create_token(name, "PER")
                        persons_map[name] = tok

            # mentioned_persons tokenisieren
            if meta.get("mentioned_persons"):
                new_meta["mentioned_persons"] = _tokenize_persons(meta["mentioned_persons"])

            # Ortsname tokenisieren
            place_map = {}
            if meta.get("place_name"):
                original_place = meta["place_name"]
                tokenized_place = _tokenize_place(original_place)
                new_meta["place_name"] = tokenized_place
                # Für Dokument-Ersetzung: auch Teilnamen der Adresse
                main_place = original_place.split(",")[0].strip()
                place_map[original_place] = tokenized_place
                if main_place != original_place:
                    place_map[main_place] = tokenized_place

            # name-Feld (Reviews, Saved Places) tokenisieren
            if meta.get("name"):
                original_name = meta["name"]
                new_meta["name"] = _get_or_create_token(original_name, "ORG")
                place_map[original_name] = new_meta["name"]

            # Personen-Flags: has_nora etc. → has_per_1 etc.
            # Alte Flags entfernen, neue auf Basis tokenisierter persons setzen
            old_flags = [k for k in new_meta if k.startswith("has_")]
            for f in old_flags:
                del new_meta[f]
            for tok_str in new_meta.get("persons", "").split(","):
                tok_str = tok_str.strip().strip("[]")
                if tok_str:
                    new_meta[f"has_{tok_str.lower()}"] = True

            # Dokument-Text tokenisieren
            new_doc = _tokenize_document(doc, persons_map, place_map)

            # Embedding neu berechnen
            new_embedding = embed_single(new_doc)

            ids.append(doc_id)
            documents.append(new_doc)
            embeddings.append(new_embedding)
            metadatas.append(new_meta)

        # Batch-Upsert
        upsert_documents(col_name, ids, documents, embeddings, metadatas)
        total_migrated += len(ids)
        logger.info("  Collection '%s' migriert: %d Dokumente.", col_name, len(ids))

    # Schritt 8: Token-Wörterbuch exportieren
    output_path = BASE_DIR / "data" / "migration_dictionary.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(list(_token_dict.values()), f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("Migration abgeschlossen!")
    logger.info("  %d Dokumente migriert", total_migrated)
    logger.info("  %d Tokens erzeugt (%d PER, %d LOC, %d ORG)",
        sum(_counters.values()),
        _counters.get("PER", 0),
        _counters.get("LOC", 0),
        _counters.get("ORG", 0),
    )
    logger.info("  Wörterbuch: %s", output_path)
    logger.info("")
    logger.info("Nächste Schritte:")
    logger.info("  1. Server starten: python -m uvicorn backend.main:app --reload")
    logger.info("  2. Browser öffnen: http://localhost:8000")
    logger.info("  3. Im Browser-Konsolendialog: Wörterbuch importieren")
    logger.info("     TokenStore.importTokens(<Inhalt von migration_dictionary.json>)")
    logger.info("  4. Datei data/migration_dictionary.json anschließend löschen!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_migration())
