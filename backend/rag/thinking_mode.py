"""
thinking_mode.py – Researcher → Challenger → Decider Pipeline für 2nd Memory.

Prinzip:
    1. RESEARCHER  Analysiert Quellen, erstellt Antwort-Entwurf + benennt Lücken.
    2. CHALLENGER  Hinterfragt den Entwurf kritisch. Schlägt bei fehlenden Fakten
                   konkrete Retrieval-Parameter (Datum, Keywords) für Nachsuche vor.
    3. DECIDER     Entscheidet: finalisieren ODER neue Retrieval-Runde mit Fokus.
                   Bei "continue" wird retrieval_fn aufgerufen → akkumulierter Kontext.

Gegenüber der Vorgängerversion neu:
    - Aktives Nachforschen: retrieval_fn-Parameter erlaubt echtes Re-Retrieval
      statt nur Text-Kommentare ohne Konsequenz.
    - Decider-JSON enthält strukturierte retrieval_focus-Parameter.
    - Challenger-Prompt explizit auf fehlende Fakten + konkrete Suchvorschläge ausgerichtet.
    - God-Function aufgebrochen in _call_researcher / _call_challenger / _call_decider.
    - Alle Imports auf Datei-Top verschoben.

SSE-Event-Typen (unverändert):
    {"type": "thinking_start", "content": {"iteration": 1, "max_iterations": 3}}
    {"type": "researcher",     "content": {"iteration": 1, "content": "..."}}
    {"type": "challenger",     "content": {"iteration": 1, "content": "..."}}
    {"type": "decider",        "content": {"decision": "continue"|"finalize", ...}}
    {"type": "retrieval_focus","content": {"date_from": "...", "keywords": [...], ...}}
    {"type": "thinking_end",   "content": {"iterations": 2}}
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Callable

from backend.llm.connector import chat
from backend.rag.constants import MAX_THINKING_ITERATIONS
from backend.rag.rag_types import RetrievalFn, RetrievalParams

logger = logging.getLogger(__name__)


# ============================================================================
# PROMPTS
# ============================================================================

# Design-Prinzip:
# FAKTEN: rein extraktiv — exakte Zitate + Zeitstempel, keine Paraphrase.
#         Verhindert Context Bloat und Information Degradation.
# THESEN: inferenziell — logische Schlüsse aus den Fakten, kurz + begründet.
#         Verhindert, dass Rohdaten ohne Interpretation an Challenger + Synthesizer gehen.
# Einzig der Final-Synthesis-Agent produziert Fließtext für den Nutzer.

_RESEARCHER_SYSTEM = """\
Du bist der RESEARCHER in einem mehrstufigen Analyse-System.

Zwei klar getrennte Aufgaben:
A) FAKTEN: Extrahiere Rohdaten rein extraktiv — exakte Zitate + Zeitstempel, keine Paraphrase.
B) THESEN: Ziehe logische Schlüsse aus diesen Fakten. Sei mutig — zaude nicht.
   Aus "kannst Jazz neues Hundefutter annehmen?" folgt zwingend: "Jazz ist vermutlich ein Hund."
   Aus "Ich bringe Anna zum Kindergarten" folgt: "Anna geht in den Kindergarten."
   Thesen müssen kurz, begründet und falsifizierbar sein.

CHAT-RICHTUNGS-REGEL (kritisch bei WhatsApp!):
Beachte IMMER wer schreibt und wer empfängt — die Richtung ändert die Bedeutung:
- "Viele Grüße an Barbara" / "Sag X Bescheid"     → X ist NICHT beim Schreibenden, sondern beim Empfänger.
- "Ich hoffe es wird schön mit deinen Freundinnen" → die Freundinnen sind beim EMPFÄNGER, nicht beim ABSENDER.
- "Wie war dein Aufenthalt in München?"            → der EMPFÄNGER war in München, nicht der ABSENDER.
Falsche These: "Marie war mit Alex in München" aus "Viele Grüße an Barbara!" (Marie schreibt AN Alex).
Richtige These: "Alex war in München; Marie war nicht dabei (sie schickt Grüße aus der Ferne)."

