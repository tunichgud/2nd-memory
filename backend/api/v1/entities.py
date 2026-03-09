from typing import List, Optional, Dict, Any
from pathlib import Path
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/entities", tags=["entities"])
logger = logging.getLogger(__name__)

# Base directory für Config-Zugriff
BASE_DIR = Path(__file__).resolve().parents[3]

# ==============================================================================
# Datenbank Clients
# ==============================================================================

from backend.rag.store import get_collection
from backend.rag.es_store import get_es_client, get_index_name


# ==============================================================================
# Pydantic Schemas
# ==============================================================================

class ChatMetadata(BaseModel):
    chat_name: str = Field(..., description="Name der Person im Chat (z.B. 'Sarah')")
    chat_identifier: str = Field(..., description="Eindeutiger Identifier aus dem Chat (z.B. Telefonnummer)")

class SingleFace(BaseModel):
    face_id: str
    image_path: str
    bbox: Optional[str] = None

class ClusterSuggestion(BaseModel):
    cluster_id: str
    image_paths: List[str] = Field(..., description="1-2 repräsentative Bilder für dieses Gesicht")
    bboxes: List[Optional[str]] = Field(default_factory=list, description="Bounding Boxes für die Gesichter (Format: 'x,y,w,h')")
    face_ids: List[str] = Field(default_factory=list, description="Face-IDs aller Gesichter in diesem Cluster")
    face_count: int = Field(..., description="Anzahl der gefundenen Gesichter in diesem Cluster")

class SuggestClustersResponse(BaseModel):
    suggestions: List[ClusterSuggestion]
    single_faces: List[SingleFace] = Field(default_factory=list, description="Gesichter, die in keinem Cluster sind")

class LinkEntityRequest(BaseModel):
    entity_name: str = Field(..., description="Der Name, der zugewiesen werden soll (z.B. 'Sarah')")
    chat_alias: Optional[str] = Field(None, description="Der verknüpfte Chat-Identifier (z.B. Telefonnummer)")
    cluster_id: str = Field(..., description="Die vom Nutzer bestätigte Cluster-ID des Gesichts")
    face_ids: List[str] = Field(default_factory=list, description="Direkte Face-IDs (optional, bevorzugt gegenüber neuem Clustering)")

class LinkEntityResponse(BaseModel):
    success: bool
    message: str
    entity: dict

class EntityUpdate(BaseModel):
    old_name: str
    new_name: str
    new_alias: Optional[str] = None

class SplitAnalysisResponse(BaseModel):
    entity_id: str
    sub_clusters: List[ClusterSuggestion]

class SplitRequest(BaseModel):
    source_entity: str
    target_entity: str
    cluster_id: str # sub-cluster within source

class LinkSingleRequest(BaseModel):
    face_id: str
    entity_name: str

class EntityListResponse(BaseModel):
    entities: List[Dict[str, Any]]

class FaceInfo(BaseModel):
    face_id: str
    filename: str
    bbox: Optional[str] = None
    confidence: float

class EntityFacesResponse(BaseModel):
    faces: List[FaceInfo]

class UnlinkFaceRequest(BaseModel):
    face_id: str
    entity_id: str


# ==============================================================================
# Endpunkte
# ==============================================================================

@router.get("/debug/faces")
async def debug_faces():
    """Debug-Endpunkt: Zeigt alle Gesichter mit entity_id"""
    col = get_collection("faces")
    all_faces = col.get(include=["metadatas"], limit=1000)

    stats = {
        "total_faces": len(all_faces["ids"]) if all_faces["ids"] else 0,
        "assigned": 0,
        "unassigned": 0,
        "entities": {}
    }

    if all_faces and all_faces["ids"]:
        for i, face_id in enumerate(all_faces["ids"]):
            meta = all_faces["metadatas"][i]
            entity_id = meta.get("entity_id")

            if entity_id in [None, "unassigned", ""]:
                stats["unassigned"] += 1
            else:
                stats["assigned"] += 1
                stats["entities"][entity_id] = stats["entities"].get(entity_id, 0) + 1

    return stats


@router.post("/suggest-clusters", response_model=SuggestClustersResponse)
async def suggest_clusters(chat_data: ChatMetadata):
    """
    Sucht nach unbekannten Gesichtern in der 'faces' Collection, gruppiert sie
    mittels DBSCAN Clustering und schlägt dem Nutzer die größten Gruppen vor.
    """
    import numpy as np
    from sklearn.cluster import DBSCAN
    
    col = get_collection("faces")
    # Nur Gesichter ohne Zuordnung holen
    # Hinweis: ChromaDB 'where' unterstützt oft nur Metadaten, wir filtern zur Sicherheit auch im Code
    all_faces = col.get(include=["embeddings", "metadatas"])
    
    if not all_faces or not all_faces.get("ids"):
        return SuggestClustersResponse(suggestions=[])
        
    embeddings = []
    metadata_list = []
    
    for i in range(len(all_faces["ids"])):
        meta = all_faces["metadatas"][i]
        # Nur unzugeordnete Gesichter berücksichtigen
        if meta.get("entity_id") in [None, "unassigned", ""]:
            embeddings.append(all_faces["embeddings"][i])
            metadata_list.append(meta)
            
    if not embeddings:
        return SuggestClustersResponse(suggestions=[])
        
    # DBSCAN Clustering - Lade Parameter aus Config
    import yaml
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    dbscan_eps = config.get("face_recognition", {}).get("dbscan_eps", 0.30)
    dbscan_min_samples = config.get("face_recognition", {}).get("dbscan_min_samples", 2)

    logger.info(f"DBSCAN Clustering with eps={dbscan_eps}, min_samples={dbscan_min_samples}")

    X = np.array(embeddings)
    clustering = DBSCAN(eps=dbscan_eps, min_samples=dbscan_min_samples, metric='cosine').fit(X)
    labels = clustering.labels_
    
    clusters = {}
    single_faces = []
    face_ids_list = []  # IDs aus all_faces, aligned mit embeddings

    for i in range(len(all_faces["ids"])):
        meta = all_faces["metadatas"][i]
        if meta.get("entity_id") in [None, "unassigned", ""]:
            face_ids_list.append(all_faces["ids"][i])

    for idx, label in enumerate(labels):
        meta = metadata_list[idx]
        img_name = meta.get("filename")
        face_id = face_ids_list[idx]
        if not img_name: continue

        if label == -1: # Noise / Einzelgesicht
            if len(single_faces) < 15: # Max 15 Einzelgesichter anzeigen
                single_faces.append(SingleFace(
                    face_id=face_id,
                    image_path=img_name,
                    bbox=meta.get("bbox")
                ))
            continue

        cid = f"cluster_{label}"
        if cid not in clusters:
            clusters[cid] = {"paths": [], "bboxes": [], "face_ids": []}
        clusters[cid]["paths"].append(img_name)
        clusters[cid]["bboxes"].append(meta.get("bbox"))
        clusters[cid]["face_ids"].append(face_id)

    # Sortiere nach Größe
    sorted_clusters = sorted(clusters.items(), key=lambda item: len(item[1]["paths"]), reverse=True)
    # Erstelle Antwort
    suggestions = []
    for cid, data in sorted_clusters[:20]:
        paths = data["paths"]
        bboxes = data["bboxes"]
        face_ids = data["face_ids"]
        num_samples = min(len(paths), 5)
        if len(paths) <= num_samples:
            diverse_paths = paths
            diverse_bboxes = bboxes
        else:
            indices = np.linspace(0, len(paths) - 1, num_samples, dtype=int)
            diverse_paths = [paths[i] for i in indices]
            diverse_bboxes = [bboxes[i] for i in indices]

        suggestions.append(ClusterSuggestion(
            cluster_id=cid,
            face_count=len(paths),
            image_paths=diverse_paths,
            bboxes=diverse_bboxes,
            face_ids=face_ids  # ALLE Face-IDs des Clusters (nicht nur Samples!)
        ))
        
    return SuggestClustersResponse(suggestions=suggestions, single_faces=single_faces)


