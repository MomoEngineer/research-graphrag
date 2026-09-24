"""Tests für den Autorenindex und die gemeinsamen FTS5-Bausteine (Phase 17 / A3, ADR 0043).

Geprüft werden: nur ``strong``-Datensätze speisen die Tabelle, der Personenschlüssel bevorzugt die
Kennung, zwei Bauten ergeben dieselbe Tabelle, die Namenssuche findet beide Schreibweisen samt
Initialen und kurzer Namen, FTS5-Sonderzeichen sind entschärft, und ein älterer Index bleibt
lesbar.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_RESOLVED,
    MetadataRecord,
    PaperMetadata,
)
from research_graphrag.bibliography.store import save_records
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SECTION_KIND_BODY, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.author_index import (
    AUTHOR_SCHEMA_VERSION,
    NAME_SEARCH_FTS,
    author_coverage,
    author_rows,
    build_author_index,
    has_author_index,
    load_author_rows,
    search_name_keys,
)
from research_graphrag.indexing.fts import quote_tokens, safe_match, tokenizer_available
from research_graphrag.indexing.metadata_index import build_metadata_index
from research_graphrag.indexing.tfidf_index import build_index


def _paper(paper_id: str) -> CanonicalPaper:
    """Ein minimales Canonical-Paper."""
    body = f"Paper {paper_id} über retrieval augmented generation im Korpus."
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{paper_id}.pdf",
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
    )


def _record(
    paper_id: str,
    authors: Sequence[str],
    ids: Sequence[str] = (),
    confidence: str = CONFIDENCE_STRONG,
) -> MetadataRecord:
    """Ein aufgelöster Datensatz mit Autoren (und optional Kennungen)."""
    return MetadataRecord(
        paper_id=paper_id,
        origin=ORIGIN_RESOLVED,
        title=f"Titel {paper_id}",
        authors=tuple(authors),
        year=2024,
        confidence=confidence,
        author_ids=tuple(ids),
    )


@pytest.fixture
def index_db(tmp_path: Path) -> Path:
    """Index mit vier Papern: drei ``strong``, eines ``weak`` (fremdes Paper verdeckt)."""
    papers = [_paper(paper_id) for paper_id in ("p1", "p2", "p3", "p4")]
    metadata = tmp_path / "paper_metadata.json"
    save_records(
        metadata,
        [
            _record("p1", ["Asai, Akari", "Y. Wang"], ["A1111", ""]),
            _record("p2", ["Akari Asai", "Yi Wang", "Wei Li"], ["A1111", "A2222", ""]),
            _record("p3", ["Müller, Jörg"]),
            _record("p4", ["Hannaneh Hajishirzi"], ["A3333"], confidence=CONFIDENCE_WEAK),
        ],
    )
    db = tmp_path / "index.sqlite"
    build_index(papers, db)
    build_metadata_index(papers, db, metadata_file=metadata)
    build_author_index(db)
    return db


def test_only_strong_records_feed_the_person_level(index_db: Path) -> None:
    """Ein ``weak``-Datensatz kann ein fremdes Paper beschreiben – seine Autoren bleiben draußen."""
    rows = load_author_rows(index_db)

    assert {row.paper_id for row in rows} == {"p1", "p2", "p3"}
    assert all(row.name != "Hannaneh Hajishirzi" for row in rows)


def test_rows_keep_the_source_spelling_and_derive_key_and_person(index_db: Path) -> None:
    """Schreibweise der Quelle bleibt; Schlüssel und Personenschlüssel werden abgeleitet."""
    p1 = load_author_rows(index_db, paper_ids=["p1"])

    assert [(row.position, row.name, row.name_key, row.person_key) for row in p1] == [
        (1, "Asai, Akari", "akari asai", "A1111"),
        (2, "Y. Wang", "y wang", "name:y wang"),
    ]
    assert [row.identity for row in p1] == ["openalex", "name"]
    assert load_author_rows(index_db, paper_ids=["p3"])[0].name_key == "joerg mueller"


def test_the_same_person_is_found_through_its_identifier(index_db: Path) -> None:
    """„Asai, Akari“ und „Akari Asai“ sind über die OpenAlex-ID **eine** Person."""
    rows = load_author_rows(index_db, person_keys=["A1111"])

    assert [(row.paper_id, row.name) for row in rows] == [
        ("p1", "Asai, Akari"),
        ("p2", "Akari Asai"),
    ]
    assert load_author_rows(index_db, person_keys=[]) == ()


def test_rows_can_be_filtered_by_name_key(index_db: Path) -> None:
    """Der Namensfilter findet alle Nennungen einer Schreibweise, Filter wirken zusammen."""
    rows = load_author_rows(index_db, name_keys=["akari asai"])

    assert [(row.paper_id, row.person_key) for row in rows] == [("p1", "A1111"), ("p2", "A1111")]
    assert load_author_rows(index_db, name_keys=["akari asai"], paper_ids=["p2"])[0].name == (
        "Akari Asai"
    )
    assert load_author_rows(index_db, name_keys=[]) == ()


def test_the_build_is_versioned_and_deterministic(index_db: Path) -> None:
    """Zwei Bauten ergeben eine identische Tabelle (Akzeptanz A3)."""
    connection = sqlite3.connect(str(index_db))
    try:
        first = connection.execute("SELECT * FROM paper_authors ORDER BY 1, 2").fetchall()
        meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
    finally:
        connection.close()

    report = build_author_index(index_db)

    connection = sqlite3.connect(str(index_db))
    try:
        second = connection.execute("SELECT * FROM paper_authors ORDER BY 1, 2").fetchall()
    finally:
        connection.close()
    assert first == second
    assert meta["author_schema_version"] == AUTHOR_SCHEMA_VERSION
    assert meta["author_name_search"] == NAME_SEARCH_FTS
    assert (report.n_rows, report.n_papers, report.n_persons) == (6, 3, 5)
    assert report.n_identified == 2


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Asai, Akari", ("akari asai",)),
        ("akari asai", ("akari asai",)),
        ("ASAI", ("akari asai",)),
        ("Y. Wang", ("y wang", "yi wang")),
        ("Yi Wang", ("yi wang",)),
        ("Wang", ("y wang", "yi wang")),
        ("Li", ("wei li",)),
        ("Jörg Müller", ("joerg mueller",)),
        ("Niemand", ()),
    ],
)
def test_the_name_search_covers_both_notations_initials_and_short_names(
    index_db: Path, query: str, expected: tuple[str, ...]
) -> None:
    """Lange Suchwörter als Teilstring (Trigramm), kurze als Wortanfang."""
    assert search_name_keys(index_db, query) == expected


@pytest.mark.parametrize("query", ['Asai" OR "x', "NEAR(asai wang)", "asai*", "wang:1", "(asai)"])
def test_fts5_syntax_in_a_name_is_defused(index_db: Path, query: str) -> None:
    """FTS5-Anfragen sind Nutzereingaben: Operatoren verlieren ihre Bedeutung, nichts bricht."""
    result = search_name_keys(index_db, query)

    assert isinstance(result, tuple)


def test_an_empty_name_is_invalid_input(index_db: Path) -> None:
    """Eine Anfrage ohne verwertbares Zeichen ist ein Eingabefehler."""
    with pytest.raises(DomainError) as excinfo:
        search_name_keys(index_db, " ,.- ")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_without_the_fts_table_the_scan_gives_the_same_result(index_db: Path) -> None:
    """Rückfallweg ohne FTS5: dieselben Treffer über die kleine Schlüsselmenge."""
    with_fts = [search_name_keys(index_db, query) for query in ("Wang", "Asai", "Li")]
    connection = sqlite3.connect(str(index_db))
    try:
        connection.execute("DROP TABLE author_name_search")
        connection.commit()
    finally:
        connection.close()

    assert [search_name_keys(index_db, query) for query in ("Wang", "Asai", "Li")] == with_fts


def test_the_coverage_counts_full_texts_with_strong_authors(index_db: Path) -> None:
    """Die Lücke, die jede Antwort der Personen-Werkzeuge ausweist."""
    assert author_coverage(index_db) == (3, 4)


def test_an_index_without_the_person_level_stays_readable(tmp_path: Path) -> None:
    """Vor Phase 17 gebaut: leere Ergebnisse statt eines Fehlers, Abdeckung 0."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("p1")], db)

    assert not has_author_index(db)
    assert load_author_rows(db) == ()
    assert search_name_keys(db, "Asai") == ()
    assert author_coverage(db) == (0, 1)