Format (strikt einhalten):
FAKTEN:
- [DATUM] QUELLE: "exaktes Zitat oder Feldwert"

THESEN (aus Fakten abgeleitet):
- These (Beleg: "Zitat das sie stützt")

FEHLENDE FAKTEN:
- [was fehlt, z.B. "Todesdatum nicht in Quellen vorhanden"]

RECHERCHE-PARAMETER (nur wenn FEHLENDE FAKTEN vorhanden):
date_from=YYYY-MM-DD, date_to=YYYY-MM-DD, keywords=["term1"]

RELEVANZ-FILTER (kritisch!):
Extrahiere NUR Fakten die DIREKT zur Nutzeranfrage beitragen.
Wenn eine Quelle thematisch unpassend ist (z.B. Anfrage nach Jazz-Hund, Quelle über Menschenbeerdigung),
dann IGNORIERE sie vollständig — extrahiere keinen einzigen Fakt daraus.
Lieber zu wenig als irrelevante Fakten, die den Kontext verstopfen.

DEDUPLICATION (kritisch!):
Fakten die bereits in "BEREITS BEKANNTE FAKTEN" stehen → NICHT nochmals extrahieren.
Wenn ALLE Fakten der neuen Quellen bereits bekannt sind → schreibe nur:
FAKTEN:
- (Keine neuen Fakten — alle relevanten Informationen bereits bekannt)

Regeln:
- FAKTEN: nur was explizit in den Quellen steht — kein Fließtext, kein Paraphrasieren.
- THESEN: nur was logisch aus den Fakten folgt — keine Spekulation ohne Quellenbeleg.
- Kein Fließtext außer in den vorgegebenen Feldern."""


_CHALLENGER_SYSTEM = """\
Du bist der CHALLENGER in einem mehrstufigen Fakten-Extraktions-System.

WICHTIG: Paraphrasiere NICHT. Arbeite rein extraktiv.
Wiederhole den Researcher-Output NICHT. Benenne nur Lücken und Widersprüche.

Aufgabe:
1. Prüfe: Fehlen wichtige Fakten in FAKTEN des Researchers?
2. Prüfe: Gibt es Widersprüche zwischen extrahierten Fakten?
3. Wenn kritisches Faktum fehlt: gib konkrete Suchparameter an.

TEMPORALE INFERENZ-REGEL (kritisch!):
Suche NIE ab dem frühesten bekannten Datum. Leite date_from logisch ab:
- Tod/Abschied: date_from = letzter bekannter Lebenszeichen-Zeitstempel
- Erste Erwähnung: date_from = frühester möglicher Zeitpunkt
- "Wann passierte X nach Y?": date_from = Datum von Y

Falsch: date_from=2000-01-01 (sucht die ganze Geschichte durch)
Richtig: letzter Jazz-Chunk war 2021-01-24 → date_from=2021-01-24

VOCABULARY-MISMATCH-REGEL (kritisch!):
Keywords müssen Wörter sein, die TATSÄCHLICH im originalen Chat-Text vorkommen.
NIEMALS analytische Meta-Begriffe verwenden — echte Menschen schreiben die nie.

VERBOTEN (analytisch, nie im Chat):       STATTDESSEN (echte Alltagssprache):
"Jazz Identität"                          "Gassi", "Futter", "Leine", "Tierarzt"
"Jazz Haustier", "Jazz Person"            "bellte", "Pfote", "brav", "Halsband"
"Jazz Todesdatum", "wer ist Jazz"         "eingeschläfert", "Regenbogenbrücke"
"Jazz Alex Mueller"                       "vermisse", "traurig", "letzter Tag"

GATTUNGSNAME-REGEL: Bei Haustier-Sterbefällen suche mit Gattungsnamen.
Im Trauermoment schreiben Besitzer "Hund"/"Katze" — nicht den Eigennamen.

SORT-ORDER-REGEL:
Wähle sort_order passend zur gesuchten Information:
- sort_order=date_desc  → wenn das LETZTE Ereignis gesucht wird (Tod, letzter Kontakt,
                          Ende eines Projekts). Neueste Nachrichten zuerst im Kontext.
