"""
query.py – FastAPI Query-Endpunkt für memosaur.

Endpunkte:
  POST /api/query  – RAG-Abfrage mit LLM-Antwort
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["query"])


# ---------------------------------------------------------------------------
# Modelle
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Die Frage des Nutzers")
    collections: list[str] | None = Field(None, description="Zu durchsuchende Collections (None = alle)")
    n_results: int = Field(10, ge=1, le=50, description="Max. Ergebnisse pro Collection")
    min_score: float = Field(0.3, ge=0.0, le=1.0, description="Mindest-Ähnlichkeit")
    date_from: str | None = Field(None, description="Datumsfilter von (YYYY-MM-DD)")
    date_to: str | None = Field(None, description="Datumsfilter bis (YYYY-MM-DD)")


class SourceItem(BaseModel):
    id: str
    collection: str
    score: float
    document: str
    metadata: dict


class ParsedQueryInfo(BaseModel):
    persons: list[str] = []
    locations: list[str] = []
    date_from: str | None = None
    date_to: str | None = None
    relevant_collections: list[str] = []
    filter_summary: str = ""


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[SourceItem]
    source_count: int
    parsed_query: ParsedQueryInfo | None = None


# ---------------------------------------------------------------------------
# Endpunkt
# ---------------------------------------------------------------------------

@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """Beantwortet eine natürlichsprachige Frage mit RAG + LLM."""
    import asyncio

    try:
        from backend.rag.retriever import answer as rag_answer

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: rag_answer(
                query=req.query,
                collections=req.collections,
                n_per_collection=req.n_results,
                min_score=req.min_score,
                date_from=req.date_from,
                date_to=req.date_to,
            ),
        )

        sources = [
            SourceItem(
                id=s["id"],
                collection=s["collection"],
                score=s["score"],
                document=s["document"],
                metadata=s["metadata"],
            )
            for s in result["sources"]
        ]

        pq_raw = result.get("parsed_query", {})
        parsed_info = ParsedQueryInfo(
            persons=pq_raw.get("persons", []),
            locations=pq_raw.get("locations", []),
            date_from=pq_raw.get("date_from"),
            date_to=pq_raw.get("date_to"),
            relevant_collections=pq_raw.get("relevant_collections", []),
            filter_summary=pq_raw.get("filter_summary", ""),
        ) if pq_raw else None

        return QueryResponse(
            query=result["query"],
            answer=result["answer"],
            sources=sources,
            source_count=len(sources),
            parsed_query=parsed_info,
        )

    except Exception as exc:
        logger.exception("Fehler bei RAG-Abfrage")
        raise HTTPException(status_code=500, detail=str(exc))
