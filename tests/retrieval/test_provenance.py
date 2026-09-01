"""Tests für den Provenienz-Assembler & die gemeinsamen Zitat-Typen (Phase 4)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.tfidf_index import TfidfIndex, build_index
from research_graphrag.retrieval.provenance import (
    REFERENCE_PAGE_LABEL,
    Citation,
    PaperRef,
    ProvenanceAssembler,
    page_label,
)


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


def _build(tmp_path: Path) -> Path:
    paper = _paper(
        "aaaa1111", ["transformer attention mechanism", "graph message passing"], "Methoden"
    )
    db = tmp_path / "index" / "index.sqlite"
    build_index([paper], db)
    return db


def test_citation_from_hit_carries_section_title(tmp_path: Path) -> None:
    """Ein Hit mit Section wird als Zitat inkl. Abschnitts-Provenienz abgebildet."""
    hit = TfidfIndex.load(_build(tmp_path)).search("attention", k=1)[0]
    citation = Citation.from_hit(hit)

    assert citation.section_title == "Methoden"
    assert citation.paper_id == "aaaa1111"
    assert citation.page_number == 1


def test_citation_to_dict_shape(tmp_path: Path) -> None:
    """Das Zitat-Dict trägt genau die dokumentierten Schlüssel (inkl. Seiten-Range)."""
    hit = TfidfIndex.load(_build(tmp_path)).search("attention", k=1)[0]
    payload = Citation.from_hit(hit).to_dict()

    assert set(payload) == {
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


def test_citation_page_end_defaults_to_start_page() -> None:
    """Ohne eigene Endseite fällt ``page_end`` auf die Startseite zurück."""
    citation = Citation(
        paper_id="pid",
        page_number=7,
        chunk_id="pid-c0000",
        score=0.5,
        source_uri="file:///x.pdf",
        snippet="…",
    )
    assert citation.page_end == 7


def test_page_label_renders_single_page_and_range() -> None:
    """Die Anzeigeform unterscheidet Einzelseite und Seiten-Range."""
    assert page_label(7, 7) == "Seite 7"
    assert page_label(7, 8) == "Seiten 7–8"


def test_page_label_names_a_missing_page_instead_of_inventing_one() -> None:
    """Ein Referenz-Eintrag hat keine Seite 1 – „Seite 1" wäre eine falsche Herkunftsangabe."""
    assert page_label(0, 0) == REFERENCE_PAGE_LABEL
    assert "Seite" not in REFERENCE_PAGE_LABEL.replace("ohne Seite", "")


def test_assembler_builds_paper_ref(tmp_path: Path) -> None:
    """Der Assembler liefert source_uri und ein Leit-Snippet aus dem ersten Chunk."""
    assembler = ProvenanceAssembler.load(_build(tmp_path))
    ref = assembler.paper_ref("aaaa1111")

    assert isinstance(ref, PaperRef)
    assert ref.source_uri == "file:///aaaa1111.pdf"
    assert "transformer" in ref.snippet
    assert ref.to_dict() == {
        "paper_id": "aaaa1111",
        "document_kind": "full",
        "source_uri": "file:///aaaa1111.pdf",
        "identifiers": {},
        "citation_key": "aaaa1111",
        "snippet": ref.snippet,
    }


def test_assembler_unknown_paper_raises_not_found(tmp_path: Path) -> None:
    """Ein unbekanntes Paper -> not_found."""
    assembler = ProvenanceAssembler.load(_build(tmp_path))
    with pytest.raises(DomainError) as excinfo:
        assembler.paper_ref("zzzz9999")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_assembler_truncates_long_leading_snippet(tmp_path: Path) -> None:
    """Ein langes Leit-Snippet wird auf das Limit gekürzt (endet mit Auslassung)."""
    long_text = "attention " + "lorem ipsum dolor sit amet consectetur " * 20
    db = tmp_path / "index.sqlite"
    build_index([_paper("bbbb2222", [long_text])], db)

    ref = ProvenanceAssembler.load(db).paper_ref("bbbb2222")

    assert len(ref.snippet) <= 200
    assert ref.snippet.endswith("…")


def test_assembler_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Fehlende Index-Datei -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        ProvenanceAssembler.load(tmp_path / "absent.sqlite")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_assembler_load_returns_cached_instance_when_file_unchanged(tmp_path: Path) -> None:
    """Zwei Ladevorgänge über dieselbe unveränderte Datei liefern denselben Assembler."""
    db = _build(tmp_path)

    first = ProvenanceAssembler.load(db)
    second = ProvenanceAssembler.load(db)

    assert first is second


def test_assembler_load_reloads_after_index_rebuilt_at_same_path(tmp_path: Path) -> None:
    """Ein neu gebauter Index am selben Pfad wirkt beim nächsten Laden sofort (kein Cache-Leck)."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("aaaa0001", ["alpha beta gamma content"])], db)
    first = ProvenanceAssembler.load(db)
    assert first.paper_ref("aaaa0001").source_uri == "file:///aaaa0001.pdf"

    build_index([_paper("bbbb0002", ["delta epsilon zeta content"])], db)
    second = ProvenanceAssembler.load(db)

    assert second is not first
    assert second.paper_ref("bbbb0002").source_uri == "file:///bbbb0002.pdf"
    with pytest.raises(DomainError):
        second.paper_ref("aaaa0001")