- sort_order=date_asc   → wenn das ERSTE Ereignis gesucht wird (erste Erwähnung,
                          Kennenlernen, Beginn). Älteste Nachrichten zuerst.
- sort_order=relevance  → wenn Zeitreihenfolge egal ist (default, semantisch beste zuerst).

Beispiel — Todesdatum von Jazz (Hund) fehlt, letzter Lebensbeleg 24.01.21:
  LÜCKEN:
  - Sterbebeleg fehlt. Letzter Lebensbeleg: [24.01.21] "Geht's Jazz gut?"
  SUCHPARAMETER: date_from=2021-01-24, date_to=2021-06-01, keywords=["Hund"], sort_order=date_desc
  HINWEIS: Todeseintrag erscheint direkt nach letztem Lebenszeichen — neueste zuerst

Format (strikt einhalten):
LÜCKEN:
- [konkret was fehlt oder welcher Widerspruch besteht]

SUCHPARAMETER (nur wenn kritisches Faktum fehlt):
date_from=YYYY-MM-DD, date_to=YYYY-MM-DD, keywords=["term1", "term2"], sort_order=relevance|date_desc|date_asc
HINWEIS: [ein Satz was gesucht wird]

Kein Fließtext. Keine Wiederholung des Researcher-Outputs."""


_DECIDER_SYSTEM = """\
Du bist der DECIDER in einem mehrstufigen Fakten-Extraktions-System.
Aktuelle Iteration: {iteration} von maximal {max_iterations}

Aufgabe: Entscheide ausschließlich auf Basis der LÜCKEN des Challengers.
Wenn SUCHPARAMETER vorhanden und das fehlende Faktum wichtig ist: "continue".
Sonst: "finalize".

Antworte NUR mit diesem JSON (kein Text davor/danach):
{{
  "decision": "continue" | "finalize",
  "reasoning": "Ein Satz Begründung",
  "retrieval_focus": {{
    "date_from": "YYYY-MM-DD",
    "date_to": "YYYY-MM-DD",
    "keywords": ["term1", "term2"],
    "sort_order": "relevance" | "date_desc" | "date_asc",
    "hint": "Ein Satz was gesucht wird"
  }}
}}

"retrieval_focus" nur bei "continue", sonst weglassen.
"sort_order" weglassen wenn "relevance" (default).
Bei Iteration {max_iterations} MUSST du "finalize" wählen."""


_FINAL_SYNTHESIS_SYSTEM = """\
Du bist der SYNTHESIZER — der einzige Agent der natürliche Sprache produziert.

Du erhältst:
- Die Nutzeranfrage
- FAKTEN (exakte Zitate + Zeitstempel) aus mehreren Analyse-Runden
- THESEN (logische Schlüsse aus den Fakten)
- AKTUELLER KONTEXT: die nummerierten Quellen [1], [2], ... der letzten Recherche-Runde

Aufgabe: Formuliere daraus eine vollständige, natürlichsprachige Antwort.

Regeln:
1. Beantworte die Frage vollständig und präzise.
2. Nutze sowohl FAKTEN als auch THESEN — Thesen explizit als Schlussfolgerung kennzeichnen
   (z.B. "Das lässt darauf schließen, dass..." oder "Vermutlich...").
3. Zitiere Quellen mit [[1]], [[2]] etc. — NUR Nummern die im AKTUELLEN KONTEXT vorhanden sind.
   Erfinde KEINE Nummern. Wenn eine Tatsache nicht im aktuellen Kontext belegt ist,
   formuliere ohne Nummer oder nenne Datum + Quellentyp (z.B. "WhatsApp, 24.06.2022").
