import sys
import os
import time
import logging
from pathlib import Path

# Add the project root to sys.path so 'backend...' imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Setze detailliertes Logging für die kritischen Module
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
# Unterdrücke HTTP-Spam
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from backend.ingestion.whatsapp import ingest_whatsapp

def main():
    if len(sys.argv) < 2:
        print("Verwendung: python tools/import_whatsapp_cli.py <pfad/zum/chat.txt>")
        sys.exit(1)

    chat_path = Path(sys.argv[1])
    if not chat_path.exists():
        print(f"FEHLER: Datei nicht gefunden -> {chat_path}")
        sys.exit(1)

    start_time = time.time()

    def on_progress(current, total, label):
        print(f"\n---> FORTSCHRITT: [{current}/{total}] {label}")

    print(f"Starte Debug-Import für {chat_path}...")
    try:
        stats = ingest_whatsapp(chat_path, progress_callback=on_progress)
        print("\n=== IMPORT ABGESCHLOSSEN ===")
        print(f"Statistiken: {stats}")
        print(f"Dauer: {time.time() - start_time:.2f} Sekunden")
    except KeyboardInterrupt:
        print("\nImport durch Benutzer abgebrochen.")
        sys.exit(1)
    except Exception as e:
        print(f"\nABSTURZ: {e}")
        logging.exception("Vollständiger Traceback:")
        sys.exit(1)

if __name__ == "__main__":
    main()
