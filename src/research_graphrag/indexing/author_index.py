"""Autorenindex: Personen als eigene Ebene im Index (Phase 17 / A3).

Leitet beim Index-Bau aus den aufgelösten Metadaten die Tabelle ``paper_authors`` ab: je Paper
und Autorposition eine Zeile mit der Schreibweise der Quelle, dem normalisierten Namensschlüssel,
den Kennungen (OpenAlex-ID, ORCID), dem **Personenschlüssel** und der Dokumentart
(docs/adr/0043-author-index-and-person-tools.md).

Drei Regeln aus der Roadmap:

* **Nur ``strong``-Datensätze speisen die Tabelle.** Ein schwach belegter Datensatz kann ein
  fremdes Paper beschreiben (Befund 3). Seine Autoren gehören nicht in die Personenebene, bis A1
  ihn geklärt hat. Die Lücke weisen die Personen-Werkzeuge als ``coverage`` aus.
* **Personenschlüssel statt Namensheuristik:** OpenAlex-ID, sonst ``orcid:<ORCID>``, sonst
  ausdrücklich ``name:<normalisiert>`` als unbestätigte Identität
  (:func:`research_graphrag.bibliography.model.person_key`). Namensidentitäten werden **nie** still
  zusammengeführt.
* **Eine Faltung:** Der Namensschlüssel entsteht über ``ascii_fold``, eine zweite gibt es nicht.

Für die Namenssuche entsteht die kleine FTS5-Tabelle ``author_name_search`` (Tokenizer
``trigram``) über die verschiedenen Namensschlüssel. Fehlt FTS5, und bei Suchwörtern unter drei
Zeichen, wird die Schlüsselmenge direkt durchsucht; sie umfasst nur einige tausend Einträge.

Der Bau läuft im **selben atomaren Fenster** wie Index, Graphen und Metadaten; die Tabelle trägt
eine eigene Teilschema-Version (``author_schema_version``). Kein Retrieval-Modus liest sie.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    PaperMetadata,
    person_name_key,
)
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import DOCUMENT_KIND_FULL
from research_graphrag.indexing.fts import (
    TRIGRAM_MIN_CHARS,
    quote_tokens,
    safe_match,
    tokenizer_available,
)
from research_graphrag.indexing.metadata_index import load_paper_metadata

AUTHOR_SCHEMA_VERSION = "0.1.0"
"""Version des Teilschemas ``paper_authors`` (additiv, unabhängig vom Kern-Schema)."""

NAME_SEARCH_FTS = "fts5-trigram"
"""Namenssuche über die FTS5-Trigramm-Tabelle."""

NAME_SEARCH_SCAN = "scan"
"""Rückfall: Durchsuchen der (kleinen) Menge der Namensschlüssel."""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
DROP TABLE IF EXISTS paper_authors;
CREATE TABLE paper_authors (
    paper_id      TEXT NOT NULL,
    position      INTEGER NOT NULL,
    name          TEXT NOT NULL,
    name_key      TEXT NOT NULL,
    person_key    TEXT NOT NULL,
    openalex_id   TEXT NOT NULL DEFAULT '',
    orcid         TEXT NOT NULL DEFAULT '',
    identity      TEXT NOT NULL,
    document_kind TEXT NOT NULL,
    PRIMARY KEY (paper_id, position)
);
CREATE INDEX idx_paper_authors_person ON paper_authors (person_key);
CREATE INDEX idx_paper_authors_name_key ON paper_authors (name_key);
DROP TABLE IF EXISTS author_name_search;
"""

_COLUMNS = (
    "paper_id, position, name, name_key, person_key, openalex_id, orcid, identity, document_kind"
)
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class AuthorRow:
    """Eine Autorennennung im Index.

    Attributes:
        paper_id: Stabile Paper-ID.
        position: Autorposition, 1-basiert.
        name: Name in der Schreibweise der Quelle.
        name_key: Normalisierter Namensschlüssel (``person_name_key``).
        person_key: Personenschlüssel (Kennung vor Name).
        openalex_id: OpenAlex-Autor-ID oder leer.
        orcid: ORCID oder leer.
        identity: ``openalex``, ``orcid`` oder ``name``.
        document_kind: Dokumentart des Papers.
    """

    paper_id: str
    position: int
    name: str
    name_key: str
    person_key: str
    openalex_id: str
    orcid: str
    identity: str
    document_kind: str