4. Erfinde keine Informationen die nicht in Fakten oder Thesen stehen.
5. Antworte auf Deutsch, klar und strukturiert.
6. Nenne Daten, Namen und Orte exakt wie in den Fakten angegeben."""


# ============================================================================
# ÖFFENTLICHE API
# ============================================================================

async def thinking_mode_stream(
    query: str,
    context: str,
    max_iterations: int = MAX_THINKING_ITERATIONS,
    retrieval_fn: RetrievalFn | None = None,
    trace_fn: Callable[[dict], None] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Researcher → Challenger → Decider Pipeline mit optionalem aktiven Nachforschen.

    Args:
        query:          Die ursprüngliche Nutzeranfrage.
        context:        Formatierter Kontext aus dem initialen Retrieval.
        max_iterations: Maximale Anzahl Durchläufe.
        retrieval_fn:   Optional. Wenn übergeben und Decider sagt "continue",
                        wird echtes Re-Retrieval mit retrieval_focus durchgeführt.
                        Signatur: async (RetrievalParams) -> str (neuer Kontext-String)

    Yields:
        JSON-Strings für SSE Events (ohne trailing \\n\\n)
    """
    accumulated_context = context          # nur aktuelle neue Docs — wird jede Iter ERSETZT
    accumulated_researcher_facts = ""      # komprimierte FAKTEN+THESEN aller Iterationen
    researcher_draft = ""
    challenger_critique = ""
    iteration = 0

    yield _event("thinking_start", {
        "iteration": 1,
        "max_iterations": max_iterations,
        "message": "Starte Thinking Mode — Researcher analysiert Quellen...",
    })

    while iteration < max_iterations:
        iteration += 1

        # ── Phase A: RESEARCHER ──────────────────────────────────────────────
        researcher_draft = await _call_researcher(
            query=query,
            context=accumulated_context,
            known_facts=accumulated_researcher_facts,
            prev_critique=challenger_critique if iteration > 1 else "",
            iteration=iteration,
        )

        # Akkumuliere FAKTEN+THESEN aller Iterationen (komprimiert, kein Roh-Kontext).
        # "Keine neuen Fakten"-Ausgaben werden NICHT angehängt — sie blähen sonst
        # accumulated_researcher_facts auf ohne inhaltlichen Mehrwert.
        _is_empty_draft = "keine neuen fakten" in researcher_draft.lower()
        if not _is_empty_draft:
            if accumulated_researcher_facts:
                accumulated_researcher_facts += f"\n\n--- Iteration {iteration} ---\n{researcher_draft}"
            else:
                accumulated_researcher_facts = researcher_draft

        yield _event("researcher", {"iteration": iteration, "content": researcher_draft})

        # ── Phase B: CHALLENGER ──────────────────────────────────────────────
        challenger_critique = await _call_challenger(
            query=query,
            researcher_draft=researcher_draft,
            known_facts=accumulated_researcher_facts,
            iteration=iteration,
        )
        yield _event("challenger", {"iteration": iteration, "content": challenger_critique})

        # ── Phase C: DECIDER ─────────────────────────────────────────────────
        decision_data = await _call_decider(
            query=query,
            researcher_draft=researcher_draft,
            challenger_critique=challenger_critique,
            iteration=iteration,
            max_iterations=max_iterations,
        )
        decision_data["iteration"] = iteration
        yield _event("decider", decision_data)

        # ── Abbruch-Bedingung ────────────────────────────────────────────────
        should_finalize = (
            decision_data.get("decision") == "finalize"
            or iteration >= max_iterations
        )

        # ── Aktives Nachforschen (nur wenn retrieval_fn vorhanden) ───────────
        context_size_before = len(accumulated_context)
        retrieval_found_count = -1

        if not should_finalize and retrieval_fn:
            focus = decision_data.get("retrieval_focus")
            if focus and isinstance(focus, dict):
                retrieval_params: RetrievalParams = {
                    k: v for k, v in focus.items()  # type: ignore[misc]
                    if k in ("date_from", "date_to", "keywords", "hint", "sort_order")
                }
                yield _event("retrieval_focus", retrieval_params)
                try:
                    new_context = await retrieval_fn(retrieval_params)
                    retrieval_found_count = len(new_context) if new_context else 0
                    if new_context:
                        accumulated_context = new_context   # NUR neue Docs, kein Merge
                        logger.info(
                            "Thinking Mode Iteration %d: neuer Kontext geladen (%d Zeichen)",
                            iteration, len(new_context),
                        )
                    else:
                        # Leerer String = Early-Exit-Signal aus build_retrieval_fn:
                        # Alle Chunks wurden bereits in früheren Iterationen gesehen.
                        logger.info(
                            "Thinking Mode Iteration %d: keine neuen Chunks — Early Exit",
                            iteration,
                        )
                        should_finalize = True
                except Exception as exc:
                    logger.warning("retrieval_fn fehlgeschlagen in Iteration %d: %s", iteration, exc)

        if trace_fn is not None:
            try:
                trace_fn({
                    "iteration": iteration,
                    "researcher_output": researcher_draft,
                    "challenger_output": challenger_critique,
                    "decider_decision": decision_data.get("decision", ""),
                    "decider_reasoning": decision_data.get("reasoning", ""),
                    "decider_retrieval_focus": decision_data.get("retrieval_focus"),
                    "retrieval_keywords": (decision_data.get("retrieval_focus") or {}).get("keywords"),
                    "retrieval_date_from": (decision_data.get("retrieval_focus") or {}).get("date_from"),
                    "retrieval_date_to": (decision_data.get("retrieval_focus") or {}).get("date_to"),
                    "retrieval_found_count": retrieval_found_count,
                    "context_size_before": context_size_before,
                    "context_size_after": len(accumulated_context),
                    "accumulated_facts_size": len(accumulated_researcher_facts),
                })
            except Exception as exc:
                logger.warning("trace_fn fehlgeschlagen in Iteration %d: %s", iteration, exc)

        if should_finalize:
            break

    # ── Finale Synthese ──────────────────────────────────────────────────────
    yield _event("thinking_end", {
        "iterations": iteration,
        "message": f"Thinking Mode abgeschlossen nach {iteration} Iteration(en)",
    })

    final_answer = await _call_final_synthesis(
        query=query,
        accumulated_facts=accumulated_researcher_facts,
        challenger_critique=challenger_critique,
        last_context=accumulated_context,
    )

    for chunk in _split_into_chunks(final_answer, chunk_size=100):
        yield _event("text", chunk)


