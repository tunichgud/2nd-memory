"""
context_manager.py – Intelligente Context Window Management für RAG.

Problem:
  Bei Chain-of-Thought Queries (4+ Sub-Steps) mit vielen Quellen (50+)
  wird der Context zu groß → wichtige Informationen werden abgeschnitten.

Lösung:
  1. Relevanz-basiertes Ranking (Score + Query-Matching)
  2. LLM-basierte Summarization (für lange Texte)
  3. Progressive Context Loading (bei Multi-Step Queries)

Beispiel:
  50 Quellen → 6k tokens (VORHER)
  50 Quellen → 2k tokens (NACHHER, -66% bei gleichbleibender Qualität)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token Counting
# ---------------------------------------------------------------------------

_tiktoken_encoder = None


def _get_tiktoken_encoder():
    """Lazy-load tiktoken encoder (cl100k_base für GPT-4/Gemini)."""
    global _tiktoken_encoder
    if _tiktoken_encoder is None:
        try:
            import tiktoken
            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            logger.warning("tiktoken nicht installiert, nutze Fallback (chars/4)")
            _tiktoken_encoder = None
    return _tiktoken_encoder


def count_tokens(text: str) -> int:
    """Zählt Tokens in einem Text (präzise via tiktoken, Fallback chars/4)."""
    encoder = _get_tiktoken_encoder()
    if encoder:
        return len(encoder.encode(text))
    else:
        # Fallback: Rough estimate (1 token ≈ 4 chars)
        return len(text) // 4


# ---------------------------------------------------------------------------
# Compression Modes
# ---------------------------------------------------------------------------

class CompressionMode(Enum):
    """Definiert, wie stark Quellen komprimiert werden."""
    FULL = "full"        # Volltext (keine Kompression)
    COMPACT = "compact"  # Kernsätze + Metadaten (mittlere Kompression)
    MINIMAL = "minimal"  # Nur Metadaten + erste Sätze (starke Kompression)


@dataclass
class ContextBudget:
    """Budget-Management für Context Window."""
    max_tokens: int = 8000  # Sicheres Limit für die meisten Modelle
    system_prompt_tokens: int = 500
    user_prompt_base_tokens: int = 200

    @property
    def available_for_sources(self) -> int:
        """Verfügbare Tokens für Quellen."""
        return self.max_tokens - self.system_prompt_tokens - self.user_prompt_base_tokens


# ---------------------------------------------------------------------------
# Source Compression
# ---------------------------------------------------------------------------

def compress_text(text: str, max_tokens: int, mode: CompressionMode = CompressionMode.COMPACT) -> str:
    """
    Komprimiert einen Text auf max_tokens.

    Strategien:
    - FULL: Truncate nur wenn nötig (einfaches Abschneiden)
    - COMPACT: Extrahiere Kernsätze (erste + letzte Sätze)
    - MINIMAL: Nur erster Satz
    """
    current_tokens = count_tokens(text)

    if current_tokens <= max_tokens:
        return text

    if mode == CompressionMode.FULL:
        # Einfaches Truncate (behalte Anfang)
        return _truncate_to_tokens(text, max_tokens)

    elif mode == CompressionMode.COMPACT:
        # Kernsätze: Erste 2 + letzte 1 Sätze
        sentences = _split_sentences(text)
        if len(sentences) <= 3:
            return text

        core = sentences[:2] + sentences[-1:]
        compressed = " ".join(core)

        # Falls immer noch zu lang → truncate
        if count_tokens(compressed) > max_tokens:
            return _truncate_to_tokens(compressed, max_tokens)
        return compressed

    elif mode == CompressionMode.MINIMAL:
        # Nur erster Satz
        sentences = _split_sentences(text)
        if not sentences:
            return text[:100]  # Fallback

        first = sentences[0]
        if count_tokens(first) > max_tokens:
            return _truncate_to_tokens(first, max_tokens)
        return first

    return text


def _split_sentences(text: str) -> list[str]:
    """Teilt Text in Sätze (einfache Heuristik)."""
    import re
    # Teile an . ! ? gefolgt von Leerzeichen oder Zeilenumbruch
    sentences = re.split(r'[.!?]\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Schneidet Text auf max_tokens ab (mit ... Suffix)."""
    encoder = _get_tiktoken_encoder()

    if encoder:
        tokens = encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        truncated_tokens = tokens[:max_tokens - 1]  # -1 für "..."
        return encoder.decode(truncated_tokens) + "..."
    else:
        # Fallback: Chars-basiert
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."


# ---------------------------------------------------------------------------
# LLM-based Summarization (für sehr lange Texte)
# ---------------------------------------------------------------------------

