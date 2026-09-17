"""Tests für get_paper_file (lokaler PDF-Pfad eines Papers, ADR 0039)."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import DOCUMENT_KIND_FULL, DOCUMENT_KIND_REFERENCE
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.paper_file import (
    REASON_FILE_MISSING,
    REASON_REFERENCE_ONLY,
    PaperFileResult,
    _path_from_file_uri,
    get_paper_file,
)


def _full_paper(paper_id: str, source_uri: str) -> CanonicalPaper:
    chunk = Chunk(
        chunk_id=f"{paper_id}-c0000",
        paper_id=paper_id,
        page_number=1,
        text="attention mechanism transformer overview",
        char_count=40,
        section_title="Introduction",
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=source_uri,
        source_sha256="0" * 64,
        n_pages=1,
        chunks=(chunk,),
        quality_flags=(),
        document_kind=DOCUMENT_KIND_FULL,
    )


def _reference_paper(paper_id: str, source_uri: str) -> CanonicalPaper:
    chunk = Chunk(
        chunk_id=f"{paper_id}-c0000",
        paper_id=paper_id,
        page_number=0,
        text="Abstract only",
        char_count=13,
        section_title="Abstract",
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=source_uri,
        source_sha256="0" * 64,
        n_pages=0,
        chunks=(chunk,),
        quality_flags=(),
        document_kind=DOCUMENT_KIND_REFERENCE,
    )


def test_available_pdf_returns_native_path_and_size(tmp_path: Path) -> None:
    """Ein vorhandenes PDF liefert available=true, den nativen Pfad und die Dateigröße."""
    pdf = tmp_path / "Beispiel Paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test content")

    db = tmp_path / "index" / "index.sqlite"
    build_index([_full_paper("aaaa1111", pdf.resolve().as_uri())], db)

    result = get_paper_file(db, "aaaa1111")

    assert isinstance(result, PaperFileResult)
    assert result.document_kind == DOCUMENT_KIND_FULL
    assert result.available is True
    assert Path(result.path) == pdf.resolve()
    assert result.size_bytes == pdf.stat().st_size
    assert result.reason == ""
    assert result.note == ""


def test_reference_entry_is_unavailable_but_not_an_error(tmp_path: Path) -> None:
    """Ein Referenz-Eintrag ohne Volltext liefert available=false, keinen Fehler."""
    db = tmp_path / "index" / "index.sqlite"
    build_index([_reference_paper("bbbb2222", "file:///bbbb2222.refjson")], db)

    result = get_paper_file(db, "bbbb2222")

    assert result.document_kind == DOCUMENT_KIND_REFERENCE
    assert result.available is False
    assert result.path == ""
    assert result.reason == REASON_REFERENCE_ONLY
    assert "ohne Volltext" in result.note


def test_full_paper_with_missing_local_file_is_unavailable_not_an_error(tmp_path: Path) -> None:
    """Ein im Index verzeichnetes, lokal aber fehlendes PDF ist kein Fehler."""
    missing_uri = (tmp_path / "verschwunden.pdf").resolve().as_uri()
    db = tmp_path / "index" / "index.sqlite"
    build_index([_full_paper("cccc3333", missing_uri)], db)

    result = get_paper_file(db, "cccc3333")

    assert result.document_kind == DOCUMENT_KIND_FULL
    assert result.available is False
    assert result.path == ""
    assert result.reason == REASON_FILE_MISSING
    assert result.source_uri == missing_uri


def test_to_dict_shape(tmp_path: Path) -> None:
    """to_dict liefert das dokumentierte Output-Schema."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    db = tmp_path / "index" / "index.sqlite"
    build_index([_full_paper("aaaa1111", pdf.resolve().as_uri())], db)

    payload = get_paper_file(db, "aaaa1111").to_dict()

    assert set(payload) == {
        "paper_id",
        "document_kind",
        "available",
        "path",
        "source_uri",
        "size_bytes",
        "reason",
        "note",
    }


def test_empty_paper_id_raises_invalid_input(tmp_path: Path) -> None:
    """Eine leere paper_id wird vor dem Index-Zugriff abgewiesen."""
    with pytest.raises(DomainError) as excinfo:
        get_paper_file(tmp_path / "any.sqlite", "   ")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Eine fehlende Index-Datei wird als not_found gemeldet."""
    with pytest.raises(DomainError) as excinfo:
        get_paper_file(tmp_path / "absent.sqlite", "aaaa1111")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_available_pdf_with_unicode_and_special_characters_in_filename(tmp_path: Path) -> None:
    """Reale Paper-Titel enthalten Unicode, Leer- und Sonderzeichen – der Pfad bleibt exakt."""
    pdf = tmp_path / "$Σ$-Mem – Über Sätze & (Klammern) [Test].pdf"
    pdf.write_bytes(b"%PDF-1.4 test content")

    db = tmp_path / "index" / "index.sqlite"
    build_index([_full_paper("dddd4444", pdf.resolve().as_uri())], db)

    result = get_paper_file(db, "dddd4444")

    assert result.available is True
    assert Path(result.path) == pdf.resolve()


def test_non_file_scheme_uri_is_treated_as_unavailable(tmp_path: Path) -> None:
    """Eine source_uri ohne file://-Schema (theoretisch) ist kein Absturz, sondern file_missing."""
    db = tmp_path / "index" / "index.sqlite"
    build_index([_full_paper("eeee5555", "https://example.org/not-a-local-file.pdf")], db)

    result = get_paper_file(db, "eeee5555")

    assert result.available is False
    assert result.reason == REASON_FILE_MISSING


def test_path_from_file_uri_handles_windows_drive_paths() -> None:
    """Lokale Laufwerkspfade (file:///C:/…) werden korrekt in native Pfade übersetzt."""
    path = _path_from_file_uri("file:///C:/Users/moritz/papers/Beispiel%20Paper.pdf")
    assert path is not None
    assert str(path) == r"C:\Users\moritz\papers\Beispiel Paper.pdf"


def test_path_from_file_uri_handles_unc_shares() -> None:
    """UNC-Freigaben (file://host/share/…) werden zu \\\\host\\share\\… aufgelöst."""
    path = _path_from_file_uri("file://fileserver/papers/Beispiel.pdf")
    assert path is not None
    assert str(path) == r"\\fileserver\papers\Beispiel.pdf"


def test_path_from_file_uri_rejects_non_file_scheme() -> None:
    """Ein anderes Schema (z. B. https) liefert None statt eines falschen Pfades."""
    assert _path_from_file_uri("https://example.org/paper.pdf") is None


def test_unknown_paper_id_raises_not_found(tmp_path: Path) -> None:
    """Eine unbekannte paper_id wird als not_found gemeldet."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    db = tmp_path / "index" / "index.sqlite"
    build_index([_full_paper("aaaa1111", pdf.resolve().as_uri())], db)

    with pytest.raises(DomainError) as excinfo:
        get_paper_file(db, "ffffffff")
    assert excinfo.value.code is ErrorCode.NOT_FOUND
