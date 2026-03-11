"""
constants.py – Zentrale Konstanten für das RAG-Subsystem.

Alle Magic Numbers und hardcodierten Konfigurationswerte gehören hierher.
Nie direkt in die Logik-Dateien streuen.
"""

# ---------------------------------------------------------------------------
# ChromaDB Collections
# ---------------------------------------------------------------------------

COLLECTIONS: list[str] = [
    "photos",
    "reviews",
    "saved_places",
    "messages",
    "faces",
    "whatsapp_config",
]

SEARCHABLE_COLLECTIONS: list[str] = [
    "photos",
    "reviews",
    "saved_places",
    "messages",
]

# ---------------------------------------------------------------------------
# Retrieval — Score-Schwellwerte
# ---------------------------------------------------------------------------

DEFAULT_MIN_SCORE: float = 0.20
"""Mindestscore für semantische Treffer im Normalbetrieb."""

FALLBACK_MIN_SCORE: float = 0.42
"""Strengerer Schwellwert bei breiten Fallback-Queries (verhindert Rauschen)."""

KEYWORD_SCORE: float = 0.85
"""Fester Score der keyword_search()-Treffer (kein echter Ähnlichkeitswert)."""

# ---------------------------------------------------------------------------
# Retrieval — Mengengrenzen
# ---------------------------------------------------------------------------

DEFAULT_N_PER_COLLECTION: int = 6
"""Standard-Ergebnisse pro Collection bei retrieve()."""

MAX_SOURCES_DISPLAY: int = 20
"""Maximale Quellen die ans Frontend gesendet werden (sources-Event)."""

# ---------------------------------------------------------------------------
# Context Compression
# ---------------------------------------------------------------------------

DEFAULT_TOKEN_BUDGET: int = 8_000
"""Token-Budget für den Kontext (sicheres Limit für die meisten Modelle)."""

TOP_N_FULL: int = 5
"""Anzahl der Top-Quellen die ungekürzt (FULL, ~400 Tokens) übergeben werden."""

KEYWORD_BUDGET_TOKENS: int = 2_500
"""Token-Budget für den separaten chronologischen Keyword-Block."""

KEYWORD_MAX_TOKENS_PER_CHUNK: int = 120
"""Maximale Tokens pro Keyword-Chunk im Keyword-Block."""

# ---------------------------------------------------------------------------
# LLM / Prompts
# ---------------------------------------------------------------------------

MAX_CHAT_HISTORY: int = 10
"""Maximale Chat-Nachrichten aus der History die ans LLM übergeben werden."""

MAX_THINKING_ITERATIONS: int = 10
"""Standard-Iterationslimit für den Thinking Mode (Researcher→Challenger→Decider)."""
