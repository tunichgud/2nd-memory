"""
embedder.py – Embedding-Erzeugung für memosaur.

Verwendet das in config.yaml konfigurierte Embedding-Modell
(Standard: paraphrase-multilingual via Ollama).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Erzeugt Embedding-Vektoren für eine Liste von Texten.

    Delegiert an den LLM-Connector (Ollama oder sentence-transformers Fallback).
    """
    from backend.llm.connector import embed
    logger.debug("Erzeuge Embeddings für %d Texte", len(texts))
    return embed(texts)


def embed_single(text: str) -> list[float]:
    """Kurzform für einen einzelnen Text."""
    return embed_texts([text])[0]