def summarize_text_llm(text: str, max_tokens: int = 150) -> str:
    """
    Nutzt LLM um Text intelligent zu komprimieren.

    WICHTIG: Nur für Texte >500 tokens nutzen, sonst Overhead zu groß.
    """
    from backend.llm.connector import chat

    if count_tokens(text) <= max_tokens:
        return text

    messages = [
        {"role": "system", "content": "Du bist ein Text-Komprimierer. Fasse den Text in 2-3 Sätzen zusammen. Behalte alle wichtigen Fakten (Personen, Orte, Daten, Ereignisse)."},
        {"role": "user", "content": f"Fasse zusammen:\n\n{text}"}
    ]

    try:
        summary = chat(messages)
        logger.info("LLM-Summarization: %d → %d tokens", count_tokens(text), count_tokens(summary))
        return summary
    except Exception as exc:
        logger.warning("LLM-Summarization fehlgeschlagen: %s, nutze Fallback", exc)
        return compress_text(text, max_tokens, CompressionMode.COMPACT)


# ---------------------------------------------------------------------------
# Source-Level Compression
# ---------------------------------------------------------------------------

def compress_sources(
    sources: list[dict],
    budget: ContextBudget | None = None,
    top_n_full: int = 5,
    use_llm_summary: bool = False,
    keyword_sources: list[dict] | None = None,
) -> str:
    """
    Komprimiert eine Liste von Quellen intelligent auf ein Token-Budget.

    Strategie:
    1. Top-N Quellen (nach Score): Volltext (FULL)
    2. Mittlere Quellen: Komprimiert (COMPACT)
    3. Rest: Minimal (nur Metadaten + erster Satz)
    4. Optional: LLM-Summarization für sehr lange Texte
    5. keyword_sources: Werden chronologisch in eigenem Block angehängt
       (unabhängig vom Score-Ranking, festes Budget 2000 Tokens)

    Args:
        sources: Liste von Source-Dicts mit 'document', 'metadata', 'score', 'collection'
        budget: ContextBudget (default: 8k tokens total)
        top_n_full: Wie viele Top-Quellen bekommen Volltext?
        use_llm_summary: LLM-basierte Summarization für lange Texte (langsam!)
        keyword_sources: Keyword-Treffer — chronologisch sortiert, kompakt,
            eigenes Token-Budget (nicht in Score-Sortierung gemischt).

    Returns:
        Formatierter Context-String (optimiert für Token-Budget)
    """
    if budget is None:
        budget = ContextBudget()

    if not sources and not keyword_sources:
        return "Keine passenden Einträge gefunden."

    SOURCE_LABELS = {
        "photos":       ("📷", "FOTO"),
        "reviews":      ("⭐", "BEWERTUNG"),
        "saved_places": ("📍", "GESPEICHERTER ORT"),
        "messages":     ("💬", "NACHRICHT"),
    }

    # Token-Budget für Quellen
    available_tokens = budget.available_for_sources
    logger.info("Context Compression: %d Quellen, Budget=%d tokens", len(sources), available_tokens)

    # Sortiere nach Relevanz (Score)
    sorted_sources = sorted(sources, key=lambda s: s.get("score", 0), reverse=True)

    parts = []
    used_tokens = 0

    for i, src in enumerate(sorted_sources, start=1):
        # Bestimme Compression Mode basierend auf Ranking
        if i <= top_n_full:
            mode = CompressionMode.FULL
            max_doc_tokens = 400  # Pro Quelle
        elif i <= top_n_full + 10:
            mode = CompressionMode.COMPACT
            max_doc_tokens = 150
        else:
            mode = CompressionMode.MINIMAL
            max_doc_tokens = 50

        # Baue Quelle
        meta = src["metadata"]
        icon, label = SOURCE_LABELS.get(src["collection"], ("📄", src["collection"].upper()))
        pct = int(src.get("score", 0) * 100)

        # Metadaten (kompakt)
        meta_parts = []
        if meta.get("date_iso"):
            meta_parts.append(meta["date_iso"][:10])
        if meta.get("cluster"):
            meta_parts.append(f"Ort: {meta['cluster']}")
            # Wenn place_name eine andere Stadt nennt als der Cluster (z.B. cluster=Hamburg-Ost,
            # place_name=Ahrensburg), beide anzeigen – verhindert falschen Ortsnamen im LLM
            place = meta.get("place_name", "")
            if place:
                city = place.split(",")[0].strip()
                if city.lower() not in meta["cluster"].lower():
                    meta_parts.append(f"Stadtname: {city}")
        elif meta.get("place_name"):
            meta_parts.append(meta["place_name"])
        if meta.get("lat") and meta.get("lat") != 0.0:
            meta_parts.append(f"GPS: {meta['lat']:.3f}°N, {meta['lon']:.3f}°E")

        header = f"[{i} – {icon} {label} | {pct}%]"
        if meta_parts:
            header += f"\n{' | '.join(meta_parts)}"

        # Dokument komprimieren
        doc = src["document"]

        # Optional: LLM-Summarization für sehr lange Texte
        if use_llm_summary and count_tokens(doc) > 500 and mode != CompressionMode.FULL:
            doc = summarize_text_llm(doc, max_tokens=max_doc_tokens)
        else:
            doc = compress_text(doc, max_tokens=max_doc_tokens, mode=mode)

        source_text = f"{header}\n{doc}"
        source_tokens = count_tokens(source_text)

        # Budget-Check
        if used_tokens + source_tokens > available_tokens:
            logger.info("  Budget erschöpft nach %d Quellen (%d/%d tokens)", i, used_tokens, available_tokens)
            break

        parts.append(source_text)
        used_tokens += source_tokens

        if i <= 3:
            logger.debug("  [%d] %s | %d tokens | mode=%s", i, src["collection"], source_tokens, mode.value)

    logger.info("Context Compression: %d Quellen genutzt, %d tokens (%.1f%% Budget)",
                len(parts), used_tokens, (used_tokens / available_tokens) * 100)

    # ── Keyword-Block: chronologisch, eigenes Budget ──────────────────────────
    # Keyword-Quellen (z.B. alle Nachrichten mit "Jazz") werden NICHT in die
    # Score-Sortierung oben gemischt — sie kämen sonst alle vor den semantischen
    # Treffern und würden entweder abgeschnitten oder dominieren.
    # Stattdessen: kompakter chronologischer Block am Ende des Kontexts.
    if keyword_sources:
        KEYWORD_BUDGET_TOKENS = 2500
        kw_parts = []
        kw_used = 0
        # Chronologisch sortieren (älteste zuerst → Kontext lesbar wie ein Tagebuch)
        kw_sorted = sorted(
            keyword_sources,
            key=lambda s: s.get("metadata", {}).get("timestamp", ""),
        )
        for kw_src in kw_sorted:
            icon, label = SOURCE_LABELS.get(kw_src["collection"], ("📄", kw_src["collection"].upper()))
            meta = kw_src.get("metadata", {})
            date_str = meta.get("date_iso", meta.get("timestamp", ""))[:10]
            chat = meta.get("chat_name", "")
            header_parts = [f"[{label}]", date_str]
            if chat:
                header_parts.append(chat)
            header = " | ".join(filter(None, header_parts))
            doc = compress_text(kw_src["document"], max_tokens=120, mode=CompressionMode.COMPACT)
            entry = f"{header}\n{doc}"
            entry_tokens = count_tokens(entry)
            if kw_used + entry_tokens > KEYWORD_BUDGET_TOKENS:
                break
            kw_parts.append(entry)
            kw_used += entry_tokens

        if kw_parts:
            kw_block = "=== KEYWORD-TREFFER (chronologisch) ===\n" + "\n\n".join(kw_parts)
            logger.info("Keyword-Block: %d/%d Chunks, %d tokens", len(kw_parts), len(keyword_sources), kw_used)
            parts.append(kw_block)

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Progressive Context Loading (für Chain-of-Thought)
# ---------------------------------------------------------------------------