def test_a_missing_index_is_not_found(tmp_path: Path) -> None:
    """Ohne Index-Datei meldet jeder Leser ``not_found``."""
    with pytest.raises(DomainError) as excinfo:
        load_author_rows(tmp_path / "fehlt.sqlite")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_author_rows_skip_names_without_usable_characters() -> None:
    """Ein Name aus Satzzeichen erzeugt keinen Schlüssel und keine Zeile."""
    metadata = {
        "p1": PaperMetadata(paper_id="p1", authors=("—", "Anna Beispiel"), confidence="strong")
    }

    rows = author_rows(metadata, {"p1": "full"})

    assert [(row.position, row.name) for row in rows] == [(2, "Anna Beispiel")]


# --------------------------------------------------------------------------------------
# Gemeinsame FTS5-Bausteine
# --------------------------------------------------------------------------------------


def test_tokens_become_string_literals() -> None:
    """Jedes Token ein String-Literal, innere Anführungszeichen verdoppelt."""
    assert quote_tokens(["asai", 'a"b', "  "]) == '"asai" "a""b"'


def test_no_tokens_is_invalid_input() -> None:
    """Eine leere Anfrage erreicht FTS5 nie."""
    with pytest.raises(DomainError) as excinfo:
        quote_tokens(["", " "])

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_an_fts5_syntax_error_becomes_invalid_input() -> None:
    """Kein ``sqlite3.OperationalError`` bis an die MCP-Grenze."""
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    try:
        with pytest.raises(DomainError) as excinfo:
            safe_match(connection, "SELECT x FROM t WHERE t MATCH ?", ['"offen'])
    finally:
        connection.close()

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_the_tokenizer_probe_checks_availability_and_its_input() -> None:
    """Die Probe erkennt vorhandene Tokenizer und lässt keinen SQL-Text durch."""
    connection = sqlite3.connect(":memory:")
    try:
        assert tokenizer_available(connection, "trigram")
        assert not tokenizer_available(connection, "gibtesnicht")
        with pytest.raises(DomainError):
            tokenizer_available(connection, "x'); DROP TABLE papers; --")
    finally:
        connection.close()
