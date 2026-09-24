"""Tests für die Literaturangabe eines Papers (Phase 12 / K1, ADR 0025)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote

import pytest

from research_graphrag.bibliography.model import ORIGIN_MANUAL, MetadataRecord
from research_graphrag.bibliography.store import save_records
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SECTION_KIND_BODY, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.metadata_index import build_metadata_index
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.reference import get_reference

_TITLE = "Graph Retrieval for Scientific Corpora at Scale"


def _paper(paper_id: str, title: str) -> CanonicalPaper:
    """Baut ein minimales Canonical-Paper mit einem Fließtext-Chunk."""
    body = f"{title} untersucht retrieval augmented generation im Korpus."
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{quote(title)}.pdf",
        source_sha256="0" * 64,
        n_pages=1,
        chunks=(
            Chunk(
                chunk_id=f"{paper_id}-c0001",
                paper_id=paper_id,
                page_number=1,
                text=body,
                char_count=len(body),
                section_id="s-body",
                section_title="Introduction",
            ),
        ),
        quality_flags=(),
        sections=(
            Section(
                section_id="s-body",
                title="Introduction",
                kind=SECTION_KIND_BODY,
                level=1,
                page_number=1,
                order=0,
            ),
        ),
        identifiers={},
    )


def _build(tmp_path: Path, records: Sequence[MetadataRecord] = ()) -> Path:
    """Baut Index und Metadaten-Tabelle; optionale Datensätze gelten als Handpflege."""
    papers = [_paper("aaaa0001", _TITLE)]
    db = tmp_path / "index.sqlite"
    build_index(papers, db)
    store = tmp_path / "paper_metadata.json"
    if records:
        save_records(store, records)
    build_metadata_index(papers, db, metadata_file=store if records else None)
    return db


def _complete_record() -> MetadataRecord:
    """Ein vollständiger, von Hand gepflegter Datensatz."""
    return MetadataRecord(
        paper_id="aaaa0001",
        origin=ORIGIN_MANUAL,
        title="Graph Retrieval for Scientific Corpora",
        authors=("Anna Beispiel", "Bert Muster"),
        year=2024,
        venue="Proceedings of ACL",
        doi="10.1145/abc",
        confidence="strong",
        evidence="von Hand geprüft",
    )


def test_complete_record_yields_both_styles(tmp_path: Path) -> None:
    """Ein vollständiger Datensatz liefert Harvard, APA und beide Kurzbelege."""
    result = get_reference(_build(tmp_path, [_complete_record()]), "aaaa0001")
    payload = result.to_dict()

    assert result.missing == ()
    assert result.note == ""
    assert payload["reference"]["citable"] is True
    assert payload["reference"]["harvard"].startswith("Beispiel, A. and Muster, B. (2024)")
    assert payload["reference"]["apa"].startswith("Beispiel, A., & Muster, B. (2024)")
    assert payload["reference"]["in_text"]["apa"] == "(Beispiel & Muster, 2024)"
    assert payload["styles"] == ["harvard", "apa"]


def test_incomplete_record_is_reported_instead_of_guessed(tmp_path: Path) -> None:
    """Fehlende Pflichtfelder werden benannt, nicht ergänzt."""
    result = get_reference(_build(tmp_path), "aaaa0001")

    assert set(result.missing) == {"authors", "year"}
    assert "Autoren" in result.note
    assert "Jahr" in result.note
    assert "scripts.resolve_metadata" in result.note
    assert result.to_dict()["reference"]["citable"] is False


def test_result_to_dict_shape(tmp_path: Path) -> None:
    """Das serialisierte Ergebnis entspricht der Tool-Spezifikation."""
    payload = get_reference(_build(tmp_path, [_complete_record()]), "aaaa0001").to_dict()

    assert set(payload) == {"paper_id", "source_uri", "styles", "reference", "missing", "note"}
    assert set(payload["reference"]) == {
        "paper_id",
        "title",
        "authors",
        "year",
        "venue",
        "doi",
        "arxiv_id",
        "url",
        "identifiers",
        "citation_key",
        "origins",
        "confidence",
        "citable",
        "author_identities",
        "review",
        "harvard",
        "apa",
        "in_text",
    }


def test_index_without_metadata_table_stays_usable(tmp_path: Path) -> None:
    """Ohne Teilschema liefert das Werkzeug einen leeren Datensatz statt eines Fehlers."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("aaaa0001", _TITLE)], db)

    result = get_reference(db, "aaaa0001")

    assert result.metadata.title == ""
    assert result.missing == ("title", "authors", "year")


def test_empty_paper_id_is_invalid_input(tmp_path: Path) -> None:
    """Eine leere Paper-ID ist ein Eingabefehler (vor jedem Index-Zugriff geprüft)."""
    with pytest.raises(DomainError) as excinfo:
        get_reference(_build(tmp_path), "   ")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_unknown_paper_and_missing_index_yield_not_found(tmp_path: Path) -> None:
    """Unbekannte ID und fehlende Index-Datei melden beide ``not_found``."""
    db = _build(tmp_path)

    with pytest.raises(DomainError) as unknown:
        get_reference(db, "gibtesnicht")
    with pytest.raises(DomainError) as missing:
        get_reference(tmp_path / "fehlt.sqlite", "aaaa0001")

    assert unknown.value.code is ErrorCode.NOT_FOUND
    assert missing.value.code is ErrorCode.NOT_FOUND