@router.post("/link", response_model=LinkEntityResponse)
async def link_entity(link_data: LinkEntityRequest):
    """
    Verknüpft ein Gesichts-Cluster permanent mit einer Person aus dem Chat.
    Da Cluster IDs (cluster_0, etc.) flüchtig sind (DBSCAN Ergebnis),
    müssen wir hier sehr vorsichtig sein. In dieser Implementierung
    müsste der Client die IDs der Cluster sofort verknüpfen.
    """
    import numpy as np
    from sklearn.cluster import DBSCAN

    # 1. Face-IDs ermitteln
    # NEU: Wenn face_ids direkt mitgeschickt wurden, nutze diese (bevorzugt!)
    # ALT: Re-Clustering als Fallback (kann zu "Cluster nicht mehr aktuell" führen)

    col = get_collection("faces")

    if link_data.face_ids:
        # NEUE Methode: Face-IDs wurden vom Frontend mitgeschickt
        ids_to_update = link_data.face_ids
        logger.info(f"Using {len(ids_to_update)} face IDs directly from request")

        # Metadaten laden
        faces = col.get(ids=ids_to_update, include=["metadatas"])
        if not faces or not faces["ids"]:
            raise HTTPException(status_code=404, detail="Face IDs nicht gefunden.")
        metas_to_update = faces["metadatas"]
    else:
        # ALTE Methode: Re-Clustering (kann fehlschlagen!)
        logger.warning("No face_ids provided, falling back to re-clustering (unstable!)")

        all_faces = col.get(include=["embeddings", "metadatas"])

        if not all_faces or not all_faces.get("ids"):
            raise HTTPException(status_code=404, detail="Keine Gesichter in DB.")

        embeddings, metadata_list, face_ids = [], [], []
        for i in range(len(all_faces["ids"])):
            meta = all_faces["metadatas"][i]
            if meta.get("entity_id") in [None, "unassigned", ""]:
                embeddings.append(all_faces["embeddings"][i])
                metadata_list.append(meta)
                face_ids.append(all_faces["ids"][i])

        if not embeddings:
             raise HTTPException(status_code=404, detail="Keine unzugeordneten Gesichter.")

        X = np.array(embeddings)
        clustering = DBSCAN(eps=0.35, min_samples=2, metric='cosine').fit(X)
        labels = clustering.labels_

        target_label = int(link_data.cluster_id.replace("cluster_", ""))
        ids_to_update = [face_ids[i] for i, label in enumerate(labels) if label == target_label]
        metas_to_update = [metadata_list[i] for i, label in enumerate(labels) if label == target_label]

        if not ids_to_update:
            raise HTTPException(status_code=404, detail=f"Cluster {link_data.cluster_id} nicht mehr aktuell.")

    # Update in ChromaDB
    # WICHTIG: Metadaten kopieren und individuell updaten (nicht Referenz!)
    updated_metas = []
    for m in metas_to_update:
        # Kopie erstellen
        new_meta = dict(m)
        new_meta["entity_id"] = link_data.entity_name
        new_meta["cluster_id"] = link_data.cluster_id
        updated_metas.append(new_meta)

    col.update(ids=ids_to_update, metadatas=updated_metas)
    updated_count = len(ids_to_update)

    logger.info(f"Updated {updated_count} faces with entity_id='{link_data.entity_name}'")

    # 2. Update Elasticsearch (Unified Entity Graph aktualisieren)
    es = get_es_client()
    index_name = get_index_name("entities")
    
    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name)
        
    try:
        res = es.get(index=index_name, id=link_data.entity_name)
        entity = res["_source"]
        if link_data.chat_alias and link_data.chat_alias not in entity.setdefault("chat_aliases", []):
            entity["chat_aliases"].append(link_data.chat_alias)
        if link_data.cluster_id not in entity.setdefault("vision_clusters", []):
            entity["vision_clusters"].append(link_data.cluster_id)
    except Exception:
        entity = {
            "entity_id": link_data.entity_name,
            "chat_aliases": [link_data.chat_alias] if link_data.chat_alias else [],
            "vision_clusters": [link_data.cluster_id]
        }
    
    es.index(index=index_name, id=link_data.entity_name, document=entity)
    es.indices.refresh(index=index_name)

    # 3. Fotos aktualisieren (Sync)
    for face_id in ids_to_update:
         _sync_photo_persons(face_id)

    return LinkEntityResponse(
        success=True,
        message=f"Erfolgreich {updated_count} Gesichter mit '{link_data.entity_name}' verknüpft.",
        entity=entity
    )


@router.get("/list", response_model=EntityListResponse)
async def list_entities():
    """Listet alle bereits verknüpften Personen aus Elasticsearch."""
    es = get_es_client()
    index_name = get_index_name("entities")
    
    if not es.indices.exists(index=index_name):
        return EntityListResponse(entities=[])
        
    res = es.search(index=index_name, query={"match_all": {}}, size=1000)
    entities = [hit["_source"] for hit in res["hits"]["hits"]]
    
    # Previews hinzufügen (erstes Gesicht finden)
    col = get_collection("faces")
    for ent in entities:
        faces = col.get(where={"entity_id": ent["entity_id"]}, limit=1, include=["metadatas"])
        if faces["ids"]:
            meta = faces["metadatas"][0]
            ent["preview_face"] = {
                "filename": meta.get("filename"),
                "bbox": meta.get("bbox")
            }
            
    return EntityListResponse(entities=entities)


@router.get("/{entity_id}/faces", response_model=EntityFacesResponse)
async def list_entity_faces(entity_id: str):
    """Listet alle Gesichter, die einer Person zugeordnet sind."""
    col = get_collection("faces")
    data = col.get(where={"entity_id": entity_id}, include=["metadatas"])
    
    faces = []
    if data["ids"]:
        for i in range(len(data["ids"])):
            m = data["metadatas"][i]
            faces.append(FaceInfo(
                face_id=data["ids"][i],
                filename=m.get("filename", ""),
                bbox=m.get("bbox"),
                confidence=m.get("confidence", 0.0)
            ))
            
    return EntityFacesResponse(faces=faces)


@router.post("/unlink-face")
async def unlink_face(req: UnlinkFaceRequest):
    """Löst die Verknüpfung eines einzelnen Gesichts auf."""
    col = get_collection("faces")
    
    # 1. Gesicht in ChromaDB zurücksetzen
    res = col.get(ids=[req.face_id], include=["metadatas"])
    if not res["ids"]:
        raise HTTPException(status_code=404, detail="Gesicht nicht gefunden")
        
    meta = res["metadatas"][0]
    meta["entity_id"] = "unassigned"
    meta["cluster_id"] = ""
    col.update(ids=[req.face_id], metadatas=[meta])
    
    # 2. Sync Photo Persons (damit das Foto nicht mehr Sarah taggt, wenn das Gesicht weg ist)
    _sync_photo_persons(req.face_id)
    
    return {"success": True}


