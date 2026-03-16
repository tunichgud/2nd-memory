"""
conftest.py – Globale Test-Fixtures und Setup fuer memosaur.

Stubs fehlende optionale Module (elasticsearch) damit Tests
ohne installierte Elasticsearch-Abhaengigkeit ausfuehren koennen.
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Elasticsearch Stub (nicht installiert in Test-Umgebung)
# ---------------------------------------------------------------------------
# Muss VOR jedem Import von backend.* in sys.modules eingetragen werden.

if "elasticsearch" not in sys.modules:
    _es_mock = ModuleType("elasticsearch")
    _es_mock.Elasticsearch = MagicMock  # type: ignore[attr-defined]
    _es_mock.helpers = MagicMock()      # type: ignore[attr-defined]
    sys.modules["elasticsearch"] = _es_mock
    sys.modules["elasticsearch.helpers"] = _es_mock.helpers
