"""
es_store.py – Elasticsearch Interface für memosaur.

Bietet eine einheitliche API für das Speichern und Abfragen von Vektoren
und Metadaten in Elasticsearch.
"""

import logging
import sys
from typing import Any, Dict, List, Optional
from elasticsearch import Elasticsearch, helpers
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

_client: Optional[Elasticsearch] = None
_config: Optional[Dict[str, Any]] = None
_es_available: Optional[bool] = None  # None = noch nicht geprueft; True/False nach erstem Check

def _get_config() -> Dict[str, Any]:
    global _config
    if _config is None:
        cfg_path = Path(__file__).resolve().parents[2] / "config.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            _config = yaml.safe_load(f)
    return _config

def get_es_client() -> Elasticsearch:
    """Gibt den gecachten Elasticsearch-Client zurueck.

    Wenn verify_elasticsearch() beim Start gemeldet hat, dass ES nicht
    erreichbar ist (_es_available == False), wird kein erneuter Verbindungsversuch
    unternommen — der Client wird trotzdem zurueckgegeben, aber Aufrufer wie
    query_es() pruefen _es_available selbst und kehren fruehzeitig zurueck.
    """
    global _client
    if _client is None:
        cfg = _get_config()
        hosts = cfg.get("elasticsearch", {}).get("hosts", ["http://localhost:9200"])
        _client = Elasticsearch(hosts)
        if _es_available is None:
            # verify_elasticsearch() wurde noch nicht aufgerufen (z.B. im Test)
            if not _client.ping():
                logger.warning("Elasticsearch ist aktuell nicht erreichbar unter %s", hosts)
            else:
                logger.info("Elasticsearch Client initialisiert: %s", hosts)
        # Wenn _es_available bereits gesetzt ist, verzichten wir auf erneutes Ping
    return _client


def verify_elasticsearch():
    """Prueft beim Systemstart, ob Elasticsearch laeuft. Nur Warning, kein Exit.

    Setzt das Modul-Flag _es_available, damit spaetere Aufrufe (query_es,
    get_es_client) nicht erneut versuchen, ES zu erreichen, wenn es beim
    Start bereits nicht erreichbar war.
    """
    global _es_available
    cfg = _get_config()
    hosts = cfg.get("elasticsearch", {}).get("hosts", ["http://localhost:9200"])
    client = Elasticsearch(hosts)

    try:
        if not client.ping():
            logger.warning(
                "Elasticsearch nicht erreichbar unter %s - laeuft im Fallback-Modus (ChromaDB only)",
                hosts,
            )
            _es_available = False
            return
    except Exception as e:
        logger.warning(
            "Elasticsearch nicht verfuegbar: %s - laeuft im Fallback-Modus (ChromaDB only)", e
        )
        _es_available = False
        return

    _es_available = True
    logger.info("Elasticsearch erreichbar: %s", hosts)


def _print_es_error(hosts: list):
    print("\n" + "="*80)
    print(" 🚨 FEHLER: ELASTICSEARCH NICHT ERREICHBAR")
    print("="*80)
    print(f"\n memosaur benötigt Elasticsearch zur Suche, aber unter {hosts}")
    print(" konnte keine Verbindung aufgebaut werden.")
    print("\n MÖGLICHE LÖSUNGEN:")
    print(" 1. Starte Elasticsearch mit Docker:")
    print("    docker compose up -d")
    print("\n 2. Prüfe, ob Docker Desktop oder der Docker-Dienst läuft.")
    print(" 3. Kontrolliere die 'hosts' in deiner config.yaml.")
    print("\n" + "="*80 + "\n")

def get_index_name(collection_name: str) -> str:
    cfg = _get_config()
    prefix = cfg.get("elasticsearch", {}).get("index_prefix", "memosaur_")
    return f"{prefix}{collection_name}"

