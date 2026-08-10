"""Tests für den Referenz-Eintrag-Adapter (Phase 13 / R2, ADR 0030).

Geprüft werden drei Dinge getrennt: die **Formatprüfung** (die Datei kann von Hand bearbeitet
worden sein), die **Abbildung** auf das kanonische Modell und die bewusst gesetzten
Eigenschaften eines Referenz-Eintrags (ein Chunk, keine Seite, keine Referenz-Sektion).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import (
    DOCUMENT_KIND_FULL,
    DOCUMENT_KIND_REFERENCE,
    SECTION_KIND_ABSTRACT,
    SECTION_KIND_REFERENCES,
    CanonicalPaper,
)
from research_graphrag.extraction.quality import FLAG_REFERENCE_WITHOUT_ABSTRACT
from research_graphrag.extraction.refstub import (
    MAX_ABSTRACT_CHARS,
    STUB_SUFFIX,
    canonical_from_stub,
    extract_stub,
    parse_stub,
)

_TITLE = "Towards Identity Anonymization on Graphs"
_ABSTRACT = "Wir zeigen, dass k-Isomorphie eine praktikable Anonymisierung erlaubt."


def _payload(**overrides: object) -> dict[str, object]:
    """Baut den Inhalt einer Stub-Datei in der Form, die R1 schreibt."""
    payload: dict[str, object] = {
        "schema_version": "0.1.0",
        "document_kind": DOCUMENT_KIND_REFERENCE,
        "requested": "doi:10.1145/1376616.1376629",
        "title": _TITLE,
        "authors": ["Anna Beispiel", "Bert Muster"],
        "year": 2008,
        "venue": "Proceedings of SIGMOD",
        "doi": "10.1145/1376616.1376629",
        "arxiv_id": "",
        "url": "https://example.org/paper.pdf",
        "source": "OpenAlex",
        "source_url": "https://api.openalex.org/works/doi:10.1145/1376616.1376629",
        "retrieved_at": "2026-08-09T10:11:12Z",
        "note": "",
        "abstract": _ABSTRACT,
    }
    payload.update(overrides)
    return payload


def _write(tmp_path: Path, **overrides: object) -> Path:
    """Legt eine Stub-Datei ab und liefert ihren Pfad."""
    target = tmp_path / f"Ein Referenz-Eintrag{STUB_SUFFIX}"
    target.write_text(json.dumps(_payload(**overrides), ensure_ascii=False), encoding="utf-8")
    return target


# --------------------------------------------------------------------------------------
# Formatprüfung
# --------------------------------------------------------------------------------------


def test_a_wellformed_stub_is_read_completely() -> None:
    """Alle Felder der Datei kommen unverfälscht an."""
    stub = parse_stub(json.dumps(_payload()).encode())

    assert stub.title == _TITLE
    assert stub.authors == ("Anna Beispiel", "Bert Muster")
    assert stub.year == 2008
    assert stub.venue == "Proceedings of SIGMOD"
    assert stub.identifiers == {"doi": "10.1145/1376616.1376629"}
    assert stub.abstract == _ABSTRACT


@pytest.mark.parametrize(
    "raw",
    [b"{kein json", b"[1, 2]", b'"nur ein string"', b"\xff\xfe nicht utf-8"],
)
def test_an_unreadable_file_is_a_parse_error(raw: bytes) -> None:
    """Eine fremde oder defekte Datei im Eingang darf keinen Schaden anrichten."""
    with pytest.raises(DomainError) as excinfo:
        parse_stub(raw)

    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_a_foreign_document_kind_is_rejected() -> None:
    """Die Dokumentart ist die Signaturprüfung des zweiten Dokumenttyps."""
    with pytest.raises(DomainError) as excinfo:
        parse_stub(json.dumps(_payload(document_kind="full")).encode())

    assert "Dokumentart" in excinfo.value.message


def test_a_stub_without_title_is_rejected() -> None:
    """Ohne Titel wäre der Eintrag weder zitierfähig noch als Zitationsziel brauchbar."""
    with pytest.raises(DomainError) as excinfo:
        parse_stub(json.dumps(_payload(title="   ")).encode())

    assert "Titel" in excinfo.value.message


def test_foreign_values_are_cleaned_before_use() -> None:
    """Die Datei kann von Hand bearbeitet worden sein – geprüft wird trotzdem vollständig."""
    stub = parse_stub(
        json.dumps(
            _payload(
                title="Zeile eins\nZeile\u0000 zwei",
                abstract="a" * (MAX_ABSTRACT_CHARS + 100),
                authors=["Gut", 42, "", "  "],
                year="2008",
            )
        ).encode()
    )

    assert stub.title == "Zeile eins Zeile zwei"
    assert len(stub.abstract) == MAX_ABSTRACT_CHARS
    assert stub.authors == ("Gut",)
    assert stub.year == 0


# --------------------------------------------------------------------------------------
# Abbildung auf das kanonische Modell
# --------------------------------------------------------------------------------------


def test_the_stub_becomes_a_paper_with_exactly_one_chunk(tmp_path: Path) -> None:
    """Ein Referenz-Eintrag hat genau einen Chunk – Titel und Abstract."""
    paper = extract_stub(_write(tmp_path))

    assert paper.document_kind == DOCUMENT_KIND_REFERENCE
    assert len(paper.chunks) == 1
    assert paper.chunks[0].text == f"{_TITLE}\n\n{_ABSTRACT}"
    assert paper.n_pages == 0
    assert paper.identifiers == {"doi": "10.1145/1376616.1376629"}


def test_the_chunk_carries_no_page(tmp_path: Path) -> None:
    """„Seite 1" wäre eine falsche Aussage über die Herkunft."""
    chunk = extract_stub(_write(tmp_path)).chunks[0]

    assert chunk.page_number == 0
    assert chunk.page_end == 0


