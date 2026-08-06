"""Tests für get_paper (Paper-Detailabruf aus dem Index, Phase 5, ADR 0009)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.paper import PaperDetail, get_paper


def _paper(
    paper_id: str,
    sections: Sequence[str],
    texts: Sequence[str],
    *,
    identifiers: dict[str, str] | None = None,
) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_title=section,
        )
        for index, (section, text) in enumerate(zip(sections, texts, strict=True))
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=len(texts),
        chunks=chunks,
        quality_flags=(),
        identifiers=identifiers or {},
    )


def _build(tmp_path: Path) -> Path:
    paper = _paper(
        "aaaa1111",
        ["Introduction", "Introduction", "Methods"],
        [
            "transformer attention mechanism overview",
            "more attention background context",
            "dataset evaluation and metrics",
        ],
        identifiers={"doi": "10.1145/3696410", "arxiv": "2405.20455"},
    )
    db = tmp_path / "index" / "index.sqlite"
    build_index([paper], db)
    return db


def test_get_paper_returns_metadata(tmp_path: Path) -> None:
    """get_paper liefert Quelle, Identifikatoren, Umfang und Leit-Snippet."""
    detail = get_paper(_build(tmp_path), "aaaa1111")

    assert isinstance(detail, PaperDetail)
    assert detail.paper_id == "aaaa1111"
    assert detail.source_uri == "file:///aaaa1111.pdf"
    assert detail.identifiers == {"doi": "10.1145/3696410", "arxiv": "2405.20455"}
    assert detail.n_pages == 3
    assert detail.n_chunks == 3
    assert detail.snippet


def test_get_paper_sections_are_unique_in_order(tmp_path: Path) -> None:
    """Abschnittstitel erscheinen eindeutig in Dokument-Reihenfolge."""
    detail = get_paper(_build(tmp_path), "aaaa1111")
    assert detail.sections == ("Introduction", "Methods")


def test_get_paper_to_dict_shape(tmp_path: Path) -> None:
    """to_dict liefert das dokumentierte Output-Schema."""
    payload = get_paper(_build(tmp_path), "aaaa1111").to_dict()
    assert set(payload) == {
        "paper_id",
        "source_uri",
        "identifiers",
        "n_pages",
        "n_chunks",
        "sections",
        "snippet",
        "reference",
    }


def test_get_paper_without_identifiers_is_empty_dict(tmp_path: Path) -> None:
    """Ein Paper ohne Identifikatoren liefert ein leeres identifiers-Objekt."""
    paper = _paper("bbbb2222", ["Body"], ["graph neural networks and message passing"])
    db = tmp_path / "index" / "index.sqlite"
    build_index([paper], db)

    detail = get_paper(db, "bbbb2222")
    assert detail.identifiers == {}


def test_get_paper_unknown_id_raises_not_found(tmp_path: Path) -> None:
    """Unbekannte paper_id -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        get_paper(_build(tmp_path), "ffffffff")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_get_paper_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Fehlende Index-Datei -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        get_paper(tmp_path / "absent.sqlite", "aaaa1111")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_get_paper_empty_id_raises_invalid_input(tmp_path: Path) -> None:
    """Leere paper_id wird vor dem Index-Zugriff abgewiesen -> invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        get_paper(tmp_path / "any.sqlite", "   ")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT
