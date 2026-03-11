"""
thinking_mode.py – Researcher → Challenger → Decider Pipeline für Memosaur.

Prinzip (Single-LLM, kein separater API-Call pro Agent):
    1. RESEARCHER: Analysiert die Quellen und erstellt einen Antwort-Entwurf + Forschungsplan.
    2. CHALLENGER:  Stellt die Schlussfolgerungen des Researchers infrage.
                   Prüft Vollständigkeit, alternative Interpretationen, vergessene Quellen.
    3. DECIDER:    Entscheidet, ob weiter recherchiert werden soll oder die Antwort reicht.
                   Berücksichtigt Iteration-Tiefe (max. 3) und Kosten-Nutzen.

Der Dialog (Researcher ↔ Challenger ↔ Decider) wird als SSE-Events gestreamt,
damit das Frontend ihn als eingeklappte Timeline zeigen kann.

Event-Typen (neu):
    {"type": "thinking_start", "content": {"iteration": 1, "max_iterations": 3}}
    {"type": "researcher",     "content": "...Entwurf und Forschungsplan..."}
    {"type": "challenger",     "content": "...Einwände und offene Fragen..."}
    {"type": "decider",        "content": {"decision": "continue"|"finalize", "reasoning": "..."}}
    {"type": "thinking_end",   "content": {"iterations": 2, "verdict": "finalized"}}

Diese Events werden neben den bestehenden Events aus retriever_v3_stream gestreamt.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from backend.llm.connector import chat, get_cfg

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3


# ============================================================================
# PROMPTS
# ============================================================================

RESEARCHER_SYSTEM = """\
Du bist der RESEARCHER in einem mehrstufigen Analyse-System für persönliche Erinnerungen.

Deine Aufgabe:
1. Analysiere die gegebene Nutzeranfrage und die verfügbaren Quellen (Fotos, Nachrichten, Bewertungen, Orte)
2. Erstelle einen **Antwort-Entwurf**: Was kannst du direkt aus den Quellen beantworten?
3. Identifiziere **Lücken**: Welche Aspekte der Frage sind noch nicht beantwortet?
4. Schlage **weitere Recherche-Schritte** vor falls nötig (z.B. andere Zeiträume, andere Personen)

Format deiner Antwort (immer genau so):
ANTWORT-ENTWURF:
[Dein Antwort-Entwurf auf Basis der verfügbaren Quellen]

LÜCKEN:
[Was ist noch unklar oder unbeantwortet?]

RECHERCHE-VORSCHLÄGE:
[Konkrete Schritte für tiefere Recherche, oder "Keine" wenn vollständig]

Antworte auf Deutsch. Sei präzise und faktentreu — erfinde keine Informationen."""

CHALLENGER_SYSTEM = """\
Du bist der CHALLENGER in einem mehrstufigen Analyse-System für persönliche Erinnerungen.

Deine Aufgabe:
1. Hinterfrage den ANTWORT-ENTWURF des Researchers kritisch
2. Prüfe: Wurden alle relevanten Quellen berücksichtigt?
3. Prüfe: Sind die Schlussfolgerungen korrekt oder gibt es alternative Interpretationen?
4. Identifiziere: Was wurde NICHT gefragt, könnte aber dennoch interessant sein?
5. Schlage **zusätzliche Aspekte** vor, die die Antwort bereichern würden

Format deiner Antwort (immer genau so):
EINWÄNDE:
[Konkrete Kritikpunkte am Antwort-Entwurf]

VERGESSENE ASPEKTE:
[Was wurde übersehen oder könnte noch interessant sein?]

ERGÄNZUNGSVORSCHLÄGE:
[Was sollte die finale Antwort noch enthalten?]

Sei konstruktiv-kritisch. Dein Ziel ist die bestmögliche Antwort für den Nutzer.
Antworte auf Deutsch."""

DECIDER_SYSTEM = """\
Du bist der DECIDER in einem mehrstufigen Analyse-System für persönliche Erinnerungen.

Du hast Folgendes gesehen:
- Die ursprüngliche Nutzeranfrage
- Den Antwort-Entwurf des Researchers
- Die Einwände des Challengers
- Aktuelle Iteration: {iteration} von maximal {max_iterations}

