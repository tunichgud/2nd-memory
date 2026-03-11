"""
thinking_mode.py – Researcher → Challenger → Decider Pipeline für Memosaur.

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

import json
import logging
import re
from typing import AsyncGenerator

from backend.llm.connector import chat
from backend.rag.constants import MAX_THINKING_ITERATIONS
from backend.rag.rag_types import RetrievalFn, RetrievalParams

logger = logging.getLogger(__name__)


# ============================================================================
# PROMPTS
# ============================================================================

# Extractive RAG-Prinzip: Researcher und Challenger arbeiten rein extraktiv —
# sie paraphrasieren NICHT, sondern extrahieren und benennen nur Rohdaten.
# Einzig der Final-Synthesis-Agent arbeitet abstraktiv (natürliche Sprache).
# Begründung: Paraphrasierung bläht das Kontextfenster auf (Context Bloat) und
# verwässert exakte Fakten wie Zeitstempel oder IDs (Information Degradation).

_RESEARCHER_SYSTEM = """\
Du bist der RESEARCHER in einem mehrstufigen Fakten-Extraktions-System.

WICHTIG: Paraphrasiere NICHT. Arbeite rein extraktiv.
Gib nur Rohdaten aus: exakte Zitate, Zeitstempel, IDs.
Kein Fließtext, keine Zusammenfassungen.

Aufgabe:
1. Extrahiere relevante Fakten direkt aus den Quellen (exakte Zitate + Zeitstempel).
2. Liste fehlende Fakten die für die Antwort nötig wären.
3. Schlage Recherche-Parameter vor wenn Fakten fehlen.

Format (strikt einhalten):
FAKTEN:
- [DATUM] QUELLE: "exaktes Zitat oder Feldwert"
- [DATUM] QUELLE: "exaktes Zitat oder Feldwert"

FEHLENDE FAKTEN:
- [was fehlt, z.B. "Todesdatum nicht in Quellen vorhanden"]

RECHERCHE-PARAMETER (nur wenn FEHLENDE FAKTEN vorhanden):
date_from=YYYY-MM-DD, date_to=YYYY-MM-DD, keywords=["term1"]

Erfinde keine Informationen. Kein Fließtext außer in den vorgegebenen Feldern."""


_CHALLENGER_SYSTEM = """\
Du bist der CHALLENGER in einem mehrstufigen Fakten-Extraktions-System.

WICHTIG: Paraphrasiere NICHT. Arbeite rein extraktiv.
Wiederhole den Researcher-Output NICHT. Benenne nur Lücken und Widersprüche.

Aufgabe:
1. Prüfe: Fehlen wichtige Fakten in FAKTEN des Researchers?
2. Prüfe: Gibt es Widersprüche zwischen extrahierten Fakten?
3. Wenn kritisches Faktum fehlt: gib konkrete Suchparameter an.

Beispiel — Todesdatum eines Haustieres fehlt:
  FEHLENDE FAKTEN: Sterbebeleg (kein Chunk mit "gestorben"/"eingeschläfert")
  SUCHPARAMETER: date_from=2021-01-28, date_to=2021-06-30, keywords=["Jazz","eingeschläfert","gestorben"]

Format (strikt einhalten):
LÜCKEN:
- [konkret was fehlt oder welcher Widerspruch besteht]

SUCHPARAMETER (nur wenn kritisches Faktum fehlt):
date_from=YYYY-MM-DD, date_to=YYYY-MM-DD, keywords=["term1", "term2"]
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
    "hint": "Ein Satz was gesucht wird"
  }}
}}

"retrieval_focus" nur bei "continue", sonst weglassen.
Bei Iteration {max_iterations} MUSST du "finalize" wählen."""


_FINAL_SYNTHESIS_SYSTEM = """\
Du bist der SYNTHESIZER — der einzige Agent der natürliche Sprache produziert.

Du erhältst:
- Die Nutzeranfrage
- Extrahierte Rohdaten (Fakten, Zitate, Zeitstempel) aus mehreren Analyse-Runden

Aufgabe: Formuliere daraus eine vollständige, natürlichsprachige Antwort.

