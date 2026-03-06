"""
geo_utils.py – Geografische Hilfsfunktionen für memosaur.
"""

import logging
import time
from typing import Optional, Dict, List
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)

# Cache für Bounding Boxes, um API-Calls zu minimieren
_bbox_cache: Dict[str, Optional[Dict[str, float]]] = {}

def get_bounding_box(location_name: str) -> Optional[Dict[str, float]]:
    """
    Löst einen Ortsnamen in eine Bounding Box auf.
    Gibt ein Dict mit {top, bottom, left, right} zurück oder None.
    """
    if not location_name:
        return None
        
    query = location_name.lower().strip()
    if query in _bbox_cache:
        return _bbox_cache[query]

    try:
        geolocator = Nominatim(user_agent="memosaur/1.0")
        # Wir suchen den Ort. Bounding Box ist standardmäßig im 'raw' Resultat enthalten.
        location = geolocator.geocode(query, language="de")
        
        if location and location.raw and "boundingbox" in location.raw:
            # Nominatim BBQ Format: [min_lat, max_lat, min_lon, max_lon]
            bbox = location.raw["boundingbox"]
            res = {
                "bottom": float(bbox[0]),
                "top":    float(bbox[1]),
                "left":   float(bbox[2]),
                "right":  float(bbox[3])
            }
            logger.info("Geo-BB für '%s' gefunden: %s", location_name, res)
            _bbox_cache[query] = res
            
            # Nominatim Policy: max 1 Request/Sekunde
            time.sleep(1.1)
            return res
            
    except (GeocoderTimedOut, GeocoderServiceError) as exc:
        logger.warning("Geocoding Timeout/Service-Fehler für '%s': %s", location_name, exc)
    except Exception as exc:
        logger.error("Unerwarteter Fehler bei Geocoding von '%s': %s", location_name, exc)

    _bbox_cache[query] = None
    return None
