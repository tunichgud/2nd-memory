import sys
import os
import logging

# Ensure we can import from backend
sys.path.insert(0, os.path.abspath("."))

from backend.llm.connector import embed

# Set logging to INFO to see our own logs but not the silenced ones
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

def test_embedding():
    print("--- Starte Embedding Test ---")
    texts = ["Das ist ein Test für die lokale Ingestion.", "München ist eine schöne Stadt."]
    
    # Der erste Aufruf sollte zeigen, dass er lokal lädt
    result = embed(texts)
    
    print(f"Erfolg! {len(result)} Embeddings erzeugt.")
    print(f"Länge des ersten Vektors: {len(result[0])}")
    print("--- Test Ende ---")

if __name__ == "__main__":
    test_embedding()
