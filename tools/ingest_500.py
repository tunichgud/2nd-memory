import sys
import os
sys.path.insert(0, os.path.abspath("."))

from backend.ingestion.photos import ingest_photos
import logging

logging.basicConfig(level=logging.INFO)

def main():
    print("Starte Ingestion (Ziel: 500 Bilder insgesamt)...")
    stats = ingest_photos(reset=False)
    print(f"\nIngestion abgeschlossen: {stats}")

if __name__ == "__main__":
    main()
