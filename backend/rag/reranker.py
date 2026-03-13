"""
reranker.py – Cross-Encoder Re-Ranking für 2nd Memory.

Problem das gelöst wird ("Lost in the Middle"):
    Nach dem Retrieval landen bis zu 24+ Chunks im Kontext. LLMs vergessen
    Informationen die in der Mitte langer Kontexte stehen. Ein Cross-Encoder
    bewertet (query, chunk)-Paare präziser als Embedding-Cosine-Similarity
    und sortiert die wirklich relevanten Chunks nach oben.

Modell:
    cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
    - Multilingual (inkl. Deutsch)
    - ~120MB, läuft lokal auf CPU in ~10ms/chunk
    - HuggingFace Hub, wird automatisch gecacht (~/.cache/huggingface/)

Fallback:
    Wenn das Modell nicht geladen werden kann (kein Internet, Disk-Probleme)
    gibt rerank() die unveränderte Liste zurück. Kein Crash.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.rag.rag_types import Source

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

_MODEL_NAME = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
_encoder: "CrossEncoder | None" = None
_load_attempted = False


def _get_encoder() -> "CrossEncoder | None":
    """
    Lazy-Singleton: Lädt den Cross-Encoder beim ersten Aufruf.

    Returns None bei Fehler (Fallback: keine Re-Ranking).
    """
    global _encoder, _load_attempted
    if _load_attempted:
        return _encoder
    _load_attempted = True

    try:
        from sentence_transformers import CrossEncoder
        logger.info("Lade Cross-Encoder '%s' …", _MODEL_NAME)
        _encoder = CrossEncoder(_MODEL_NAME)
        logger.info("Cross-Encoder geladen.")
    except Exception as exc:
        logger.warning(
            "Cross-Encoder konnte nicht geladen werden — Re-Ranking deaktiviert: %s", exc
        )
        _encoder = None

    return _encoder


def rerank(
    query: str,
    sources: list[Source],
    top_n: int = 10,
) -> list[Source]:
    """
    Re-rankt eine Liste von Retrieval-Quellen anhand der Query.

    Der Cross-Encoder bewertet jedes (query, chunk)-Paar direkt und vergibt
    einen Relevanz-Score. Dieser ersetzt den ursprünglichen Embedding-Score.

    Args:
        query:   Die Nutzeranfrage (vollständiger Text).
        sources: Retrieval-Ergebnisse aus retrieve().
        top_n:   Maximale Anzahl zurückgegebener Quellen.

    Returns:
        Bis zu top_n Quellen, nach Re-Rank-Score absteigend sortiert.
        Bei Fehler oder fehlendem Modell: ursprüngliche Liste (max top_n).
    """
    if not sources:
        return sources

    encoder = _get_encoder()
    if encoder is None:
        logger.debug("Re-Ranking übersprungen (kein Encoder)")
        return sources[:top_n]

    try:
        pairs = [(query, s["document"]) for s in sources]
        scores: list[float] = encoder.predict(pairs).tolist()

        # Score in Source übernehmen (überschreibt Embedding-Score)
        for source, score in zip(sources, scores):
            source["score"] = round(float(score), 4)

        ranked = sorted(sources, key=lambda s: s["score"], reverse=True)
        result = ranked[:top_n]

        logger.info(
            "Re-Ranking: %d → %d Quellen | Top-Score: %.3f | Bottom-Score: %.3f",
            len(sources), len(result),
            result[0]["score"] if result else 0,
            result[-1]["score"] if result else 0,
        )
        return result

    except Exception as exc:
        logger.warning("Re-Ranking fehlgeschlagen, verwende Original-Reihenfolge: %s", exc)
        return sources[:top_n]