Deine Aufgabe:
Entscheide, ob weitere Recherche sinnvoll ist, ODER ob die Antwort jetzt finalisiert werden soll.

Berücksichtige dabei:
- Kosten: Jede weitere Iteration kostet Zeit und Ressourcen
- Nutzen: Würde weitere Recherche die Antwort-Qualität messbar verbessern?
- Vollständigkeit: Sind die wesentlichen Fakten bereits vorhanden?

Antworte IMMER im folgenden JSON-Format:
{{"decision": "continue" | "finalize", "reasoning": "...", "focus": "...(nur wenn continue)"}}

- "continue": Weitere Recherche sinnvoll (nur wenn noch echte Lücken bestehen UND Iteration < {max_iterations})
- "finalize": Antwort ist gut genug, weiter macht keinen Sinn

Bei Iteration {max_iterations} MUSST du "finalize" wählen."""

FINAL_SYNTHESIS_SYSTEM = """\
Du bist ein Synthese-Agent für persönliche Erinnerungen.

Du hast mehrere Analyse-Runden abgeschlossen:
- Der Researcher hat die Quellen analysiert
- Der Challenger hat Lücken und Ergänzungen identifiziert
- Der Decider hat zur Finalisierung entschieden

Deine Aufgabe: Erstelle die finale, vollständige Antwort für den Nutzer.

Regeln:
1. Beantworte die ursprüngliche Frage vollständig und präzise
2. Integriere die wertvollen Ergänzungen des Challengers
3. Zitiere Quellen mit [[1]], [[2]] etc.
4. Nutze ausschließlich Fakten aus den bereitgestellten Quellen
5. Antworte auf Deutsch, klar und strukturiert"""


# ============================================================================
# THINKING MODE ENGINE
# ============================================================================

async def thinking_mode_stream(
    query: str,
    context: str,
    max_iterations: int = MAX_ITERATIONS,
) -> AsyncGenerator[str, None]:
    """
    Führt die Researcher → Challenger → Decider Pipeline aus.

    Args:
        query: Die ursprüngliche Nutzeranfrage
        context: Formatierter Kontext aus den RAG-Quellen
        max_iterations: Maximale Anzahl Durchläufe (default: 3)

    Yields:
        JSON-Strings für SSE Events (ohne trailing \\n\\n)
    """
    import json

    def event(etype: str, content) -> str:
        return json.dumps({"type": etype, "content": content}, ensure_ascii=False)

    # Tracking-State
    researcher_draft = ""
    challenger_critique = ""
    iteration = 0

    yield event("thinking_start", {
        "iteration": 1,
        "max_iterations": max_iterations,
        "message": "Starte Thinking Mode — Researcher analysiert Quellen..."
    }) + "\n\n"

    while iteration < max_iterations:
        iteration += 1

        # ────────────────────────────────────────────────────────────────────
        # Phase A: RESEARCHER
        # ────────────────────────────────────────────────────────────────────
        researcher_input = f"""NUTZERANFRAGE: {query}

VERFÜGBARE QUELLEN:
{context}

{f'VORHERIGE ANALYSE (Iteration {iteration-1}):' if iteration > 1 else ''}
{researcher_draft if iteration > 1 else ''}

{f'CHALLENGER-EINWÄNDE (Iteration {iteration-1}):' if iteration > 1 else ''}
{challenger_critique if iteration > 1 else ''}

Führe deine Analyse durch:"""

        try:
            researcher_response = chat([
                {"role": "system", "content": RESEARCHER_SYSTEM},
                {"role": "user",   "content": researcher_input},
            ])
            researcher_draft = researcher_response
        except Exception as e:
            logger.error("Researcher-Fehler in Iteration %d: %s", iteration, e)
            researcher_draft = f"[Fehler: {e}]"

        yield event("researcher", {
            "iteration": iteration,
            "content": researcher_draft,
        }) + "\n\n"

        # ────────────────────────────────────────────────────────────────────
        # Phase B: CHALLENGER
        # ────────────────────────────────────────────────────────────────────
        challenger_input = f"""URSPRÜNGLICHE ANFRAGE: {query}

ANTWORT-ENTWURF DES RESEARCHERS (Iteration {iteration}):
{researcher_draft}

VERFÜGBARE QUELLEN (Überblick):
{context[:3000]}...

