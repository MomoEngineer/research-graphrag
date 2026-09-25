"""FTS5-Volltextindex über ``chunks``: Phrase, Präfix, Nähe (Phase 16 / F2).

Eine **Infrastruktur**, kein Retrieval-Modus: Die vier Suchmodi bleiben unberührt, ihr Ranking
entsteht weiterhin allein aus der Hybrid-Wertung (docs/adr/0044-response-latency-bit-identical-
scoring-and-fts5-phase16.md). Die Tabelle dient Phase 17 / A5 (Personen im Text) als Grundlage
und beantwortet, was die lexikalische Wertung nicht kann: eine Wortfolge **als Folge**, einen
Wortanfang oder zwei Begriffe **nahe beieinander**.

Festlegungen (gemessen in Phase 16 / F0):

* **external content über** ``chunks``: Der Text liegt nicht doppelt in der Datei, nur der
  invertierte Index (+16,0 % am realen Bestand). Die Tabelle entsteht im Index-Bau in derselben
  SQLite-Datei und damit im selben atomaren Swap – kein zweiter Aktualisierungsweg.
* **Tokenizer** ``unicode61 remove_diacritics 2`` mit ``detail=full``: Phrase und Nähe brauchen
  Positionen; ``trigram`` belegt über den Fließtext das 2,9-Fache des Textes und bleibt der
  Namenstabelle aus Phase 17 / A3 vorbehalten.
* **Anfragen sind Nutzereingaben.** Entschärft wird ausschließlich über
  :mod:`research_graphrag.indexing.fts`; eine missglückte Anfrage endet als ``invalid_input``.
* **Verfügbarkeit wird geprüft.** Fehlt FTS5 oder der Tokenizer, entsteht keine Tabelle; der
  ``meta``-Eintrag weist das aus, und eine Anfrage endet als ``constraint_violation``.

Die Tabelle ist an die ``rowid`` der ``chunks`` gebunden. Das ist tragfähig, weil der Index
**nur als Ganzes** neu gebaut wird (voller Re-Index, atomarer Swap) und ``chunks`` danach nie
geändert wird.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.fts import (
    quote_near,
    quote_phrase,
    quote_prefix,
    safe_match,
    tokenizer_available,
)
from research_graphrag.limits import check_max_count

CHUNK_FTS_VERSION = "0.1.0"
"""Version der Tabelle ``chunk_fts`` (eigener ``meta``-Schlüssel wie beim Autorenindex – die
``schema_version`` des Index und damit der Fingerprint der Baselines bleiben unberührt)."""

CHUNK_FTS_TOKENIZER = "unicode61 remove_diacritics 2"
"""Tokenizer der Tabelle (Phase 16 / F0.4)."""

CHUNK_SEARCH_FTS = "fts5-unicode61"
"""``meta``-Wert: Die Tabelle ist gebaut."""

CHUNK_SEARCH_UNAVAILABLE = "unavailable"
"""``meta``-Wert: FTS5 oder der Tokenizer fehlt in diesem ``sqlite3``; keine Tabelle."""

DEFAULT_LIMIT = 20
"""Standardzahl der gelieferten Fundstellen."""

MIN_PREFIX_CHARS = 3
"""Kürzere Präfixe treffen einen großen Teil des Korpus und werden abgelehnt."""

MAX_NEAR_DISTANCE = 50
"""Größter zulässiger Wortabstand einer Nähe-Suche."""

SNIPPET_TOKENS = 16
"""Länge des Ausschnitts um die Fundstelle (in Wörtern)."""

_TABLE = "chunk_fts"


@dataclass(frozen=True)
class ChunkFtsReport:
    """Ergebnis des Aufbaus: Suchweg (``meta``-Wert) und Zahl der erfassten Chunks."""

    search: str
    n_chunks: int


@dataclass(frozen=True)
class ChunkMatch:
    """Eine Fundstelle mit Provenienz und Ausschnitt (Fundstelle zwischen ``«`` und ``»``)."""

    chunk_id: str
    paper_id: str
    page_number: int
    page_end: int
    section_title: str
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Fundstelle."""
        return {
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "page_number": self.page_number,
            "page_end": self.page_end,
            "section_title": self.section_title,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class ChunkMatches:
    """Fundstellen einer Anfrage (höchstens ``limit``) und die Gesamtzahl der Treffer."""

    matches: tuple[ChunkMatch, ...]
    total_matching: int


def build_chunk_fts(db_path: str | Path) -> ChunkFtsReport:
    """Legt die external-content-Tabelle über ``chunks`` an und füllt sie (``rebuild``).

    Läuft im Index-Bau nach :func:`research_graphrag.indexing.tfidf_index.build_index` auf der
    Temporärdatei, also vor dem atomaren Swap (docs/adr/0010-drop-in-workflow-and-qa-phase6.md).

    Raises:
        DomainError: ``not_found``, wenn die Index-Datei fehlt.
    """
    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")
    connection = sqlite3.connect(str(path))
    try:
        n_chunks = int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        search = CHUNK_SEARCH_UNAVAILABLE
        if tokenizer_available(connection, CHUNK_FTS_TOKENIZER):
            connection.execute(
                f"CREATE VIRTUAL TABLE {_TABLE} USING fts5(text, content='chunks', "
                f"content_rowid='rowid', tokenize='{CHUNK_FTS_TOKENIZER}')"
            )
            connection.execute(f"INSERT INTO {_TABLE}({_TABLE}) VALUES ('rebuild')")
            search = CHUNK_SEARCH_FTS
        for key, value in (("chunk_fts_version", CHUNK_FTS_VERSION), ("chunk_search", search)):
            connection.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
            )
        connection.commit()
    finally:
        connection.close()
    return ChunkFtsReport(search=search, n_chunks=n_chunks)


