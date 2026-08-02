"""Tests für das Gold-Set und die mechanische Label-Regel, Phase 7 / A4 + A6."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from research_graphrag.evaluation.gold import (
    MECHANICAL_LABELS,
    GoldQuestion,
    GoldSet,
    derive_expected_papers,
    load_gold_set,
    verify_labels,
)
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.tfidf_index import build_index

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GOLD_SET = _REPO_ROOT / "eval" / "retrieval-gold.json"


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
        _paper("aaaa0001", ["graph retrieval with communities", "evaluation on faiss benchmarks"]),
        _paper("bbbb0002", ["transformer attention mechanism", "unrelated cooking recipes"]),
    ]
    db = tmp_path / "index.sqlite"
    build_index(papers, db)
    return db


def test_derive_expected_papers_requires_all_terms(tmp_path: Path) -> None:
    """Die Label-Regel verlangt alle Strings in **einem** Chunk."""
    db = _build(tmp_path)

    assert derive_expected_papers(db, ("faiss",)) == ("aaaa0001",)
    assert derive_expected_papers(db, ("faiss", "benchmarks")) == ("aaaa0001",)
    assert derive_expected_papers(db, ("faiss", "attention")) == ()


def test_derive_expected_papers_is_case_insensitive(tmp_path: Path) -> None:
    """Groß-/Kleinschreibung spielt für die Ableitung keine Rolle."""
    assert derive_expected_papers(_build(tmp_path), ("FAISS",)) == ("aaaa0001",)


def test_verify_labels_detects_stale_expectations(tmp_path: Path) -> None:
    """Eingefrorene Labels, die der Index nicht mehr hergibt, werden gemeldet."""
    db = _build(tmp_path)
    good = GoldQuestion("G01", "faiss?", "fact", ("faiss",), ("aaaa0001",))
    stale = GoldQuestion("G02", "faiss?", "fact", ("faiss",), ("bbbb0002",))

    assert verify_labels(db, GoldSet("1.0.0", (good,))) == ()
    findings = verify_labels(db, GoldSet("1.0.0", (good, stale)))
    assert len(findings) == 1
    assert findings[0].startswith("G02")


def test_verify_labels_skips_non_mechanical_sources(tmp_path: Path) -> None:
    """Nur mechanisch abgeleitete Labels sind nachrechenbar – andere werden übersprungen."""
    db = _build(tmp_path)
    judged = GoldQuestion("J01", "faiss?", "fact", ("faiss",), ("bbbb0002",), label_source="judged")

    assert verify_labels(db, GoldSet("1.0.0", (judged,))) == ()


def test_gold_question_defaults_to_the_mechanical_label_source() -> None:
    """Ohne Angabe gilt die nachrechenbare mechanische Regel."""
    question = GoldQuestion("G01", "faiss?", "fact", ("faiss",), ("aaaa0001",))

    assert question.label_source in MECHANICAL_LABELS


def test_versioned_gold_set_is_wellformed() -> None:
    """Das versionierte Gold-Set ist ladbar und vollständig annotiert."""
    gold = load_gold_set(_GOLD_SET)

    assert gold.version
    assert gold.questions
    assert all(question.query and question.match_all for question in gold.questions)
    assert all(question.expected_paper_ids for question in gold.questions)
    assert len({question.qid for question in gold.questions}) == len(gold.questions)
    assert {question.label_source for question in gold.questions} == set(MECHANICAL_LABELS)
    assert "label_rule" in json.loads(_GOLD_SET.read_text(encoding="utf-8"))