@router.post("/update")
async def update_entity(update: EntityUpdate):
    """Aktualisiert Name oder Alias einer Person."""
    es = get_es_client()
    index_name = get_index_name("entities")
    col = get_collection("faces")
    
    # 1. ES Dokument holen und ggf. umbenennen
    try:
        res = es.get(index=index_name, id=update.old_name)
        entity = res["_source"]
        entity["entity_id"] = update.new_name
        if update.new_alias is not None:
            entity["chat_aliases"] = [update.new_alias] if update.new_alias else []
            
        # Wenn der Name sich ändert: Altes löschen, Neues anlegen
        if update.old_name != update.new_name:
            es.delete(index=index_name, id=update.old_name)
            
        es.index(index=index_name, id=update.new_name, document=entity)
        es.indices.refresh(index=index_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Entity nicht gefunden: {e}")

    # 2. ChromaDB updaten
    # Wir suchen alle Gesichter mit der alten entity_id
    faces = col.get(where={"entity_id": update.old_name})
    if faces["ids"]:
        new_metas = faces["metadatas"]
        for m in new_metas:
            m["entity_id"] = update.new_name
        col.update(ids=faces["ids"], metadatas=new_metas)
        # 3. Fotos aktualisieren
        for face_id in faces["ids"]:
            await _sync_photo_persons(face_id)
        
    return {"success": True, "entity": entity}


@router.delete("/unlink/{entity_id}")
async def unlink_entity(entity_id: str):
    """Löst die Verknüpfung einer Person auf (Gesichter werden wieder 'unassigned')."""
    es = get_es_client()
    index_name = get_index_name("entities")
    col = get_collection("faces")
    
    # 1. Aus ES löschen
    try:
        es.delete(index=index_name, id=entity_id)
        es.indices.refresh(index=index_name)
    except Exception:
        pass # Wenn nicht in ES, egal

    # 2. In ChromaDB zurücksetzen
    faces = col.get(where={"entity_id": entity_id})
    if faces["ids"]:
        new_metas = faces["metadatas"]
        for m in new_metas:
            m["entity_id"] = "unassigned"
            m["cluster_id"] = ""
        col.update(ids=faces["ids"], metadatas=new_metas)
        
    return {"success": True}


@router.get("/{entity_id}/analyze-split", response_model=SplitAnalysisResponse)
async def analyze_split(entity_id: str):
    """Analysiert eine Person auf mögliche Sub-Cluster (für Splits)."""
    import numpy as np
    from sklearn.cluster import DBSCAN

    col = get_collection("faces")
    data = col.get(where={"entity_id": entity_id}, include=["embeddings", "metadatas"])
    
    if not data or not data["ids"]:
        raise HTTPException(status_code=404, detail="Keine Gesichter für diese Person gefunden.")

    X = np.array(data["embeddings"])
    # Sehr sensitiv clustern innerhalb der Person (eps=0.38)
    clustering = DBSCAN(eps=0.38, min_samples=2, metric='cosine').fit(X)
    labels = clustering.labels_
    
    clusters = {}
    for idx, label in enumerate(labels):
        if label == -1: continue
        cid = f"sub_{label}"
        if cid not in clusters: clusters[cid] = []
        img_name = data["metadatas"][idx].get("filename")
        if img_name: clusters[cid].append(img_name)

    suggestions = []
    for cid, paths in sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True):
        num_samples = min(len(paths), 5)
        indices = np.linspace(0, len(paths)-1, num_samples, dtype=int)
        diverse_paths = [paths[i] for i in indices]
        suggestions.append(ClusterSuggestion(cluster_id=cid, face_count=len(paths), image_paths=diverse_paths))

    return SplitAnalysisResponse(entity_id=entity_id, sub_clusters=suggestions)


@router.post("/split")
async def apply_split(split: SplitRequest):
    """Trennt ein Sub-Cluster von einer Person ab und weist es einer neuen zu."""
    import numpy as np
    from sklearn.cluster import DBSCAN

    col = get_collection("faces")
    data = col.get(where={"entity_id": split.source_entity}, include=["embeddings", "metadatas"])
    
    if not data or not data["ids"]:
        raise HTTPException(status_code=404, detail="Source Entity nicht gefunden.")

    X = np.array(data["embeddings"])
    clustering = DBSCAN(eps=0.38, min_samples=2, metric='cosine').fit(X)
    labels = clustering.labels_
    
    target_label = int(split.cluster_id.replace("sub_", ""))
    ids_to_move = [data["ids"][i] for i, label in enumerate(labels) if label == target_label]
    metas_to_update = [data["metadatas"][i] for i, label in enumerate(labels) if label == target_label]

    if not ids_to_move:
        raise HTTPException(status_code=404, detail="Sub-Cluster nicht gefunden.")

    for m in metas_to_update:
        m["entity_id"] = split.target_entity
    
    col.update(ids=ids_to_move, metadatas=metas_to_update)

    # Entity Graph in ES aktualisieren
    es = get_es_client()
    index_name = get_index_name("entities")
    
    # Target Entity anlegen/updaten
    try:
        res = es.get(index=index_name, id=split.target_entity)
        target = res["_source"]
    except Exception:
        target = {"entity_id": split.target_entity, "chat_aliases": [], "vision_clusters": []}
    
    es.index(index=index_name, id=split.target_entity, document=target)
    es.indices.refresh(index=index_name)

    return {"success": True, "moved_count": len(ids_to_move)}


