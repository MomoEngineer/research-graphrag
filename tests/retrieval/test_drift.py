"""Tests für DRIFT Search (Community-Vereinigung + Basic-Fallback, Phase 4 / V2)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph, load_communities
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.drift import DEFAULT_COMMUNITIES, DriftSearchResult, search_drift
from research_graphrag.retrieval.global_search import rank_communities

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
_ORPHAN_TERM = "zzfallbackterm"
"""Term, der im Chunk-Text steht, aber **nicht** im Community-Dokument landet.

Die Community-Keywords sind auf die zehn bestbewerteten Terme begrenzt (Tie-Break alphabetisch),
und die Summary ist der Auszug des **ersten** Chunks. Der Term steht deshalb im zweiten Chunk und
sortiert hinter zehn gleichwertigen Begriffen – dadurch scort keine Community darauf.
"""


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


def _orphan_paper() -> CanonicalPaper:
    """Ein thematisch isoliertes Paper (eigene Community) mit dem Fallback-Term im 2. Chunk."""
    return _paper(
        "cccc0001",
        [
            "alpha bravo charlie delta echo foxtrot golf hotel india juliett",
            f"kilo lima mike november {_ORPHAN_TERM}",
        ],
    )


def _build(tmp_path: Path, *, graph: bool = True, orphan: bool = False) -> Path:
    db = tmp_path / "index" / "index.sqlite"
    papers = _two_cluster_papers()
    if orphan:
        papers.append(_orphan_paper())
    build_index(papers, db)
    if graph:
        build_graph(papers, db)
    return db


def test_drift_returns_communities_and_local_citations(tmp_path: Path) -> None:
    """DRIFT wählt passende Communities und verfeinert innerhalb ihrer Mitglieder."""
    db = _build(tmp_path)
    result = search_drift(db, "transformer attention encoder", k=6)

    assert isinstance(result, DriftSearchResult)
    assert result.communities
    assert result.fallback is False
    assert result.citations

    members = {
        paper_id
        for community in load_communities(db)
        if community.community_id in {match.community_id for match in result.communities}
        for paper_id in community.members
    }
    assert {citation.paper_id for citation in result.citations} <= members


def test_drift_communities_match_the_global_ranking(tmp_path: Path) -> None:
    """Die gewählten Communities sind exakt die Top-n des Global-Rankings."""
    db = _build(tmp_path)
    expected = [
        community.community_id
        for community, _score in rank_communities(db, "attention transformer", 3)
    ]

    result = search_drift(db, "attention transformer", k=4, communities=3)

    assert [match.community_id for match in result.communities] == expected


def test_drift_uses_five_communities_by_default(tmp_path: Path) -> None:
    """Ohne Angabe berücksichtigt DRIFT DEFAULT_COMMUNITIES Communities (ADR 0022)."""
    assert DEFAULT_COMMUNITIES == 5

    db = _build(tmp_path)
    result = search_drift(db, "attention transformer clustering communities", k=4)

    assert 1 < len(result.communities) <= DEFAULT_COMMUNITIES


def test_drift_with_one_community_stays_within_the_best_one(tmp_path: Path) -> None:
    """Mit communities=1 ist das Verhalten von vor V2 exakt reproduzierbar."""
    db = _build(tmp_path)
    result = search_drift(db, "transformer attention encoder", k=6, communities=1)

    assert len(result.communities) == 1
    best = next(
        community
        for community in load_communities(db)
        if community.community_id == result.communities[0].community_id
    )
    assert {citation.paper_id for citation in result.citations} <= set(best.members)


def test_drift_falls_back_to_the_corpus_search(tmp_path: Path) -> None:
    """Ohne passende Community liefert DRIFT die Belege der Basic-Suche – sichtbar."""
    db = _build(tmp_path, orphan=True)

    result = search_drift(db, _ORPHAN_TERM, k=4)

    assert result.communities == ()
    assert result.fallback is True
    assert result.citations
    expected = search_basic(db, _ORPHAN_TERM, 4)
    assert [citation.chunk_id for citation in result.citations] == [
        citation.chunk_id for citation in expected.citations
    ]


def test_drift_without_any_match_returns_no_citations(tmp_path: Path) -> None:
    """Findet auch die Basic-Suche nichts, bleibt das Ergebnis leer – aber ausgewiesen."""
    result = search_drift(_build(tmp_path), "banana smoothie recipe")

    assert result.communities == ()
    assert result.fallback is True
    assert result.citations == ()


def test_drift_is_deterministic(tmp_path: Path) -> None:
    """Zwei Läufe liefern dasselbe Ergebnis."""
    db = _build(tmp_path)

    first = search_drift(db, "attention transformer", k=4)
    second = search_drift(db, "attention transformer", k=4)

    assert first.to_dict() == second.to_dict()


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


@pytest.mark.parametrize("communities", [0, -1])
def test_drift_non_positive_communities_raises_invalid_input(
    tmp_path: Path, communities: int
) -> None:
    """communities <= 0 -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        search_drift(_build(tmp_path), "transformer", communities=communities)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_drift_without_graph_raises_constraint_violation(tmp_path: Path) -> None:
    """Ohne gebauten Graphen -> constraint_violation; der Fallback verdeckt das **nicht**."""
    with pytest.raises(DomainError) as excinfo:
        search_drift(_build(tmp_path, graph=False), "transformer")
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_drift_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Fehlender Index -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        search_drift(tmp_path / "absent.sqlite", "transformer")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_drift_to_dict_shape(tmp_path: Path) -> None:
    """to_dict liefert das dokumentierte Output-Schema (Spec 0.3.0)."""
    payload = search_drift(_build(tmp_path), "transformer attention", k=4).to_dict()

    assert set(payload) == {"query", "communities", "fallback", "citations"}
    assert payload["fallback"] is False
    assert set(payload["communities"][0]) == {
        "community_id",
        "score",
        "size",
        "keywords",
        "representatives",
    }
    assert set(payload["citations"][0]) == {
        "paper_id",
        "document_kind",
        "section_title",
        "page_number",
        "page_end",
        "chunk_id",
        "score",
        "score_tfidf",
        "score_bm25",
        "source_uri",
        "identifiers",
        "citation_key",
        "snippet",
    }
