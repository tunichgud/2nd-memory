import logging
import numpy as np
import cv2
import torch
from PIL import Image
import mediapipe as mp
import torch
from pathlib import Path
from typing import List, Dict, Any, Tuple
from PIL import Image
from facenet_pytorch import InceptionResnetV1

logger = logging.getLogger(__name__)

# MediaPipe Face Detection Setup
from mediapipe.python.solutions import face_detection as mp_face_detection
face_detector = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)

# Initialize DirectML for AMD GPU acceleration
try:
    import torch_directml
    if torch_directml.is_available():
        device = torch_directml.device()
        logger.info(f"Using DirectML for AMD GPU: {torch_directml.device_name(0)}")
    else:
        device = torch.device('cpu')
        logger.info("DirectML not available, falling back to CPU.")
except ImportError:
    device = torch.device('cpu')
    logger.info("torch-directml not installed, falling back to CPU.")

resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)

def detect_faces(image_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Erkennt Gesichter in einem Bild und extrahiert Bounding Boxes.
    Returns: Liste von Dicts mit {'box': [ymin, xmin, ymax, xmax], 'score': float}
    """
    # Bytes in OpenCV Format konvertieren (MediaPipe braucht RGB)
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        return []
    
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w, _ = image.shape
    
    results = face_detector.process(image_rgb)
    faces = []
    
    if results.detections:
        for detection in results.detections:
            bbox = detection.location_data.relative_bounding_box
            # In absolute Koordinaten umrechnen (begrenzt auf Bildgröße)
            xmin = max(0, int(bbox.xmin * w))
            ymin = max(0, int(bbox.ymin * h))
            width = min(w - xmin, int(bbox.width * w))
            height = min(h - ymin, int(bbox.height * h))
            
            faces.append({
                'box': [ymin, xmin, ymin + height, xmin + width],
                'score': detection.score[0]
            })
            
    return faces

def get_face_embedding(image_bytes: bytes, box: List[int]) -> np.ndarray:
    """
    Extrahiert ein 128D oder 512D Embedding für einen Bildausschnitt.
    Box Format: [ymin, xmin, ymax, xmax]
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        return None
    
    ymin, xmin, ymax, xmax = box
    face_img = image[ymin:ymax, xmin:xmax]
    if face_img.size == 0:
        return None
    
    # Vorbereitung für Facenet: RGB + Resize auf 160x160 + Normalisierung
    face_rgb = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
    face_pil = Image.fromarray(face_rgb).resize((160, 160))
    
    # In Tensor konvertieren und Normalisieren (-1 bis 1)
    face_tensor = torch.tensor(np.array(face_pil)).permute(2, 0, 1).float()
    face_tensor = (face_tensor - 127.5) / 128.0
    face_tensor = face_tensor.unsqueeze(0).to(device)
    
    with torch.no_grad():
        embedding = resnet(face_tensor).cpu().numpy().flatten()
    
    return embedding

def process_and_store_faces(photo_id: str, image_bytes: bytes, metadata: Dict[str, Any]):
    """
    Erkennt Gesichter in einem Foto, erzeugt Embeddings und speichert sie in ChromaDB.
    """
    from backend.rag.store import upsert_documents
    
    logger.info(f"Suche nach Gesichtern in {photo_id}...")
    faces = detect_faces(image_bytes)
    
    if not faces:
        return 0
    
    ids, embeddings, metas, docs = [], [], [], []
    
    for i, face in enumerate(faces):
        emb = get_face_embedding(image_bytes, face['box'])
        if emb is not None:
            face_id = f"{photo_id}_face_{i}"
            ids.append(face_id)
            embeddings.append(emb.tolist())
            
            # Neue Metadaten für das Gesicht
            face_meta = metadata.copy()
            face_meta.update({
                "face_index": i,
                "confidence": float(face['score']),
                "bbox": ",".join(map(str, face['box'])),
                "entity_id": "", # Noch nicht zugeordnet
                "cluster_id": ""  # Wird später per DBSCAN gesetzt
            })
            metas.append(face_meta)
            docs.append(f"Gesicht {i} aus {photo_id}")
    
    if ids:
        upsert_documents("faces", ids, docs, embeddings, metas)
        logger.info(f"  -> {len(ids)} Gesichter gespeichert.")
        
    return len(ids)
