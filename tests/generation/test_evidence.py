"""Tests für die Evidenz-Adapter der vier Retrieval-Modi (Phase 7 / A1, ADR 0012)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from research_graphrag.bibliography.model import ORIGIN_MANUAL, MetadataRecord
from research_graphrag.bibliography.store import save_records
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.generation.evidence import (
    evidence_from_basic,
    evidence_from_drift,
    evidence_from_global,
    evidence_from_local,
    references_for,
)
from research_graphrag.generation.synthesis import Evidence, EvidenceSource
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.metadata_index import build_metadata_index
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.drift import search_drift
from research_graphrag.retrieval.global_search import search_global
from research_graphrag.retrieval.local import search_local

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
_NO_MATCH = "zzzqqqwww xxyyzzq"


def _paper(paper_id: str, texts: Sequence[str]) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index + 1:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_title="Introduction" if index == 0 else "Methods",
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
    db = tmp_path / "index" / "index.sqlite"
    papers = [_paper(pid, texts) for pid, texts in _CLUSTER_TRANSFORMER.items()]
    papers += [_paper(pid, texts) for pid, texts in _CLUSTER_CITATION.items()]
    build_index(papers, db)
    build_graph(papers, db)
    store = tmp_path / "paper_metadata.json"
    save_records(
        store,
        [
            MetadataRecord(
                paper_id="aaaa0001",
                origin=ORIGIN_MANUAL,
                title="Attention Is All You Need Again",
                authors=("Anna Beispiel",),
                year=2024,
                doi="10.1145/abc",
                confidence="strong",
            )
        ],
    )
    build_metadata_index(papers, db, metadata_file=store)
    return db


def test_references_are_collected_once_per_paper_in_order_of_appearance(tmp_path: Path) -> None:
    """Jedes belegte Paper erscheint genau einmal, in der Reihenfolge seines ersten Belegs."""
    db = _build(tmp_path)
    evidence = evidence_from_basic(search_basic(db, "transformer attention", k=5))

    references = references_for(db, evidence)
    paper_ids = [reference["paper_id"] for reference in references]

    assert len(paper_ids) == len(set(paper_ids))
    assert paper_ids[0] == evidence.items[0].paper_id
    assert all("harvard" in reference and "apa" in reference for reference in references)


def test_references_use_the_resolved_metadata(tmp_path: Path) -> None:
    """Die Angabe stammt aus dem aufgelösten Datensatz, nicht aus dem Dateinamen."""
    db = _build(tmp_path)
    evidence = Evidence.build(
        "q",
        "basic",
        (EvidenceSource(paper_id="aaaa0001", label="l", snippet="s", source_uri="file:///a.pdf"),),
    )

    reference = references_for(db, evidence)[0]

    assert reference["citation_key"] == "Beispiel2024"
    assert reference["apa"].startswith("Beispiel, A. (2024). Attention Is All You Need Again.")
    assert reference["citable"] is True


def test_references_are_empty_without_evidence(tmp_path: Path) -> None:
    """Ohne Belege gibt es nichts zu zitieren – und keinen Index-Zugriff."""
    assert references_for(tmp_path / "fehlt.sqlite", Evidence.build("q", "basic", ())) == ()


def test_basic_evidence_carries_chunk_provenance(tmp_path: Path) -> None:
    """Basic-Zitate werden zu nummerierten Belegen mit Abschnitt und Seite."""
    result = search_basic(_build(tmp_path), "transformer attention", k=3)

    evidence = evidence_from_basic(result)

    assert evidence.mode == "basic"
    assert evidence.query == "transformer attention"
    assert [item.index for item in evidence.items] == list(range(1, len(result.citations) + 1))
    first = evidence.items[0]
    assert first.paper_id == result.citations[0].paper_id
    assert "Seite" in first.label
    assert "Abschnitt" in first.label
    assert first.source_uri.startswith("file:")


def test_local_evidence_covers_seed_neighborhood_and_fanout(tmp_path: Path) -> None:
    """Local liefert Seeds, Chunk-Nachbarschaft und belegte Fan-out-Nachbarn als eine Liste."""
    result = search_local(_build(tmp_path), "transformer attention", k=3)

    evidence = evidence_from_local(result)

    expected = (
        len(result.seeds)
        + len(result.neighborhood)
        + sum(1 for neighbor in result.fan_out if neighbor.citation is not None)
    )
    assert evidence.mode == "local"
    assert len(evidence.items) == expected
    assert evidence.items[0].paper_id == result.seeds[0].paper_id if result.seeds else True


def test_global_evidence_uses_community_representatives(tmp_path: Path) -> None:
    """Global-Belege sind die repräsentativen Paper und tragen den Community-Bezug."""
    result = search_global(_build(tmp_path), "community detection louvain", 3)

    evidence = evidence_from_global(result)

    assert evidence.mode == "global"
    assert evidence.items
    assert all("Community #" in item.label for item in evidence.items)
    assert evidence.items[0].paper_id == result.communities[0].representatives[0].paper_id


def test_drift_evidence_uses_local_citations(tmp_path: Path) -> None:
    """DRIFT-Belege sind die innerhalb der Community verfeinerten Chunk-Zitate."""
    result = search_drift(_build(tmp_path), "community detection louvain", k=4)

    evidence = evidence_from_drift(result)

    assert evidence.mode == "drift"
    assert len(evidence.items) == len(result.citations)


def test_empty_results_yield_empty_evidence(tmp_path: Path) -> None:
    """Ohne Treffer bleibt die Evidenz leer (statt zu scheitern)."""
    db = _build(tmp_path)

    basic = evidence_from_basic(search_basic(db, _NO_MATCH, k=3))
    local = evidence_from_local(search_local(db, _NO_MATCH, k=3))
    global_ = evidence_from_global(search_global(db, _NO_MATCH, 3))
    drift = evidence_from_drift(search_drift(db, _NO_MATCH, k=3))

    assert basic.is_empty()
    assert local.is_empty()
    assert global_.is_empty()
    assert drift.is_empty()


def test_evidence_is_deterministic(tmp_path: Path) -> None:
    """Gleiche Anfrage → identische Belege in identischer Reihenfolge."""
    db = _build(tmp_path)

    first = evidence_from_basic(search_basic(db, "transformer attention", k=3))
    second = evidence_from_basic(search_basic(db, "transformer attention", k=3))

    assert first == second
