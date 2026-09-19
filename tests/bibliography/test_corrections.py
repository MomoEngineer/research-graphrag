"""Tests für die Metadaten-Korrektur in der Herkunft ``manual`` (ADR 0039)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import pytest

import research_graphrag.bibliography.corrections as corrections_module
from research_graphrag.bibliography.corrections import (
    CLEARED_MARKER,
    EFFECTIVE_AFTER,
    LOG_NAME,
    apply_manual_correction,
)
from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    ORIGIN_MANUAL,
    ORIGIN_RESOLVED,
    MetadataRecord,
)
from research_graphrag.bibliography.store import load_records, save_records
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.tfidf_index import build_index


def _paper(paper_id: str) -> CanonicalPaper:
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
        source_uri=f"file:///{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=1,
        chunks=(chunk,),
        quality_flags=(),
    )


def _index(tmp_path: Path, paper_ids: Sequence[str] = ("aaaa1111",)) -> Path:
    db = tmp_path / "index" / "index.sqlite"
    build_index([_paper(pid) for pid in paper_ids], db)
    return db


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "metadata" / "paper_metadata.json", tmp_path / "data"


def test_correction_writes_manual_record_and_log(tmp_path: Path) -> None:
    """Eine erste Korrektur legt einen manual-Record an und protokolliert den Aufruf."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    result = apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {"doi": "10.1145/3696410"}, "laut Publisher-Seite"
    )

    assert result.applied_fields == ("doi",)
    assert result.previous == {"doi": ""}
    assert result.record.origin == ORIGIN_MANUAL
    assert result.record.doi == "10.1145/3696410"
    assert result.record.confidence == CONFIDENCE_STRONG
    assert result.record.evidence == "laut Publisher-Seite"
    assert result.log_path == data_dir / LOG_NAME

    stored = load_records(metadata_path)
    assert stored == (result.record,)

    log_text = result.log_path.read_text(encoding="utf-8")
    assert "aaaa1111" in log_text
    assert "10.1145/3696410" in log_text
    assert "laut Publisher-Seite" in log_text


def test_correction_to_dict_shape(tmp_path: Path) -> None:
    """to_dict liefert das dokumentierte Output-Schema inkl. effective_after."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    payload = apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {"venue": "ACM SIGCOMM"}, "Beleg"
    ).to_dict()

    assert set(payload) == {
        "paper_id",
        "applied_fields",
        "previous",
        "record",
        "log_path",
        "effective_after",
    }
    assert payload["effective_after"] == EFFECTIVE_AFTER == "python -m scripts.ingest"


def test_second_correction_merges_instead_of_replacing(tmp_path: Path) -> None:
    """Eine zweite Korrektur an einem anderen Feld überschreibt die erste nicht."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    apply_manual_correction(db, metadata_path, data_dir, "aaaa1111", {"doi": "10.1/x"}, "Beleg 1")
    result = apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {"venue": "ACM SIGCOMM"}, "Beleg 2"
    )

    assert result.record.doi == "10.1/x"
    assert result.record.venue == "ACM SIGCOMM"
    assert result.record.evidence == "Beleg 1; Beleg 2"
    assert result.applied_fields == ("venue",)
    assert result.previous == {"venue": ""}


def test_second_correction_of_same_field_overwrites_it(tmp_path: Path) -> None:
    """Eine erneute Korrektur desselben Feldes ersetzt den vorherigen Wert."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    apply_manual_correction(db, metadata_path, data_dir, "aaaa1111", {"doi": "alt"}, "Beleg 1")
    result = apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {"doi": "neu"}, "Beleg 2"
    )

    assert result.record.doi == "neu"
    assert result.previous == {"doi": "alt"}


def test_clear_fields_marks_a_field_as_explicitly_empty(tmp_path: Path) -> None:
    """clear_fields setzt den leeren Wert und markiert das Feld in cleared_fields (ADR 0040)."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    result = apply_manual_correction(
        db,
        metadata_path,
        data_dir,
        "aaaa1111",
        {},
        "arXiv-ID gehört zu einem im Volltext zitierten Fremdpaper",
        clear_fields=["arxiv_id"],
    )

    assert result.applied_fields == ("arxiv_id",)
    assert result.previous == {"arxiv_id": ""}
    assert result.record.arxiv_id == ""
    assert result.record.cleared_fields == frozenset({"arxiv_id"})
    assert result.record.confidence == CONFIDENCE_STRONG

    stored = load_records(metadata_path)[0]
    assert stored.cleared_fields == frozenset({"arxiv_id"})

    log_text = result.log_path.read_text(encoding="utf-8")
    assert f"`arxiv_id`: (leer) → {CLEARED_MARKER}" in log_text


