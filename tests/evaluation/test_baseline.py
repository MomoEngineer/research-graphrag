"""Tests für das Baseline-Artefakt und den qid-genauen Regressions-Check, Phase 7 / A6."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.evaluation.baseline import (
    Fingerprint,
    build_baseline,
    compare,
    load_baseline,
    precheck,
    read_fingerprint,
    save_baseline,
)
from research_graphrag.evaluation.gold import GoldQuestion, GoldSet
from research_graphrag.evaluation.metrics import EvaluationReport, QuestionScore
from research_graphrag.evaluation.runner import RunParameters
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index

_GOLD = GoldSet(
    "test-1.0.0",
    (
        GoldQuestion("G01", "attention", "fact", ("attention",), ("aaaa0001",)),
        GoldQuestion("G02", "louvain", "fact", ("louvain",), ("bbbb0001",)),
    ),
)


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
    papers = [
        _paper("aaaa0001", ["transformer attention mechanism", "multi head attention encoder"]),
        _paper("bbbb0001", ["community detection louvain", "louvain modularity communities"]),
    ]
    db = tmp_path / "index" / "index.sqlite"
    build_index(papers, db)
    build_graph(papers, db)
    return db


def _reports(*ranks: int | None) -> dict[str, EvaluationReport]:
    scores = tuple(
        QuestionScore(qid=f"G{index + 1:02d}", kind="fact", first_rank=rank)
        for index, rank in enumerate(ranks)
    )
    return {"basic": EvaluationReport(label="basic", k=5, scoring="hybrid", scores=scores)}


def _fingerprint(n_papers: int = 2) -> Fingerprint:
    return Fingerprint(
        gold_set_version="test-1.0.0",
        index_schema_version="0.4.0",
        n_papers=n_papers,
        n_chunks=4,
        n_communities=2,
        parameters=RunParameters().to_dict(),
    )


def test_baseline_survives_a_write_read_roundtrip(tmp_path: Path) -> None:
    """Die eingefrorene Baseline wird unverändert wieder eingelesen."""
    baseline = build_baseline(_reports(1, None), _fingerprint(), created="2026-08-02")
    path = tmp_path / "retrieval-baseline.json"

    save_baseline(baseline, path)

    assert load_baseline(path) == baseline
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Gespeichert wird ausschließlich der erste relevante Rang – Aggregate werden abgeleitet.
    assert payload["ranks"]["basic"] == {"G01": 1, "G02": None}


def test_missing_baseline_is_a_domain_error(tmp_path: Path) -> None:
    """Eine fehlende Baseline ist ein Fund, kein stiller Vergleich gegen nichts."""
    with pytest.raises(DomainError) as excinfo:
        load_baseline(tmp_path / "fehlt.json")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_unchanged_run_reports_no_change(tmp_path: Path) -> None:
    """Ein unveränderter Lauf meldet keine Abweichung und endet mit Exit-Code 0."""
    reports = _reports(1, None)
    baseline = build_baseline(reports, _fingerprint(), created="2026-08-02")

    comparison = compare(baseline, reports, _fingerprint())

    assert comparison.comparable is True
    assert comparison.changes == ()
    assert comparison.exit_code == 0


def test_lost_hit_is_a_regression(tmp_path: Path) -> None:
    """Treffer → kein Treffer ist der einzige Fall, der den Exit-Code auf 1 zieht."""
    baseline = build_baseline(_reports(1, 3), _fingerprint(), created="2026-08-02")

    comparison = compare(baseline, _reports(1, None), _fingerprint())

    assert [change.severity for change in comparison.changes] == ["regression"]
    assert comparison.changes[0].qid == "G02"
    assert comparison.changes[0].before == 3
    assert comparison.changes[0].after is None
    assert comparison.exit_code == 1


def test_rank_movement_is_reported_but_not_fatal() -> None:
    """Rangrauschen wird berichtet, bricht den Lauf aber nicht ab."""
    baseline = build_baseline(_reports(1, 3), _fingerprint(), created="2026-08-02")

    comparison = compare(baseline, _reports(2, 1), _fingerprint())

    severities = {change.qid: change.severity for change in comparison.changes}
    assert severities == {"G01": "verschlechterung", "G02": "verbesserung"}
    assert comparison.exit_code == 0


def test_new_hit_is_an_improvement() -> None:
    """Ein neu gewonnener Treffer ist eine Verbesserung, keine Abweichung nach unten."""
    baseline = build_baseline(_reports(1, None), _fingerprint(), created="2026-08-02")

    comparison = compare(baseline, _reports(1, 4), _fingerprint())

    assert [change.severity for change in comparison.changes] == ["verbesserung"]
    assert comparison.exit_code == 0


def test_stale_fingerprint_blocks_the_comparison() -> None:
    """Passt der Korpus nicht mehr, wird **nicht** still verglichen (Exit-Code 2)."""
    baseline = build_baseline(_reports(1, 3), _fingerprint(), created="2026-08-02")

    comparison = compare(baseline, _reports(1, 3), _fingerprint(n_papers=150))

    assert comparison.comparable is False
    assert "n_papers" in comparison.reason
    assert comparison.changes == ()
    assert comparison.exit_code == 2


def test_different_levels_block_the_comparison() -> None:
    """Deckt die Baseline andere Ebenen ab, wird ebenfalls nicht verglichen."""
    baseline = build_baseline(_reports(1, 3), _fingerprint(), created="2026-08-02")
    reports = dict(_reports(1, 3))
    reports["local"] = reports["basic"]

    comparison = compare(baseline, reports, _fingerprint())

    assert comparison.comparable is False
    assert "Ebenen" in comparison.reason
    assert comparison.exit_code == 2


def test_precheck_blocks_before_an_expensive_run() -> None:
    """Die Vergleichbarkeit steht fest, bevor überhaupt gemessen wird."""
    baseline = build_baseline(_reports(1, 3), _fingerprint(), created="2026-08-02")

    assert precheck(baseline, _fingerprint()) is None
    blocked = precheck(baseline, _fingerprint(n_papers=150))
    assert blocked is not None
    assert blocked.exit_code == 2


def test_fingerprint_is_read_from_the_real_index(tmp_path: Path) -> None:
    """Der Fingerprint stammt aus dem Index selbst, nicht aus gepflegten Zahlen."""
    fingerprint = read_fingerprint(_build(tmp_path), _GOLD, RunParameters())

    assert fingerprint.gold_set_version == "test-1.0.0"
    assert fingerprint.n_papers == 2
    assert fingerprint.n_chunks == 4
    assert fingerprint.n_communities >= 1
    assert fingerprint.index_schema_version
    assert fingerprint.parameters["scoring"] == RunParameters().scoring


def test_fingerprint_without_a_graph_counts_zero_communities(tmp_path: Path) -> None:
    """Ohne gebauten Graphen fehlt die Tabelle – das ist kein Fehler, sondern null."""
    db = tmp_path / "index" / "index.sqlite"
    build_index([_paper("aaaa0001", ["transformer attention mechanism"])], db)

    assert read_fingerprint(db, _GOLD, RunParameters()).n_communities == 0


def test_missing_index_is_a_domain_error(tmp_path: Path) -> None:
    """Ein fehlender Index wird als Fund gemeldet, nicht als leerer Fingerprint."""
    with pytest.raises(DomainError) as excinfo:
        read_fingerprint(tmp_path / "fehlt.sqlite", _GOLD, RunParameters())

    assert excinfo.value.code is ErrorCode.NOT_FOUND
