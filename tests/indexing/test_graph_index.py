"""Tests für den Paper-Ähnlichkeitsgraphen & Louvain-Communities (Phase 3, Option B)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import (
    TOP_REPRESENTATIVES,
    CommunityView,
    _mutual_topk_edges,
    build_graph,
    load_communities,
    load_neighbors,
)
from research_graphrag.indexing.tfidf_index import build_index

# Zwei klar getrennte Themencluster (disjunktes Vokabular nach Stopwort-Entfernung).
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


def test_build_graph_detects_two_communities(tmp_path: Path) -> None:
    """Zwei disjunkte Themencluster ergeben zwei Communities mit je einer Kante."""
    db = tmp_path / "index" / "index.sqlite"

    report = build_graph(_two_cluster_papers(), db)

    assert report.n_nodes == 4
    assert report.n_edges == 2  # je Cluster genau eine Mutual-Top-k-Kante
    assert report.n_communities == 2

    communities = load_communities(db)
    assert [c.size for c in communities] == [2, 2]
    members = {member for community in communities for member in community.members}
    assert members == {"aaaa0001", "aaaa0002", "bbbb0001", "bbbb0002"}


def test_communities_carry_keywords_and_representatives(tmp_path: Path) -> None:
    """Jede Community trägt extraktive Keywords, Vertreter und einen Auszug."""
    db = tmp_path / "index.sqlite"
    build_graph(_two_cluster_papers(), db)

    communities = load_communities(db)
    for community in communities:
        assert community.keywords, "Keywords dürfen nicht leer sein."
        assert 1 <= len(community.representatives) <= TOP_REPRESENTATIVES
        assert set(community.representatives).issubset(set(community.members))
        assert community.summary, "Die extraktive Zusammenfassung darf nicht leer sein."

    transformer = next(c for c in communities if "aaaa0001" in c.members)
    assert "transformer" in transformer.keywords or "attention" in transformer.keywords


def test_build_graph_is_deterministic(tmp_path: Path) -> None:
    """Zwei unabhängige Baudurchläufe liefern identische Communities (fixer Seed)."""
    papers = _two_cluster_papers()
    first_db = tmp_path / "first.sqlite"
    second_db = tmp_path / "second.sqlite"

    first_report = build_graph(papers, first_db)
    second_report = build_graph(list(reversed(papers)), second_db)

    assert first_report == second_report
    assert load_communities(first_db) == load_communities(second_db)


def test_edges_are_undirected_and_weighted(tmp_path: Path) -> None:
    """Kanten werden ungerichtet (source < target) mit Gewicht in (0, 1] gespeichert."""
    db = tmp_path / "index.sqlite"
    build_graph(_two_cluster_papers(), db)

    connection = sqlite3.connect(str(db))
    try:
        rows = connection.execute(
            "SELECT source_paper_id, target_paper_id, weight FROM graph_edges"
        ).fetchall()
    finally:
        connection.close()

    assert rows
    for source, target, weight in rows:
        assert source < target
        assert 0.0 < weight <= 1.0 + 1e-9


def test_disjoint_papers_form_singleton_communities(tmp_path: Path) -> None:
    """Ohne Vokabular-Überschneidung entstehen kantenlose Singleton-Communities."""
    papers = [
        _paper("cccc0001", ["semantic parsing of natural language queries"]),
        _paper("dddd0002", ["hardware accelerator throughput benchmarks"]),
    ]
    db = tmp_path / "index.sqlite"

    report = build_graph(papers, db)

    assert report.n_edges == 0
    assert report.n_communities == 2
    communities = load_communities(db)
    assert all(c.size == 1 for c in communities)
    for community in communities:
        assert community.representatives == community.members
        assert community.summary


def test_single_paper_builds_one_community(tmp_path: Path) -> None:
    """Ein einzelnes Paper ergibt genau eine Community ohne Kanten."""
    db = tmp_path / "index.sqlite"

    report = build_graph([_paper("eeee0001", ["a lone paper about knowledge graphs"])], db)

    assert (report.n_nodes, report.n_edges, report.n_communities) == (1, 0, 1)


def test_build_graph_without_indexable_raises_invalid_input(tmp_path: Path) -> None:
    """Nur leere Chunks -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        build_graph([_paper("ffff0001", ["", "   "])], tmp_path / "index.sqlite")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_build_graph_skips_duplicate_paper_ids(tmp_path: Path) -> None:
    """Doppelte paper_id werden nur einmal als Knoten geführt."""
    paper = _paper("aaaa9999", ["duplicate content about attention"])
    db = tmp_path / "index.sqlite"

    report = build_graph([paper, paper], db)

    assert report.n_nodes == 1


