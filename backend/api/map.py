"""
map.py – FastAPI Karten-Endpunkt für 2nd Memory.

Endpunkte:
  GET /api/locations  – Alle GPS-Punkte für Leaflet.js Kartenansicht
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["map"])


class LocationPoint(BaseModel):
    id: str
    source: str
    name: str
    lat: float
    lon: float
    date_iso: str
    extra: dict


class LocationsResponse(BaseModel):
    points: list[LocationPoint]
    total: int


@router.get("/locations", response_model=LocationsResponse)
async def get_locations(
    source: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> LocationsResponse:
    """Gibt alle GPS-Punkte für die Kartenansicht zurück."""
    from backend.rag.store import get_all_documents, COLLECTIONS

    points: list[LocationPoint] = []

    target_collections = [source] if source else COLLECTIONS

    for col_name in target_collections:
        if col_name == "messages":
            continue  # Nachrichten haben meist keine GPS-Daten

        try:
            data = get_all_documents(col_name)
            if not data["ids"]:
                continue

            for doc_id, meta in zip(data["ids"], data["metadatas"]):
                lat = meta.get("lat", 0.0)
                lon = meta.get("lon", 0.0)

                if not lat and not lon:
                    continue
                if lat == 0.0 and lon == 0.0:
                    continue

                # Datumsfilter
                if date_from or date_to:
                    date_ts = meta.get("date_ts", 0)
                    if date_from:
                        from datetime import datetime
                        try:
                            ts_from = int(datetime.fromisoformat(date_from).timestamp())
                            if date_ts < ts_from:
                                continue
                        except ValueError:
                            pass
                    if date_to:
                        from datetime import datetime
                        try:
                            ts_to = int(datetime.fromisoformat(date_to).timestamp())
                            if date_ts > ts_to:
                                continue
                        except ValueError:
                            pass

                # Name bestimmen
                name = (
                    meta.get("name")
                    or meta.get("filename")
                    or doc_id
                )

                # Zusätzliche Felder je nach Quelle
                extra = {}
                if col_name == "photos":
                    extra = {
                        "persons": meta.get("persons", ""),
                        "cluster": meta.get("cluster", ""),
                    }
                elif col_name in ("reviews", "saved_places"):
                    extra = {
                        "address": meta.get("address", ""),
                        "country": meta.get("country", ""),
                        "rating": meta.get("rating", 0),
                        "maps_url": meta.get("maps_url", ""),
                    }

                points.append(
                    LocationPoint(
                        id=doc_id,
                        source=col_name,
                        name=name,
                        lat=lat,
                        lon=lon,
                        date_iso=meta.get("date_iso", ""),
                        extra=extra,
                    )
                )

        except Exception as exc:
            logger.warning("Fehler beim Abrufen von '%s': %s", col_name, exc)
            continue

    return LocationsResponse(points=points, total=len(points))