@router.post("/link-single")
async def link_single(req: LinkSingleRequest):
    """Verknüpft ein einzelnes Gesicht permanent mit einer Person."""
    col = get_collection("faces")
    face = col.get(ids=[req.face_id], include=["metadatas"])
    
    if not face or not face["ids"]:
        raise HTTPException(status_code=404, detail="Gesicht nicht gefunden.")
        
    meta = face["metadatas"][0]
    meta["entity_id"] = req.entity_name
    meta["cluster_id"] = f"single_{req.face_id}" # Markierung als Einzelverknüpfung
    
    col.update(ids=[req.face_id], metadatas=[meta])
    
    # Entity Graph in ES aktualisieren (analog zu split)
    es = get_es_client()
    index_name = get_index_name("entities")
    try:
        res = es.get(index=index_name, id=req.entity_name)
        target = res["_source"]
    except Exception:
        target = {"entity_id": req.entity_name, "chat_aliases": [], "vision_clusters": []}
    
    es.index(index=index_name, id=req.entity_name, document=target)
    es.indices.refresh(index=index_name)
    
    # 3. Fotos aktualisieren
    _sync_photo_persons(req.face_id)
    
    return {"success": True}


def _sync_photo_persons(face_id: str):
    """
    Synchronisiert die entity_ids aller Gesichter eines Fotos zurück in die Metadaten des Fotos.
    Dies ist wichtig für das RAG-Retrieval (Filterung nach Personen).
    """
    import logging
    from backend.rag.store import get_collection
    from backend.rag.es_store import get_es_client, get_index_name, upsert_documents_es
    logger = logging.getLogger(__name__)

    try:
        f_col = get_collection("faces")
        p_col = get_collection("photos")
        
        # 1. Foto-ID aus dem Gesicht extrahieren
        f_res = f_col.get(ids=[face_id], include=["metadatas"])
        if not f_res["metadatas"]: return
        f_meta = f_res["metadatas"][0]
        
        # image_path/filename ist der Link zum Foto
        filename = f_meta.get("image_path") or f_meta.get("filename")
        if not filename: return
        
        # 2. Alle Gesichter dieses Fotos finden
        all_faces_of_photo = f_col.get(where={"image_path": filename}, include=["metadatas"])
        if (not all_faces_of_photo or not all_faces_of_photo.get("ids")) and f_meta.get("filename"):
             all_faces_of_photo = f_col.get(where={"filename": filename}, include=["metadatas"])

        persons = set()
        for m in all_faces_of_photo["metadatas"]:
            # 1. Moderne entity_id (manuell verknüpft)
            eid = m.get("entity_id")
            if eid and eid not in ("unassigned", ""):
                persons.add(eid)
            
            # 2. Legacy persons Feld (automatisch erkannt bei Ingestion)
            legacy_p = m.get("persons")
            if legacy_p:
                for p in legacy_p.split(","):
                    p = p.strip()
                    if p: persons.add(p)
        
        # 3. Foto-Metadaten in ChromaDB updaten
        # Wir versuchen verschiedene ID-Varianten
        search_ids = [filename, f"photo_{filename}"]
        p_res = p_col.get(ids=search_ids, include=["metadatas", "documents", "embeddings"])
        
        if p_res and p_res.get("ids"):
            pid = p_res["ids"][0]
            pmeta = p_res["metadatas"][0]
            doc = p_res["documents"][0]
            emb = p_res["embeddings"][0]
            
            p_list = sorted(list(persons))
            pmeta["persons"] = ",".join(p_list)
            
            # has_... flags setzen
            for p in p_list:
                first = p.split()[0].lower()
                for src, dst in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
                    first = first.replace(src, dst)
                pmeta[f"has_{first}"] = True
                
            p_col.update(ids=[pid], metadatas=[pmeta])
            
            # 4. Foto in ES updaten
            upsert_documents_es("photos", [pid], [doc], [emb], [pmeta])
            logger.info("Synced persons for photo %s: %s", pid, p_list)

    except Exception as exc:
        logger.warning("Sync Photo Persons fehlgeschlagen für %s: %s", face_id, exc)


