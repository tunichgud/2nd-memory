#!/usr/bin/env python3
"""
check_face_assignments.py
=========================
Debug-Tool: Zeigt den Status aller Gesichtszuordnungen an.

Verwendung:
    python tools/check_face_assignments.py

    Optional mit Limit:
    python tools/check_face_assignments.py --limit 10

Output:
    - Anzahl zugeordnete vs. unzugeordnete Gesichter
    - Liste aller Personen mit Anzahl Gesichtern
    - Optional: Details zu einzelnen Gesichtern
"""

import sys
import argparse
import logging
from pathlib import Path
from collections import Counter

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.rag.store import get_collection

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_assignments(limit=None, show_details=False):
    """Prüft alle Gesichtszuordnungen."""
    logger.info("Lade Gesichter aus ChromaDB...")

    col = get_collection("faces")
    all_faces = col.get(include=["metadatas"], limit=limit or 10000)

    if not all_faces or not all_faces.get("ids"):
        logger.warning("Keine Gesichter in der Datenbank gefunden")
        return

    total = len(all_faces["ids"])
    assigned = 0
    unassigned = 0
    entities = Counter()

    # Statistiken sammeln
    for i, face_id in enumerate(all_faces["ids"]):
        meta = all_faces["metadatas"][i]
        entity_id = meta.get("entity_id")

        if entity_id in [None, "unassigned", ""]:
            unassigned += 1
        else:
            assigned += 1
            entities[entity_id] += 1

        # Details ausgeben (optional)
        if show_details and i < 20:
            logger.info(f"  Face {i+1}: entity_id='{entity_id}', filename='{meta.get('filename', 'N/A')}'")

    # Zusammenfassung
    print("\n" + "="*70)
    print("📊 GESICHTSZUORDNUNGEN - ÜBERSICHT")
    print("="*70)
    print(f"Total Gesichter:     {total}")
    print(f"✅ Zugeordnet:       {assigned} ({assigned/total*100:.1f}%)")
    print(f"❌ Unzugeordnet:     {unassigned} ({unassigned/total*100:.1f}%)")
    print(f"👥 Verschiedene Personen: {len(entities)}")
    print("="*70)

    if entities:
        print("\n🏆 TOP PERSONEN (nach Anzahl Gesichter):")
        print("-"*70)
        for i, (person, count) in enumerate(entities.most_common(20), 1):
            bar = "█" * min(int(count / max(entities.values()) * 40), 40)
            print(f"{i:2}. {person:20} {count:4} Gesichter  {bar}")
        print("-"*70)

    if unassigned > 0:
        print(f"\n⚠️  {unassigned} Gesichter sind noch nicht zugeordnet.")
        print("   → Gehe zum 'Personen'-Tab, um Cluster zu benennen")
        print("   → Oder nutze 'tools/migrate_ground_truth.py' für alte Validierungen")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prüft Gesichtszuordnungen in ChromaDB")
    parser.add_argument("--limit", type=int, help="Maximale Anzahl Gesichter (default: alle)")
    parser.add_argument("--details", action="store_true", help="Zeige Details zu einzelnen Gesichtern")
    args = parser.parse_args()

    try:
        check_assignments(limit=args.limit, show_details=args.details)
    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)
        sys.exit(1)