def test_clearing_a_previously_set_field_overwrites_its_value(tmp_path: Path) -> None:
    """Ein zuvor gesetzter Wert wird beim Leeren durch den leeren Wert ersetzt."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {"arxiv_id": "2406.12934"}, "Beleg 1"
    )
    result = apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {}, "Beleg 2", clear_fields=["arxiv_id"]
    )

    assert result.previous == {"arxiv_id": "2406.12934"}
    assert result.record.arxiv_id == ""
    assert result.record.cleared_fields == frozenset({"arxiv_id"})


def test_setting_a_cleared_field_again_leaves_cleared_fields(tmp_path: Path) -> None:
    """Ein später tatsächlich gesetzter Wert verlässt cleared_fields wieder."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {}, "Beleg 1", clear_fields=["arxiv_id"]
    )
    result = apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {"arxiv_id": "2401.00001"}, "Beleg 2"
    )

    assert result.record.arxiv_id == "2401.00001"
    assert result.record.cleared_fields == frozenset()


def test_clear_fields_can_combine_with_setting_other_fields_in_one_call(tmp_path: Path) -> None:
    """Ein Aufruf darf gleichzeitig Felder setzen und andere explizit leeren."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    result = apply_manual_correction(
        db,
        metadata_path,
        data_dir,
        "aaaa1111",
        {"doi": "10.1145/3696410"},
        "Beleg",
        clear_fields=["arxiv_id"],
    )

    assert result.applied_fields == ("arxiv_id", "doi")
    assert result.record.doi == "10.1145/3696410"
    assert result.record.arxiv_id == ""
    assert result.record.cleared_fields == frozenset({"arxiv_id"})


def test_cleared_fields_accumulate_and_persist_across_unrelated_corrections(tmp_path: Path) -> None:
    """Ein späterer, unbeteiligter Korrektur-Aufruf verwirft cleared_fields nicht."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {}, "Beleg 1", clear_fields=["arxiv_id"]
    )
    result = apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {"venue": "ACM SIGCOMM"}, "Beleg 2"
    )

    assert result.record.venue == "ACM SIGCOMM"
    assert result.record.cleared_fields == frozenset({"arxiv_id"})


@pytest.mark.parametrize(
    ("fields", "clear_fields", "evidence"),
    [
        ({}, (), "Beleg"),
        ({"doi": "10.1/x"}, ["doi"], "Beleg"),
        ({}, ["unbekanntes_feld"], "Beleg"),
    ],
)
def test_invalid_clear_field_requests_raise_invalid_input(
    tmp_path: Path, fields: dict[str, object], clear_fields: list[str], evidence: str
) -> None:
    """Widersprüchliche oder leere clear_fields-Angaben werden vor jedem Schreiben abgelehnt."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    with pytest.raises(DomainError) as excinfo:
        apply_manual_correction(
            db, metadata_path, data_dir, "aaaa1111", fields, evidence, clear_fields=clear_fields
        )

    assert excinfo.value.code is ErrorCode.INVALID_INPUT
    assert load_records(metadata_path) == ()


def test_authors_field_round_trips_as_a_list(tmp_path: Path) -> None:
    """Eine Autorenkorrektur wird als Liste gespeichert und im Protokoll lesbar dargestellt."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    result = apply_manual_correction(
        db,
        metadata_path,
        data_dir,
        "aaaa1111",
        {"authors": ["Anna Beispiel", "Bert Muster"]},
        "laut Titelseite",
    )

    assert result.record.authors == ("Anna Beispiel", "Bert Muster")
    assert result.previous == {"authors": []}
    payload = result.to_dict()
    assert payload["record"]["authors"] == ["Anna Beispiel", "Bert Muster"]

    log_text = (data_dir / LOG_NAME).read_text(encoding="utf-8")
    assert "Anna Beispiel" in log_text
    assert "Bert Muster" in log_text