# ==============================================================================
# Persona Suggestions Endpoint
# ==============================================================================

class PersonaSuggestion(BaseModel):
    name: str
    face_count: int = Field(..., description="Anzahl zugeordneter Gesichter")
    has_chat: bool = Field(False, description="Hat Chat-Verknüpfung")

class PersonaSuggestionsResponse(BaseModel):
    all_personas: List[str] = Field(..., description="Alle bekannten Persona-Namen (sortiert)")
    unassigned_personas: List[str] = Field(..., description="Personas ohne Gesichter")
    assigned_personas: List[PersonaSuggestion] = Field(..., description="Personas mit Gesichtern")


@router.get("/persona-suggestions", response_model=PersonaSuggestionsResponse)
async def get_persona_suggestions():
    """
    Gibt Vorschläge für Persona-Namen zurück.

    Nützlich beim Zuordnen von Gesichts-Clustern: Zeigt welche Personas
    bereits Gesichter haben und welche noch nicht.
    """
    from collections import defaultdict

    # 1. Gesichter-Collection: Wer hat bereits Gesichter?
    faces_col = get_collection("faces")
    all_faces = faces_col.get(include=["metadatas"], limit=10000)

    face_counts = defaultdict(int)

    if all_faces and all_faces.get("ids"):
        for meta in all_faces["metadatas"]:
            entity_id = meta.get("entity_id", "")
            if entity_id and entity_id not in ["", "unassigned"]:
                face_counts[entity_id] += 1

    # 2. Messages-Collection: Alle Chat-Personas
    try:
        messages_col = get_collection("messages")
        messages = messages_col.get(include=["metadatas"], limit=10000)

        chat_personas = set()
        if messages and messages.get("ids"):
            for meta in messages["metadatas"]:
                sender = meta.get("sender", "")
                if sender and sender not in ["", "unknown", "Me"]:
                    chat_personas.add(sender)
    except Exception as e:
        logger.warning(f"Could not load messages collection: {e}")
        chat_personas = set()

    # 3. Kombiniere beide Quellen
    all_personas_set = set(face_counts.keys()) | chat_personas
    all_personas = sorted(all_personas_set)

    # 4. Kategorisiere
    assigned_personas = []
    unassigned_personas = []

    for persona in all_personas:
        count = face_counts.get(persona, 0)
        has_chat = persona in chat_personas

        if count > 0:
            assigned_personas.append(PersonaSuggestion(
                name=persona,
                face_count=count,
                has_chat=has_chat
            ))
        else:
            unassigned_personas.append(persona)

    # Sortiere assigned_personas nach Anzahl Gesichter (absteigend)
    assigned_personas.sort(key=lambda x: x.face_count, reverse=True)

    logger.info(f"Persona suggestions: {len(all_personas)} total, {len(assigned_personas)} with faces, {len(unassigned_personas)} without")

    return PersonaSuggestionsResponse(
        all_personas=all_personas,
        unassigned_personas=sorted(unassigned_personas),
        assigned_personas=assigned_personas
    )