def test_load_communities_missing_db_raises_not_found(tmp_path: Path) -> None:
    """Fehlende Index-Datei -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        load_communities(tmp_path / "absent.sqlite")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_load_communities_without_graph_raises_constraint_violation(tmp_path: Path) -> None:
    """Ein Index ohne gebauten Graphen -> constraint_violation."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("aaaa0001", ["content without a graph build"])], db)

    with pytest.raises(DomainError) as excinfo:
        load_communities(db)
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_load_communities_returns_cached_instance_when_file_unchanged(tmp_path: Path) -> None:
    """Zwei Ladevorgänge über dieselbe unveränderte Datei liefern dasselbe Objekt (Cache-Hit)."""
    db = tmp_path / "index.sqlite"
    build_graph(_two_cluster_papers(), db)

    first = load_communities(db)
    second = load_communities(db)

    assert first is second


def test_load_communities_reloads_after_graph_rebuilt_at_same_path(tmp_path: Path) -> None:
    """Ein neu gebauter Graph am selben Pfad wirkt beim nächsten Laden sofort (kein Cache-Leck)."""
    db = tmp_path / "index.sqlite"
    build_graph([_paper("aaaa0001", ["semantic parsing of natural language queries"])], db)
    first = load_communities(db)
    assert len(first) == 1

    build_graph(_two_cluster_papers(), db)
    second = load_communities(db)

    assert second is not first
    assert len(second) == 2


def test_build_graph_preserves_existing_index_tables(tmp_path: Path) -> None:
    """Der Graph-Bau schreibt additiv und lässt papers/chunks unangetastet."""
    papers = _two_cluster_papers()
    db = tmp_path / "index.sqlite"
    build_index(papers, db)

    build_graph(papers, db)

    connection = sqlite3.connect(str(db))
    try:
        n_chunks = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_nodes = connection.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
        graph_version = connection.execute(
            "SELECT value FROM meta WHERE key = 'graph_schema_version'"
        ).fetchone()[0]
    finally:
        connection.close()

    assert n_chunks == 8  # 4 Paper × 2 Chunks
    assert n_nodes == 4
    assert graph_version == "0.1.0"


def test_load_neighbors_returns_weighted_neighbor(tmp_path: Path) -> None:
    """Innerhalb eines Clusters liefert load_neighbors den Partner mit Kantengewicht."""
    db = tmp_path / "index.sqlite"
    build_graph(_two_cluster_papers(), db)

    neighbors = load_neighbors(db, "aaaa0001")

    assert neighbors == [("aaaa0002", pytest.approx(neighbors[0][1]))]
    assert 0.0 < neighbors[0][1] <= 1.0 + 1e-9


def test_load_neighbors_isolated_paper_is_empty(tmp_path: Path) -> None:
    """Ein Singleton-Paper ohne Kanten hat keine Nachbarn."""
    papers = [
        _paper("cccc0001", ["semantic parsing of natural language queries"]),
        _paper("dddd0002", ["hardware accelerator throughput benchmarks"]),
    ]
    db = tmp_path / "index.sqlite"
    build_graph(papers, db)

    assert load_neighbors(db, "cccc0001") == []


