"""
persons.py – Personen-Extraktion aus Nachrichtentext für memosaur.

Extrahiert erwähnte Personennamen aus Chat-Chunks via:
  1. Schneller Pre-Check: bekannte Namen aus den Foto-Tags prüfen
  2. LLM-Extraktion für unbekannte Namen

Bekannte Personen werden aus ChromaDB (photos Collection) geladen und gecacht.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Gecachte bekannte Personen aus Foto-Tags
_known_persons_cache: list[str] | None = None


def get_known_persons() -> list[str]:
    """Lädt bekannte Personennamen aus den Foto-Metadaten (gecacht)."""
    global _known_persons_cache
    if _known_persons_cache is not None:
        return _known_persons_cache

    try:
        from backend.rag.store import get_all_documents
        data = get_all_documents("photos")
        names: set[str] = set()
        for meta in data.get("metadatas", []):
            persons_str = meta.get("persons", "")
            if persons_str:
                for name in persons_str.split(","):
                    name = name.strip()
                    if name:
                        # Auch Kurzformen hinzufügen (Vorname)
                        names.add(name)
                        first = name.split()[0]
                        if first != name:
                            names.add(first)
        _known_persons_cache = sorted(names, key=len, reverse=True)  # längste zuerst
        logger.info("Bekannte Personen aus Fotos: %s", _known_persons_cache)
    except Exception as exc:
        logger.warning("Fehler beim Laden bekannter Personen: %s", exc)
        _known_persons_cache = []

    return _known_persons_cache


def extract_mentioned_persons(text: str, sender_names: list[str] | None = None) -> list[str]:
    """Extrahiert alle im Text erwähnten Personennamen.

    Kombiniert:
    1. Bekannte Namen aus Foto-Tags (schnell, kein LLM)
    2. LLM-Extraktion falls bekannte Namen nicht ausreichen

    Args:
        text: Nachrichtentext (z.B. ein Chat-Chunk)
        sender_names: Namen der Chat-Teilnehmer (werden immer eingeschlossen)

    Returns:
        Deduplizierte Liste von Personennamen
    """
    found: set[str] = set()

    # Absender immer einschließen
    if sender_names:
        for name in sender_names:
            found.add(name.strip())

    # Bekannte Namen im Text suchen (case-insensitive)
    known = get_known_persons()
    text_lower = text.lower()
    for name in known:
        if name.lower() in text_lower:
            found.add(name)

    # LLM nur wenn Text wahrscheinlich unbekannte Personennamen enthält
    # Heuristik: Großgeschriebene Wörter die nicht am Satzanfang stehen
    # und nicht in den bekannten Namen sind
    unknown_caps = _find_unknown_capitalized(text, found, known)
    if unknown_caps:
        llm_names = _extract_persons_llm(text)
        found.update(llm_names)

    result = sorted(found)
    logger.debug("Erwähnte Personen in Chunk: %s", result)
    return result


def _find_unknown_capitalized(text: str, already_found: set[str], known: list[str]) -> list[str]:
    """Findet großgeschriebene Wörter die potenziell unbekannte Namen sind."""
    known_lower = {n.lower() for n in known}
    # Wörter die großgeschrieben sind und NICHT am Satzanfang stehen
    # (einfache Heuristik: nach Leerzeichen + nicht nach Satzzeichen)
    pattern = re.compile(r'(?<=[a-zäöüß,]\s)([A-ZÄÖÜ][a-zäöüß]{2,})')
    candidates = pattern.findall(text)
    unknown = [c for c in candidates if c.lower() not in known_lower and c not in already_found]
    return unknown


def _extract_persons_llm(text: str) -> list[str]:
    """Extrahiert Personennamen via LLM (nur für kurze Chunks)."""
    # Auf 500 Zeichen kürzen um Tokens zu sparen
    excerpt = text[:500]

    from backend.llm.connector import chat
    prompt = (
        "Extrahiere alle Personennamen aus folgendem Chat-Text. "
        "Antworte NUR mit einer kommagetrennten Liste der Namen, "
        "oder 'keine' wenn keine Personennamen vorhanden. "
        "Keine Erklärungen.\n\n"
        f"Text: {excerpt}"
    )
    response = chat([{"role": "user", "content": prompt}])
    response = response.strip()

    if response.lower() in ("keine", "keine.", "none", "-"):
        return []

    names = [n.strip() for n in response.split(",") if n.strip()]
    # Plausibilitätscheck: max 10 Namen, jeder max 30 Zeichen
    names = [n for n in names if len(n) <= 30 and len(n) >= 2][:10]
    return names
