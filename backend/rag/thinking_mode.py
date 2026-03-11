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

_RESEARCHER_SYSTEM = """\
Du bist der RESEARCHER in einem mehrstufigen Analyse-System für persönliche Erinnerungen.

Deine Aufgabe:
1. Analysiere die Nutzeranfrage und die verfügbaren Quellen (Fotos, Nachrichten, Bewertungen, Orte).
2. Erstelle einen ANTWORT-ENTWURF: Was kannst du direkt aus den Quellen beantworten?
3. Benenne LÜCKEN: Welche konkreten Fakten (Datum, Ort, Name) fehlen noch?
4. Schlage RECHERCHE-SCHRITTE vor, falls Lücken bestehen.

Format (genau einhalten):
ANTWORT-ENTWURF:
[Dein Entwurf auf Basis der verfügbaren Quellen]

LÜCKEN:
[Fehlende konkrete Fakten — oder "Keine" wenn vollständig]

RECHERCHE-VORSCHLÄGE:
[Konkrete Schritte für tiefere Recherche — oder "Keine" wenn vollständig]

Antworte auf Deutsch. Erfinde keine Informationen."""


_CHALLENGER_SYSTEM = """\
Du bist der CHALLENGER in einem mehrstufigen Analyse-System für persönliche Erinnerungen.

Deine Aufgabe:
1. Hinterfrage den ANTWORT-ENTWURF des Researchers kritisch.
2. Prüfe: Wurden alle relevanten Quellen berücksichtigt?
3. Prüfe: Sind Schlussfolgerungen korrekt oder gibt es alternative Interpretationen?
4. Wenn ein konkretes Faktum (Datum, Todesfall, Ort, Name) fehlt oder unsicher ist:
   Schlage einen KONKRETEN SUCHFOKUS vor mit:
   - Zeitraum (date_from / date_to im Format YYYY-MM-DD)
   - Keywords die im Text vorkommen MÜSSEN (z.B. Tiernamen, Ereignisse)
   - Einen kurzen Hinweis was gesucht werden soll

Beispiel — wenn Todesdatum eines Haustieres fehlt:
  SUCHFOKUS: date_from=2021-01-01, date_to=2021-06-30, keywords=["Jazz", "eingeschläfert", "gestorben"]
  HINWEIS: Nachrichten nach dem letzten bekannten Schlaganfall durchsuchen

Format (genau einhalten):
EINWÄNDE:
[Konkrete Kritikpunkte]

VERGESSENE ASPEKTE:
[Was wurde übersehen?]

SUCHFOKUS (nur wenn ein wichtiges Faktum fehlt, sonst weglassen):
date_from=YYYY-MM-DD, date_to=YYYY-MM-DD, keywords=["term1", "term2"]
HINWEIS: [Was wird gesucht]

Sei konstruktiv-kritisch. Antworte auf Deutsch."""


_DECIDER_SYSTEM = """\
Du bist der DECIDER in einem mehrstufigen Analyse-System für persönliche Erinnerungen.

Du hast gesehen:
- Die Nutzeranfrage
- Den Antwort-Entwurf des Researchers
- Die Einwände des Challengers inkl. optionalem SUCHFOKUS
- Aktuelle Iteration: {iteration} von maximal {max_iterations}

Deine Aufgabe:
Entscheide ob weitere Recherche sinnvoll ist ODER ob finalisiert werden soll.

Wenn der Challenger einen SUCHFOKUS vorgeschlagen hat UND das gesuchte Faktum
wirklich wichtig für die Antwort ist: wähle "continue" und übernimm den Fokus.

Antworte IMMER im folgenden JSON-Format:
{{
  "decision": "continue" | "finalize",
  "reasoning": "...",
  "retrieval_focus": {{
    "date_from": "YYYY-MM-DD",
    "date_to": "YYYY-MM-DD",
    "keywords": ["term1", "term2"],
    "hint": "Kurze Beschreibung was gesucht wird"
  }}
}}

"retrieval_focus" ist OPTIONAL — nur bei "continue" und nur wenn der Challenger
einen konkreten SUCHFOKUS geliefert hat. Andernfalls weglassen.

Bei Iteration {max_iterations} MUSST du "finalize" wählen."""


_FINAL_SYNTHESIS_SYSTEM = """\
Du bist ein Synthese-Agent für persönliche Erinnerungen.

Du hast mehrere Analyse-Runden abgeschlossen.

Erstelle die finale, vollständige Antwort für den Nutzer:
1. Beantworte die ursprüngliche Frage vollständig und präzise.
2. Integriere wertvolle Ergänzungen des Challengers.
3. Zitiere Quellen mit [[1]], [[2]] etc.
4. Nutze ausschließlich Fakten aus den bereitgestellten Quellen.
5. Antworte auf Deutsch, klar und strukturiert."""


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