# ============================================================================
# INTERNE AGENT-CALLS (SRP: je eine Funktion pro Agent)
# ============================================================================

async def _call_researcher(
    query: str,
    context: str,       # neue, noch nicht verarbeitete Roh-Docs dieser Iteration
    known_facts: str,   # akkumulierte FAKTEN+THESEN aus Voriterationen (leer in Iter 1)
    prev_critique: str,
    iteration: int,
) -> str:
    """Ruft den Researcher-Agent auf und gibt seinen Text-Output zurück."""
    known_section = ""
    if known_facts:
        known_section = (
            f"\nBEREITS BEKANNTE FAKTEN + THESEN (aus Voriterationen — nicht neu extrahieren):\n"
            f"{known_facts}\n\n"
            f"CHALLENGER-EINWÄNDE (Iteration {iteration - 1}):\n{prev_critique}\n"
        )

    user_content = (
        f"NUTZERANFRAGE: {query}\n\n"
        f"{known_section}"
        f"NEUE QUELLEN ZUM ANALYSIEREN:\n{context}\n\n"
        "Führe deine Analyse durch — extrahiere NUR aus den NEUEN QUELLEN:"
    )

    try:
        return await asyncio.to_thread(chat, [
            {"role": "system", "content": _RESEARCHER_SYSTEM},
            {"role": "user",   "content": user_content},
        ])
    except Exception as exc:
        logger.error("Researcher-Fehler in Iteration %d: %s", iteration, exc)
        return f"[Researcher-Fehler: {exc}]"


async def _call_challenger(
    query: str,
    researcher_draft: str,   # nur die neue Extraktion dieser Iteration
    known_facts: str,        # gesamter akkumulierter Stand (für Konsistenzcheck)
    iteration: int,
) -> str:
    """Ruft den Challenger-Agent auf und gibt seinen Text-Output zurück."""
    user_content = (
        f"URSPRÜNGLICHE ANFRAGE: {query}\n\n"
        f"BISHERIGER AKKUMULIERTER WISSENSSTAND (alle Iterationen):\n{known_facts}\n\n"
        "Stelle den Entwurf kritisch infrage:"
    )

    try:
        return await asyncio.to_thread(chat, [
            {"role": "system", "content": _CHALLENGER_SYSTEM},
            {"role": "user",   "content": user_content},
        ])
    except Exception as exc:
        logger.error("Challenger-Fehler in Iteration %d: %s", iteration, exc)
        return f"[Challenger-Fehler: {exc}]"


