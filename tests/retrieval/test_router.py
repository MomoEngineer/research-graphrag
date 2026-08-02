"""Tests für den gehärteten Query-Router (Heuristik, Phase 4 · Härtung Phase 7 / A7)."""

from __future__ import annotations

import pytest

from research_graphrag.retrieval.router import (
    CONFIDENCE_NONE,
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    CONFIDENCES,
    DEFAULT_MODE,
    MODES,
    SIGNALS,
    STRUCTURAL_MODES,
    RouteDecision,
    matched_signals,
    route,
)


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
        ("Which thematic clusters combine graphs and retrieval?", "global"),
        ("Which works relate to knowledge-graph-based code generation?", "local"),
    ],
)
def test_route_maps_question_to_mode(query: str, expected: str) -> None:
    """Repräsentative Fragen je Fragetyp werden dem erwarteten Modus zugeordnet."""
    decision = route(query)
    assert decision.mode == expected
    assert decision.mode in MODES
    assert decision.rationale
    assert decision.confidence in CONFIDENCES


def test_route_defaults_to_basic_without_any_signal() -> None:
    """Ohne Signal fällt der Router auf basic zurück – sichtbar über die Konfidenz."""
    decision = route("Erkläre den Inhalt dieses Papers.")
    assert decision.mode == DEFAULT_MODE
    assert decision.confidence == CONFIDENCE_NONE
    assert decision.signals == ()
    assert "Standard" in decision.rationale


def test_fact_signals_confirm_but_do_not_decide() -> None:
    """Fakt-Signale bestätigen den Default, ohne die Entscheidung zu verschieben."""
    decision = route("What F1 score is reported for the evaluation?")
    assert decision.mode == DEFAULT_MODE
    assert decision.confidence == CONFIDENCE_NONE
    assert decision.signals == ("score", "f1")
    assert "bestätigt basic" in decision.rationale


def test_structural_signal_beats_fact_signals() -> None:
    """Ein struktureller Kandidat gewinnt gegen mehrere bestätigende Fakt-Signale."""
    decision = route("Vergleiche den F1-Score von A und B.")
    assert decision.mode == "drift"
    assert decision.confidence == CONFIDENCE_STRONG


def test_more_signals_win_and_rationale_names_the_loser() -> None:
    """Bei Konkurrenz entscheidet die Signalzahl; der unterlegene Modus wird benannt."""
    decision = route("Vergleiche die Unterschiede zwischen den Themen.")
    assert decision.mode == "drift"
    assert decision.confidence == CONFIDENCE_STRONG
    assert "schwächer: global" in decision.rationale


def test_tie_falls_back_to_basic_and_names_the_candidates() -> None:
    """Gleichstand entscheidet nichts still, sondern fällt sichtbar auf basic zurück."""
    decision = route("Vergleiche die Themen der beiden Communities.")
    assert decision.mode == DEFAULT_MODE
    assert decision.confidence == CONFIDENCE_WEAK
    assert "Gleichstand" in decision.rationale
    assert "drift" in decision.rationale
    assert "global" in decision.rationale


@pytest.mark.parametrize(
    "query",
    [
        "What does the paper say about different retrieval strategies?",
        "What does the paper say about the differentiation of entities?",
        "What does the paper report about comparable systems?",
        "Was steht im Paper zu unterschiedlichen Chunk-Größen?",
    ],
)
def test_word_boundaries_prevent_false_drift(query: str) -> None:
    """Ableitungen ohne Vergleichsabsicht lösen keinen DRIFT mehr aus (Messbefund A7)."""
    assert route(query).mode == DEFAULT_MODE


def test_prefix_signals_are_anchored_at_the_word_start() -> None:
    """``cite`` greift am Wortanfang, aber nicht in der Mitte eines Systemnamens."""
    assert route("Which studies cited this approach?").mode == "local"
    assert route("What does the paper say about ContextCite?").mode == DEFAULT_MODE


