"""Tests für die Textausgabe der Evaluation, Phase 7 / A6."""

from __future__ import annotations

from research_graphrag.evaluation.baseline import Baseline, Change, Comparison, Fingerprint
from research_graphrag.evaluation.gold import GoldQuestion, GoldSet
from research_graphrag.evaluation.metrics import CoverageStats, EvaluationReport, QuestionScore
from research_graphrag.evaluation.report import (
    LIMITATION,
    render_comparison,
    render_modes,
    render_report,
)
from research_graphrag.evaluation.runner import RunParameters

_GOLD = GoldSet(
    "test-1.0.0",
    (GoldQuestion("G01", "Welche Paper nutzen FAISS?", "fact", ("faiss",), ("aaaa0001",)),),
)
_REPORT = EvaluationReport(
    label="primitive",
    k=5,
    scoring="hybrid",
    scores=(QuestionScore(qid="G01", kind="fact", first_rank=2),),
)
_BASELINE = Baseline(
    version="1.0.0",
    created="2026-08-02",
    fingerprint=Fingerprint(
        gold_set_version="test-1.0.0",
        index_schema_version="0.4.0",
        n_papers=1,
        n_chunks=1,
        n_communities=1,
        parameters=RunParameters().to_dict(),
    ),
    ranks={"basic": {"G01": 2}},
)


def test_report_shows_question_lines_and_aggregates() -> None:
    """Der ausführliche Bericht nennt Rang, Kehrwert, Anfrage und die Aggregate."""
    rendered = render_report(_REPORT, _GOLD)

    assert "G01" in rendered
    assert "Welche Paper nutzen FAISS?" in rendered
    assert "Hit@5" in rendered
    assert "GESAMT" in rendered


def test_mode_report_never_shows_coverage_without_its_reference_values() -> None:
    """Coverage erscheint nur zusammen mit Selektivität, Lift und Trivial-Baselines."""
    reports = {
        "local": EvaluationReport(
            label="local",
            k=5,
            scoring="hybrid",
            scores=(QuestionScore(qid="G01", kind="fact", first_rank=1, diagnosis="seed"),),
        ),
        "global": EvaluationReport(
            label="global",
            k=5,
            scoring="hybrid",
            scores=(QuestionScore(qid="G01", kind="fact", first_rank=1, diagnosis="in_community"),),
            coverage=(
                CoverageStats("global", 0.248, 0.070),
                CoverageStats("größte-5", 0.567, 0.559),
                CoverageStats("zufällig-5", 0.083, 0.214),
            ),
        ),
    }

    rendered = render_modes(reports, _GOLD)

    assert "seed 1" in rendered  # Diagnose je Modus
    for label in ("global", "größte-5", "zufällig-5"):
        assert label in rendered
    assert "Selektivität" in rendered
    assert "Lift" in rendered
    assert LIMITATION in rendered


def test_comparison_without_changes_is_explicit() -> None:
    """Ein unauffälliger Lauf sagt das ausdrücklich, statt leer zu bleiben."""
    rendered = render_comparison(Comparison(True, "", ()), _BASELINE)

    assert "Keine Abweichung" in rendered
    assert "2026-08-02" in rendered


def test_comparison_marks_regressions() -> None:
    """Regressionen werden markiert, Rangbewegungen nur mitgeführt."""
    comparison = Comparison(
        True,
        "",
        (
            Change("basic", "G01", 2, None, "regression"),
            Change("local", "G01", 2, 4, "verschlechterung"),
        ),
    )

    rendered = render_comparison(comparison, _BASELINE)

    assert "! regression" in rendered
    assert "kein Treffer" in rendered
    assert "1 Regression(en) · 1 weitere Abweichung(en)" in rendered


def test_incomparable_baseline_names_the_reason_and_the_way_out() -> None:
    """Bei unpassendem Fingerprint wird der Grund genannt und der nächste Schritt gezeigt."""
    rendered = render_comparison(Comparison(False, "n_papers: 145 → 150", ()), _BASELINE)

    assert "nicht vergleichbar" in rendered
    assert "n_papers: 145 → 150" in rendered
    assert "--write-baseline" in rendered
