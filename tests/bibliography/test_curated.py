"""Tests für die kuratierte Identifikator-Quelle der Übersicht (Phase 12 / K1, ADR 0025)."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_graphrag.bibliography.curated import (
    CuratedEntry,
    column_index,
    load_curated,
    parse_curated,
    parse_identifier,
    records_from_curated,
)
from research_graphrag.bibliography.model import CONFIDENCE_STRONG, ORIGIN_CURATED

_HEADER = (
    "| ID | Name | Themenfokus | Keyword | Kompakte Zusammenfassung | Interner Link | "
    "Relevanz fuer Expose | SRQ-Zuordnung | Externer Link/Indetifikator |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)


def _row(row_id: str, name: str, filename: str, external: str) -> str:
    """Baut eine Übersichtszeile im realen 9-Spalten-Layout."""
    return (
        f"| {row_id} | {name} | (manuell) | kw | Zusammenfassung | [Quelle](papers/{filename}) "
        f"| (manuell) | (manuell) | {external} |\n"
    )


def test_column_index_finds_the_identifier_column() -> None:
    """Die Identifikator-Spalte wird über den Anfang ihrer Kopfzelle gefunden."""
    assert column_index(_HEADER, "externer link") == 8
    assert column_index(_HEADER, "name") == 1
    assert column_index(_HEADER, "gibt es nicht") is None


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("[DOI:10.1145/abc](https://doi.org/10.1145/abc)", ("10.1145/abc", "", "")),
        ("[arXiv:2503.06689](https://arxiv.org/abs/2503.06689)", ("", "2503.06689", "")),
        ("[arXiv](https://arxiv.org/abs/2503.06689v2)", ("", "2503.06689", "")),
        (
            "[OR:x](https://openreview.net/forum?id=x)",
            ("", "", "https://openreview.net/forum?id=x"),
        ),
        ("10.1145/abc", ("10.1145/abc", "", "")),
        ("(zu ergänzen)", ("", "", "")),
        ("Findings ACL 2025, S. 1897-1913", ("", "", "")),
        ("10.1/zu-kurz", ("", "", "")),
    ],
)
def test_identifier_forms_are_recognised(cell: str, expected: tuple[str, str, str]) -> None:
    """Die in der Übersicht real vorkommenden Schreibweisen werden zerlegt."""
    assert parse_identifier(cell) == expected


def test_arxiv_datacite_doi_fills_both_identifier_fields() -> None:
    """Ein arXiv-DataCite-DOI liefert zusätzlich die arXiv-ID."""
    doi, arxiv_id, url = parse_identifier("[x](https://doi.org/10.48550/arXiv.2002.09440)")

    assert doi == "10.48550/arXiv.2002.09440"
    assert arxiv_id == "2002.09440"
    assert url == ""


def test_draft_rows_are_ignored() -> None:
    """Entwurfszeilen spiegeln die Extraktion und zählen deshalb nicht als eigene Quelle."""
    markdown = _HEADER + _row("A3", "Kuratiert", "a.pdf", "[x](https://doi.org/10.1/a)")
    markdown += _row("Z7", "Entwurf", "b.pdf", "[x](https://doi.org/10.1/b)")

    entries = parse_curated(markdown)

    assert set(entries) == {"a.pdf"}
    assert entries["a.pdf"].row_id == "A3"


def test_title_and_filename_are_read_from_their_columns() -> None:
    """Name und interner Link werden spaltengenau gelesen (auch url-kodiert)."""
    markdown = _HEADER + _row(
        "B1", "Ein kuratierter Titel", "Mein%20Paper%20%28RAG%29.pdf", "10.1145/x"
    )

    entry = parse_curated(markdown)["Mein Paper (RAG).pdf"]

    assert entry.title == "Ein kuratierter Titel"
    assert entry.doi == "10.1145/x"
    assert entry.has_identifier() is True


def test_rows_without_internal_link_are_skipped() -> None:
    """Ohne internen Link lässt sich die Zeile keinem Paper zuordnen."""
    markdown = _HEADER + "| C1 | Ohne Link | x | x | x | (fehlt) | x | x | 10.1145/x |\n"

    assert parse_curated(markdown) == {}


def test_markdown_without_table_header_yields_nothing() -> None:
    """Ohne erkennbaren Tabellenkopf wird nichts geraten."""
    assert parse_curated("# Nur eine Überschrift\n") == {}


def test_load_curated_tolerates_a_missing_file(tmp_path: Path) -> None:
    """Eine fehlende Übersicht ist kein Fehler – die Herkunft entfällt dann."""
    assert load_curated(tmp_path / "fehlt.md") == {}


def test_load_curated_reads_a_real_file(tmp_path: Path) -> None:
    """Der Dateipfad-Einstieg liefert dasselbe wie das Parsen des Inhalts."""
    target = tmp_path / "Übersicht.md"
    target.write_text(_HEADER + _row("A1", "Titel", "a.pdf", "10.1145/x"), encoding="utf-8")

    assert set(load_curated(target)) == {"a.pdf"}


def test_records_are_built_only_for_known_papers() -> None:
    """Nur Einträge mit zugeordnetem Korpus-Paper werden zu Datensätzen."""
    entries = {
        "a.pdf": CuratedEntry(row_id="A1", filename="a.pdf", title="Titel A", doi="10.1145/a"),
        "fremd.pdf": CuratedEntry(
            row_id="A2", filename="fremd.pdf", title="Fremd", doi="10.1145/f"
        ),
    }

    records = records_from_curated(entries, {"a.pdf": "p1"})

    assert len(records) == 1
    assert records[0].paper_id == "p1"
    assert records[0].origin == ORIGIN_CURATED
    assert records[0].confidence == CONFIDENCE_STRONG
    assert records[0].evidence == "Übersicht.md Zeile A1"


def test_entries_without_title_and_identifier_are_dropped() -> None:
    """Eine leere Zeile trägt nichts bei und erzeugt keinen Datensatz."""
    entries = {"a.pdf": CuratedEntry(row_id="A1", filename="a.pdf")}

    assert records_from_curated(entries, {"a.pdf": "p1"}) == ()