def test_log_entry_neutralizes_markdown_and_control_characters_in_values(tmp_path: Path) -> None:
    """Feldwerte/Belege aus nicht vertrauenswürdigem Text zerstören das Protokoll nicht."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)
    hostile_evidence = "Beleg mit *Markdown* [Link](javascript:alert(1)) und\nZeilenumbruch"
    hostile_venue = "## Fake-Überschrift `code` | Pipe"

    apply_manual_correction(
        db, metadata_path, data_dir, "aaaa1111", {"venue": hostile_venue}, hostile_evidence
    )

    log_text = (data_dir / LOG_NAME).read_text(encoding="utf-8")
    # Der Log bleibt ein gültiges, einzelnes Dokument: Die injizierte "## "-Überschrift steht
    # nicht am Zeilenanfang und wird deshalb nicht als eigener Markdown-Abschnitt interpretiert
    # (nur der echte, von _render_entry gesetzte Eintrags-Header zählt).
    assert len(re.findall(r"(?m)^## ", log_text)) == 1
    # Der eingebettete Zeilenumbruch im Beleg wurde zu einem Leerzeichen kollabiert (escape_markdown)
    # – sonst könnte hostiler Text eine neue Zeile und damit eine eigene "## "-Zeile erzeugen.
    beleg_line = next(line for line in log_text.splitlines() if line.startswith("- Beleg:"))
    assert "Zeilenumbruch" in beleg_line
    # Der eigentliche Inhalt bleibt (maskiert) auffindbar.
    assert "Fake" in log_text
    assert "Markdown" in log_text

    # Der live gespeicherte Record ist von der Maskierung unberührt (reines JSON, kein Markdown).
    stored = load_records(metadata_path)[0]
    assert stored.venue == hostile_venue
    assert stored.evidence == hostile_evidence


def test_correction_keeps_other_papers_and_resolved_records_untouched(tmp_path: Path) -> None:
    """Datensätze anderer Paper und andere Herkünfte bleiben unangetastet."""
    db = _index(tmp_path, paper_ids=("aaaa1111", "bbbb2222"))
    metadata_path, data_dir = _paths(tmp_path)
    save_records(
        metadata_path,
        [
            MetadataRecord(paper_id="aaaa1111", origin=ORIGIN_RESOLVED, title="Aufgelöst"),
            MetadataRecord(paper_id="bbbb2222", origin=ORIGIN_MANUAL, title="Anderes Paper"),
        ],
    )

    apply_manual_correction(db, metadata_path, data_dir, "aaaa1111", {"doi": "10.1/x"}, "Beleg")

    stored = {(r.paper_id, r.origin): r for r in load_records(metadata_path)}
    assert stored[("aaaa1111", ORIGIN_RESOLVED)].title == "Aufgelöst"
    assert stored[("bbbb2222", ORIGIN_MANUAL)].title == "Anderes Paper"
    assert stored[("aaaa1111", ORIGIN_MANUAL)].doi == "10.1/x"


def test_log_is_append_only_across_calls(tmp_path: Path) -> None:
    """Zwei Korrekturen erzeugen zwei Protokoll-Abschnitte, keiner überschreibt den anderen."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    apply_manual_correction(db, metadata_path, data_dir, "aaaa1111", {"doi": "10.1/x"}, "Beleg 1")
    apply_manual_correction(db, metadata_path, data_dir, "aaaa1111", {"venue": "ACM"}, "Beleg 2")

    log_text = (data_dir / LOG_NAME).read_text(encoding="utf-8")
    assert log_text.count("## ") == 2
    assert "Beleg 1" in log_text
    assert "Beleg 2" in log_text


