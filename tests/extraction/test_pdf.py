"""Tests für die PDF-Extraktion (AP1, Offline-Hybrid)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, extract_pdf

MakePdf = Callable[..., Path]


def test_extract_two_pages_with_provenance(make_pdf: MakePdf) -> None:
    """Ein zweiseitiges PDF ergibt zwei Seiten-Chunks mit Provenienz."""
    pdf = make_pdf(["Alpha GraphRAG retrieval method", "Beta dataset evaluation report"])

    paper = extract_pdf(pdf)

    assert paper.n_pages == 2
    assert len(paper.chunks) == 2
    assert paper.chunks[0].page_number == 1
    assert paper.chunks[1].page_number == 2
    assert "GraphRAG" in paper.chunks[0].text
    assert "dataset" in paper.chunks[1].text
    assert paper.chunks[0].chunk_id == f"{paper.paper_id}-c0000"
    assert paper.chunks[1].chunk_id == f"{paper.paper_id}-c0001"
    assert len(paper.source_sha256) == 64
    assert len(paper.paper_id) == 16
    assert paper.source_uri.startswith("file:")


def test_paper_id_is_deterministic(make_pdf: MakePdf) -> None:
    """Gleiche Bytes ergeben dieselbe paper_id (Datei-Hash)."""
    pdf = make_pdf(["Stable content for hashing"])
    assert extract_pdf(pdf).paper_id == extract_pdf(pdf).paper_id


def test_empty_page_sets_quality_flag(make_pdf: MakePdf) -> None:
    """Eine textlose Seite wird als quality-flag markiert und erzeugt keinen Chunk."""
    pdf = make_pdf(["Gamma content present", ""])

    paper = extract_pdf(pdf)

    assert "empty_page:2" in paper.quality_flags
    assert len(paper.chunks) == 1
    assert paper.chunks[0].page_number == 1


def test_roundtrip_canonical_json(make_pdf: MakePdf, tmp_path: Path) -> None:
    """save_json/load_json ist verlustfrei."""
    paper = extract_pdf(make_pdf(["Delta roundtrip page one", "Epsilon page two"]))
    out = tmp_path / "canonical" / f"{paper.paper_id}.json"

    paper.save_json(out)
    loaded = CanonicalPaper.load_json(out)

    assert loaded == paper


def test_empty_path_raises_invalid_input() -> None:
    """Ein leerer Pfad liefert invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        extract_pdf("   ")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_missing_file_raises_not_found(tmp_path: Path) -> None:
    """Ein fehlender Pfad liefert not_found."""
    with pytest.raises(DomainError) as excinfo:
        extract_pdf(tmp_path / "does_not_exist.pdf")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_non_pdf_raises_parse_error(tmp_path: Path) -> None:
    """Eine leere/kaputte Datei liefert parse_error."""
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"")
    with pytest.raises(DomainError) as excinfo:
        extract_pdf(broken)
    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_extract_respects_explicit_source_uri(make_pdf: MakePdf) -> None:
    """Eine explizite source_uri wird in die Provenienz übernommen."""
    paper = extract_pdf(make_pdf(["content"]), source_uri="file:///custom/uri.pdf")
    assert paper.source_uri == "file:///custom/uri.pdf"


def test_os_read_error_raises_internal_error(
    make_pdf: MakePdf, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ein OS-Lesefehler beim Einlesen wird als internal_error gemeldet."""
    pdf = make_pdf(["content"])

    def _boom(self: Path) -> bytes:
        raise OSError("read failed")

    monkeypatch.setattr(Path, "read_bytes", _boom)
    with pytest.raises(DomainError) as excinfo:
        extract_pdf(pdf)
    assert excinfo.value.code is ErrorCode.INTERNAL_ERROR


def test_extract_detects_doi_and_arxiv(make_pdf: MakePdf) -> None:
    """DOI und arXiv-ID werden aus dem Text als Identifikatoren erkannt."""
    pdf = make_pdf(["Reference 10.1145/3696410.3714748 and arXiv:2405.20455 here."])

    paper = extract_pdf(pdf)

    assert paper.identifiers.get("doi") == "10.1145/3696410.3714748"
    assert paper.identifiers.get("arxiv") == "2405.20455"


def test_extract_identifier_falls_back_to_body(make_pdf: MakePdf) -> None:
    """Fehlt die ID auf der Titelseite, wird der Volltext herangezogen."""
    pdf = make_pdf(["title page without id", "second page", "body cites arXiv:2405.20455 here"])

    paper = extract_pdf(pdf)

    assert paper.identifiers.get("arxiv") == "2405.20455"


def test_extract_always_has_front_section(make_pdf: MakePdf) -> None:
    """Ohne erkennbare Überschrift bildet der Text einen front-Abschnitt."""
    paper = extract_pdf(make_pdf(["plain body text without any headings here"]))

    assert paper.sections
    assert paper.chunks[0].section_id == paper.sections[0].section_id


def test_extract_schema_version_is_current(make_pdf: MakePdf) -> None:
    """Das Canonical JSON trägt die aktuelle Schema-Version 0.2.0."""
    paper = extract_pdf(make_pdf(["content"]))
    assert paper.to_dict()["schema_version"] == "0.2.0"