@dataclass(frozen=True)
class AuthorBuildReport:
    """Zählwerte eines Baus."""

    n_rows: int
    n_papers: int
    n_persons: int
    n_identified: int
    name_search: str


def author_rows(
    metadata: Mapping[str, PaperMetadata], document_kinds: Mapping[str, str]
) -> tuple[AuthorRow, ...]:
    """Leitet die Zeilen aus den aufgelösten Metadaten ab (nur ``strong``, deterministisch).

    Args:
        metadata: Aufgelöste Datensätze je Paper.
        document_kinds: Dokumentart je Paper (aus der Tabelle ``papers``).

    Returns:
        Die Zeilen, sortiert nach Paper und Position.
    """
    rows: list[AuthorRow] = []
    for paper_id in sorted(metadata):
        item = metadata[paper_id]
        if item.confidence != CONFIDENCE_STRONG or paper_id not in document_kinds:
            continue
        for position, identity in enumerate(item.author_identities, start=1):
            key = person_name_key(identity.name)
            if not key:
                continue
            rows.append(
                AuthorRow(
                    paper_id=paper_id,
                    position=position,
                    name=identity.name,
                    name_key=key,
                    person_key=identity.person_key,
                    openalex_id=identity.openalex_id,
                    orcid=identity.orcid,
                    identity=identity.identity,
                    document_kind=document_kinds[paper_id],
                )
            )
    return tuple(rows)


def build_author_index(db_path: str | Path) -> AuthorBuildReport:
    """Baut ``paper_authors`` (und die Namenssuche) aus den bereits gebauten Metadaten.

    Muss **nach** :func:`research_graphrag.indexing.metadata_index.build_metadata_index` laufen.

    Raises:
        DomainError: ``not_found``, wenn die Index-Datei fehlt.
    """
    path = Path(db_path)
    metadata = load_paper_metadata(path)
    connection = sqlite3.connect(str(path))
    try:
        kinds = {
            str(row[0]): str(row[1])
            for row in connection.execute("SELECT paper_id, document_kind FROM papers")
        }
        rows = author_rows(metadata, kinds)
        connection.executescript(_SCHEMA)
        connection.executemany(
            f"INSERT INTO paper_authors ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    row.paper_id,
                    row.position,
                    row.name,
                    row.name_key,
                    row.person_key,
                    row.openalex_id,
                    row.orcid,
                    row.identity,
                    row.document_kind,
                )
                for row in rows
            ],
        )
        keys = sorted({row.name_key for row in rows})
        search = NAME_SEARCH_SCAN
        if tokenizer_available(connection, "trigram"):
            connection.execute(
                "CREATE VIRTUAL TABLE author_name_search USING fts5(name_key, tokenize='trigram')"
            )
            connection.executemany(
                "INSERT INTO author_name_search (name_key) VALUES (?)", [(key,) for key in keys]
            )
            search = NAME_SEARCH_FTS
        for key, value in (
            ("author_schema_version", AUTHOR_SCHEMA_VERSION),
            ("author_name_search", search),
        ):
            connection.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
            )
        connection.commit()
    finally:
        connection.close()
    return AuthorBuildReport(
        n_rows=len(rows),
        n_papers=len({row.paper_id for row in rows}),
        n_persons=len({row.person_key for row in rows}),
        n_identified=len({row.person_key for row in rows if row.identity != "name"}),
        name_search=search,
    )


def _connect(db_path: str | Path) -> sqlite3.Connection:
    """Öffnet den Index (``not_found``, wenn er fehlt)."""
    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")
    return sqlite3.connect(str(path))


def _has_table(connection: sqlite3.Connection, name: str) -> bool:
    """Prüft, ob eine Tabelle existiert (ein älterer Index hat keine Personenebene)."""
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def _row(values: Sequence[object]) -> AuthorRow:
    """Bildet eine Tabellenzeile ab."""
    return AuthorRow(
        paper_id=str(values[0]),
        position=int(str(values[1])),
        name=str(values[2]),
        name_key=str(values[3]),
        person_key=str(values[4]),
        openalex_id=str(values[5]),
        orcid=str(values[6]),
        identity=str(values[7]),
        document_kind=str(values[8]),
    )


def has_author_index(db_path: str | Path) -> bool:
    """``True``, wenn der Index die Personenebene trägt (gebaut ab Phase 17 / A3)."""
    connection = _connect(db_path)
    try:
        return _has_table(connection, "paper_authors")
    finally:
        connection.close()


