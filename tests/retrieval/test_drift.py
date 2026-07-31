"""Tests für DRIFT Search (Global→Local-Hybrid, Phase 4)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.drift import DriftSearchResult, search_drift

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


def _two_cluster_papers() -> list[CanonicalPaper]:
    papers = [_paper(pid, texts) for pid, texts in _CLUSTER_TRANSFORMER.items()]
    papers += [_paper(pid, texts) for pid, texts in _CLUSTER_CITATION.items()]
    return papers


def _build(tmp_path: Path, *, graph: bool = True) -> Path:
    db = tmp_path / "index" / "index.sqlite"
    papers = _two_cluster_papers()
    build_index(papers, db)
    if graph:
        build_graph(papers, db)
    return db


def test_drift_returns_community_and_local_citations(tmp_path: Path) -> None:
    """DRIFT wählt die passende Community und verfeinert innerhalb ihrer Mitglieder."""
    result = search_drift(_build(tmp_path), "transformer attention encoder", k=6)

    assert isinstance(result, DriftSearchResult)
    assert result.community is not None
    assert result.citations
    # Lokale Verfeinerung bleibt auf die Mitglieds-Paper der transformer-Community beschränkt.
    assert {citation.paper_id for citation in result.citations} <= {"aaaa0001", "aaaa0002"}


def test_drift_no_match_returns_empty(tmp_path: Path) -> None:
    """Ohne passende Community bleibt das Ergebnis leer."""
    result = search_drift(_build(tmp_path), "banana smoothie recipe")

    assert result.community is None
    assert result.citations == ()


def test_drift_empty_query_raises_invalid_input(tmp_path: Path) -> None:
    """Leere Anfrage -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        search_drift(_build(tmp_path), "   ")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_drift_non_positive_k_raises_invalid_input(tmp_path: Path) -> None:
    """k <= 0 -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        search_drift(_build(tmp_path), "transformer", k=0)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_drift_without_graph_raises_constraint_violation(tmp_path: Path) -> None:
    """Ohne gebauten Graphen -> constraint_violation."""
    with pytest.raises(DomainError) as excinfo:
        search_drift(_build(tmp_path, graph=False), "transformer")
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_drift_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Fehlender Index -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        search_drift(tmp_path / "absent.sqlite", "transformer")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_drift_to_dict_shape(tmp_path: Path) -> None:
    """to_dict liefert das dokumentierte Output-Schema."""
    payload = search_drift(_build(tmp_path), "transformer attention", k=4).to_dict()

    assert set(payload) == {"query", "community", "citations"}
    assert set(payload["community"]) == {
        "community_id",
        "score",
        "size",
        "keywords",
        "representatives",
    }
    assert set(payload["citations"][0]) == {
        "paper_id",
        "section_title",
        "page_number",
        "chunk_id",
        "score",
        "source_uri",
        "snippet",
    }