def search_phrase(
    db_path: str | Path,
    phrase: str,
    *,
    paper_ids: Collection[str] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ChunkMatches:
    """Findet eine Wortfolge **als Folge** (Groß-/Kleinschreibung und Diakritika egal).

    Args:
        db_path: Pfad zur Index-Datei.
        phrase: Die Wortfolge; Sonderzeichen und FTS5-Operatoren sind wirkungslos.
        paper_ids: Optional nur in diesen Papern suchen.
        limit: Höchstzahl der Fundstellen (``0 < limit <= MAX_RESULT_COUNT``, ADR 0037).

    Returns:
        Fundstellen nach FTS5-Relevanz (Tie-Break ``chunk_id``) und die Gesamtzahl.

    Raises:
        DomainError: ``invalid_input`` bei leerer Phrase oder unzulässigem ``limit``;
            ``not_found`` ohne Index-Datei; ``constraint_violation`` ohne Tabelle.
    """
    return _search(db_path, quote_phrase(phrase), paper_ids, limit)


def search_prefix(
    db_path: str | Path,
    prefix: str,
    *,
    paper_ids: Collection[str] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ChunkMatches:
    """Findet Wortfolgen, deren **letztes** Wort mit dem Präfix beginnt (``retriev`` → retrieval).

    Raises:
        DomainError: ``invalid_input`` bei einem letzten Wort unter :data:`MIN_PREFIX_CHARS`
            Zeichen oder unzulässigem ``limit``; sonst wie :func:`search_phrase`.
    """
    words = prefix.split()
    if not words or len(words[-1]) < MIN_PREFIX_CHARS:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            f"Das Präfix braucht mindestens {MIN_PREFIX_CHARS} Zeichen.",
        )
    return _search(db_path, quote_prefix(prefix), paper_ids, limit)


def search_near(
    db_path: str | Path,
    terms: Sequence[str],
    *,
    distance: int = 10,
    paper_ids: Collection[str] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ChunkMatches:
    """Findet Chunks, in denen alle Begriffe höchstens ``distance`` Wörter auseinanderstehen.

    Raises:
        DomainError: ``invalid_input`` bei weniger als zwei Begriffen, einem Abstand außerhalb
            ``0 … MAX_NEAR_DISTANCE`` oder unzulässigem ``limit``; sonst wie
            :func:`search_phrase`.
    """
    check_max_count("distance", distance, MAX_NEAR_DISTANCE)
    return _search(db_path, quote_near(terms, distance), paper_ids, limit)


def _search(
    db_path: str | Path, match: str, paper_ids: Collection[str] | None, limit: int
) -> ChunkMatches:
    """Führt eine entschärfte ``MATCH``-Anfrage aus: Fundstellen plus Gesamtzahl."""
    if limit <= 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "limit muss > 0 sein.")
    check_max_count("limit", limit)
    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")

    ids = sorted(set(paper_ids)) if paper_ids is not None else None
    if ids is not None and not ids:
        return ChunkMatches(matches=(), total_matching=0)
    paper_filter = f" AND c.paper_id IN ({','.join('?' for _ in ids)})" if ids else ""
    params: list[Any] = [match, *(ids or [])]

    connection = sqlite3.connect(str(path))
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (_TABLE,)
        ).fetchone()
        if exists is None:
            raise DomainError(
                ErrorCode.CONSTRAINT_VIOLATION,
                "Kein Phrasenindex im Index (vor Phase 16 / F2 gebaut oder FTS5 nicht "
                "verfügbar); `python -m scripts.ingest` baut ihn.",
            )
        rows = safe_match(
            connection,
            "SELECT c.chunk_id, c.paper_id, c.page_number, c.page_end, c.section_title, "
            f"snippet({_TABLE}, 0, '«', '»', '…', {SNIPPET_TOKENS}) "
            f"FROM {_TABLE} f JOIN chunks c ON c.rowid = f.rowid "
            f"WHERE {_TABLE} MATCH ?{paper_filter} ORDER BY f.rank, c.chunk_id LIMIT ?",
            [*params, limit],
        )
        total = safe_match(
            connection,
            f"SELECT COUNT(*) FROM {_TABLE} f JOIN chunks c ON c.rowid = f.rowid "
            f"WHERE {_TABLE} MATCH ?{paper_filter}",
            params,
        )[0][0]
    finally:
        connection.close()

    return ChunkMatches(
        matches=tuple(
            ChunkMatch(
                chunk_id=str(row[0]),
                paper_id=str(row[1]),
                page_number=int(row[2]),
                page_end=int(row[3]) or int(row[2]),
                section_title=str(row[4]),
                snippet=" ".join(str(row[5]).split()),
            )
            for row in rows
        ),
        total_matching=int(total),
    )
