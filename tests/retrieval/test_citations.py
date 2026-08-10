"""Tests für get_citations (Zitationen mit Paper-Provenienz, Phase 7 / A2, ADR 0011)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SECTION_KIND_BODY, SECTION_KIND_REFERENCES, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.citation_graph import build_citation_graph
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.citations import get_citations

_DOI = "10.1234/grag.2026"


def _paper(
    paper_id: str,
    title: str,
    *,
    identifiers: dict[str, str] | None = None,
    references: Sequence[str] = (),
) -> CanonicalPaper:
    """Baut ein Canonical-Paper mit Body- und optionalem Referenzabschnitt.

    Die eigenen Identifikatoren stehen im Text der ersten Seite – nur dann taugen sie als
    Zielschlüssel des Zitations-Matchings (ADR 0011).
    """
    own_ids = " ".join(sorted((identifiers or {}).values()))
    body = f"retrieval augmented generation study {paper_id} {own_ids}".strip()
    sections = [
        Section(
            section_id="s-body",
            title="Introduction",
            kind=SECTION_KIND_BODY,
            level=1,
            page_number=1,
            order=0,
        )
    ]
    chunks = [
        Chunk(
            chunk_id=f"{paper_id}-c0001",
            paper_id=paper_id,
            page_number=1,
            text=body,
            char_count=len(body),
            section_id="s-body",
            section_title="Introduction",
        )
    ]
    if references:
        sections.append(
            Section(
                section_id="s-refs",
                title="References",
                kind=SECTION_KIND_REFERENCES,
                level=1,
                page_number=2,
                order=1,
            )
        )
        for index, entry in enumerate(references, start=2):
            chunks.append(
                Chunk(
                    chunk_id=f"{paper_id}-c{index:04d}",
                    paper_id=paper_id,
                    page_number=2,
                    text=entry,
                    char_count=len(entry),
                    section_id="s-refs",
                    section_title="References",
                )
            )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{title}.pdf",
        source_sha256="0" * 64,
        n_pages=2 if references else 1,
        chunks=tuple(chunks),
        quality_flags=(),
        sections=tuple(sections),
        identifiers=identifiers or {},
    )


def _corpus() -> list[CanonicalPaper]:
    """Zielpaper plus zwei zitierende Paper (DOI-Match)."""
    return [
        _paper("aaaa0001", "Graph Retrieval Augmented Generation", identifiers={"doi": _DOI}),
        _paper("bbbb0001", "Benchmarking Retrieval Pipelines", references=[f"[1] doi:{_DOI}"]),
        _paper("cccc0001", "Evaluating Graph Indexes", references=[f"[1] doi:{_DOI}"]),
    ]


def _build(tmp_path: Path, corpus: list[CanonicalPaper] | None = None) -> Path:
    """Baut Index und Zitationsgraph für den (Standard-)Fixture-Korpus."""
    db = tmp_path / "index" / "index.sqlite"
    papers = _corpus() if corpus is None else corpus
    build_index(papers, db)
    build_citation_graph(papers, db)
    return db


def test_incoming_citations_carry_provenance(tmp_path: Path) -> None:
    """``cited_by`` liefert Quelle und Leit-Snippet der zitierenden Paper."""
    db = _build(tmp_path)

    result = get_citations(db, "aaaa0001")

    assert result.paper.paper_id == "aaaa0001"
    assert [link.paper.paper_id for link in result.cited_by] == ["bbbb0001", "cccc0001"]
    for link in result.cited_by:
        assert link.paper.source_uri.startswith("file:///papers/")
        assert link.paper.snippet
        assert link.method == "doi"
    assert result.cites == ()


def test_outgoing_citations_carry_provenance(tmp_path: Path) -> None:
    """``cites`` liefert das zitierte Paper mit Quelle."""
    db = _build(tmp_path)

    result = get_citations(db, "bbbb0001")

    assert [link.paper.paper_id for link in result.cites] == ["aaaa0001"]
    assert result.cites[0].paper.source_uri.endswith(".pdf")
    assert result.cited_by == ()


def test_result_to_dict_shape(tmp_path: Path) -> None:
    """Das serialisierte Ergebnis entspricht der Tool-Spezifikation."""
    db = _build(tmp_path)

    payload = get_citations(db, "aaaa0001").to_dict()

    assert set(payload) == {"paper", "cites", "cited_by"}
    assert set(payload["paper"]) == {
        "paper_id",
        "document_kind",
        "source_uri",
        "identifiers",
        "citation_key",
        "snippet",
    }
    assert set(payload["cited_by"][0]) == {
        "paper_id",
        "document_kind",
        "source_uri",
        "identifiers",
        "citation_key",
        "snippet",
        "method",
    }


def test_paper_without_citations_returns_empty_lists(tmp_path: Path) -> None:
    """Ein Paper ohne erkannte Bezüge liefert leere Listen statt eines Fehlers."""
    db = _build(
        tmp_path,
        [_paper("aaaa0001", "Graph Retrieval Augmented Generation", identifiers={"doi": _DOI})],
    )

    result = get_citations(db, "aaaa0001")

    assert result.cites == ()
    assert result.cited_by == ()


def test_is_deterministic(tmp_path: Path) -> None:
    """Wiederholte Abfragen liefern identische Ergebnisse."""
    db = _build(tmp_path)

    assert get_citations(db, "aaaa0001").to_dict() == get_citations(db, "aaaa0001").to_dict()


def test_errors_are_domain_errors(tmp_path: Path) -> None:
    """Leere ID, fehlender Index und unbekanntes Paper melden die vereinbarten Codes."""
    db = _build(tmp_path)

    with pytest.raises(DomainError) as empty:
        get_citations(db, "")
    with pytest.raises(DomainError) as missing_index:
        get_citations(tmp_path / "missing.sqlite", "aaaa0001")
    with pytest.raises(DomainError) as unknown:
        get_citations(db, "zzzz9999")

    assert empty.value.code is ErrorCode.INVALID_INPUT
    assert missing_index.value.code is ErrorCode.NOT_FOUND
    assert unknown.value.code is ErrorCode.NOT_FOUND
