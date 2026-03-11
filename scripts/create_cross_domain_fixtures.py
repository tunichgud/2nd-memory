#!/usr/bin/env python3
"""
create_cross_domain_fixtures.py

Erstellt 20 Cross-Domain-Benchmark-Fixtures für den Thinking-Mode-Vergleich.
Diese Queries erfordern die Verknüpfung mehrerer Collections (Fotos + Nachrichten + Reviews + Saved Places).

Muster-Typen:
  A) Foto + Nachricht (zeitlich verknüpft)
  B) Review + Foto (Ort verknüpft)
  C) Saved Places + Nachricht (was wurde besprochen?)
  D) Multi-Person + Multi-Zeitraum
  E) Emotionale / zwischenmenschliche Queries
  F) Organisations-Queries (wann, wer, wo organisiert)
  G) Vergleichs-Queries (welche Orte öfter, was wurde bewertet)
"""
from __future__ import annotations
import json, time, hashlib
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

FIXTURES_DIR = BASE_DIR / "tests" / "fixtures" / "rag_test_cases"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

def make_id(query: str) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    h  = hashlib.md5(query.encode()).hexdigest()[:6]
    return f"q_{ts}_{h}"

def get_sources(collection_name: str, query_text: str, n: int = 6) -> list[dict]:
    import chromadb
    client = chromadb.PersistentClient(path=str(BASE_DIR / "data" / "chroma"))
    col = client.get_collection(collection_name)
    r = col.query(query_texts=[query_text], n_results=n, include=["documents","metadatas","distances"])
    sources = []
    for doc, meta, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0]):
        score = round(max(0.0, 1 - dist), 4)
        sources.append({
            "id": f"{collection_name}_{hashlib.md5(doc.encode()).hexdigest()[:8]}",
            "collection": collection_name,
            "document": doc,
            "metadata": meta,
            "score": score,
        })
    return sources