async def _call_decider(
    query: str,
    researcher_draft: str,
    challenger_critique: str,
    iteration: int,
    max_iterations: int,
) -> dict:
    """
    Ruft den Decider-Agent auf.

    Returns:
        Dict mit mindestens {"decision": "continue"|"finalize", "reasoning": "..."}
        Optional: {"retrieval_focus": {"date_from": ..., "keywords": [...], ...}}
    """
    system = _DECIDER_SYSTEM.format(iteration=iteration, max_iterations=max_iterations)
    user_content = (
        f"NUTZERANFRAGE: {query}\n\n"
        f"ANTWORT-ENTWURF (Researcher, Iteration {iteration}):\n{researcher_draft}\n\n"
        f"EINWÄNDE (Challenger, Iteration {iteration}):\n{challenger_critique}\n\n"
        "Deine Entscheidung (JSON):"
    )

    try:
        response = await asyncio.to_thread(chat, [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_content},
        ])
        return _parse_decider_json(response, iteration, max_iterations)
    except Exception as exc:
        logger.error("Decider-Fehler in Iteration %d: %s", iteration, exc)
        return {
            "decision": "finalize",
            "reasoning": f"Fehler im Decider: {exc}",
        }


async def _call_final_synthesis(
    query: str,
    accumulated_facts: str,   # FAKTEN+THESEN aller Iterationen (kein Roh-Kontext)
    challenger_critique: str,
    last_context: str = "",   # Letzter nummerierter Quellenkontext für [[n]]-Zitate
) -> str:
    """Erstellt die finale Antwort aus allen gesammelten Erkenntnissen."""
    context_section = (
        f"\nAKTUELLER KONTEXT (Quellen mit Nummern für [[n]]-Zitate):\n{last_context}\n"
        if last_context else ""
    )
    user_content = (
        f"URSPRÜNGLICHE ANFRAGE: {query}\n\n"
        f"ANALYSIERTE FAKTEN + THESEN (alle Iterationen):\n{accumulated_facts}\n\n"
        f"LETZTE CHALLENGER-EINWÄNDE:\n{challenger_critique}\n"
        f"{context_section}\n"
        "Erstelle jetzt die finale, vollständige Antwort für den Nutzer:"
    )

    try:
        return await asyncio.to_thread(chat, [
            {"role": "system", "content": _FINAL_SYNTHESIS_SYSTEM},
            {"role": "user",   "content": user_content},
        ])
    except Exception as exc:
        logger.error("Synthese-Fehler: %s", exc)
        return accumulated_facts  # Fallback auf akkumulierte Fakten


# ============================================================================
# HILFSFUNKTIONEN
# ============================================================================

def _parse_decider_json(response: str, iteration: int, max_iterations: int) -> dict:
    """
    Parst die JSON-Antwort des Deciders.

    Fallback-Strategie bei Parse-Fehler: finalize wenn letzte Iteration,
    sonst continue (damit wir nicht ewig stecken bleiben).
    """
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Decider JSON-Parse fehlgeschlagen in Iteration %d", iteration)
    return {
        "decision": "finalize" if iteration >= max_iterations else "continue",
        "reasoning": response[:200],
    }


def _event(event_type: str, content: object) -> str:
    """Formatiert ein SSE-Event als JSON-String (ohne trailing \\n\\n)."""
    return json.dumps({"type": event_type, "content": content}, ensure_ascii=False)


def _split_into_chunks(text: str, chunk_size: int = 100) -> list[str]:
    """Teilt Text in Wort-Chunks für Streaming-Simulation.

    Wichtig: Nicht-letzte Chunks erhalten einen trailing Space, damit
    das Frontend beim Konkatenieren keine Wörter zusammenführt.
    ("Jazz hatte" + "bereits" würde sonst zu "Jazz hattebereits".)
    """
    words = text.split(" ")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_size:
            chunks.append(" ".join(current) + " ")  # trailing space!
            current = []
            current_len = 0
    if current:
        chunks.append(" ".join(current))  # letzter Chunk: kein trailing space
    return chunks