def test_load_neighbors_missing_db_raises_not_found(tmp_path: Path) -> None:
    """Fehlende Index-Datei -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        load_neighbors(tmp_path / "absent.sqlite", "aaaa0001")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_load_neighbors_without_graph_raises_constraint_violation(tmp_path: Path) -> None:
    """Ein Index ohne gebauten Graphen -> constraint_violation."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("aaaa0001", ["content without a graph build"])], db)

    with pytest.raises(DomainError) as excinfo:
        load_neighbors(db, "aaaa0001")
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_community_view_to_dict_shape() -> None:
    """CommunityView.to_dict liefert das Output-Schema von list_topics (Phase 5)."""
    view = CommunityView(
        community_id=0,
        size=2,
        keywords=("graph", "neural"),
        summary="lead snippet",
        members=("aaaa0001", "bbbb0002"),
        representatives=("aaaa0001",),
    )

    assert view.to_dict() == {
        "community_id": 0,
        "size": 2,
        "keywords": ["graph", "neural"],
        "summary": "lead snippet",
        "members": ["aaaa0001", "bbbb0002"],
        "representatives": ["aaaa0001"],
    }


# ---------------------------------------------------------------------------
# _mutual_topk_edges (Phase 15 / G1): NumPy-Vektorisierung statt Python-Liste-von-
# Listen + Kandidatentupeln. Muss fuer JEDE Aehnlichkeitsmatrix dasselbe Ergebnis
# wie die urspruengliche, rein-Python-basierte Fassung liefern (inkl. Tie-Break).
# ---------------------------------------------------------------------------


def _brute_force_mutual_topk_edges(
    paper_ids: list[str], sims: list[list[float]], k: int, min_similarity: float
) -> list[tuple[str, str, float]]:
    """Referenzimplementierung (Stand vor G1): reines Python, ohne NumPy."""
    n = len(paper_ids)
    neighbors: list[set[int]] = []
    for i in range(n):
        candidates = [
            (-sims[i][j], paper_ids[j], j)
            for j in range(n)
            if j != i and sims[i][j] >= min_similarity
        ]
        candidates.sort()
        neighbors.append({index for _neg_sim, _paper_id, index in candidates[:k]})

    edges: list[tuple[str, str, float]] = []
    for i in range(n):
        for j in neighbors[i]:
            if i < j and i in neighbors[j]:
                first, second = paper_ids[i], paper_ids[j]
                source, target = (first, second) if first < second else (second, first)
                edges.append((source, target, sims[i][j]))
    return sorted(edges)


@pytest.mark.parametrize("seed", range(30))
def test_mutual_topk_edges_matches_brute_force_on_random_matrices(seed: int) -> None:
    """Zufällige Ähnlichkeitsmatrizen (mit erzwungenen Gleichständen): kein Fall weicht ab."""
    rng = np.random.default_rng(seed)
    n = rng.integers(2, 12)
    # Wenige Nachkommastellen erzwingen haeufige Gleichstaende - genau der Fall, den der
    # Tie-Break (aufsteigende paper_id) eindeutig entscheiden muss.
    raw = rng.integers(0, 4, size=(n, n)).astype(np.float64) / 3.0
    sims = (raw + raw.T) / 2.0  # symmetrisch, wie eine Kosinus-Aehnlichkeitsmatrix
    np.fill_diagonal(sims, 1.0)
    paper_ids = [f"p{index:03d}" for index in rng.permutation(n)]
    k = int(rng.integers(1, n + 2))
    min_similarity = float(rng.choice([0.0, 0.1, 0.34, 0.5, 1.1]))

    expected = _brute_force_mutual_topk_edges(paper_ids, sims.tolist(), k, min_similarity)
    actual = _mutual_topk_edges(paper_ids, sims, k, min_similarity)

    assert actual == expected


def test_mutual_topk_edges_empty_neighborhood_when_all_below_threshold() -> None:
    """Liegt keine Ähnlichkeit über der Schwelle, entstehen keine Kanten."""
    paper_ids = ["a", "b", "c"]
    sims = np.array([[1.0, 0.05, 0.02], [0.05, 1.0, 0.03], [0.02, 0.03, 1.0]])

    assert _mutual_topk_edges(paper_ids, sims, k=8, min_similarity=0.1) == []