def test_stem_signals_still_match_german_compounds() -> None:
    """Deutsche Stämme bleiben Teilwort-Signale (Komposita/Beugung)."""
    assert route("Gib mir einen Themenüberblick.").mode == "global"
    assert route("Welche Arbeiten widersprechen sich?").mode == "drift"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("What is the trend in Figure 3?", DEFAULT_MODE),
        ("Which trends emerge in recent work?", "global"),
        ("How is the corpus constructed in this study?", DEFAULT_MODE),
        ("Which topics recur across the corpus?", "global"),
    ],
)
def test_ambiguous_terms_only_count_in_their_question_form(query: str, expected: str) -> None:
    """Gegenstandsbezeichnungen sind kein Signal – nur die Frageform zählt."""
    assert route(query).mode == expected


def test_which_papers_is_no_longer_a_signal() -> None:
    """Die gemessene Hauptquelle der Fehlleitung ist entfernt (16 von 22 Fakt-Fragen)."""
    assert route("Which papers use the Qdrant vector database?").mode == DEFAULT_MODE
    assert route("Welche Paper nennen einen F1-Wert?").mode == DEFAULT_MODE


def test_route_is_case_insensitive() -> None:
    """Groß-/Kleinschreibung ist unerheblich."""
    assert route("VECTOR SEARCH VERSUS GRAPH SEARCH").mode == "drift"


def test_route_is_deterministic() -> None:
    """Dieselbe Anfrage liefert dieselbe Entscheidung."""
    query = "Welche Forschungsrichtungen zeichnen sich ab?"
    assert route(query) == route(query)


def test_matched_signals_reports_every_mode() -> None:
    """``matched_signals`` weist die Treffer je Modus in Lexikon-Reihenfolge aus."""
    found = matched_signals("Vergleiche den exakten F1-Score.")
    assert found["drift"] == ("vergleich",)
    assert found["basic"] == ("exakt", "score", "f1")
    assert "global" not in found


def test_route_decision_serializes_for_the_tool_output() -> None:
    """``to_dict`` liefert genau die vier Felder des ``answer_question``-Schemas."""
    payload = route("Which papers build on GraphRAG?").to_dict()
    assert set(payload) == {"mode", "confidence", "signals", "rationale"}
    assert payload["mode"] == "local"
    assert payload["signals"] == ["build on"]


def test_route_returns_frozen_decision() -> None:
    """Die Entscheidung ist ein unveränderliches Wertobjekt."""
    decision = route("Themenüberblick")
    assert isinstance(decision, RouteDecision)
    with pytest.raises(AttributeError):
        decision.mode = "basic"  # type: ignore[misc]


def test_signal_lexicon_is_wellformed() -> None:
    """Jedes Signal ist eindeutig, klein geschrieben und zeigt auf einen gültigen Modus."""
    texts = [signal.text for signal in SIGNALS]
    assert len(texts) == len(set(texts))
    for signal in SIGNALS:
        assert signal.text == signal.text.lower().strip()
        assert signal.mode in MODES
        assert signal.match in ("word", "prefix", "stem")


def test_stem_matching_is_reserved_for_german_signals() -> None:
    """Die riskante Teilwort-Semantik gilt nur für die gemessen unbedenklichen DE-Stämme."""
    stems = {signal.text for signal in SIGNALS if signal.match == "stem"}
    assert stems == {
        "widerspr",
        "gegensatz",
        "gegensätz",
        "vergleich",
        "forschungsrichtung",
        "themen",
        "überblick",
        "landschaft",
        "insgesamt",
        "übergreifend",
        "korpusweit",
        "zitier",
        "zitat",
        "methodennetz",
        "folgearbeit",
        "abkürzung",
        "exakt",
    }


@pytest.mark.parametrize(
    "word",
    [
        "different",
        "differentiation",
        "comparable",
        "contextcite",
        "underscores",
        "geometric",
        "biometrika",
    ],
)
def test_no_stem_signal_fires_inside_an_english_word(word: str) -> None:
    """Kein Teilwort-Signal greift in den gemessenen englischen Fehlalarm-Trägern."""
    assert route(f"What does the paper say about {word}?").mode == DEFAULT_MODE


def test_structural_modes_exclude_the_default() -> None:
    """``basic`` ist Rückfallebene und tritt nie als Kandidat an."""
    assert DEFAULT_MODE not in STRUCTURAL_MODES
    assert set(STRUCTURAL_MODES) | {DEFAULT_MODE} == set(MODES)
