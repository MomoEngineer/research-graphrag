"""Tests für Local Search (Chunk-Nachbarschaft + Paper-Fan-out, Phase 4)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.local import LocalSearchResult, search_local


def _paper(paper_id: str, texts: Sequence[str], section: str = "") -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index + 1:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_title=section,
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


def _linked_papers() -> list[CanonicalPaper]:
    """Zwei stark überlappende Paper -> Graph-Kante; p1 trägt einen distinktiven Term."""
    return [
        _paper(
            "aaaa0001",
            [
                "transformer attention reconciliation unique term",
                "multi head attention transformer",
            ],
            "Methoden",
        ),
        _paper(
            "aaaa0002",
            ["transformer attention encoder heads", "attention transformer architecture layers"],
        ),
    ]


def _build(tmp_path: Path, *, graph: bool = True) -> Path:
    db = tmp_path / "index" / "index.sqlite"
    papers = _linked_papers()
    build_index(papers, db)
    if graph:
        build_graph(papers, db)
    return db


def test_local_returns_seed_neighborhood_and_fanout(tmp_path: Path) -> None:
    """Local liefert Seed, Chunk-Nachbarschaft und einen belegten Paper-Fan-out."""
    result = search_local(_build(tmp_path), "attention", k=3, fan_out=3)

    assert isinstance(result, LocalSearchResult)
    assert result.seed is not None
    assert result.seed.paper_id in {"aaaa0001", "aaaa0002"}
    assert len(result.neighborhood) >= 1
    assert len(result.fan_out) >= 1
    assert result.fan_out[0].weight > 0.0
    assert result.fan_out[0].citation is not None


def test_local_seed_carries_section_provenance(tmp_path: Path) -> None:
    """Ein distinktiver Term führt deterministisch zum Seed-Paper inkl. Abschnitt."""
    result = search_local(_build(tmp_path), "reconciliation", k=2, fan_out=0)

    assert result.seed is not None
    assert result.seed.paper_id == "aaaa0001"
    assert result.seed.section_title == "Methoden"


def test_local_fanout_zero_needs_no_graph(tmp_path: Path) -> None:
    """Mit fan_out=0 funktioniert Local ohne gebauten Graphen."""
    result = search_local(_build(tmp_path, graph=False), "attention", k=2, fan_out=0)

    assert result.seed is not None
    assert result.fan_out == ()


def test_local_fanout_without_graph_raises_constraint_violation(tmp_path: Path) -> None:
    """Fan-out ohne gebauten Graphen -> constraint_violation."""
    with pytest.raises(DomainError) as excinfo:
        search_local(_build(tmp_path, graph=False), "attention", k=2, fan_out=2)
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_local_no_match_returns_empty_seed(tmp_path: Path) -> None:
    """Ohne Vokabular-Überschneidung gibt es keinen Seed."""
    result = search_local(_build(tmp_path), "banana smoothie", k=3, fan_out=3)

    assert result.seed is None
    assert result.neighborhood == ()
    assert result.fan_out == ()


def test_local_negative_fanout_raises_invalid_input(tmp_path: Path) -> None:
    """fan_out < 0 -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        search_local(_build(tmp_path), "attention", fan_out=-1)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_local_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Fehlender Index -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        search_local(tmp_path / "absent.sqlite", "attention")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_local_to_dict_shape(tmp_path: Path) -> None:
    """to_dict liefert das dokumentierte Output-Schema."""
    payload = search_local(_build(tmp_path), "attention", k=2, fan_out=2).to_dict()

    assert set(payload) == {"query", "seed", "neighborhood", "fan_out"}
    assert set(payload["seed"]) == {
        "paper_id",
        "section_title",
        "page_number",
        "page_end",
        "chunk_id",
        "score",
        "source_uri",
        "snippet",
    }
    assert set(payload["fan_out"][0]) == {"paper_id", "weight", "citation"}
