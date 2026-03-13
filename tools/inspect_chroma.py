#!/usr/bin/env python3
"""
inspect_chroma.py - 2nd Memory ChromaDB Entity Inspector

Dieses Skript liest alle Dokumente aus der ChromaDB und extrahiert
die eindeutigen Klarnamen von Personen und Orten (Cluster).
"""

import argparse
import os
import sys
from pathlib import Path

# Pfad zum Backend hinzufügen, damit Imports klappen
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.rag.store import get_all_documents, COLLECTIONS

def inspect(
    target_collections: list[str],
    show_persons: bool,
    show_locations: bool,
    show_missing: bool
):
    print("=== 2nd Memory ChromaDB Entity Inspector ===\n")
    
    for col_name in target_collections:
        if col_name not in COLLECTIONS:
            print(f"Warnung: Unbekannte Collection '{col_name}'. Überspringe.")
            continue
            
        print(f"--- Collection: {col_name} ---")
        try:
            data = get_all_documents(col_name)
            ids = data.get("ids", [])
            metas = data.get("metadatas", [])
            
            print(f"Einträge gesamt: {len(ids)}")
            if not ids:
                print()
                continue
            
            all_persons = set()
            all_clusters = set()
            
            # Für Debugging: Dokumente ohne die jeweiligen Metadaten
            missing_persons = []
            missing_locations = []
            
            for doc_id, meta in zip(ids, metas):
                has_person = False
                has_location = False
                
                # 1. Personen extrahieren
                persons = meta.get("persons", "")
                if persons:
                    has_person = True
                    # Komma-Separiert (z.B. "[PER_1], [PER_2]")
                    for p in persons.split(","):
                        if p.strip():
                            all_persons.add(p.strip())
                
                if not has_person:
                    missing_persons.append(doc_id)
                
                # 2. Orte/Cluster extrahieren
                cluster = meta.get("cluster", "")
                if cluster:
                    has_location = True
                    all_clusters.add(cluster)
                
                # Fallback für Reviews/Saved Places: Adress-Bestandteile nutzen
                # (Oft steht im vorletzten Teil des address Strings die Stadt/Region)
                address = meta.get("address", "")
                if address and not cluster:
                    parts = address.split(",")
                    if len(parts) > 1:
                        has_location = True
                        city_part = parts[-2].strip()
                        all_clusters.add(city_part)
                
                if not has_location:
                    missing_locations.append(doc_id)

            # --- Ausgabe ---
            
            if show_persons:
                if all_persons:
                    print(f"Erkannte Personen: {len(all_persons)}")
                    print(f"  {sorted(list(all_persons))}")
                else:
                    print("Keine Personen-Metadaten gefunden.")
                    
                if show_missing and missing_persons:
                    print(f"  Info: {len(missing_persons)} Dokumente ohne Personen.")
                    
            if show_locations:
                if all_clusters:
                    print(f"Erkannte Orte/Cluster: {len(all_clusters)}")
                    print(f"  {sorted(list(all_clusters))}")
                else:
                    print("Keine Orts-/Cluster-Metadaten gefunden.")
                    
                if show_missing and missing_locations:
                    if col_name != "messages": # Messages haben naturgemäß oft keine Orte
                        print(f"  Info: {len(missing_locations)} Dokumente ohne Orte.")
            
            print()
                
        except Exception as e:
            print(f"Fehler beim Lesen der Collection '{col_name}': {e}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="2nd Memory ChromaDB Inspector")
    
    parser.add_argument(
        "-c", "--collections",
        nargs="+",
        default=COLLECTIONS,
        choices=COLLECTIONS,
        help="Collections filtern (Standard: alle)"
    )
    
    parser.add_argument(
        "--no-persons",
        action="store_true",
        help="Personen nicht anzeigen"
    )
    
    parser.add_argument(
        "--no-locations",
        action="store_true",
        help="Orte/Cluster nicht anzeigen"
    )
    
    parser.add_argument(
        "--show-missing",
        action="store_true",
        help="Anzahl der Dokumente anzeigen, die keine Entitäten haben"
    )
    
    args = parser.parse_args()
    
    inspect(
        target_collections=args.collections,
        show_persons=not args.no_persons,
        show_locations=not args.no_locations,
        show_missing=args.show_missing
    )