@pytest.mark.parametrize(
    ("fields", "evidence"),
    [
        ({}, "Beleg"),
        ({"unbekanntes_feld": "x"}, "Beleg"),
        ({"title": "   "}, "Beleg"),
        ({"authors": []}, "Beleg"),
        ({"year": 42}, "Beleg"),
        ({"year": 3000}, "Beleg"),
        ({"doi": "10.1/x"}, ""),
        ({"doi": "10.1/x"}, "   "),
    ],
)
def test_invalid_requests_raise_invalid_input(
    tmp_path: Path, fields: dict[str, object], evidence: str
) -> None:
    """Ungültige Feldkombinationen werden vor jedem Schreibzugriff abgelehnt."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    with pytest.raises(DomainError) as excinfo:
        apply_manual_correction(db, metadata_path, data_dir, "aaaa1111", fields, evidence)

    assert excinfo.value.code is ErrorCode.INVALID_INPUT
    assert load_records(metadata_path) == ()


def test_empty_paper_id_raises_invalid_input(tmp_path: Path) -> None:
    """Eine leere paper_id wird vor dem Index-Zugriff abgewiesen."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    with pytest.raises(DomainError) as excinfo:
        apply_manual_correction(db, metadata_path, data_dir, "   ", {"doi": "x"}, "Beleg")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_unknown_paper_id_raises_not_found(tmp_path: Path) -> None:
    """Eine unbekannte paper_id wird abgelehnt, bevor etwas geschrieben wird."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    with pytest.raises(DomainError) as excinfo:
        apply_manual_correction(db, metadata_path, data_dir, "ffffffff", {"doi": "x"}, "Beleg")

    assert excinfo.value.code is ErrorCode.NOT_FOUND
    assert load_records(metadata_path) == ()


def test_missing_index_raises_not_found(tmp_path: Path) -> None:
    """Eine fehlende Index-Datei wird als not_found gemeldet."""
    metadata_path, data_dir = _paths(tmp_path)

    with pytest.raises(DomainError) as excinfo:
        apply_manual_correction(
            tmp_path / "absent.sqlite", metadata_path, data_dir, "aaaa1111", {"doi": "x"}, "Beleg"
        )

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_os_error_while_saving_metadata_is_reported_with_exception_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ein OS-Schreibfehler beim Speichern wird als internal_error **mit** Details gemeldet.

    Anders als der generische Catch-all in ``mcp_server.server._guard`` (dessen Text bewusst
    keine Details preisgibt) ist ein Schreibfehler hier ein **erwarteter** Fall – analog zum
    OS-Lesefehler in ``extraction.pdf.extract_pdf`` (ADR 0039, Nachtrag 2026-09-19).
    """
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("Zugriff verweigert (Test)")

    monkeypatch.setattr(corrections_module, "save_records", _boom)

    with pytest.raises(DomainError) as excinfo:
        apply_manual_correction(db, metadata_path, data_dir, "aaaa1111", {"doi": "x"}, "Beleg")

    assert excinfo.value.code is ErrorCode.INTERNAL_ERROR
    assert "PermissionError" in excinfo.value.message
    assert "Zugriff verweigert (Test)" in excinfo.value.message
    assert excinfo.value.details["metadata_path"] == str(metadata_path)


def test_os_error_while_writing_the_log_mentions_the_already_saved_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scheitert nur das Protokoll, bleibt der bereits gespeicherte manual-Record erkennbar."""
    db = _index(tmp_path)
    metadata_path, data_dir = _paths(tmp_path)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("Datei gesperrt (Test)")

    monkeypatch.setattr(corrections_module, "append_section", _boom)

    with pytest.raises(DomainError) as excinfo:
        apply_manual_correction(db, metadata_path, data_dir, "aaaa1111", {"doi": "x"}, "Beleg")

    assert excinfo.value.code is ErrorCode.INTERNAL_ERROR
    assert "OSError" in excinfo.value.message
    assert "Datei gesperrt (Test)" in excinfo.value.message
    assert str(metadata_path) in excinfo.value.message
    assert excinfo.value.details["log_path"] == str(data_dir / LOG_NAME)
    # Der manual-Record wurde trotz des Protokoll-Fehlers bereits gespeichert.
    stored = load_records(metadata_path)
    assert len(stored) == 1
    assert stored[0].doi == "x"
