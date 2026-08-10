"""Tests für Local Search (Multi-Seed, Chunk-Nachbarschaft + Paper-Fan-out, Phase 4 / V1)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph, load_neighbors
from research_graphrag.indexing.tfidf_index import TfidfIndex, build_index
from research_graphrag.retrieval.local import DEFAULT_SEEDS, LocalSearchResult, search_local


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
    """Vier stark überlappende Paper -> Graph-Kanten; aaaa0001 trägt einen distinktiven Term."""
    return [
        _paper(
            "aaaa0001",
            [
                "transformer attention reconciliation unique term",
                "multi head attention transformer",
                "attention transformer training objective",
            ],
            "Methoden",
        ),
        _paper(
            "aaaa0002",
            [
                "transformer attention encoder heads",
                "attention transformer architecture layers",
                "encoder attention transformer blocks",
            ],
        ),
        _paper(
            "aaaa0003",
            [
                "attention transformer decoder heads",
                "transformer attention positional encoding",
                "decoder attention transformer stack",
            ],
        ),
        _paper(
            "aaaa0004",
            [
                "transformer attention pretraining corpus",
                "attention transformer fine tuning",
                "transformer attention evaluation setup",
            ],
        ),
    ]


def _build(tmp_path: Path, *, graph: bool = True) -> Path:
    db = tmp_path / "index" / "index.sqlite"
    papers = _linked_papers()
    build_index(papers, db)
    if graph:
        build_graph(papers, db)
    return db


def test_local_returns_seeds_neighborhood_and_fanout(tmp_path: Path) -> None:
    """Local liefert Seeds, Chunk-Nachbarschaft und einen belegten Paper-Fan-out."""
    result = search_local(_build(tmp_path), "attention", k=3, fan_out=3)

    assert isinstance(result, LocalSearchResult)
    assert len(result.seeds) >= 1
    assert all(citation.paper_id.startswith("aaaa") for citation in result.seeds)
    assert len(result.neighborhood) >= 1
    assert len(result.fan_out) >= 1
    assert result.fan_out[0].weight > 0.0
    assert result.fan_out[0].citation is not None


def test_local_first_seed_carries_section_provenance(tmp_path: Path) -> None:
    """Ein distinktiver Term führt deterministisch zum Anker-Paper inkl. Abschnitt."""
    result = search_local(_build(tmp_path), "reconciliation", k=2, fan_out=0)

    assert result.seeds[0].paper_id == "aaaa0001"
    assert result.seeds[0].section_title == "Methoden"


def test_local_seeds_are_the_top_hits_of_the_scoring(tmp_path: Path) -> None:
    """Die Seeds sind exakt die Top-m der Chunk-Wertung, in deren Reihenfolge."""
    db = _build(tmp_path)
    expected = [hit.chunk_id for hit in TfidfIndex.load(db).search("attention transformer", 3)]

    result = search_local(db, "attention transformer", k=3, fan_out=0, seeds=3)

    assert [citation.chunk_id for citation in result.seeds] == expected


def test_local_uses_five_seeds_by_default(tmp_path: Path) -> None:
    """Ohne Angabe verankert Local an DEFAULT_SEEDS Chunks (ADR 0021)."""
    result = search_local(_build(tmp_path), "attention transformer", k=2, fan_out=0)

    assert DEFAULT_SEEDS == 5
    assert len(result.seeds) == DEFAULT_SEEDS


def test_local_with_one_seed_reproduces_the_plain_chunk_neighborhood(tmp_path: Path) -> None:
    """Mit seeds=1 ist die Nachbarschaft identisch zur reinen Chunk-Nachbarschaft.

    Das ist der Rückwärts-Anker der Umstellung: Die Rang-Fusion über **eine** Teilrangliste
    erhält deren Reihenfolge, damit bleibt das Verhalten vor V1 exakt reproduzierbar. Nur der
    ``score`` ist jetzt der Fusionswert – der Kosinus bleibt in ``score_tfidf``.
    """
    db = _build(tmp_path)
    index = TfidfIndex.load(db)
    seed = index.search("attention transformer", 1)[0]
    expected = index.neighbors_of_chunk(seed.chunk_id, 3)

    result = search_local(db, "attention transformer", k=3, fan_out=0, seeds=1)

    assert [c.chunk_id for c in result.neighborhood] == [hit.chunk_id for hit in expected]
    assert [c.score_tfidf for c in result.neighborhood] == [hit.score for hit in expected]


def test_local_neighborhood_score_follows_the_order(tmp_path: Path) -> None:
    """Der ausgewiesene Score ist der Fusionswert und fällt daher monoton (ADR 0014)."""
    result = search_local(_build(tmp_path), "attention transformer", k=4, fan_out=0, seeds=3)

    scores = [citation.score for citation in result.neighborhood]
    assert scores == sorted(scores, reverse=True)
    assert all(citation.score_bm25 == 0.0 for citation in result.neighborhood)


def test_local_neighborhood_excludes_the_seed_chunks(tmp_path: Path) -> None:
    """Ein Chunk erscheint nie doppelt: Seeds sind aus der Nachbarschaft ausgeschlossen."""
    result = search_local(_build(tmp_path), "attention transformer", k=5, fan_out=0, seeds=4)

    seed_ids = {citation.chunk_id for citation in result.seeds}
    neighbor_ids = [citation.chunk_id for citation in result.neighborhood]

    assert seed_ids
    assert not seed_ids & set(neighbor_ids)
    assert len(neighbor_ids) == len(set(neighbor_ids))


def test_local_neighborhood_is_capped_at_k_across_all_seeds(tmp_path: Path) -> None:
    """k begrenzt die gesamte Nachbarschaft, nicht die je Seed."""
    result = search_local(_build(tmp_path), "attention transformer", k=2, fan_out=0, seeds=4)

    assert len(result.neighborhood) <= 2


def test_local_neighborhood_comes_from_the_seed_neighborhoods(tmp_path: Path) -> None:
    """Jeder Nachbar stammt aus der Nachbarschaft mindestens eines Seeds."""
    db = _build(tmp_path)
    index = TfidfIndex.load(db)
    result = search_local(db, "attention transformer", k=4, fan_out=0, seeds=3)

    allowed: set[str] = set()
    for seed in result.seeds:
        allowed.update(hit.chunk_id for hit in index.neighbors_of_chunk(seed.chunk_id, 4))

    assert {citation.chunk_id for citation in result.neighborhood} <= allowed


def test_local_fanout_follows_the_first_seed(tmp_path: Path) -> None:
    """Der Fan-out ist am Ankerpaper (Paper des ersten Seeds) verankert."""
    db = _build(tmp_path)
    result = search_local(db, "attention transformer", k=2, fan_out=2, seeds=3)

    anchor = result.seeds[0].paper_id
    expected = [paper_id for paper_id, _weight in load_neighbors(db, anchor)[:2]]

    assert [neighbor.paper_id for neighbor in result.fan_out] == expected


def test_local_is_deterministic(tmp_path: Path) -> None:
    """Zwei Läufe liefern dasselbe Ergebnis (Tie-Break über chunk_id)."""
    db = _build(tmp_path)

    first = search_local(db, "attention transformer", k=3, fan_out=2, seeds=3)
    second = search_local(db, "attention transformer", k=3, fan_out=2, seeds=3)

    assert first.to_dict() == second.to_dict()


def test_local_fanout_zero_needs_no_graph(tmp_path: Path) -> None:
    """Mit fan_out=0 funktioniert Local ohne gebauten Graphen."""
    result = search_local(_build(tmp_path, graph=False), "attention", k=2, fan_out=0)

    assert result.seeds
    assert result.fan_out == ()


def test_local_fanout_without_graph_raises_constraint_violation(tmp_path: Path) -> None:
    """Fan-out ohne gebauten Graphen -> constraint_violation."""
    with pytest.raises(DomainError) as excinfo:
        search_local(_build(tmp_path, graph=False), "attention", k=2, fan_out=2)
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_local_no_match_returns_no_seeds(tmp_path: Path) -> None:
    """Ohne Vokabular-Überschneidung gibt es keine Seeds."""
    result = search_local(_build(tmp_path), "banana smoothie", k=3, fan_out=3)

    assert result.seeds == ()
    assert result.neighborhood == ()
    assert result.fan_out == ()


def test_local_negative_fanout_raises_invalid_input(tmp_path: Path) -> None:
    """fan_out < 0 -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        search_local(_build(tmp_path), "attention", fan_out=-1)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


@pytest.mark.parametrize("seeds", [0, -1])
def test_local_non_positive_seeds_raises_invalid_input(tmp_path: Path, seeds: int) -> None:
    """seeds <= 0 -> invalid_input (vor dem Index geprüft)."""
    with pytest.raises(DomainError) as excinfo:
        search_local(_build(tmp_path), "attention", seeds=seeds)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_local_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Fehlender Index -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        search_local(tmp_path / "absent.sqlite", "attention")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_local_to_dict_shape(tmp_path: Path) -> None:
    """to_dict liefert das dokumentierte Output-Schema (Spec 0.3.0)."""
    payload = search_local(_build(tmp_path), "attention", k=2, fan_out=2).to_dict()

    assert set(payload) == {"query", "seeds", "neighborhood", "fan_out"}
    assert set(payload["seeds"][0]) == {
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
    assert set(payload["fan_out"][0]) == {"paper_id", "weight", "citation"}