Stelle den Entwurf kritisch infrage:"""

        try:
            challenger_response = chat([
                {"role": "system", "content": CHALLENGER_SYSTEM},
                {"role": "user",   "content": challenger_input},
            ])
            challenger_critique = challenger_response
        except Exception as e:
            logger.error("Challenger-Fehler in Iteration %d: %s", iteration, e)
            challenger_critique = f"[Fehler: {e}]"

        yield event("challenger", {
            "iteration": iteration,
            "content": challenger_critique,
        }) + "\n\n"

        # ────────────────────────────────────────────────────────────────────
        # Phase C: DECIDER
        # ────────────────────────────────────────────────────────────────────
        decider_system = DECIDER_SYSTEM.format(
            iteration=iteration,
            max_iterations=max_iterations,
        )
        decider_input = f"""NUTZERANFRAGE: {query}

ANTWORT-ENTWURF (Researcher, Iteration {iteration}):
{researcher_draft}

EINWÄNDE (Challenger, Iteration {iteration}):
{challenger_critique}

Deine Entscheidung (JSON):"""

        try:
            decider_response = chat([
                {"role": "system", "content": decider_system},
                {"role": "user",   "content": decider_input},
            ])
            # JSON parsen
            import re
            json_match = re.search(r'\{[^{}]+\}', decider_response, re.DOTALL)
            if json_match:
                decision_data = json.loads(json_match.group())
            else:
                # Fallback: Iteration aufbrauchen
                decision_data = {
                    "decision": "finalize" if iteration >= max_iterations else "continue",
                    "reasoning": decider_response[:200],
                    "focus": "",
                }
        except Exception as e:
            logger.error("Decider-Fehler in Iteration %d: %s", iteration, e)
            decision_data = {
                "decision": "finalize",
                "reasoning": f"Fehler im Decider: {e}",
                "focus": "",
            }

        decision_data["iteration"] = iteration
        yield event("decider", decision_data) + "\n\n"

        # ────────────────────────────────────────────────────────────────────
        # Abbruch-Bedingung
        # ────────────────────────────────────────────────────────────────────
        if decision_data.get("decision") == "finalize" or iteration >= max_iterations:
            break

        # Für nächste Iteration: Fokus aus Decider übernehmen
        if decision_data.get("focus"):
            # Nicht verwendbar ohne neues Retrieval — aber als Kontext weitergeben
            researcher_draft = f"{researcher_draft}\n\n[FOKUS für nächste Runde: {decision_data['focus']}]"

    # ────────────────────────────────────────────────────────────────────────
    # FINALE SYNTHESE
    # ────────────────────────────────────────────────────────────────────────
    yield event("thinking_end", {
        "iterations": iteration,
        "verdict": "finalized",
        "message": f"Thinking Mode abgeschlossen nach {iteration} Iteration(en)",
    }) + "\n\n"

    # Finale Antwort aus Researcher-Draft + Challenger-Ergänzungen synthetisieren
    synthesis_input = f"""URSPRÜNGLICHE ANFRAGE: {query}

ANALYSE-ERGEBNIS (Researcher, letzte Iteration):
{researcher_draft}

ERGÄNZUNGEN (Challenger):
{challenger_critique}

VOLLSTÄNDIGE QUELLEN:
{context}

Erstelle jetzt die finale, vollständige Antwort für den Nutzer:"""

    try:
        final_answer = chat([
            {"role": "system", "content": FINAL_SYNTHESIS_SYSTEM},
            {"role": "user",   "content": synthesis_input},
        ])
    except Exception as e:
        logger.error("Synthese-Fehler: %s", e)
        final_answer = researcher_draft  # Fallback auf letzten Draft

    # Finale Antwort als text-Event streamen (Token-by-Token wäre ideal,
    # aber für den Benchmark reicht ein einzelnes Event)
    for chunk in _split_into_chunks(final_answer, chunk_size=100):
        yield event("text", chunk) + "\n\n"


def _split_into_chunks(text: str, chunk_size: int = 100) -> list[str]:
    """Teilt Text in Chunks auf für Streaming-Simulation."""
    words = text.split(" ")
    chunks = []
    current = []
    current_len = 0
    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_size:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
    if current:
        chunks.append(" ".join(current))
    return chunks
