"""Tests für die Kennzahl-Datentypen der Evaluation (retrieval-frei), Phase 7 / A6."""

from __future__ import annotations

from research_graphrag.evaluation.metrics import (
    CoverageStats,
    EvaluationReport,
    QuestionScore,
    first_hit,
)


def _score(qid: str, kind: str, rank: int | None, diagnosis: str | None = None) -> QuestionScore:
    return QuestionScore(qid=qid, kind=kind, first_rank=rank, diagnosis=diagnosis)


def test_first_hit_reports_rank_and_component() -> None:
    """Der erste relevante Eintrag liefert Rang **und** den beitragenden Baustein."""
    entries = (("aaaa", "seed"), ("bbbb", "neighborhood"), ("cccc", "fan_out"))

    assert first_hit(entries, {"cccc"}) == (3, "fan_out")
    assert first_hit(entries, {"bbbb", "cccc"}) == (2, "neighborhood")


def test_first_hit_without_match_is_empty() -> None:
    """Ohne relevanten Eintrag bleiben Rang und Baustein leer."""
    assert first_hit((("aaaa", "seed"),), {"zzzz"}) == (None, None)
    assert first_hit((), {"aaaa"}) == (None, None)


def test_question_score_derives_hit_and_reciprocal_rank() -> None:
    """``first_rank`` ist die einzige Quelle; Treffer und Kehrwert werden abgeleitet."""
    hit = _score("G01", "fact", 4)
    miss = _score("G02", "fact", None)

    assert hit.hit is True
    assert hit.reciprocal_rank == 0.25
    assert miss.hit is False
    assert miss.reciprocal_rank == 0.0


def test_report_aggregates_over_questions_and_kinds() -> None:
    """Hit-Rate, MRR und die Aufschlüsselung je Fragetyp rechnen korrekt."""
    report = EvaluationReport(
        label="primitive",
        k=5,
        scoring="hybrid",
        scores=(_score("G01", "fact", 1), _score("G02", "fact", 4), _score("G03", "concept", None)),
    )

    assert report.hit_rate == 2 / 3
    assert report.mrr == (1.0 + 0.25) / 3
    assert report.by_kind()["fact"] == (1.0, 0.625, 2)
    assert report.by_kind()["concept"] == (0.0, 0.0, 1)


def test_empty_report_stays_zero() -> None:
    """Ein Bericht ohne Fragen liefert 0.0 statt einer Division durch null."""
    report = EvaluationReport(label="local", k=5, scoring="hybrid", scores=())

    assert report.hit_rate == 0.0
    assert report.mrr == 0.0
    assert report.by_kind() == {}


def test_report_counts_diagnoses() -> None:
    """Die Diagnose-Aufschlüsselung zählt die Bausteine bzw. Fehlerursachen."""
    report = EvaluationReport(
        label="local",
        k=5,
        scoring="hybrid",
        scores=(
            _score("G01", "fact", 1, "seed"),
            _score("G02", "fact", 3, "seed"),
            _score("G03", "fact", 7, "fan_out"),
            _score("G04", "fact", None),
        ),
    )

    assert report.by_diagnosis() == {"fan_out": 1, "seed": 2}


def test_coverage_lift_relates_coverage_to_selectivity() -> None:
    """Der Lift misst die Coverage **je Korpusanteil** – nur so sind Strategien vergleichbar."""
    real = CoverageStats(label="global", coverage=0.248, selectivity=0.070)
    trivial = CoverageStats(label="größte-5", coverage=0.567, selectivity=0.559)

    assert round(real.lift, 2) == 3.54
    assert round(trivial.lift, 2) == 1.01
    # Die nackte Coverage würde die triviale Strategie bevorzugen – der Lift nicht.
    assert trivial.coverage > real.coverage
    assert real.lift > trivial.lift


def test_coverage_lift_without_selectivity_is_zero() -> None:
    """Ohne ausgewählte Community ist der Lift definiert (0.0) statt undefiniert."""
    assert CoverageStats(label="global", coverage=0.0, selectivity=0.0).lift == 0.0