def make_fixture(query: str, golden_answer: str, required_facts: list[str],
                 forbidden_facts: list[str], sources_spec: list[tuple[str,str,int]]) -> dict:
    """
    sources_spec: Liste von (collection_name, query_text, n_results)
    """
    all_sources = []
    for coll, q, n in sources_spec:
        all_sources.extend(get_sources(coll, q, n))

    from backend.rag.retriever_v2 import _get_system_prompt
    system_prompt = _get_system_prompt()

    return {
        "test_id": make_id(query),
        "query": query,
        "snapshot": {
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "sources": all_sources,
            "system_prompt": system_prompt,
            "parsed_query": {},
        },
        "golden": {
            "answer": golden_answer,
            "required_facts": required_facts,
            "forbidden_facts": forbidden_facts,
            "set_by": "prompt-engineer",
            "set_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    }


QUERIES = [
    # ── A) FOTO + NACHRICHT (zeitlich verknüpft) ────────────────────────────────
    {
        "query": "Wo war ich mit Nora und Sarah zusammen im Januar 2025?",
        "golden_answer": "Ihr wart gemeinsam in Ahrensburg. Am 1. Januar 2025 gibt es ein Foto von euch dreien in Ahrensburg.",
        "required_facts": ["Ahrensburg", "Januar 2025"],
        "forbidden_facts": ["München", "Hamburg"],
        "sources_spec": [
            ("photos", "Nora Sarah Januar 2025 Ahrensburg", 6),
            ("messages", "Nora Sarah Ahrensburg Neujahr", 4),
        ],
    },
    {
        "query": "Wann war ich das erste Mal mit Nora in München?",
        "golden_answer": "Das erste gemeinsame Foto mit Nora in München stammt vom August 2025.",
        "required_facts": ["München", "August 2025"],
        "forbidden_facts": [],
        "sources_spec": [
            ("photos", "Nora München erstes Mal", 8),
        ],
    },
    {
        "query": "Mit wem war ich im Stepenitztal?",
        "golden_answer": "Im Stepenitztal warst du mit Nora. Es gibt Fotos vom 29. Juni 2025 und vom 30. Mai 2025 aus dem Stepenitztal.",
        "required_facts": ["Nora", "Stepenitztal"],
        "forbidden_facts": ["Sarah"],
        "sources_spec": [
            ("photos", "Stepenitztal Personen", 6),
            ("messages", "Stepenitztal Wismar Reise", 3),
        ],
    },
    {
        "query": "Was haben Sarah und ich im Sommer 2019 gemacht? Gab es Urlaube oder besondere Ereignisse?",
        "golden_answer": "Im Sommer 2019 hat Sarah Urlaub auf Amrum gemacht. Josh war währenddessen auf einer Surfveranstaltung (vermutlich Fehmarn/Ostsee). Sie haben sich regelmäßig per WhatsApp ausgetauscht.",
        "required_facts": ["Amrum", "Urlaub", "2019"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Urlaub Sommer 2019 Amrum", 6),
            ("photos", "Sommer 2019 Fehmarn Ostsee", 4),
        ],
    },
    # ── B) REVIEW + FOTO (Ort-verknüpft) ───────────────────────────────────────
    {
        "query": "Welche Restaurants in Ahrensburg habe ich bewertet und war ich dort auch mit jemandem auf Fotos?",
        "golden_answer": "In Ahrensburg wurde das Ristorante Pizzeria da Barone (2/5 Sterne, April 2025) und das Caligo Coffee (5/5 Sterne, August 2024) bewertet. In Ahrensburg gibt es viele Fotos, u.a. mit Nora und Sarah.",
        "required_facts": ["Ahrensburg", "da Barone", "Caligo Coffee"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Ahrensburg Restaurant Bewertung", 5),
            ("photos", "Ahrensburg Personen Foto", 4),
        ],
    },
    {
        "query": "Ich erinnere mich an ein schlechtes Zahnarzt-Erlebnis — wann war das und was ist danach passiert?",
        "golden_answer": "Du hast die Zahnärzte Dorotheenstraße in Hamburg mit 1/5 Sternen bewertet (März 2025). Als Privatpatient hast du dich nicht gut aufgehoben gefühlt und die Praxis hat sogar eine Abmahnung wegen deiner negativen Rezension versucht.",
        "required_facts": ["Dorotheenstraße", "1/5 Sterne", "Abmahnung"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Zahnarzt schlechte Bewertung Abmahnung", 4),
            ("messages", "Zahnarzt Arzt Hamburg", 3),
        ],
    },
    {
        "query": "Wo war ich im September 2025 und was habe ich dort gemacht?",
        "golden_answer": "Im September 2025 warst du in Oranienbaum-Wörlitz und hast das Restaurant 'Zum Herzog von Anhalt' besucht und mit 5 Sternen bewertet.",
        "required_facts": ["September 2025", "Herzog von Anhalt", "Oranienbaum"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "September 2025 Restaurant Bewertung", 4),
            ("photos", "September 2025 Reise Ort", 4),
        ],
    },
    {
        "query": "Welchen Campingplatz habe ich in Sardinien am besten bewertet?",
        "golden_answer": "Du hast den Villaggio Camping La Mandragola in Siniscola mit 5 Sternen bewertet — schöner Campingplatz mit direktem Strandzugang und toller Umgebung.",
        "required_facts": ["Sardinien", "La Mandragola", "5 Sterne"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Sardinien Camping Bewertung", 5),
            ("saved_places", "Sardinien Camping", 3),
        ],
    },
    # ── C) SAVED PLACES + NACHRICHT ─────────────────────────────────────────────
    {
        "query": "Habe ich den Tierpark Wismar schon mal besucht und bewertet?",
        "golden_answer": "Ja, du hast den Tierpark Wismar mehrfach bewertet — Bewertungen vom 3. Mai 2025 und 11. Mai 2025 sind vorhanden.",
        "required_facts": ["Tierpark Wismar", "Mai 2025"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Tierpark Wismar Bewertung Besuch", 5),
            ("saved_places", "Wismar Tierpark", 3),
        ],
    },
    {
        "query": "Gibt es einen veganen Ort in Hamburg, den ich empfehlen würde?",
        "golden_answer": "Ja, The Vegan Eagle im Norden Hamburgs (Wischhöfen 4) wurde mit 5 Sternen bewertet. Essen, Service und Ambiente seien alle großartig gewesen.",
        "required_facts": ["Vegan Eagle", "Hamburg", "5 Sterne"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "vegan Hamburg Restaurant Empfehlung", 4),
            ("saved_places", "Hamburg vegan Restaurant", 3),
        ],
    },
    {
        "query": "Habe ich Arztpraxen in Hamburg gespeichert oder bewertet?",
        "golden_answer": "Ja, du hast die Zahnärzte Dorotheenstraße in Hamburg bewertet (1 Stern) und die Hausarzt-Praxis Forum Winterhude am Winterhuder Marktplatz als gespeicherten Ort. Außerdem gibt es einen Eintrag für Frau Ioanna Paradowski (Ärztin) in Eppendorf.",
        "required_facts": ["Dorotheenstraße", "Forum Winterhude"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Arzt Zahnarzt Hamburg Bewertung", 4),
            ("saved_places", "Arzt Hausarzt Hamburg", 4),
        ],
    },
    # ── D) MULTI-PERSON + MULTI-ZEITRAUM ────────────────────────────────────────
    {
        "query": "Wann war Nora zuletzt in München auf Fotos und wann war Sarah das letzte Mal dabei?",
        "golden_answer": "Nora war zuletzt im August 2025 in München auf Fotos. Sarah war ebenfalls im August 2025 in München dabei (z.B. Fotos vom 29.08.2025 in München-Ost und am 30.08.2025 in Bruck).",
        "required_facts": ["München", "August 2025", "Nora", "Sarah"],
        "forbidden_facts": [],
        "sources_spec": [
            ("photos", "Nora München letztes Mal", 6),
            ("photos", "Sarah München letztes Mal", 6),
        ],
    },
    {
        "query": "Haben Monika und Sarah gemeinsam an Ereignissen teilgenommen?",
        "golden_answer": "Auf Fotos aus Ahrensburg (Januar 2025, Mai 2025) sind sowohl Nora als auch Sarah zu sehen. Monika ist ebenfalls in Ahrensburg auf Fotos. Eine direkte Überschneidung aller drei in einer Szene lässt sich aus den Metadaten schließen.",
        "required_facts": ["Ahrensburg", "Monika", "Sarah"],
        "forbidden_facts": [],
        "sources_spec": [
            ("photos", "Monika Sarah Treffen Ahrensburg", 6),
            ("messages", "Monika Sarah treffen", 4),
        ],
    },
    {
        "query": "In welchen Ländern war ich auf Reisen und wo habe ich schlechte Erfahrungen gemacht?",
        "golden_answer": "Du warst in Deutschland, Italien, Portugal, Spanien, Vietnam und auf den Azoren. Schlechte Erfahrungen: Salitre Hostel Lissabon (2 Sterne, Schimmel), A Cabana Esposende Portugal (1 Stern), ElementFish Kite Camp Portugal (2 Sterne), sowie mehrere 1-Stern-Bewertungen in Hamburg.",
        "required_facts": ["Portugal", "Lissabon", "1 Stern"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "schlechte Bewertung Erfahrung Ausland", 6),
            ("saved_places", "Ausland Reise international", 4),
        ],
    },
    # ── E) EMOTIONALE / ZWISCHENMENSCHLICHE QUERIES ─────────────────────────────
    {
        "query": "Wie war die Stimmung zwischen Sarah und mir im Februar/März 2020?",
        "golden_answer": "Im Februar und März 2020 schrieben sich Sarah und Josh regelmäßig. Die Nachrichten zeigen eine enge, unterstützende Beziehung. Es gab Momente der Sorge und gegenseitigen Unterstützung (Josh: 'Geht es Dir gut?', Sarah: 'Ja, ist schön.'). Die Corona-Zeit begann, was Reisen und Treffen erschwerte.",
        "required_facts": ["2020", "Sarah"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Sarah Josh Februar März 2020 Stimmung Gefühle", 6),
        ],
    },
    {
        "query": "Gab es Momente wo Sarah in Nachrichten frustriert oder verärgert war?",
        "golden_answer": "Ja — im Juli 2019 schrieb Sarah, sie sei 'plötzlich so wütend und unzufrieden geworden'. Im August 2019 klagte sie über einen unerträglichen SEV (Schienenersatzverkehr, 30 Minuten im Bus). Im März 2020 schrieb sie 'Ist mega ätzend hier.'",
        "required_facts": ["wütend", "2019"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Sarah frustriert verärgert wütend unzufrieden", 6),
        ],
    },
    {
        "query": "Hat Josh jemals über Papa oder Monika in Nachrichten gesprochen und in welchem Kontext?",
        "golden_answer": "Ja — Im Juni 2019 fragte Sarah ob sie sich 'Samstagabend mit Papa und Monika' treffen können, Josh stimmte begeistert zu. Im Januar 2020 erwähnte Josh einen Anruf von 'Dieter'. Monika wird auch in Zusammenhang mit Jazz (dem Hund) erwähnt.",
        "required_facts": ["Papa", "Monika"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Papa Monika Treffen Familie", 6),
        ],
    },
    # ── F) ORGANISATIONS-QUERIES ────────────────────────────────────────────────
    {
        "query": "Wo habe ich in Hamburg gespeicherte Orte die mit Essen zu tun haben?",
        "golden_answer": "In Hamburg sind gespeichert: Pizza Social Club (Mühlenkamp), Ky Lan (Dorotheenstraße), Goldbeker (Schinkelstraße), Schramme 10 (Schrammsweg), Zum tanzenden Einhorn (Hammer Steindamm), Gröninger Privatbrauerei.",
        "required_facts": ["Hamburg", "Pizza Social Club"],
        "forbidden_facts": [],
        "sources_spec": [
            ("saved_places", "Hamburg Essen Restaurant Café Bar", 8),
        ],
    },
    # ── G) VERGLEICHS- / AGGREGATIONS-QUERIES ───────────────────────────────────
    {
        "query": "In welcher Stadt bin ich am häufigsten auf Fotos zu sehen — Hamburg oder München?",
        "golden_answer": "In den gespeicherten Fotos ist Hamburg häufiger vertreten als München. Nora war in München vor allem im August 2025. Hamburg (inkl. Ahrensburg als Umland) ist über mehrere Jahre mit deutlich mehr Fotos präsent.",
        "required_facts": ["Hamburg", "München"],
        "forbidden_facts": [],
        "sources_spec": [
            ("photos", "Hamburg Fotos", 6),
            ("photos", "München Fotos", 6),
        ],
    },
    {
        "query": "Welche Urlaubsreise war für mich besonders positiv — laut Bewertungen und Nachrichten?",
        "golden_answer": "Besonders positiv bewertet wurde der Aufenthalt bei Agriturismo B&B Monte Majore in Sardinien (5 Sterne, 2024) — 'Ein absolutes Highlight'. Ebenfalls sehr positiv: die Azoren-Reise (Surf Center, Terra do Pico Whale Watching, alle 5 Sterne, 2018).",
        "required_facts": ["Sardinien", "5 Sterne", "Highlight"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Urlaub positiv Highlight beste Erfahrung", 6),
            ("messages", "Urlaub toll schön Reise", 4),
        ],
    },
]


def main():
    print(f"Erstelle {len(QUERIES)} Cross-Domain-Fixtures...")
    created = []
    for i, q in enumerate(QUERIES, 1):
        print(f"  [{i:02d}/{len(QUERIES)}] {q['query'][:60]}...")
        try:
            fixture = make_fixture(
                query=q["query"],
                golden_answer=q["golden_answer"],
                required_facts=q["required_facts"],
                forbidden_facts=q["forbidden_facts"],
                sources_spec=q["sources_spec"],
            )
            filename = FIXTURES_DIR / f"{fixture['test_id']}.json"
            filename.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
            created.append(fixture["test_id"])
            print(f"         ✓ {fixture['test_id']} ({len(fixture['snapshot']['sources'])} Sources)")
        except Exception as e:
            print(f"         ❌ Fehler: {e}")
    print(f"\n✅ {len(created)}/{len(QUERIES)} Fixtures erstellt in {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