def ensure_index(collection_name: str, dim: int = 384):
    """Erstellt den Index mit passenden Mappings falls nicht vorhanden."""
    client = get_es_client()
    index_name = get_index_name(collection_name)
    
    if client.indices.exists(index=index_name):
        return

    # Basis-Mapping
    mappings = {
        "properties": {
            "id": {"type": "keyword"},
            "user_id": {"type": "keyword"},
            "timestamp": {"type": "date"},
            "content": {"type": "text", "analyzer": "german"},
            "embedding": {
                "type": "dense_vector",
                "dims": dim,
                "index": True,
                "similarity": "cosine"
            },
            "source": {"type": "keyword"},
            # Dynamische Metadaten-Felder als Keywords für exakte Filter
            "metadata": {
                "type": "object",
                "dynamic": True
            }
        }
    }

    # Spezialisierungen
    if collection_name == "photos":
        mappings["properties"]["location"] = {"type": "geo_point"}
        mappings["properties"]["place_name"] = {
            "type": "text", 
            "analyzer": "german",
            "fields": {
                "keyword": {"type": "keyword", "ignore_above": 256}
            }
        }
        mappings["properties"]["persons"] = {"type": "keyword"} # Array
        mappings["properties"]["cluster"] = {"type": "keyword"}
    elif collection_name == "messages":
        mappings["properties"]["persons"] = {"type": "keyword"}  # Array
        mappings["properties"]["senders"] = {"type": "keyword"}
        mappings["properties"]["chat_name"] = {"type": "keyword"}
    elif collection_name == "reviews":
        mappings["properties"]["rating"] = {"type": "float"}
        mappings["properties"]["place_name"] = {
            "type": "text",
            "analyzer": "german",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
        }
        mappings["properties"]["address"] = {"type": "text", "analyzer": "german"}
        mappings["properties"]["location"] = {"type": "geo_point"}
    elif collection_name == "saved_places":
        mappings["properties"]["location"] = {"type": "geo_point"}
        mappings["properties"]["place_name"] = {
            "type": "text",
            "analyzer": "german",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
        }
        mappings["properties"]["address"] = {"type": "text", "analyzer": "german"}
        mappings["properties"]["category"] = {"type": "keyword"}
    elif collection_name == "faces":
        # Faces use 128-dim embeddings (face recognition), not 384-dim (sentence embeddings)
        mappings["properties"]["embedding"] = {
            "type": "dense_vector",
            "dims": 128,
            "index": True,
            "similarity": "cosine",
        }
        mappings["properties"]["cluster"] = {"type": "keyword"}
        mappings["properties"]["persons"] = {"type": "keyword"}  # Array

    client.indices.create(index=index_name, mappings=mappings)
    logger.info("Elasticsearch Index created: %s", index_name)

def upsert_documents_es(
    collection_name: str,
    ids: List[str],
    documents: List[str],
    embeddings: List[List[float]],
    metadatas: List[Dict[str, Any]],
):
    """Speichert Dokumente via Bulk-API in Elasticsearch."""
    client = get_es_client()
    index_name = get_index_name(collection_name)
    
    # Sicherstellen, dass Index existiert (nimmt Dimension vom ersten Embedding)
    if len(embeddings) > 0:
        ensure_index(collection_name, dim=len(embeddings[0]))

    actions = []
    for i in range(len(ids)):
        meta = metadatas[i]
        doc = {
            "id": ids[i],
            "user_id": meta.get("user_id"),
            "content": documents[i],
            "embedding": embeddings[i],
            "timestamp": meta.get("date_ts") * 1000 if meta.get("date_ts") else None, # ES nutzt ms
            "source": meta.get("source"),
            "metadata": meta
        }
        
        # Flache Top-Level Felder für effizientes Filtern extrahieren
        if collection_name == "photos":
            if meta.get("lat") and meta.get("lon"):
                doc["location"] = {"lat": meta["lat"], "lon": meta["lon"]}
            doc["place_name"] = meta.get("place_name")
            doc["cluster"] = meta.get("cluster")
            # Personen-Liste aus Metadaten (String -> List)
            pers_str = meta.get("persons") or meta.get("people", "")
            if isinstance(pers_str, str):
                doc["persons"] = [p.strip() for p in pers_str.split(",") if p.strip()]
            else:
                doc["persons"] = pers_str

        elif collection_name == "messages":
            doc["chat_name"] = meta.get("chat_name")
            pers_str = meta.get("persons") or meta.get("mentioned_persons", "")
            if isinstance(pers_str, str):
                doc["persons"] = [p.strip() for p in pers_str.split(",") if p.strip()]
            else:
                doc["persons"] = pers_str
            
            sender = meta.get("sender")
            if sender:
                doc["senders"] = [sender]

        actions.append({
            "_index": index_name,
            "_id": ids[i],
            "_source": doc
        })

    helpers.bulk(client, actions)
    client.indices.refresh(index=index_name)
    logger.info("ES Bulk Upsert: %d Dokumente in '%s'", len(ids), index_name)