def load_author_rows(
    db_path: str | Path,
    *,
    person_keys: Iterable[str] | None = None,
    paper_ids: Iterable[str] | None = None,
) -> tuple[AuthorRow, ...]:
    """Lädt Zeilen – alle, oder gefiltert nach Personen bzw. Papern.

    Ein Index ohne Personenebene liefert ein leeres Ergebnis (kein Fehler).
    """
    connection = _connect(db_path)
    try:
        if not _has_table(connection, "paper_authors"):
            return ()
        clauses: list[str] = []
        params: list[str] = []
        for column, values in (("person_key", person_keys), ("paper_id", paper_ids)):
            if values is None:
                continue
            chosen = sorted(set(values))
            if not chosen:
                return ()
            clauses.append(f"{column} IN ({', '.join('?' for _ in chosen)})")
            params.extend(chosen)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"SELECT {_COLUMNS} FROM paper_authors{where} ORDER BY paper_id, position", params
        ).fetchall()
    finally:
        connection.close()
    return tuple(_row(row) for row in rows)


def _matches(key: str, tokens: Sequence[str]) -> bool:
    """Prüft einen Namensschlüssel gegen die Suchwörter.

    Ein langes Suchwort muss als Teilstring vorkommen (wie in der Trigramm-Suche), ein kurzes
    (unter drei Zeichen, etwa die Initiale in „Y. Wang“) als Wortanfang.
    """
    words = key.split()
    for token in tokens:
        if len(token) >= TRIGRAM_MIN_CHARS:
            if token not in key:
                return False
        elif not any(word.startswith(token) for word in words):
            return False
    return True


def search_name_keys(db_path: str | Path, query: str) -> tuple[str, ...]:
    """Findet die Namensschlüssel, die zu einer Namensanfrage passen.

    Die Anfrage wird wie ein Name normalisiert. „Asai, Akari“, „akari asai“ und „Asai Akari“
    finden deshalb dasselbe. Jedes Suchwort muss vorkommen: lange als Teilstring, kurze als
    Wortanfang.

    Args:
        db_path: Pfad zur Index-Datei.
        query: Name oder Namensteil (Nutzereingabe).

    Returns:
        Passende Namensschlüssel, sortiert.

    Raises:
        DomainError: ``invalid_input`` bei einer Anfrage ohne verwertbares Zeichen;
            ``not_found``, wenn der Index fehlt.
    """
    tokens = _WORD.findall(person_name_key(query))
    if not tokens:
        raise DomainError(ErrorCode.INVALID_INPUT, "Name ohne verwertbare Zeichen.")
    long_tokens = [token for token in tokens if len(token) >= TRIGRAM_MIN_CHARS]
    connection = _connect(db_path)
    try:
        if not _has_table(connection, "paper_authors"):
            return ()
        if long_tokens and _has_table(connection, "author_name_search"):
            candidates = [
                str(row[0])
                for row in safe_match(
                    connection,
                    "SELECT name_key FROM author_name_search WHERE author_name_search MATCH ?",
                    [quote_tokens(long_tokens)],
                )
            ]
        else:
            candidates = [
                str(row[0])
                for row in connection.execute("SELECT DISTINCT name_key FROM paper_authors")
            ]
    finally:
        connection.close()
    return tuple(sorted({key for key in candidates if _matches(key, tokens)}))


def author_coverage(db_path: str | Path) -> tuple[int, int]:
    """Abdeckung der Personenebene: ``(Volltexte mit Autoren im Index, Volltexte gesamt)``.

    Das ist die Lücke, die die Personen-Werkzeuge in jeder Antwort ausweisen (Roadmap Phase 17,
    Abbruchkriterium von A0).
    """
    connection = _connect(db_path)
    try:
        total = int(
            connection.execute(
                "SELECT COUNT(*) FROM papers WHERE document_kind = ?", (DOCUMENT_KIND_FULL,)
            ).fetchone()[0]
        )
        if not _has_table(connection, "paper_authors"):
            return 0, total
        covered = int(
            connection.execute(
                "SELECT COUNT(DISTINCT paper_id) FROM paper_authors WHERE document_kind = ?",
                (DOCUMENT_KIND_FULL,),
            ).fetchone()[0]
        )
    finally:
        connection.close()
    return covered, total
