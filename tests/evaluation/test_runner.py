"""Tests für die Modus-Evaluation gegen einen realen Index, Phase 7 / A6."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.evaluation.gold import GoldQuestion, GoldSet
from research_graphrag.evaluation.metrics import EvaluationReport
from research_graphrag.evaluation.runner import (
    LABELS,
    RunParameters,
    evaluate_all,
    evaluate_mode,
    evaluate_primitive,
)
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import TfidfIndex, build_index

_CLUSTER_TRANSFORMER = {
    "aaaa0001": ["transformer attention mechanism self attention", "multi head attention encoder"],
    "aaaa0002": ["self attention transformer architecture", "transformer encoder attention heads"],
}
_CLUSTER_CITATION = {
    "bbbb0001": [
        "citation network clustering communities",
        "community detection louvain modularity",
    ],
    "bbbb0002": [
        "community detection citation clustering",
        "louvain modularity communities network",
    ],
}

_HIT = GoldQuestion(
    "G01", "transformer attention encoder", "fact", ("attention",), ("aaaa0001", "aaaa0002")
)
_MISS = GoldQuestion("G02", "zzzqqqwww xxyyzzq", "concept", ("attention",), ("aaaa0001",))
_GOLD = GoldSet("test-1.0.0", (_HIT, _MISS))


def _paper(paper_id: str, texts: Sequence[str]) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index + 1:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
        )
        for index, text in enumerate(texts)
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=len(texts),
        chunks=chunks,
        quality_flags=(),
    )


def _build(tmp_path: Path) -> Path:
    papers = [_paper(pid, texts) for pid, texts in _CLUSTER_TRANSFORMER.items()]
    papers += [_paper(pid, texts) for pid, texts in _CLUSTER_CITATION.items()]
    db = tmp_path / "index" / "index.sqlite"
    build_index(papers, db)
    build_graph(papers, db)
    return db


def _ranks(report: EvaluationReport) -> dict[str, int | None]:
    return {score.qid: score.first_rank for score in report.scores}


def test_basic_mode_matches_the_shared_primitive(tmp_path: Path) -> None:
    """Contract: ``search_basic`` erhält die Reihenfolge der Primitive **exakt**.

    Deshalb wird Basic nicht als zweite Kennzahl gepflegt (ADR 0016).
    """
    db = _build(tmp_path)
    params = RunParameters()

    primitive = evaluate_primitive(TfidfIndex.load(db), _GOLD, params)
    basic = evaluate_mode(db, _GOLD, "basic", params)

    assert _ranks(basic) == _ranks(primitive)
    assert basic.hit_rate == primitive.hit_rate
    assert basic.mrr == primitive.mrr
    # Basic kennt nur eine Belegsorte – eine Diagnose wäre Rauschen.
    assert basic.by_diagnosis() == {}


def test_local_bundle_reports_the_contributing_component(tmp_path: Path) -> None:
    """Local weist aus, welcher Baustein den ersten Treffer beisteuert."""
    report = evaluate_mode(_build(tmp_path), _GOLD, "local", RunParameters())

    assert report.label == "local"
    assert set(report.by_diagnosis()) <= {"seed", "neighborhood", "fan_out"}
    assert _ranks(report)["G01"] is not None
    assert _ranks(report)["G02"] is None


def test_local_fan_out_can_only_add_evidence(tmp_path: Path) -> None:
    """Der Fan-out erweitert das Bündel – ein Treffer kann dadurch nicht verloren gehen."""
    db = _build(tmp_path)

    without = evaluate_mode(db, _GOLD, "local", RunParameters(fan_out=0))
    with_fan_out = evaluate_mode(db, _GOLD, "local", RunParameters(fan_out=2))

    for qid, rank in _ranks(without).items():
        if rank is not None:
            assert _ranks(with_fan_out)[qid] == rank


def test_global_reports_coverage_next_to_trivial_baselines(tmp_path: Path) -> None:
    """Global liefert Coverage **nur** zusammen mit Selektivität und Trivial-Baselines."""
    report = evaluate_mode(_build(tmp_path), _GOLD, "global", RunParameters())

    labels = [stats.label for stats in report.coverage]
    assert labels[0] == "global"
    assert len(labels) == 3  # echte Auswahl + größte-n + zufällig-n
    for stats in report.coverage:
        assert 0.0 <= stats.coverage <= 1.0
        assert 0.0 <= stats.selectivity <= 1.0


def test_drift_diagnosis_separates_selection_from_ranking(tmp_path: Path) -> None:
    """DRIFT unterscheidet Community-Wahl, verfehlte Auswahl und Basic-Fallback."""
    report = evaluate_mode(_build(tmp_path), _GOLD, "drift", RunParameters())
    diagnoses = {score.qid: score.diagnosis for score in report.scores}

    assert diagnoses["G01"] == "in_community"
    # Ohne passende Community greift der Fallback – ausgewiesen statt still (ADR 0022).
    assert diagnoses["G02"] == "fallback"


def test_global_marks_a_thematically_wrong_community(tmp_path: Path) -> None:
    """Wird eine Community gewählt, die kein erwartetes Paper enthält, heißt das so."""
    gold = GoldSet(
        "test-1.0.0",
        (GoldQuestion("G01", "louvain modularity communities", "fact", ("x",), ("aaaa0001",)),),
    )

    report = evaluate_mode(_build(tmp_path), gold, "global", RunParameters())

    assert report.scores[0].diagnosis == "community_missed"
    assert report.scores[0].first_rank is None


def test_global_without_questions_stays_defined(tmp_path: Path) -> None:
    """Ein leeres Gold-Set liefert Nullwerte statt einer Division durch null."""
    report = evaluate_mode(_build(tmp_path), GoldSet("leer", ()), "global", RunParameters())

    assert report.scores == ()
    assert [stats.coverage for stats in report.coverage] == [0.0, 0.0, 0.0]


def test_evaluate_all_covers_primitive_and_every_mode(tmp_path: Path) -> None:
    """Der Sammellauf liefert genau die angeforderten Berichte."""
    reports = evaluate_all(_build(tmp_path), _GOLD, RunParameters())

    assert tuple(reports) == LABELS
    assert all(report.scores for report in reports.values())


def test_evaluation_is_deterministic(tmp_path: Path) -> None:
    """Zwei Läufe über denselben Index liefern identische Berichte (inkl. Baselines)."""
    db = _build(tmp_path)

    assert evaluate_all(db, _GOLD, RunParameters()) == evaluate_all(db, _GOLD, RunParameters())


def test_unknown_label_is_rejected(tmp_path: Path) -> None:
    """Ein unbekannter Modus ist ein Eingabefehler, kein stiller Leerlauf."""
    with pytest.raises(DomainError) as excinfo:
        evaluate_mode(_build(tmp_path), _GOLD, "semantic", RunParameters())

    assert excinfo.value.code is ErrorCode.INVALID_INPUT
