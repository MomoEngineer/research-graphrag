"""Tests für Basic Search (AP3, Offline-Hybrid)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.basic import BasicSearchResult, search_basic


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


def _build(tmp_path: Path) -> Path:
    paper = _paper("aaaa1111", ["transformer attention mechanism", "graph message passing dataset"])
    db = tmp_path / "index" / "index.sqlite"
    build_index([paper], db)
    return db


def test_search_basic_returns_cited_result(tmp_path: Path) -> None:
    """Ein Treffer trägt belegte Provenienz und positiven Score."""
    result = search_basic(_build(tmp_path), "attention", k=3)

    assert isinstance(result, BasicSearchResult)
    assert result.query == "attention"
    assert result.citations[0].page_number == 1
    assert result.citations[0].paper_id == "aaaa1111"
    assert result.citations[0].score > 0.0
    assert result.citations[0].source_uri == "file:///aaaa1111.pdf"
    assert result.citations[0].snippet


def test_search_basic_no_match_is_empty(tmp_path: Path) -> None:
    """Ohne Vokabular-Überschneidung gibt es keine Zitate."""
    result = search_basic(_build(tmp_path), "banana smoothie", k=5)
    assert result.citations == ()


def test_search_basic_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Fehlender Index -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        search_basic(tmp_path / "absent.sqlite", "attention")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_search_basic_empty_query_raises_invalid_input(tmp_path: Path) -> None:
    """Leere Anfrage -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        search_basic(_build(tmp_path), "   ")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_result_to_dict_shape(tmp_path: Path) -> None:
    """to_dict liefert das dokumentierte Output-Schema."""
    payload = search_basic(_build(tmp_path), "dataset", k=2).to_dict()

    assert set(payload) == {"query", "citations"}
    assert set(payload["citations"][0]) == {
        "paper_id",
        "section_title",
        "page_number",
        "page_end",
        "chunk_id",
        "score",
        "source_uri",
        "snippet",
    }
