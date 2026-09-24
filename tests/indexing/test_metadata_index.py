"""Tests für die bibliografischen Metadaten im Index (Phase 12 / K1, ADR 0025)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote

import pytest

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_CURATED,
    ORIGIN_EXTRACTED,
    ORIGIN_MANUAL,
    ORIGIN_RESOLVED,
    MetadataRecord,
)
from research_graphrag.bibliography.resolve import resolve_all
from research_graphrag.bibliography.store import save_records
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SECTION_KIND_BODY, SECTION_KIND_REFERENCES, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.extraction.refstub import canonical_from_stub, parse_stub
from research_graphrag.indexing.metadata_index import (
    METADATA_SCHEMA_VERSION,
    build_metadata_index,
    collect_records,
    extracted_records,
    load_paper_metadata,
    metadata_for,
    stub_records,
    year_from_arxiv,
)
from research_graphrag.indexing.tfidf_index import build_index

_TITLE_A = "Graph Retrieval for Scientific Corpora at Scale"
_TITLE_B = "Benchmarking Retrieval Pipelines in Practice Today"

_HEADER = (
    "| ID | Name | Themenfokus | Keyword | Kompakte Zusammenfassung | Interner Link | "
    "Relevanz fuer Expose | SRQ-Zuordnung | Externer Link/Indetifikator |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)


def _paper(
    paper_id: str,
    title: str,
    *,
    front: str = "",
    identifiers: dict[str, str] | None = None,
    references: Sequence[str] = (),
) -> CanonicalPaper:
    """Baut ein Canonical-Paper mit Titelseite und optionalem Referenzabschnitt."""
    body = front or f"{title} untersucht retrieval augmented generation im Korpus."
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
        source_uri=f"file:///papers/{quote(title)}.pdf",
        source_sha256="0" * 64,
        n_pages=2 if references else 1,
        chunks=tuple(chunks),
        quality_flags=(),
        sections=tuple(sections),
        identifiers=identifiers or {},
    )


def _index(tmp_path: Path, papers: Sequence[CanonicalPaper]) -> Path:
    """Baut einen Kern-Index (ohne Metadaten-Tabelle) und liefert seinen Pfad."""
    db = tmp_path / "index.sqlite"
    build_index(list(papers), db)
    return db


@pytest.mark.parametrize(
    ("arxiv_id", "expected"),
    [
        ("2503.06689", 2025),
        ("0704.0001", 2007),
        ("2513.00001", 0),
        ("nicht-arxiv", 0),
        ("", 0),
    ],
)
def test_year_from_arxiv(arxiv_id: str, expected: int) -> None:
    """Das Preprint-Jahr folgt dem seit 2007 gültigen ID-Format; alles andere liefert 0."""
    assert year_from_arxiv(arxiv_id) == expected


def test_extracted_record_is_strong_when_the_identifier_is_on_the_title_page() -> None:
    """Ein auf der Titelseite belegter Identifikator gilt als starker Beleg."""
    paper = _paper(
        "aaaa0001",
        _TITLE_A,
        front=f"{_TITLE_A} arXiv:2401.00001 retrieval augmented generation",
        identifiers={"arxiv": "2401.00001"},
    )

    record = extracted_records([paper])[0]

    assert record.origin == ORIGIN_EXTRACTED
    assert record.confidence == CONFIDENCE_STRONG
    assert record.arxiv_id == "2401.00001"
    assert record.year == 2024
    assert record.title == _TITLE_A


def test_extracted_record_is_weak_when_the_identifier_is_only_in_the_full_text() -> None:
    """Ein nicht auf der Titelseite belegter Identifikator wird als schwach ausgewiesen."""
    paper = _paper(
        "aaaa0001",
        _TITLE_A,
        identifiers={"arxiv": "2108.07732"},
        references=["Austin et al. arXiv:2108.07732 Program synthesis with large language models"],
    )

    record = extracted_records([paper])[0]

    assert record.confidence == CONFIDENCE_WEAK
    assert "nicht auf der Titelseite belegt" in record.evidence


def test_extracted_record_is_weak_when_the_identifier_has_several_carriers() -> None:
    """Ein im Korpus mehrfach vergebener Identifikator ist kein verlässlicher Beleg."""
    shared = "10.1145/nnnnnnn.nnnnnnn"
    papers = [
        _paper("aaaa0001", _TITLE_A, front=f"{_TITLE_A} doi:{shared}", identifiers={"doi": shared}),
        _paper("bbbb0001", _TITLE_B, front=f"{_TITLE_B} doi:{shared}", identifiers={"doi": shared}),
    ]

    records = extracted_records(papers)

    assert {record.confidence for record in records} == {CONFIDENCE_WEAK}
    assert "mehrfach vergeben" in records[0].evidence


def test_paper_without_identifier_keeps_a_strong_title_record() -> None:
    """Fehlt jeder Identifikator, bleibt der Dateiname-Titel dennoch eine sichere Tatsache."""
    record = extracted_records([_paper("aaaa0001", _TITLE_A)])[0]

    assert record.confidence == CONFIDENCE_STRONG
    assert record.evidence == "kein Identifikator im PDF gefunden"
    assert record.doi == ""


def test_collect_records_joins_all_three_sources(tmp_path: Path) -> None:
    """Extraktion, Übersicht und Metadatendatei fließen gemeinsam ein."""
    paper = _paper("aaaa0001", _TITLE_A)
    overview = tmp_path / "Übersicht.md"
    overview.write_text(
        _HEADER
        + (
            f"| A1 | {_TITLE_A} | x | x | x | [Quelle](papers/{quote(_TITLE_A)}.pdf) | x | x | "
            "[DOI:10.1145/abc](https://doi.org/10.1145/abc) |\n"
        ),
        encoding="utf-8",
    )
    store = tmp_path / "paper_metadata.json"
    save_records(
        store,
        [
            MetadataRecord(
                paper_id="aaaa0001",
                origin=ORIGIN_RESOLVED,
                authors=("Anna Beispiel",),
                year=2024,
            )
        ],
    )

    records = collect_records([paper], overview_path=overview, metadata_file=store)

    assert {record.origin for record in records} == {
        ORIGIN_EXTRACTED,
        ORIGIN_CURATED,
        ORIGIN_RESOLVED,
    }


def test_collect_records_ignores_stored_records_of_unknown_papers(tmp_path: Path) -> None:
    """Datensätze zu Papern außerhalb des Korpus werden nicht übernommen."""
    store = tmp_path / "paper_metadata.json"
    save_records(store, [MetadataRecord(paper_id="fremd", origin=ORIGIN_MANUAL, title="Fremd")])

    records = collect_records([_paper("aaaa0001", _TITLE_A)], metadata_file=store)

    assert [record.paper_id for record in records] == ["aaaa0001"]


def test_build_writes_the_table_and_its_schema_version(tmp_path: Path) -> None:
    """Der Bau legt die Tabelle additiv an und vermerkt ihre Teilschema-Version."""
    papers = [_paper("aaaa0001", _TITLE_A), _paper("bbbb0001", _TITLE_B)]
    db = _index(tmp_path, papers)

    report = build_metadata_index(papers, db)

    connection = sqlite3.connect(str(db))
    try:
        version = connection.execute(
            "SELECT value FROM meta WHERE key = 'metadata_schema_version'"
        ).fetchone()
        rows = connection.execute("SELECT COUNT(*) FROM paper_metadata").fetchone()
        chunks = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()
    finally:
        connection.close()

    assert version[0] == METADATA_SCHEMA_VERSION
    assert rows[0] == 2
    assert chunks[0] > 0  # Kern-Tabellen bleiben unangetastet
    assert report.n_papers == 2


def test_curated_identifier_outranks_the_extracted_one(tmp_path: Path) -> None:
    """Der kuratierte Publisher-DOI verdrängt die extrahierte arXiv-ID nicht, sondern ergänzt sie."""
    paper = _paper(
        "aaaa0001",
        _TITLE_A,
        front=f"{_TITLE_A} arXiv:2401.00001",
        identifiers={"arxiv": "2401.00001"},
    )
    overview = tmp_path / "Übersicht.md"
    overview.write_text(
        _HEADER
        + (
            f"| A1 | Kuratierter Titel | x | x | x | [Quelle](papers/{quote(_TITLE_A)}.pdf) "
            "| x | x | [DOI:10.1145/abc](https://doi.org/10.1145/abc) |\n"
        ),
        encoding="utf-8",
    )
    db = _index(tmp_path, [paper])

    build_metadata_index([paper], db, overview_path=overview)
    metadata = load_paper_metadata(db)["aaaa0001"]

    assert metadata.doi == "10.1145/abc"
    assert metadata.arxiv_id == "2401.00001"
    assert metadata.title == "Kuratierter Titel"
    assert metadata.origins == {
        "title": ORIGIN_CURATED,
        "doi": ORIGIN_CURATED,
        "arxiv_id": ORIGIN_EXTRACTED,
        "year": ORIGIN_EXTRACTED,
    }


def test_report_counts_identifiers_citable_and_weak(tmp_path: Path) -> None:
    """Der Bericht zählt Identifikatoren, vollständige Angaben und schwache Belege."""
    strong = _paper(
        "aaaa0001",
        _TITLE_A,
        front=f"{_TITLE_A} arXiv:2401.00001",
        identifiers={"arxiv": "2401.00001"},
    )
    weak = _paper("bbbb0001", _TITLE_B, identifiers={"doi": "10.1145/unbelegt"})
    db = _index(tmp_path, [strong, weak])
    store = tmp_path / "paper_metadata.json"
    save_records(
        store,
        [
            MetadataRecord(
                paper_id="aaaa0001",
                origin=ORIGIN_RESOLVED,
                authors=("Anna Beispiel",),
                confidence=CONFIDENCE_STRONG,
            )
        ],
    )

    report = build_metadata_index([strong, weak], db, metadata_file=store)

    assert report.n_papers == 2
    assert report.n_with_identifier == 2
    assert report.n_citable == 1
    assert report.n_resolved == 1
    assert report.n_weak == 1


def test_metadata_for_returns_an_empty_record_for_unknown_papers(tmp_path: Path) -> None:
    """Ein unbekanntes Paper liefert einen leeren Datensatz statt eines Fehlers."""
    papers = [_paper("aaaa0001", _TITLE_A)]
    db = _index(tmp_path, papers)
    build_metadata_index(papers, db)

    assert metadata_for(db, "gibtesnicht").title == ""
    assert metadata_for(db, "aaaa0001").title == _TITLE_A


def test_missing_table_is_tolerated(tmp_path: Path) -> None:
    """Ein vor Phase 12 gebauter Index bleibt lesbar (nur ohne Zitationsdaten)."""
    db = _index(tmp_path, [_paper("aaaa0001", _TITLE_A)])

    assert load_paper_metadata(db) == {}


def test_missing_index_is_reported_as_not_found(tmp_path: Path) -> None:
    """Ohne Index-Datei melden Bau und Lesen ``not_found``."""
    with pytest.raises(DomainError) as build_error:
        build_metadata_index([_paper("aaaa0001", _TITLE_A)], tmp_path / "fehlt.sqlite")
    with pytest.raises(DomainError) as read_error:
        load_paper_metadata(tmp_path / "fehlt.sqlite")

    assert build_error.value.code is ErrorCode.NOT_FOUND
    assert read_error.value.code is ErrorCode.NOT_FOUND


def test_build_is_deterministic(tmp_path: Path) -> None:
    """Zwei Läufe erzeugen dieselbe Tabelle (Reihenfolge der Paper ist unerheblich)."""
    papers = [_paper("bbbb0001", _TITLE_B), _paper("aaaa0001", _TITLE_A)]
    db = _index(tmp_path, papers)

    build_metadata_index(papers, db)
    first = load_paper_metadata(db)
    build_metadata_index(list(reversed(papers)), db)

    assert load_paper_metadata(db) == first


# --------------------------------------------------------------------------------------
# Referenz-Einträge und Personenkennung (Phase 17 / A2, ADR 0041)
# --------------------------------------------------------------------------------------


def _stub_paper(paper_id: str = "cccc0001", **overrides: object) -> CanonicalPaper:
    """Baut das Canonical eines Referenz-Eintrags über den echten Stub-Adapter."""
    payload: dict[str, object] = {
        "schema_version": "0.2.0",
        "document_kind": "reference",
        "requested": "doi:10.1145/1376616.1376629",
        "title": "Towards Identity Anonymization on Graphs",
        "authors": ["Kun Liu", "Evimaria Terzi"],
        "author_ids": ["A1111", "A2222"],
        "author_orcids": [],
        "year": 2008,
        "venue": "Proceedings of SIGMOD",
        "doi": "10.1145/1376616.1376629",
        "arxiv_id": "",
        "url": "",
        "source": "OpenAlex",
        "abstract": "Ein Abstract.",
    }
    payload.update(overrides)
    stub = parse_stub(json.dumps(payload).encode())
    return canonical_from_stub(
        stub,
        paper_id=paper_id,
        source_uri=f"file:///papers/{paper_id}.refjson",
        source_sha256="f" * 64,
    )


def test_a_reference_entry_contributes_a_strong_resolved_record() -> None:
    """Die Stub-Datei wurde über die eigene Kennung aufgelöst – ihr Datensatz ist ``strong``."""
    (record,) = stub_records([_stub_paper(), _paper("aaaa0001", _TITLE_A)])

    assert record.origin == ORIGIN_RESOLVED
    assert record.confidence == CONFIDENCE_STRONG
    assert record.authors == ("Kun Liu", "Evimaria Terzi")
    assert record.author_ids == ("A1111", "A2222")
    assert record.doi == "10.1145/1376616.1376629"
    assert record.evidence == "Referenz-Eintrag über doi:10.1145/1376616.1376629, OpenAlex"


def test_the_stub_authors_reach_the_index_with_their_identifiers(tmp_path: Path) -> None:
    """Befund 2 ist geschlossen: Autoren und Kennungen kommen ohne Netzzugriff im Index an."""
    papers = [_stub_paper(), _paper("aaaa0001", _TITLE_A)]
    db = _index(tmp_path, papers)

    report = build_metadata_index(papers, db)
    item = load_paper_metadata(db)["cccc0001"]

    assert item.authors == ("Kun Liu", "Evimaria Terzi")
    assert item.author_ids == ("A1111", "A2222")
    assert item.year == 2008
    assert item.confidence == CONFIDENCE_STRONG
    assert item.is_citable()
    assert report.n_from_stubs == 1
    assert report.n_with_author_ids == 1


def test_the_stub_outranks_a_stored_resolved_record_of_the_same_entry(tmp_path: Path) -> None:
    """Die Stub-Datei beschreibt den Eintrag; ein späterer Lauf ergänzt nur fehlende Felder."""
    stored = MetadataRecord(
        paper_id="cccc0001",
        origin=ORIGIN_RESOLVED,
        title="Ein fremder Titel aus einer Titel-Suche",
        authors=("Jemand Anderes",),
        venue="",
        url="https://example.org/landing",
        confidence=CONFIDENCE_WEAK,
    )
    metadata_file = tmp_path / "paper_metadata.json"
    save_records(metadata_file, [stored])

    records = collect_records([_stub_paper(venue="")], metadata_file=metadata_file)
    resolved = resolve_all(records, ["cccc0001"])["cccc0001"]

    assert resolved.authors == ("Kun Liu", "Evimaria Terzi")
    assert resolved.url == "https://example.org/landing"


def test_the_report_measures_the_author_coverage_of_full_texts(tmp_path: Path) -> None:
    """Die Kennzahl des A0-Abbruchkriteriums: Volltexte mit Autoren aus ``strong``-Datensätzen."""
    papers = [
        _paper("aaaa0001", _TITLE_A),
        _paper("bbbb0001", _TITLE_B),
        _stub_paper(),
    ]
    metadata_file = tmp_path / "paper_metadata.json"
    save_records(
        metadata_file,
        [
            MetadataRecord(
                paper_id="aaaa0001",
                origin=ORIGIN_RESOLVED,
                authors=("Anna Beispiel",),
                confidence=CONFIDENCE_STRONG,
            )
        ],
    )
    db = _index(tmp_path, papers)

    report = build_metadata_index(papers, db, metadata_file=metadata_file)

    assert report.n_full_texts == 2
    assert report.n_full_with_strong_authors == 1
    assert report.author_coverage == pytest.approx(0.5)


def test_an_index_from_before_the_identity_columns_stays_readable(tmp_path: Path) -> None:
    """Ein Teilschema 0.1.0 liefert Metadaten ohne Kennungen statt eines Fehlers."""
    papers = [_paper("aaaa0001", _TITLE_A)]
    db = _index(tmp_path, papers)
    build_metadata_index(papers, db)
    connection = sqlite3.connect(str(db))
    try:
        connection.execute("ALTER TABLE paper_metadata DROP COLUMN author_ids")
        connection.execute("ALTER TABLE paper_metadata DROP COLUMN author_orcids")
        connection.commit()
    finally:
        connection.close()

    item = load_paper_metadata(db)["aaaa0001"]

    assert item.author_ids == ()
    assert item.author_identities == ()
