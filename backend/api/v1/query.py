"""
query.py – /api/v1/query

Token-aware RAG-Abfrage. Das Frontend schickt bereits maskierten Text
(Tokens statt Klarnamen). Die Antwort enthält ebenfalls nur Tokens –
das Re-Mapping findet im Browser via IndexedDB statt.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import aiosqlite

from backend.db.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["v1/query"])


class V1QueryRequest(BaseModel):
    user_id: str
    # Bereits maskierte Anfrage, z.B. "Wo war ich mit [PER_1] in [LOC_1]?"
    masked_query: str = Field(..., min_length=1, max_length=2000)
    # Optionale strukturierte Filter (aus Browser-NER extrahiert)
    person_tokens: list[str] = Field(default_factory=list)   # ["[PER_1]", "[PER_2]"]
    person_names: list[str] = Field(default_factory=list)
    location_tokens: list[str] = Field(default_factory=list) # ["[LOC_1]"]
    # Klarnamen der erkannten Orte (aus IndexedDB-Lookup im Browser)
    # z.B. ["München"] für location_tokens = ["[LOC_11]"]
    # Wird für cluster-basierten Post-Filter verwendet (robuster als Token-Matching)
    location_names: list[str] = Field(default_factory=list)
    collections: list[str] | None = None
    n_results: int = Field(default=6, ge=1, le=50)
    min_score: float = Field(default=0.2, ge=0.0, le=1.0)
    date_from: str | None = None
    date_to: str | None = None


class V1SourceItem(BaseModel):
    id: str
    collection: str
    score: float
    document: str           # Enthält nur Tokens
    metadata: dict


class V1QueryResponse(BaseModel):
    masked_query: str
    masked_answer: str      # Antwort mit Tokens statt Klarnamen
    sources: list[V1SourceItem]
    source_count: int
    filter_summary: str = ""


@router.post("/query", response_model=V1QueryResponse)
async def query_v1(
    req: V1QueryRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Token-aware RAG-Abfrage. Ein- und Ausgabe enthalten nur Tokens."""
    import asyncio

    logger.info("=== DEBUG API /v1/query ===")
    logger.info("  masked_query:    %s", req.masked_query)
    logger.info("  location_tokens: %s", req.location_tokens)
    logger.info("  location_names:  %s", req.location_names)
    logger.info("===========================")

    # User prüfen
    cursor = await db.execute("SELECT id FROM users WHERE id = ? AND is_active = 1", (req.user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User nicht gefunden oder inaktiv")

    try:
        from backend.rag.retriever_v2 import answer_v2

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: answer_v2(
                masked_query=req.masked_query,
                user_id=req.user_id,
                person_tokens=req.person_tokens,
                location_tokens=req.location_tokens,
                location_names=req.location_names,
                collections=req.collections,
                n_per_collection=req.n_results,
                min_score=req.min_score,
                date_from=req.date_from,
                date_to=req.date_to,
            ),
        )

        sources = [
            V1SourceItem(
                id=s["id"],
                collection=s["collection"],
                score=s["score"],
                document=s["document"],
                metadata=s["metadata"],
            )
            for s in result["sources"]
        ]

        return V1QueryResponse(
            masked_query=req.masked_query,
            masked_answer=result["answer"],
            sources=sources,
            source_count=len(sources),
            filter_summary=result.get("filter_summary", ""),
        )

    except Exception as exc:
        logger.exception("Fehler bei v1 RAG-Abfrage")
        raise HTTPException(status_code=500, detail=str(exc))


from fastapi.responses import StreamingResponse

@router.post("/query_stream")
async def query_stream_v1(
    req: V1QueryRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Token-aware RAG-Abfrage per Server-Sent Events (SSE). 
    Yields JSON Chunks mit {"type": "plan"|"text"|"sources", "content": ...}
    """
    logger.info("=== DEBUG API /v1/query_stream ===")
    logger.info("  masked_query:    %s", req.masked_query)
    logger.info("  location_tokens: %s", req.location_tokens)
    logger.info("==================================")

    # User prüfen
    cursor = await db.execute("SELECT id FROM users WHERE id = ? AND is_active = 1", (req.user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User nicht gefunden oder inaktiv")

    from backend.rag.retriever_v2 import answer_v2_stream
    
    # Da answer_v2_stream asynchrone DB Reads via aiosqlite/Chroma in asyncio.run laufen lässt
    # und wir hier schon in async def sind, muss der Generator so gebaut sein, 
    # dass FastAPI ihn direkt konsumieren kann.
    # Da unser chat_stream bereits asynchron funktioniert, können wir ihn als
    # media_type "text/event-stream" ausgeben:

    async def stream_generator():
        try:
            async for chunk in answer_v2_stream(
                masked_query=req.masked_query,
                user_id=req.user_id,
                person_tokens=req.person_tokens,
                person_names=req.person_names,
                location_tokens=req.location_tokens,
                location_names=req.location_names,
                collections=req.collections,
                n_per_collection=req.n_results,
                min_score=req.min_score,
                date_from=req.date_from,
                date_to=req.date_to,
            ):
                yield chunk
        except Exception as e:
            logger.exception("Stream unterbrochen oder Fehler")
            import json
            yield json.dumps({"type": "error", "content": str(e)}) + "\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
