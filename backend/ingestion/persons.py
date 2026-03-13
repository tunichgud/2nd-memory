"""
persons.py – Personen-Extraktion aus Nachrichtentext für 2nd Memory.

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

    # LLM (bzw. ab jetzt lokales NER via spaCy) nur wenn Text potenziell unbekannte Namen enthält
    unknown_caps = _find_unknown_capitalized(text, found, known)
    if unknown_caps:
        spacy_names = _extract_persons_spacy(text)
        found.update(spacy_names)

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


# Lazy-Loading für spaCy-Modell
_nlp = None

def _extract_persons_spacy(text: str) -> list[str]:
    """Extrahiert Personennamen via lokalem spaCy NER (schnell, offline)."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            logger.info("Lade lokales NER Modell (de_core_news_sm)...")
            _nlp = spacy.load("de_core_news_sm")
        except ImportError:
            logger.error("spaCy nicht installiert! Bitte 'pip install spacy' und 'python -m spacy download de_core_news_sm' ausführen.")
            return []
        except Exception as e:
            logger.error(f"Fehler beim Laden des spaCy Modells: {e}")
            return []

    # Auf ca. 1000 Zeichen kürzen (für Chunks meist ausreichend, verhindert CPU Spikes)
    excerpt = text[:1000]
    doc = _nlp(excerpt)
    
    names = []
    for ent in doc.ents:
        if ent.label_ == "PER":
            # Bereinigung: Oft werden Wörter wie "Die", "Hallo" fälschlicherweise als PER markiert
            name = ent.text.strip()
            # Plausibilität: Mindestens 2 Zeichen, unter 30 Zeichen, keine Sonderzeichen, fängt mit Großbuchstaben an
            if len(name) >= 2 and len(name) <= 30 and name[0].isupper() and not any(char in "!?,;:\"'" for char in name):
                names.append(name)
                
    # Deduplizieren und max 10 zurückgeben
    return list(dict.fromkeys(names))[:10]