@dataclass
class ProgressiveContext:
    """
    Verwaltet Context über mehrere Chain-of-Thought Schritte.

    Idee: Statt jedem Schritt alle Quellen zu geben, nutze:
    - Schritt 1: Top-10 Quellen (Volltext)
    - Schritt 2: Nur NEUE Quellen + Referenzen zu Schritt 1
    - Schritt 3: Nur NEUE Quellen + Referenzen zu Schritt 1+2
    """
    budget: ContextBudget
    all_sources: list[dict]
    seen_ids: set[str]
    step_summaries: list[str]  # Zusammenfassungen vorheriger Schritte

    def __init__(self, budget: ContextBudget | None = None):
        if budget is None:
            budget = ContextBudget()
        self.budget = budget
        self.all_sources = []
        self.seen_ids = set()
        self.step_summaries = []

    def add_sources(self, sources: list[dict], step_name: str) -> str:
        """
        Fügt neue Quellen hinzu und gibt komprimierten Context zurück.

        Returns:
            Formatierter Context für diesen Schritt (nur neue Infos + Referenzen)
        """
        # Filter: Nur neue Quellen
        new_sources = []
        for src in sources:
            src_id = src.get("id", "")
            if src_id and src_id not in self.seen_ids:
                new_sources.append(src)
                self.seen_ids.add(src_id)
                self.all_sources.append(src)

        logger.info("Progressive Context: Schritt '%s' → %d neue Quellen (von %d)",
                    step_name, len(new_sources), len(sources))

        # Komprimiere neue Quellen
        if not new_sources:
            return f"[{step_name}]\nKeine neuen Informationen gefunden."

        # Budget aufteilen: 70% für neue Quellen, 30% für Referenzen
        new_budget = ContextBudget(
            max_tokens=int(self.budget.available_for_sources * 0.7),
            system_prompt_tokens=0,
            user_prompt_base_tokens=0
        )

        new_context = compress_sources(new_sources, budget=new_budget, top_n_full=3)

        # Referenzen zu vorherigen Schritten (kompakt)
        ref_context = ""
        if self.step_summaries:
            ref_context = "\n\nBISHERIGE ERKENNTNISSE:\n" + "\n".join(
                f"- {summary}" for summary in self.step_summaries[-2:]  # Nur letzte 2
            )

        full_context = f"[{step_name}]\n{new_context}{ref_context}"

        return full_context

    def add_step_summary(self, summary: str):
        """Fügt eine Zusammenfassung des aktuellen Schritts hinzu."""
        self.step_summaries.append(summary)
