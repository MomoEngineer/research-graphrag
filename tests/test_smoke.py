"""Smoke-Test: Das Paket und seine Unterpakete sind importierbar und versioniert.

Dieser Test hält die Test-Suite grün und prüft die zugesagte Struktur (src-Layout mit neun
Unterpaketen).
"""

from __future__ import annotations

import importlib

import research_graphrag


def test_version_is_exposed() -> None:
    """Die Paket-Version ist gesetzt und entspricht pyproject.toml."""
    assert research_graphrag.__version__ == "0.1.0"


def test_subpackages_importable() -> None:
    """Die neun Pipeline-/Server-Unterpakete sind importierbar."""
    for name in (
        "extraction",
        "indexing",
        "overview",
        "retrieval",
        "generation",
        "evaluation",
        "online",
        "bibliography",
        "mcp_server",
    ):
        module = importlib.import_module(f"research_graphrag.{name}")
        assert module is not None