def test_there_is_one_abstract_section_and_no_references(tmp_path: Path) -> None:
    """Ein Stub ist Ziel von CITES-Kanten, nie deren Quelle."""
    paper = extract_stub(_write(tmp_path))

    kinds = [section.kind for section in paper.sections]
    assert kinds == [SECTION_KIND_ABSTRACT]
    assert SECTION_KIND_REFERENCES not in kinds
    assert paper.chunks[0].section_id == paper.sections[0].section_id


def test_a_missing_abstract_leaves_the_title_and_one_flag(tmp_path: Path) -> None:
    """Ohne Abstract bleibt der Titel – sonst wäre der Eintrag unauffindbar."""
    paper = extract_stub(_write(tmp_path, abstract=""))

    assert paper.chunks[0].text == _TITLE
    assert paper.quality_flags == (FLAG_REFERENCE_WITHOUT_ABSTRACT,)


def test_a_complete_stub_carries_no_flag(tmp_path: Path) -> None:
    """Die Volltext-Gates gelten hier nicht – ein vollständiger Stub ist unauffällig."""
    assert extract_stub(_write(tmp_path)).quality_flags == ()


def test_the_paper_id_is_the_file_hash(tmp_path: Path) -> None:
    """Dieselbe Regel wie bei PDFs – der Intake dedupliziert darüber."""
    path = _write(tmp_path)
    paper = extract_stub(path)

    assert paper.paper_id == paper.source_sha256[:16]
    assert paper.source_uri.startswith("file:")


def test_extraction_is_deterministic(tmp_path: Path) -> None:
    """Die Stub-Datei **ist** die eingefrorene Antwort – zweimal lesen ergibt dasselbe."""
    path = _write(tmp_path)

    assert extract_stub(path).to_dict() == extract_stub(path).to_dict()


def test_a_missing_file_is_not_found(tmp_path: Path) -> None:
    """Fehlt die Datei, gibt es einen benannten Fehler statt eines Stacktrace."""
    with pytest.raises(DomainError) as excinfo:
        extract_stub(tmp_path / "fehlt.refjson")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_an_empty_path_is_invalid_input() -> None:
    """Leerer Pfad ist ein Aufruffehler, kein Dateisystemfehler."""
    with pytest.raises(DomainError) as excinfo:
        extract_stub("  ")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


# --------------------------------------------------------------------------------------
# Schema und Rückwärtstoleranz
# --------------------------------------------------------------------------------------


def test_the_document_kind_survives_the_round_trip(tmp_path: Path) -> None:
    """Das Feld muss über Canonical JSON und Index tragen – R2 führt es genau dafür ein."""
    paper = extract_stub(_write(tmp_path))
    path = tmp_path / "canonical.json"
    paper.save_json(path)

    assert CanonicalPaper.load_json(path).document_kind == DOCUMENT_KIND_REFERENCE


def test_an_old_canonical_without_the_field_counts_as_full_text() -> None:
    """Vor Schema 0.5.0 gab es nur Volltext – ein fehlendes Feld ist eindeutig deutbar."""
    paper = CanonicalPaper.from_dict(
        {
            "paper_id": "abc123",
            "source_uri": "file:///papers/Alt.pdf",
            "source_sha256": "0" * 64,
            "n_pages": 3,
            "chunks": [],
        }
    )

    assert paper.document_kind == DOCUMENT_KIND_FULL


def test_canonical_from_stub_is_pure(tmp_path: Path) -> None:
    """Die Abbildung braucht kein Dateisystem – nur Werte."""
    stub = parse_stub(json.dumps(_payload()).encode())

    paper = canonical_from_stub(
        stub, paper_id="deadbeef", source_uri="file:///papers/X.refjson", source_sha256="f" * 64
    )

    assert paper.paper_id == "deadbeef"
    assert paper.chunks[0].chunk_id == "deadbeef-c0001"
    assert paper.sections[0].section_id == "deadbeef-s0001"
