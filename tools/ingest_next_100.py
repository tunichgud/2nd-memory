import sys
import os
sys.path.insert(0, os.path.abspath("."))

from backend.ingestion.photos import ingest_photos
import logging

logging.basicConfig(level=logging.INFO)

def main():
    print("Starte Ingestion der nächsten 100 Bilder (Ziel: 150 insgesamt)...")
    # reset=False damit wir die alten behalten oder einfach überschreiben (upsert)
    stats = ingest_photos(reset=False)
    print(f"\nIngestion abgeschlossen: {stats}")

if __name__ == "__main__":
    main()