Regeln:
1. Beantworte die Frage vollständig und präzise.
2. Zitiere Quellen mit [[1]], [[2]] etc. (aus den Fakten-Einträgen).
3. Nutze ausschließlich die extrahierten Fakten — erfinde nichts.
4. Antworte auf Deutsch, klar und strukturiert.
5. Nenne Daten, Namen und Orte exakt wie in den Fakten angegeben."""


# ============================================================================
# ÖFFENTLICHE API
# ============================================================================

async def thinking_mode_stream(
    query: str,
    context: str,
    max_iterations: int = MAX_THINKING_ITERATIONS,
    retrieval_fn: RetrievalFn | None = None,
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
    accumulated_context = context
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
            prev_draft=researcher_draft if iteration > 1 else "",
            prev_critique=challenger_critique if iteration > 1 else "",
            iteration=iteration,
        )
        yield _event("researcher", {"iteration": iteration, "content": researcher_draft})

        # ── Phase B: CHALLENGER ──────────────────────────────────────────────
        challenger_critique = await _call_challenger(
            query=query,
            researcher_draft=researcher_draft,
            context_preview=accumulated_context[:3000],
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
        if not should_finalize and retrieval_fn:
            focus = decision_data.get("retrieval_focus")
            if focus and isinstance(focus, dict):
                retrieval_params: RetrievalParams = {
                    k: v for k, v in focus.items()  # type: ignore[misc]
                    if k in ("date_from", "date_to", "keywords", "hint")
                }
                yield _event("retrieval_focus", retrieval_params)
                try:
                    new_context = await retrieval_fn(retrieval_params)
                    accumulated_context = _merge_contexts(accumulated_context, new_context)
                    logger.info(
                        "Thinking Mode Iteration %d: neuer Kontext hinzugefügt (%d Zeichen)",
                        iteration, len(new_context),
                    )
                except Exception as exc:
                    logger.warning("retrieval_fn fehlgeschlagen in Iteration %d: %s", iteration, exc)

        if should_finalize:
            break

    # ── Finale Synthese ──────────────────────────────────────────────────────
    yield _event("thinking_end", {
        "iterations": iteration,
        "message": f"Thinking Mode abgeschlossen nach {iteration} Iteration(en)",
    })

    final_answer = await _call_final_synthesis(
        query=query,
        researcher_draft=researcher_draft,
        challenger_critique=challenger_critique,
        context=accumulated_context,
    )

    for chunk in _split_into_chunks(final_answer, chunk_size=100):
        yield _event("text", chunk)


# ============================================================================
# INTERNE AGENT-CALLS (SRP: je eine Funktion pro Agent)
# ============================================================================

async def _call_researcher(
    query: str,
    context: str,
    prev_draft: str,
    prev_critique: str,
    iteration: int,
) -> str:
    """Ruft den Researcher-Agent auf und gibt seinen Text-Output zurück."""
    prev_section = ""
    if iteration > 1 and prev_draft:
        prev_section = (
            f"\nVORHERIGE ANALYSE (Iteration {iteration - 1}):\n{prev_draft}"
            f"\n\nCHALLENGER-EINWÄNDE (Iteration {iteration - 1}):\n{prev_critique}"
        )

    user_content = (
        f"NUTZERANFRAGE: {query}\n\n"
        f"VERFÜGBARE QUELLEN:\n{context}"
        f"{prev_section}\n\n"
        "Führe deine Analyse durch:"
    )

    try:
        return chat([
            {"role": "system", "content": _RESEARCHER_SYSTEM},
            {"role": "user",   "content": user_content},
        ])
    except Exception as exc:
        logger.error("Researcher-Fehler in Iteration %d: %s", iteration, exc)
        return f"[Researcher-Fehler: {exc}]"


async def _call_challenger(
    query: str,
    researcher_draft: str,
    context_preview: str,
    iteration: int,
) -> str:
    """Ruft den Challenger-Agent auf und gibt seinen Text-Output zurück."""
    user_content = (
        f"URSPRÜNGLICHE ANFRAGE: {query}\n\n"
        f"ANTWORT-ENTWURF DES RESEARCHERS (Iteration {iteration}):\n{researcher_draft}\n\n"
        f"VERFÜGBARE QUELLEN (Überblick):\n{context_preview}...\n\n"
        "Stelle den Entwurf kritisch infrage:"
    )

    try:
        return chat([
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
        response = chat([
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
    researcher_draft: str,
    challenger_critique: str,
    context: str,
) -> str:
    """Erstellt die finale Antwort aus allen gesammelten Erkenntnissen."""
    user_content = (
        f"URSPRÜNGLICHE ANFRAGE: {query}\n\n"
        f"ANALYSE-ERGEBNIS (Researcher, letzte Iteration):\n{researcher_draft}\n\n"
        f"ERGÄNZUNGEN (Challenger):\n{challenger_critique}\n\n"
        f"VOLLSTÄNDIGE QUELLEN:\n{context}\n\n"
        "Erstelle jetzt die finale, vollständige Antwort für den Nutzer:"
    )

    try:
        return chat([
            {"role": "system", "content": _FINAL_SYNTHESIS_SYSTEM},
            {"role": "user",   "content": user_content},
        ])
    except Exception as exc:
        logger.error("Synthese-Fehler: %s", exc)
        return researcher_draft  # Fallback auf letzten Draft


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


def _merge_contexts(original: str, addition: str) -> str:
    """
    Fügt neuen Kontext an den bestehenden an.

    Verhindert einfache Duplikate (identischer Text) durch string-Check.
    """
    if not addition or addition.strip() in original:
        return original
    return original + "\n\n=== NACHFORSCHUNG ===\n" + addition


def _event(event_type: str, content: object) -> str:
    """Formatiert ein SSE-Event als JSON-String (ohne trailing \\n\\n)."""
    return json.dumps({"type": event_type, "content": content}, ensure_ascii=False)


def _split_into_chunks(text: str, chunk_size: int = 100) -> list[str]:
    """Teilt Text in Wort-Chunks für Streaming-Simulation."""
    words = text.split(" ")
    chunks: list[str] = []
    current: list[str] = []
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
