"""Orchestrierung einer belegten Antwort: Router → Retrieval → Evidenz → optionale Synthese.

Bündelt den Weg von einer Frage zu einer **einheitlichen, nummerierten** Beleg-Sammlung an genau
einer Stelle, damit CLI (``python -m scripts.ask --synthese``) und MCP-Tool (``answer_question``)
dieselbe Semantik teilen. Die Synthese selbst ist optional: Ohne sampling-fähigen Provider bleibt
``generated = False`` und die Evidenz maßgeblich
(docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.generation.evidence import (
    evidence_from_basic,
    evidence_from_drift,
    evidence_from_global,
    evidence_from_local,
)
from research_graphrag.generation.provider import GenerationProvider, NoopGenerationProvider
from research_graphrag.generation.synthesis import Evidence, SynthesisResult, synthesize_answer
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, Scoring
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.drift import search_drift
from research_graphrag.retrieval.global_search import search_global
from research_graphrag.retrieval.local import search_local
from research_graphrag.retrieval.router import MODES, route

AUTO_MODE = "auto"
"""Modus-Wert, der die Heuristik des Query-Routers auswählt."""

EVIDENCE_BUILDERS: dict[str, Callable[[str, str, int, Scoring], Evidence]] = {
    "basic": lambda db_path, query, k, scoring: evidence_from_basic(
        search_basic(db_path, query, k, scoring=scoring)
    ),
    "local": lambda db_path, query, k, scoring: evidence_from_local(
        search_local(db_path, query, k=k, scoring=scoring)
    ),
    # Global rankt Communities statt Chunks; die Chunk-Wertung bleibt dort ohne Wirkung.
    "global": lambda db_path, query, k, _scoring: evidence_from_global(
        search_global(db_path, query, k)
    ),
    "drift": lambda db_path, query, k, scoring: evidence_from_drift(
        search_drift(db_path, query, k=k, scoring=scoring)
    ),
}
"""Abbildung Modus → Evidenz-Aufbau (Single Source of Truth für CLI und MCP-Tool)."""


def resolve_mode(query: str, mode: str) -> str:
    """Löst ``auto`` über den Heuristik-Router auf und prüft den Modus.

    Args:
        query: Natürlichsprachige Frage (für die Router-Heuristik).
        mode: ``auto`` oder einer der Modi aus :data:`research_graphrag.retrieval.router.MODES`.

    Returns:
        Der tatsächlich zu verwendende Modus.

    Raises:
        DomainError: ``invalid_input`` bei unbekanntem Modus (siehe docs/error-model.md).
    """
    if mode == AUTO_MODE:
        return route(query).mode
    if mode not in EVIDENCE_BUILDERS:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            f"Unbekannter Modus: {mode!r}. Erlaubt: {AUTO_MODE}, {', '.join(MODES)}.",
        )
    return mode


def answer_question(
    db_path: str | Path,
    query: str,
    *,
    mode: str = AUTO_MODE,
    k: int = 5,
    provider: GenerationProvider | None = None,
    scoring: Scoring = DEFAULT_SCORING,
) -> SynthesisResult:
    """Beantwortet eine Frage über den passenden Modus – mit Belegen, optional formuliert.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        query: Natürlichsprachige Frage (nicht leer).
        mode: ``auto`` (Router) oder ein expliziter Modus.
        k: Trefferzahl je Modus (> 0).
        provider: Generierungs-Port; ohne Angabe der ``NoopGenerationProvider`` (keine Synthese).
        scoring: Wertung der Chunk-Modi – ``hybrid`` (Default), ``tfidf`` oder ``bm25``.

    Returns:
        Ein :class:`SynthesisResult` mit vollständiger Evidenz; ``answer`` ist leer, solange
        keine Generierung stattgefunden hat.

    Raises:
        DomainError: ``invalid_input`` bei unbekanntem Modus, leerer Anfrage, ``k <= 0`` oder
            unbekannter Wertung; ``not_found``/``constraint_violation`` wenn kein Index vorliegt.
    """
    resolved = resolve_mode(query, mode)
    evidence = EVIDENCE_BUILDERS[resolved](str(db_path), query, k, scoring)
    return synthesize_answer(evidence, provider or NoopGenerationProvider())
