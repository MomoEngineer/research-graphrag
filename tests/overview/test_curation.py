"""Tests für das kuratierte Relevanzurteil aus der Übersicht (Phase 15 / G4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.overview.curation import (
    SCHEMA_VERSION,
    CurationEntry,
    load_curation,
    load_curation_rows,
    migrate_from_overview,
    parse_curation_rows,
    save_curation,
)

_HEADER = (
    "| ID | Name | Themenfokus | Keyword | Kompakte Zusammenfassung | Interner Link "
    "| Relevanz fuer Expose | SRQ-Zuordnung | Externer Link/Indetifikator |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)

_TABLE = (
    _HEADER + "| A1 | Erstes Paper | Thema A | k1, k2 | Kurzfassung "
    "| [Quelle](papers/Erstes%20Paper.pdf) | Hoch (Begründung) | SRQ1, SRQ2 | doi:10.1/x |\n"
    + "| B3 | Zweites Paper | Thema B | k3 | Kurzfassung2 "
    "| [Quelle](papers/Zweites%20Paper.pdf) | Mittel | SRQ3 | |\n"
    + "| Z1 | Entwurf | Thema C | k4 | ENTWURF "
    "| [Quelle](papers/Entwurf.pdf) | (manuell) | (manuell) | |\n"
)


def test_parse_curation_rows_reads_curated_columns_verbatim() -> None:
    """Themenfokus, Relevanz und SRQ-Zuordnung werden wörtlich übernommen."""
    entries = parse_curation_rows(_TABLE)

    assert set(entries) == {"Erstes Paper.pdf", "Zweites Paper.pdf"}
    first = entries["Erstes Paper.pdf"]
    assert first.row_id == "A1"
    assert first.title == "Erstes Paper"
    assert first.themenfokus == "Thema A"
    assert first.relevanz == "Hoch (Begründung)"
    assert first.srq == ("SRQ1", "SRQ2")


def test_parse_curation_rows_skips_draft_rows() -> None:
    """Entwurfszeilen (``Z…``) zählen nicht als kuratiertes Urteil."""
    entries = parse_curation_rows(_TABLE)

    assert "Entwurf.pdf" not in entries


def test_parse_curation_rows_without_header_is_empty() -> None:
    """Ohne erkennbaren Tabellenkopf (keine ``Interner Link``-Spalte) ist das Ergebnis leer."""
    assert parse_curation_rows("kein Tabellenkopf hier") == {}


def test_parse_curation_rows_single_srq_value() -> None:
    """Eine einzelne SRQ-Kennung ohne Komma wird als Ein-Element-Tupel gelesen."""
    entries = parse_curation_rows(_TABLE)

    assert entries["Zweites Paper.pdf"].srq == ("SRQ3",)


def test_load_curation_rows_missing_file_returns_empty(tmp_path: Path) -> None:
    """Fehlende Übersicht ⇒ leeres Ergebnis, kein Fehler."""
    assert load_curation_rows(tmp_path / "fehlt.md") == {}


def test_migrate_from_overview_maps_to_paper_id() -> None:
    """Zeilen werden über den Dateinamen auf ``paper_id`` abgebildet."""
    entries = parse_curation_rows(_TABLE)
    migrated = migrate_from_overview(entries, {"Erstes Paper.pdf": "aaaa1111"})

    assert set(migrated) == {"aaaa1111"}
    assert migrated["aaaa1111"].row_id == "A1"


def test_migrate_from_overview_skips_unmapped_rows() -> None:
    """Eine Zeile ohne zuordenbares Korpus-Paper wird ausgelassen, nicht als Fehler behandelt."""
    entries = parse_curation_rows(_TABLE)
    migrated = migrate_from_overview(entries, {})

    assert migrated == {}


def test_save_and_load_curation_round_trip(tmp_path: Path) -> None:
    """Ein gespeicherter Datensatz kommt inhaltlich identisch zurück."""
    target = tmp_path / "curation.json"
    entry = CurationEntry(
        row_id="A1",
        filename="Erstes Paper.pdf",
        title="Erstes Paper",
        themenfokus="Thema A",
        relevanz="Hoch",
        srq=("SRQ1", "SRQ2"),
    )

    written = save_curation({"aaaa1111": entry}, target)
    loaded = load_curation(target)

    assert written == 1
    assert loaded["aaaa1111"] == entry


def test_load_curation_missing_file_returns_empty(tmp_path: Path) -> None:
    """Fehlende Datei ⇒ leeres Ergebnis, kein Fehler."""
    assert load_curation(tmp_path / "fehlt.json") == {}


def test_load_curation_rejects_broken_json(tmp_path: Path) -> None:
    """Defektes JSON -> parse_error."""
    target = tmp_path / "curation.json"
    target.write_text("{nicht json", encoding="utf-8")

    with pytest.raises(DomainError) as excinfo:
        load_curation(target)
    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_load_curation_rejects_unknown_schema_version(tmp_path: Path) -> None:
    """Unerwartete Schema-Version -> constraint_violation."""
    target = tmp_path / "curation.json"
    target.write_text('{"schema_version": "9.9.9", "papers": {}}', encoding="utf-8")

    with pytest.raises(DomainError) as excinfo:
        load_curation(target)
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_save_curation_is_deterministic(tmp_path: Path) -> None:
    """Zweimaliges Schreiben derselben Daten ergibt byte-identische Dateien."""
    target = tmp_path / "curation.json"
    entries = {
        "bbbb2222": CurationEntry(row_id="B1", filename="b.pdf", themenfokus="X"),
        "aaaa1111": CurationEntry(row_id="A1", filename="a.pdf", themenfokus="Y"),
    }

    save_curation(entries, target)
    first = target.read_bytes()
    save_curation(entries, target)
    second = target.read_bytes()

    assert first == second
    assert f'"schema_version": "{SCHEMA_VERSION}"'.encode() in first
