"""Tests für den TF-IDF/SQLite-Index (AP2, Offline-Hybrid)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.tfidf_index import TfidfIndex, _snippet, build_index


def _paper(paper_id: str, texts: Sequence[str]) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-p{index + 1}",
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


def test_build_and_search_returns_provenance(tmp_path: Path) -> None:
    """Ein Treffer trägt die korrekte Seiten-/Paper-Provenienz."""
    paper = _paper("aaaa1111", ["transformer attention mechanism", "graph message passing"])
    db = tmp_path / "index" / "index.sqlite"

    n = build_index([paper], db)
    index = TfidfIndex.load(db)
    hits = index.search("attention", k=3)

    assert n == 2
    assert index.size == 2
    assert hits[0].chunk_id == "aaaa1111-p1"
    assert hits[0].page_number == 1
    assert hits[0].paper_id == "aaaa1111"
    assert hits[0].score > 0.0
    assert hits[0].source_uri == "file:///aaaa1111.pdf"


def test_search_ranks_relevant_chunk_first(tmp_path: Path) -> None:
    """Der thematisch passende Chunk steht vorn."""
    paper = _paper("bbbb2222", ["clustering of citation networks", "reinforcement learning agents"])
    db = tmp_path / "index.sqlite"
    build_index([paper], db)

    hits = TfidfIndex.load(db).search("reinforcement learning", k=2)

    assert hits[0].page_number == 2


def test_no_match_returns_empty(tmp_path: Path) -> None:
    """Ohne Vokabular-Überschneidung gibt es keine Treffer."""
    paper = _paper("cccc3333", ["semantic parsing of queries"])
    db = tmp_path / "index.sqlite"
    build_index([paper], db)

    assert TfidfIndex.load(db).search("banana smoothie", k=5) == []


def test_build_without_text_raises_invalid_input(tmp_path: Path) -> None:
    """Nur leere Chunks -> invalid_input."""
    paper = _paper("dddd4444", ["", "   "])
    with pytest.raises(DomainError) as excinfo:
        build_index([paper], tmp_path / "index.sqlite")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_empty_query_raises_invalid_input(tmp_path: Path) -> None:
    """Leere Anfrage -> invalid_input."""
    paper = _paper("eeee5555", ["content for the index"])
    db = tmp_path / "index.sqlite"
    build_index([paper], db)
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db).search("  ", k=3)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_load_missing_db_raises_not_found(tmp_path: Path) -> None:
    """Fehlende Index-Datei -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(tmp_path / "absent.sqlite")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_reindex_is_deterministic(tmp_path: Path) -> None:
    """Zweimaliger Bau + Suche liefert identische Top-Treffer (Determinismus)."""
    paper = _paper("ffff6666", ["alpha beta gamma", "delta epsilon zeta"])
    db = tmp_path / "index.sqlite"

    build_index([paper], db)
    first = TfidfIndex.load(db).search("alpha", k=1)
    build_index([paper], db)
    second = TfidfIndex.load(db).search("alpha", k=1)

    assert first[0].chunk_id == second[0].chunk_id
    assert first[0].score == pytest.approx(second[0].score)


def test_multi_paper_index_and_k_limit(tmp_path: Path) -> None:
    """Zwei Papers werden gemeinsam indexiert; k begrenzt die Trefferzahl."""
    p1 = _paper("aaaa0001", ["neural network training", "gradient descent optimization"])
    p2 = _paper("bbbb0002", ["bayesian inference methods", "gradient boosting trees"])
    db = tmp_path / "index.sqlite"

    n = build_index([p1, p2], db)
    index = TfidfIndex.load(db)
    hits = index.search("gradient", k=1)

    assert n == 4
    assert index.size == 4
    assert len(hits) == 1
    assert "gradient" in hits[0].snippet.lower()


def test_search_snippet_is_truncated(tmp_path: Path) -> None:
    """Lange Chunk-Texte werden im Snippet auf das Limit gekürzt."""
    long_text = "alpha " + "lorem ipsum dolor sit amet consectetur " * 20
    db = tmp_path / "index.sqlite"
    build_index([_paper("cccc0003", [long_text])], db)

    hit = TfidfIndex.load(db).search("alpha", k=1)[0]

    assert len(hit.snippet) <= 200
    assert hit.snippet.endswith("…")


def test_constraint_violation_when_index_has_no_chunks(tmp_path: Path) -> None:
    """Ein Index ohne Chunks (manuell geleert) -> constraint_violation."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("dddd0004", ["content to be removed"])], db)
    connection = sqlite3.connect(str(db))
    connection.execute("DELETE FROM chunks")
    connection.commit()
    connection.close()

    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db)
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


@given(st.text(), st.integers(min_value=1, max_value=60))
def test_snippet_never_exceeds_limit(text: str, limit: int) -> None:
    """Eigenschaft: _snippet ist einzeilig und überschreitet das Limit nie."""
    snippet = _snippet(text, limit)
    assert len(snippet) <= limit
    assert "\n" not in snippet


def test_non_positive_k_raises_invalid_input(tmp_path: Path) -> None:
    """k <= 0 -> invalid_input."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("iiii9999", ["content for the index"])], db)
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db).search("content", k=0)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT
