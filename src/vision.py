"""
vision.py – Bildanalyse via Ollama (qwen3:8b).

Sendet rohe Bildbytes an einen lokalen Ollama-Server und gibt
eine kurze deutschsprachige Bildbeschreibung zurück.
"""

import base64
from typing import Optional

import ollama

OLLAMA_HOST = "http://172.26.112.1:11434"
MODEL = "qwen3:8b"

_client: Optional[ollama.Client] = None


def _get_client() -> ollama.Client:
    """Gibt eine (gecachte) Ollama-Client-Instanz zurück."""
    global _client
    if _client is None:
        _client = ollama.Client(host=OLLAMA_HOST)
    return _client


def describe_image(image_bytes: bytes) -> str:
    """Analysiert ein Bild und gibt eine kurze Beschreibung zurück.

    Args:
        image_bytes: Rohe Bilddaten (JPEG/PNG/WebP).

    Returns:
        Kurze Bildbeschreibung als String.
    """
    client = _get_client()

    # Ollama erwartet Bilder als Base64-kodierte Strings
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.chat(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": (
                    "Beschreibe dieses Bild in 1-3 kurzen Sätzen auf Deutsch. "
                    "Fokussiere dich auf die wichtigsten Elemente: Personen, Objekte, "
                    "Ort und Stimmung."
                ),
                "images": [image_b64],
            }
        ],
    )

    return response["message"]["content"].strip()
