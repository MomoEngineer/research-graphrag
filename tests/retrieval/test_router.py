"""Tests für den Query-Router (Heuristik, Phase 4)."""

from __future__ import annotations

import pytest

from research_graphrag.retrieval.router import MODES, RouteDecision, route


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Wie lautet die DOI von Paper Z?", "basic"),
        ("Welcher F1-Score wird berichtet?", "basic"),
        ("Welche Forschungsrichtungen zeichnen sich im Korpus ab?", "global"),
        ("Gib einen Überblick über die Themen.", "global"),
        ("Welche Paper bauen auf Methode Y auf?", "local"),
        ("Welche Arbeiten zitieren Paper Z?", "local"),
        ("Wo widersprechen sich die Ergebnisse zu Thema T?", "drift"),
        ("Vergleiche Paper A und Paper B im Aspekt Genauigkeit.", "drift"),
    ],
)
def test_route_maps_question_to_mode(query: str, expected: str) -> None:
    """Repräsentative Fragen je Fragetyp werden dem erwarteten Modus zugeordnet."""
    decision = route(query)
    assert decision.mode == expected
    assert decision.mode in MODES
    assert decision.rationale


def test_route_defaults_to_basic() -> None:
    """Ohne Modus-Signal fällt der Router auf basic zurück (präziseste Antwort)."""
    decision = route("Erkläre den Inhalt dieses Papers.")
    assert decision.mode == "basic"
    assert "Standard" in decision.rationale


def test_route_precedence_drift_over_basic() -> None:
    """Bei gemischten Signalen gewinnt die höhere Präzedenz (drift vor basic)."""
    decision = route("Vergleiche den F1-Score von A und B.")
    assert decision.mode == "drift"


def test_route_returns_frozen_decision() -> None:
    """Die Entscheidung ist ein unveränderliches Wertobjekt."""
    decision = route("Themenüberblick")
    assert isinstance(decision, RouteDecision)
    with pytest.raises(AttributeError):
        decision.mode = "basic"  # type: ignore[misc]
