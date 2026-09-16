"""Tests für Global Search (Query→Community-Ranking, Phase 4)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, TfidfIndex, build_index
from research_graphrag.retrieval.global_search import (
    MEMBER_TOP_K,
    GlobalSearchResult,
    rank_communities,
    search_global,
)

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


def test_global_ranks_matching_community_first(tmp_path: Path) -> None:
    """Eine transformer-Anfrage liefert die transformer-Community mit belegten Vertretern."""
    result = search_global(_build(tmp_path), "transformer attention encoder", n=5)

    assert isinstance(result, GlobalSearchResult)
    assert result.communities
    top = result.communities[0]
    assert top.score > 0.0
    assert set(top.keywords) & {"transformer", "attention", "encoder"}
    assert top.representatives
    rep_ids = {ref.paper_id for ref in top.representatives}
    assert rep_ids <= {"aaaa0001", "aaaa0002"}
    assert all(ref.source_uri.startswith("file:") for ref in top.representatives)


def test_global_no_match_returns_empty(tmp_path: Path) -> None:
    """Ohne Vokabular-Überschneidung gibt es keine Community-Treffer."""
    result = search_global(_build(tmp_path), "banana smoothie recipe", n=5)
    assert result.communities == ()


def test_global_empty_query_raises_invalid_input(tmp_path: Path) -> None:
    """Leere Anfrage -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        search_global(_build(tmp_path), "   ")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_global_non_positive_n_raises_invalid_input(tmp_path: Path) -> None:
    """n <= 0 -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        search_global(_build(tmp_path), "transformer", n=0)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_global_n_above_max_result_count_raises_invalid_input(tmp_path: Path) -> None:
    """n > MAX_RESULT_COUNT -> invalid_input (ADR 0037)."""
    with pytest.raises(DomainError) as excinfo:
        search_global(_build(tmp_path), "transformer", n=51)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_global_without_graph_raises_constraint_violation(tmp_path: Path) -> None:
    """Ohne gebauten Graphen (keine Communities) -> constraint_violation."""
    with pytest.raises(DomainError) as excinfo:
        search_global(_build(tmp_path, graph=False), "transformer")
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_global_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Fehlender Index -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        search_global(tmp_path / "absent.sqlite", "transformer")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


_DEEP_TERM = "zzdeepmemberterm"
"""Ein Begriff im **zweiten** Chunk eines isolierten Papers, außerhalb der Top-10-Keywords.

Das erste Chunk füllt die zehn Keyword-Plätze mit eigenen, alphabetisch früheren Begriffen; der
Begriff im zweiten Chunk landet dadurch nie in den Anzeige-Keywords oder der (aus dem ersten
Chunk gezogenen) Zusammenfassung – dasselbe Konstruktionsmuster wie ``_ORPHAN_TERM`` in
``tests/retrieval/test_drift.py``.
"""


def _paper_with_deep_term(paper_id: str) -> CanonicalPaper:
    return _paper(
        paper_id,
        [
            "alpha bravo charlie delta echo foxtrot golf hotel india juliett",
            f"kilo lima mike november {_DEEP_TERM}",
        ],
    )


def test_global_ranks_by_member_chunk_content_not_just_keywords(tmp_path: Path) -> None:
    """Ein Begriff im zweiten (Nicht-Keyword-)Chunk eines Mitglieds findet trotzdem die Community.

    Vor Phase 10 / V4 rankte Global über ein Dokument aus Top-10-Keywords + Zusammenfassung des
    ersten Chunks; ein Begriff, der nur im zweiten Chunk steht, hätte dort nie gescort. Seit V4
    aggregiert der Score aus den echten Mitglieds-Chunk-Scores (ADR 0036), daher findet die
    Anfrage die Community trotzdem.
    """
    db = tmp_path / "index" / "index.sqlite"
    papers = _two_cluster_papers() + [_paper_with_deep_term("dddd0001")]
    build_index(papers, db)
    build_graph(papers, db)

    result = search_global(db, _DEEP_TERM, n=5)

    assert result.communities
    rep_ids = {ref.paper_id for match in result.communities for ref in match.representatives}
    assert "dddd0001" in rep_ids
    # Der Begriff darf nicht in den Anzeige-Keywords stehen - sonst waere das Beispiel entwertet.
    assert all(_DEEP_TERM not in match.keywords for match in result.communities)


def test_global_score_equals_mean_of_top_member_chunk_scores(tmp_path: Path) -> None:
    """Der Community-Score ist exakt das Mittel der ``MEMBER_TOP_K`` höchsten Mitglieds-Scores."""
    db = _build(tmp_path)
    query = "transformer attention encoder"

    ranked = rank_communities(db, query, n=5)
    assert ranked

    index = TfidfIndex.load(db)
    scores_by_paper = index.score_chunks_by_paper(query, scoring=DEFAULT_SCORING)

    for community, score in ranked:
        member_scores = [
            s for paper_id in community.members for s in scores_by_paper.get(paper_id, ())
        ]
        top = sorted(member_scores, reverse=True)[:MEMBER_TOP_K]
        expected = sum(top) / len(top)
        assert score == pytest.approx(expected)


def test_global_to_dict_shape(tmp_path: Path) -> None:
    """to_dict liefert das dokumentierte Output-Schema."""
    payload = search_global(_build(tmp_path), "transformer attention", n=3).to_dict()

    assert set(payload) == {"query", "communities"}
    community = payload["communities"][0]
    assert set(community) == {"community_id", "score", "size", "keywords", "representatives"}
    assert set(community["representatives"][0]) == {
        "paper_id",
        "document_kind",
        "source_uri",
        "identifiers",
        "citation_key",
        "snippet",
    }
