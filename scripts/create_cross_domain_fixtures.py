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
    # ── DESIGN-PRINZIPIEN dieser Queries ────────────────────────────────────────
    # 1. Nur Foto-Daten aus 2025 (was hochgeladen wurde)
    # 2. Cross-domain: mindestens 2 Collections müssen kombiniert werden
    # 3. Golden Answer nur aus verifizierten Datenpunkten — keine Spekulation
    # 4. Ahrensburg ist Wohnort seit 2023 → keine triviale Foto-Frage dort
    # 5. Jazz (Hündin, hatte Jan/Feb 2020 Schlaganfälle, April 2021 "Ich vermisse Jazzi"
    #    von Sarah) → emotionale cross-domain Fragen auf echter Grundlage
    # 6. Required facts: präzise und aus den Quellen belegbar
    # ────────────────────────────────────────────────────────────────────────────

    # ── A) FOTO + NACHRICHT (2025 Photos + Messages) ────────────────────────────

    # Wismar-Trip mit Nora: Fotos vom Mai 2025 + Messages mit Zeitkontext
    {
        "query": "Wann war ich in Wismar und mit wem?",
        "golden_answer": "Du warst im Mai 2025 in Wismar, zusammen mit Nora. Es gibt Fotos aus Wismar vom 3. bis 11. Mai 2025.",
        "required_facts": ["Wismar", "Nora", "Mai 2025"],
        "forbidden_facts": ["Sarah", "Tom"],
        "sources_spec": [
            ("photos", "Wismar Nora Mai 2025", 6),
            ("messages", "Wismar Reise Nora", 4),
        ],
    },

    # München August 2025: Nora + Sarah + Tom — cross-domain Foto+Nachricht
    {
        "query": "Mit wem war ich im August 2025 in München?",
        "golden_answer": "Im August 2025 warst du in München mit Nora, Sarah und Tom zusammen. Fotos zeigen euch gemeinsam am 29. und 30. August 2025.",
        "required_facts": ["München", "August 2025", "Nora", "Sarah", "Tom"],
        "forbidden_facts": [],
        "sources_spec": [
            ("photos", "München August 2025 Personen", 6),
            ("messages", "München Urlaub August 2025", 4),
        ],
    },

    # Stepenitztal: Fotos + Messages ob Ausflug geplant wurde
    {
        "query": "Was war das für ein Ausflugsziel Stepenitztal — und war ich dort mit jemandem?",
        "golden_answer": "Das Stepenitztal ist ein Naturgebiet (Wandergebiet) in Mecklenburg. Du warst dort mit Nora, es gibt Fotos aus dem Stepenitztal aus dem Jahr 2025.",
        "required_facts": ["Stepenitztal", "Nora"],
        "forbidden_facts": [],
        "sources_spec": [
            ("photos", "Stepenitztal Wandern Natur", 6),
            ("messages", "Stepenitztal Wandern Natur Ausflug", 3),
        ],
    },

    # Silvester / Neujahr 2025: Fotos + Messages zu Plänen/Stimmung
    {
        "query": "Was habe ich zu Silvester / Neujahr 2025 gemacht?",
        "golden_answer": "Zu Silvester/Neujahr 2025 warst du in Ahrensburg, gemeinsam mit Nora und Sarah. Es gibt Fotos vom 1. Januar 2025 aus Ahrensburg.",
        "required_facts": ["Silvester", "Neujahr", "Nora", "Sarah"],
        "forbidden_facts": [],
        "sources_spec": [
            ("photos", "Silvester Neujahr 2025 Feier", 6),
            ("messages", "Silvester Neujahr 2025 Pläne Feier", 5),
        ],
    },

    # ── B) JAZZ — NACHRICHTEN-CROSS-DOMAIN (Messages + Messages) ───────────────
    # Jazz: 140 Erwähnungen, Schlaganfall Jan/Feb 2020, "Ich vermisse Jazzi" April 2021

    # Wann hatte Jazz die Schlaganfälle?
    {
        "query": "Was ist mit Jazzi passiert — wann hatte er/sie die Schlaganfälle?",
        "golden_answer": "Jazz (Hündin) hatte im Januar und Februar 2020 Schlaganfälle. In den Nachrichten werden die Anfälle in diesem Zeitraum mehrfach erwähnt.",
        "required_facts": ["Jazz", "Schlaganfall", "2020"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Jazz Schlaganfall krank 2020", 7),
        ],
    },

    # Wann wurde Jazz zuletzt lebendig erwähnt?
    {
        "query": "Wann wurde Jazz zuletzt in Nachrichten erwähnt — und in welchem Kontext?",
        "golden_answer": "Jazz wurde zuletzt im April 2021 in den Nachrichten erwähnt — Sarah schrieb 'Ich vermisse Jazzi'. Dies deutet darauf hin, dass Jazz zu diesem Zeitpunkt bereits gestorben war.",
        "required_facts": ["Jazz", "2021", "vermisse"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Jazz vermisse tot letzter Eintrag 2021", 6),
            ("messages", "Jazz Hund 2020 2021", 5),
        ],
    },

    # Wer hat über Jazz gesprochen und in welchem Kontext?
    {
        "query": "Wer hat in den Nachrichten über den Hund Jazz gesprochen — und was wurde gesagt?",
        "golden_answer": "Über Jazz schrieben hauptsächlich Sarah und Josh. Sarah erwähnte Jazz oft liebevoll, fragte nach seinem/ihrem Zustand, und schrieb im April 2021 'Ich vermisse Jazzi'. Monika wird auch in Verbindung mit Jazz genannt (Fotos in Winningen).",
        "required_facts": ["Jazz", "Sarah", "Monika"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Jazz Hund Sarah Monika erwähnt", 7),
        ],
    },

    # ── C) REVIEW + FOTO (nur wenn Reviews existieren) ──────────────────────────

    # Tierpark Wismar: Reviews vom Mai 2025 + Fotos aus Wismar
    {
        "query": "Wie habe ich den Tierpark Wismar bewertet und war ich dort mit jemandem auf Fotos?",
        "golden_answer": "Du hast den Tierpark Wismar im Mai 2025 bewertet. Aus Wismar gibt es auch Fotos vom Mai 2025, auf denen Nora zu sehen ist.",
        "required_facts": ["Tierpark Wismar", "Mai 2025", "Nora"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Tierpark Wismar Bewertung", 5),
            ("photos", "Wismar Mai 2025 Nora", 4),
        ],
    },

    # Hamburg schlechte Erfahrungen: Reviews + Saved Places
    {
        "query": "Wo in Hamburg hatte ich schlechte Erlebnisse laut meinen Bewertungen?",
        "golden_answer": "In Hamburg hast du die Zahnärzte Dorotheenstraße mit 1 Stern bewertet (März 2025) — als Privatpatient hattest du dich dort nicht gut aufgehoben gefühlt, und die Praxis versuchte eine Abmahnung wegen deiner negativen Rezension.",
        "required_facts": ["Hamburg", "1 Stern", "Dorotheenstraße"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Hamburg schlechte Bewertung 1 Stern Erfahrung", 5),
            ("saved_places", "Hamburg Arzt Zahnarzt", 3),
        ],
    },

    # Sardinien: positive Reviews + saved places
    {
        "query": "Was weiß ich über meine Reise nach Sardinien — Bewertungen und gespeicherte Orte?",
        "golden_answer": "Du hast in Sardinien den Agriturismo B&B Monte Majore mit 5 Sternen bewertet ('Ein absolutes Highlight') und den Villaggio Camping La Mandragola in Siniscola. Mehrere Campingplätze und Unterkünfte sind auch als gespeicherte Orte vorhanden.",
        "required_facts": ["Sardinien", "Monte Majore", "5 Sterne"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Sardinien Camping Hotel Bewertung", 6),
            ("saved_places", "Sardinien Camping Unterkunft", 4),
        ],
    },

    # ── D) NACHRICHTEN + SAVED PLACES ───────────────────────────────────────────

    # Papa / Monika: wer sind sie und wie tauchen sie in Nachrichten auf?
    {
        "query": "Wer sind Papa und Monika und welche Rolle spielen sie in den Nachrichten?",
        "golden_answer": "Papa und Monika sind Familienmitglieder (vermutlich Vater und seine Partnerin). In den Nachrichten werden gemeinsame Treffen erwähnt, z.B. 'Samstagabend mit Papa und Monika'. Monika wird auch im Zusammenhang mit Jazz (dem Hund) und Fotos aus Winningen erwähnt.",
        "required_facts": ["Papa", "Monika"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Papa Monika Treffen Familie Winningen", 7),
        ],
    },

    # Gespeicherte Orte Hamburg + Nachrichten über Hamburg
    {
        "query": "Welche Restaurants oder Cafés in Hamburg habe ich gespeichert und worüber wurde in Nachrichten gesprochen?",
        "golden_answer": "In Hamburg hast du u.a. gespeichert: Pizza Social Club (Mühlenkamp), Ky Lan (Dorotheenstraße), Goldbeker, Schramme 10, The Vegan Eagle (5 Sterne Bewertung). In Nachrichten wurde Hamburg als Wohnort und für Ausgehtipps erwähnt.",
        "required_facts": ["Hamburg", "Pizza Social Club"],
        "forbidden_facts": [],
        "sources_spec": [
            ("saved_places", "Hamburg Restaurant Café Bar Essen", 6),
            ("messages", "Hamburg ausgehen Essen Restaurant", 4),
        ],
    },

    # ── E) MULTI-PERSON FOTO-QUERIES (2025) ──────────────────────────────────

    # Wann war Tom auf Fotos zu sehen?
    {
        "query": "Wann taucht Tom auf Fotos auf und in welchem Zusammenhang?",
        "golden_answer": "Tom ist auf Fotos aus München im August 2025 zu sehen, zusammen mit Nora und Sarah.",
        "required_facts": ["Tom", "München", "August 2025"],
        "forbidden_facts": [],
        "sources_spec": [
            ("photos", "Tom München August 2025", 6),
            ("messages", "Tom München Urlaub", 3),
        ],
    },

    # ── F) EMOTIONALE NACHRICHTEN-QUERIES ──────────────────────────────────────

    # Sarah frustriert / verärgert
    {
        "query": "Gab es Momente wo Sarah in Nachrichten frustriert oder unglücklich war?",
        "golden_answer": "Ja — im Juli 2019 schrieb Sarah, sie sei 'plötzlich so wütend und unzufrieden geworden'. Im August 2019 beschwerte sie sich über den SEV (Schienenersatzverkehr). Im März 2020 schrieb sie 'Ist mega ätzend hier.'",
        "required_facts": ["wütend", "Sarah", "2019"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Sarah frustriert verärgert wütend unzufrieden ätzend", 7),
        ],
    },

    # Wie haben Sarah und Josh 2020 kommuniziert (Corona-Zeit + Jazz krank)
    {
        "query": "Wie haben Sarah und Josh in der Corona-Zeit 2020 kommuniziert — gab es besondere Themen?",
        "golden_answer": "In der Corona-Zeit 2020 haben Sarah und Josh regelmäßig per WhatsApp kommuniziert. Themen waren: gegenseitige Unterstützung, Jazzi's Krankheit (Schlaganfälle im Januar/Februar 2020), Reisebeschränkungen und Alltagssituationen.",
        "required_facts": ["2020", "Sarah", "Jazz"],
        "forbidden_facts": [],
        "sources_spec": [
            ("messages", "Sarah Josh 2020 Corona Jazz krank Schlaganfall", 8),
        ],
    },

    # ── G) VERGLEICHS-QUERIES ───────────────────────────────────────────────────

    # Vergleich: beste vs. schlechteste Bewertungen
    {
        "query": "Was sind meine besten und schlechtesten Reiseerfahrungen laut Bewertungen?",
        "golden_answer": "Beste Erfahrungen (5 Sterne): Agriturismo B&B Monte Majore Sardinien, Vegan Eagle Hamburg, Azoren-Reise (Surf Center, Whale Watching), Tierpark Wismar. Schlechteste (1 Stern): Zahnärzte Dorotheenstraße Hamburg, A Cabana Esposende Portugal, Salitre Hostel Lissabon.",
        "required_facts": ["Monte Majore", "Sardinien", "5 Sterne", "1 Stern"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "beste schlechteste Bewertung Reise Erfahrung", 8),
        ],
    },

    # Azoren vs. Sardinien
    {
        "query": "War ich auf den Azoren und in Sardinien — und welche Reise hat mir besser gefallen?",
        "golden_answer": "Du warst auf beiden Reisen. Die Azoren-Reise umfasste Whale Watching und Surfstunden (alle 5 Sterne). In Sardinien warst du auf einem Agriturismo ('Ein absolutes Highlight', 5 Sterne). Beide Reisen waren sehr positiv bewertet.",
        "required_facts": ["Azoren", "Sardinien", "5 Sterne"],
        "forbidden_facts": [],
        "sources_spec": [
            ("reviews", "Azoren Sardinien Vergleich Bewertung", 6),
            ("saved_places", "Azoren Sardinien", 3),
        ],
    },

    # Wo war ich im Frühjahr 2025 auf Reisen (nicht Ahrensburg)?
    {
        "query": "Wo war ich im Frühjahr 2025 auf Reisen — außerhalb von Ahrensburg?",
        "golden_answer": "Im Frühjahr 2025 warst du in Wismar (mit Nora, Mai 2025) und im Stepenitztal. Diese Reisen sind durch Fotos aus dem Mai und Juni 2025 dokumentiert.",
        "required_facts": ["Wismar", "Mai 2025", "Nora"],
        "forbidden_facts": ["Ahrensburg"],
        "sources_spec": [
            ("photos", "Wismar Stepenitztal Frühling 2025 Reise", 7),
            ("messages", "Wismar Reise Frühjahr 2025", 4),
        ],
    },

    # Lübeck: War ich dort und was weiß man?
    {
        "query": "War ich in Lübeck und gibt es dazu Fotos oder Nachrichten?",
        "golden_answer": "Ja, es gibt Fotos aus Lübeck aus dem Jahr 2025. Lübeck liegt in der Nähe von Ahrensburg und Wismar.",
        "required_facts": ["Lübeck"],
        "forbidden_facts": [],
        "sources_spec": [
            ("photos", "Lübeck Fotos Besuch 2025", 5),
            ("messages", "Lübeck Besuch Stadt", 3),
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
