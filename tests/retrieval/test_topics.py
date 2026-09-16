"""Tests für list_topics: gefilterte Community-Übersicht + Einzelabruf (ADR 0037)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.retrieval.topics import (
    DEFAULT_LIMIT,
    DEFAULT_MIN_SIZE,
    TopicsOverview,
    get_topic,
    list_topics,
)

# Zwei Zwei-Paper-Cluster (disjunktes Vokabular) plus ein isoliertes Singleton-Paper.
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
_SINGLETON = {"cccc0001": ["quantum entangled photon polarization experiment isolated"]}


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


def _papers_with_singleton() -> list[CanonicalPaper]:
    papers = [_paper(pid, texts) for pid, texts in _CLUSTER_TRANSFORMER.items()]
    papers += [_paper(pid, texts) for pid, texts in _CLUSTER_CITATION.items()]
    papers += [_paper(pid, texts) for pid, texts in _SINGLETON.items()]
    return papers


def _build(tmp_path: Path) -> Path:
    db = tmp_path / "index" / "index.sqlite"
    build_graph(_papers_with_singleton(), db)
    return db


def test_default_excludes_singleton_communities(tmp_path: Path) -> None:
    """Mit DEFAULT_MIN_SIZE (2) fällt die Singleton-Community aus der Übersicht."""
    overview = list_topics(_build(tmp_path))

    assert DEFAULT_MIN_SIZE == 2
    assert isinstance(overview, TopicsOverview)
    assert overview.total_matching == 2
    assert all(topic.size >= 2 for topic in overview.topics)
    assert overview.truncated is False


def test_min_size_one_includes_the_singleton(tmp_path: Path) -> None:
    """min_size=1 lässt auch die Singleton-Community durch."""
    overview = list_topics(_build(tmp_path), min_size=1)

    assert overview.total_matching == 3
    assert any(topic.size == 1 for topic in overview.topics)


def test_topics_are_sorted_by_size_descending_with_community_id_tiebreak(tmp_path: Path) -> None:
    """Sortierung: absteigend nach Größe, bei Gleichstand aufsteigend nach community_id."""
    overview = list_topics(_build(tmp_path), min_size=1)

    sizes = [topic.size for topic in overview.topics]
    assert sizes == sorted(sizes, reverse=True)
    same_size_ids = [topic.community_id for topic in overview.topics if topic.size == 2]
    assert same_size_ids == sorted(same_size_ids)


def test_limit_caps_the_overview_and_flags_truncation(tmp_path: Path) -> None:
    """limit deckelt die Trefferzahl und setzt truncated, wenn etwas abgeschnitten wurde."""
    overview = list_topics(_build(tmp_path), min_size=1, limit=1)

    assert len(overview.topics) == 1
    assert overview.total_matching == 3
    assert overview.truncated is True


def test_limit_covering_everything_is_not_truncated(tmp_path: Path) -> None:
    """Deckt limit alle passenden Communities ab, bleibt truncated falsch."""
    overview = list_topics(_build(tmp_path), min_size=1, limit=DEFAULT_LIMIT)

    assert overview.truncated is False
    assert len(overview.topics) == overview.total_matching


def test_topic_summary_to_dict_has_no_members_field(tmp_path: Path) -> None:
    """Die Übersicht enthält bewusst keine volle Mitgliederliste (ADR 0037)."""
    overview = list_topics(_build(tmp_path))

    payload = overview.topics[0].to_dict()
    assert set(payload) == {"community_id", "size", "keywords", "summary", "representatives"}
    assert "members" not in payload


def test_overview_to_dict_shape(tmp_path: Path) -> None:
    """Das serialisierte Ergebnis entspricht dem Output-Schema der Tool-Spezifikation."""
    payload = list_topics(_build(tmp_path)).to_dict()

    assert set(payload) == {"topics", "total_matching", "truncated"}


@pytest.mark.parametrize("min_size", [0, -1])
def test_min_size_below_one_raises_invalid_input(tmp_path: Path, min_size: int) -> None:
    """min_size < 1 -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        list_topics(_build(tmp_path), min_size=min_size)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


@pytest.mark.parametrize("limit", [0, -1, 51])
def test_limit_out_of_range_raises_invalid_input(tmp_path: Path, limit: int) -> None:
    """limit <= 0 oder limit > MAX_RESULT_COUNT -> invalid_input (ADR 0037)."""
    with pytest.raises(DomainError) as excinfo:
        list_topics(_build(tmp_path), limit=limit)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_list_topics_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Fehlender Index -> not_found (geerbt aus load_communities)."""
    with pytest.raises(DomainError) as excinfo:
        list_topics(tmp_path / "absent.sqlite")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_get_topic_returns_full_detail_with_members(tmp_path: Path) -> None:
    """get_topic liefert genau eine Community inklusive voller Mitgliederliste."""
    db = _build(tmp_path)
    overview = list_topics(db, min_size=1)
    target = overview.topics[0]

    detail = get_topic(db, target.community_id)

    assert detail.community_id == target.community_id
    assert detail.size == target.size
    assert len(detail.members) == target.size
    payload = detail.to_dict()
    assert "members" in payload


def test_get_topic_unknown_id_raises_not_found(tmp_path: Path) -> None:
    """Eine unbekannte community_id -> not_found."""
    db = _build(tmp_path)
    with pytest.raises(DomainError) as excinfo:
        get_topic(db, 999_999)
    assert excinfo.value.code is ErrorCode.NOT_FOUND