def query_es(
    collection_name: str,
    query_vector: List[float],
    user_id: str,
    n_results: int = 10,
    person_names: Optional[List[str]] = None,
    location_names: Optional[List[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Hybride Suche in Elasticsearch (Vektor + Filter).

    Gibt sofort eine leere Liste zurueck wenn Elasticsearch beim Start als
    nicht erreichbar markiert wurde (_es_available == False), um wiederholte
    Verbindungsversuche und Log-Spam zu vermeiden.
    """
    if _es_available is False:
        return []
    client = get_es_client()
    index_name = get_index_name(collection_name)
    
    if not client.indices.exists(index=index_name):
        return []

    # Bool Query für Filter
    must_filters = [{"term": {"user_id": user_id}}]
    
    if person_names:
        # person_names ist jetzt eine flache Liste aller aufgelösten IDs (Clusters, Aliase, Namen)
        # Wenn wir mehrere Personen suchen, kommen diese als Gruppen vom Retriever?
        # Nein, retriever_v2 verschmilzt aktuell alle zu einer Liste.
        # WICHTIG: Sollten wir OR oder AND nutzen? 
        # POC-Ansatz: Wenn person_names eine flache Liste ist, suchen wir Dokumente,
        # die MINDESTENS EINEN dieser Identifier enthalten.
        must_filters.append({"terms": {"persons": person_names}})

    if location_names:
        from backend.rag.geo_utils import get_bounding_box
        geo_filters = []
        for loc_name in location_names:
            bbox = get_bounding_box(loc_name)
            if bbox:
                geo_filters.append({
                    "geo_bounding_box": {
                        "location": {
                            "top_left": {"lat": bbox["top"], "lon": bbox["left"]},
                            "bottom_right": {"lat": bbox["bottom"], "lon": bbox["right"]}
                        }
                    }
                })
            else:
                # Fallback auf Textsuche (keyword) falls keine Bounding-Box gefunden
                geo_filters.append({"term": {"place_name.keyword": loc_name.lower()}})
        
        if geo_filters:
            # Mindestens einer der Orte muss matchen (OR)
            must_filters.append({"bool": {"should": geo_filters, "minimum_should_match": 1}})

    if date_from or date_to:
        date_range = {}
        if date_from: date_range["gte"] = date_from
        if date_to: date_range["lte"] = date_to
        must_filters.append({"range": {"timestamp": date_range}})

    # KNN Suche kombiniert mit Filter
    search_query = {
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": n_results,
            "num_candidates": 100,
            "filter": must_filters
        }
    }

    import json
    logger.debug("ES Search Query [%s]: %s", collection_name, json.dumps(search_query, indent=2, ensure_ascii=False))

    res = client.search(index=index_name, body=search_query, size=n_results)
    
    hits = []
    for hit in res["hits"]["hits"]:
        source = hit["_source"]
        hits.append({
            "id": hit["_id"],
            "document": source["content"],
            "metadata": source["metadata"],
            "score": hit["_score"],
            "collection": collection_name
        })
    
    return hits

def keyword_search_es(
    collection_name: str,
    query: str,
    user_id: str,
    n_results: int = 10,
    person_names: Optional[List[str]] = None,
    location_names: Optional[List[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """BM25 Volltext-Suche auf dem content-Feld via Elasticsearch match-Query.

    Args:
        collection_name: Name der Collection (z.B. "messages").
        query: Suchstring, wird als BM25 match-Query ausgewertet.
        user_id: Pflicht-Filter, wird als term-Filter auf user_id angewendet.
        n_results: Maximale Anzahl Treffer.
        person_names: Optionale Personen-Filter (OR-Verknüpfung auf persons-Feld).
        location_names: Optionale Orts-Filter (geo_bounding_box oder place_name.keyword).
        date_from: Optionales Startdatum (ISO-Format, z.B. "2024-01-01").
        date_to: Optionales Enddatum.

    Returns:
        Liste von Dicts mit id, document, metadata, score, collection.
        Leere Liste wenn ES nicht verfügbar oder Index nicht existiert.
    """
    if _es_available is False:
        return []
    client = get_es_client()
    index_name = get_index_name(collection_name)

    if not client.indices.exists(index=index_name):
        return []

    must_filters: List[Dict[str, Any]] = [{"term": {"user_id": user_id}}]

    if person_names:
        must_filters.append({"terms": {"persons": person_names}})

    if location_names:
        from backend.rag.geo_utils import get_bounding_box
        geo_filters = []
        for loc_name in location_names:
            bbox = get_bounding_box(loc_name)
            if bbox:
                geo_filters.append({
                    "geo_bounding_box": {
                        "location": {
                            "top_left": {"lat": bbox["top"], "lon": bbox["left"]},
                            "bottom_right": {"lat": bbox["bottom"], "lon": bbox["right"]},
                        }
                    }
                })
            else:
                geo_filters.append({"term": {"place_name.keyword": loc_name.lower()}})
        if geo_filters:
            must_filters.append({"bool": {"should": geo_filters, "minimum_should_match": 1}})

    if date_from or date_to:
        date_range: Dict[str, Any] = {}
        if date_from:
            date_range["gte"] = date_from
        if date_to:
            date_range["lte"] = date_to
        must_filters.append({"range": {"timestamp": date_range}})

    search_query = {
        "query": {
            "bool": {
                "must": [{"match": {"content": query}}],
                "filter": must_filters,
            }
        }
    }

    import json
    logger.debug(
        "ES Keyword Search [%s]: %s",
        collection_name,
        json.dumps(search_query, indent=2, ensure_ascii=False),
    )

    res = client.search(index=index_name, body=search_query, size=n_results)

    hits = []
    for hit in res["hits"]["hits"]:
        source = hit["_source"]
        hits.append({
            "id": hit["_id"],
            "document": source["content"],
            "metadata": source.get("metadata", {}),
            "score": hit["_score"],
            "collection": collection_name,
        })

    return hits


def get_all_documents_es(
    collection_name: str,
    user_id: str,
    filters: Optional[Dict[str, Any]] = None,
    max_docs: int = 10_000,
) -> List[Dict[str, Any]]:
    """Gibt alle Dokumente einer Collection für einen User zurück.

    Nutzt search_after für effizientes Paging über grosse Ergebnismengen.
    Für den Karten-Endpunkt und die Validierungsansicht.

    Args:
        collection_name: Name der Collection.
        user_id: Pflicht-Filter.
        filters: Optionale zusätzliche Elasticsearch filter-Klauseln (Liste von Dicts).
        max_docs: Maximale Anzahl Dokumente (Sicherheits-Cap, Standard 10.000).

    Returns:
        Liste von Dicts mit id, document, metadata, collection.
        Leere Liste wenn ES nicht verfügbar.
    """
    if _es_available is False:
        return []
    client = get_es_client()
    index_name = get_index_name(collection_name)

    if not client.indices.exists(index=index_name):
        return []

    must_filters: List[Dict[str, Any]] = [{"term": {"user_id": user_id}}]
    if filters:
        must_filters.extend(filters)

    page_size = min(1000, max_docs)
    search_query: Dict[str, Any] = {
        "query": {"bool": {"filter": must_filters}},
        "sort": [{"_id": "asc"}],
    }

    results = []
    search_after = None

    while len(results) < max_docs:
        body = dict(search_query)
        if search_after is not None:
            body["search_after"] = search_after

        res = client.search(index=index_name, body=body, size=page_size)
        page_hits = res["hits"]["hits"]
        if not page_hits:
            break

        for hit in page_hits:
            source = hit["_source"]
            results.append({
                "id": hit["_id"],
                "document": source.get("content", ""),
                "metadata": source.get("metadata", {}),
                "collection": collection_name,
            })

        search_after = page_hits[-1]["sort"]

        if len(page_hits) < page_size:
            break

    logger.debug(
        "get_all_documents_es: %d Dokumente aus '%s' geladen", len(results), collection_name
    )
    return results[:max_docs]


def count_documents_es(collection_name: str, user_id: str) -> int:
    """Zählt Dokumente einer Collection für einen User via Elasticsearch _count API.

    Ersetzt store_v2.count_documents_for_user() für den ES-Pfad.

    Args:
        collection_name: Name der Collection.
        user_id: Filter auf diesen User.

    Returns:
        Anzahl Dokumente als int. 0 wenn ES nicht verfügbar.
    """
    if _es_available is False:
        return 0
    client = get_es_client()
    index_name = get_index_name(collection_name)

    if not client.indices.exists(index=index_name):
        return 0

    res = client.count(
        index=index_name,
        body={"query": {"term": {"user_id": user_id}}},
    )
    return int(res.get("count", 0))


def get_document_by_id_es(
    collection_name: str, doc_id: str
) -> Optional[Dict[str, Any]]:
    """Gibt ein einzelnes Dokument anhand seiner ID zurück.

    Args:
        collection_name: Name der Collection.
        doc_id: Elasticsearch-Dokument-ID.

    Returns:
        Dict mit id, document, metadata oder None wenn nicht gefunden / ES down.
    """
    if _es_available is False:
        return None
    client = get_es_client()
    index_name = get_index_name(collection_name)

    try:
        res = client.get(index=index_name, id=doc_id)
        source = res["_source"]
        return {
            "id": res["_id"],
            "document": source.get("content", ""),
            "metadata": source.get("metadata", {}),
            "collection": collection_name,
        }
    except Exception as exc:
        logger.debug("get_document_by_id_es '%s/%s': %s", collection_name, doc_id, exc)
        return None


def delete_document_es(collection_name: str, doc_id: str) -> bool:
    """Löscht ein einzelnes Dokument aus dem Elasticsearch-Index.

    Args:
        collection_name: Name der Collection.
        doc_id: Elasticsearch-Dokument-ID.

    Returns:
        True wenn erfolgreich gelöscht, False sonst (inkl. ES down oder nicht gefunden).
    """
    if _es_available is False:
        return False
    client = get_es_client()
    index_name = get_index_name(collection_name)

    try:
        client.delete(index=index_name, id=doc_id)
        logger.info("ES Dokument gelöscht: %s/%s", collection_name, doc_id)
        return True
    except Exception as exc:
        logger.warning("delete_document_es '%s/%s' fehlgeschlagen: %s", collection_name, doc_id, exc)
        return False


def reset_es_index(collection_name: str):
    client = get_es_client()
    index_name = get_index_name(collection_name)
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)
        logger.info("ES Index gelöscht: %s", index_name)
