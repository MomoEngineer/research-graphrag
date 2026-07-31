"""TF-IDF-Index über SQLite (Offline-Hybrid, Option B).

Die **SQLite-Datei ist die Source of Truth** (Papers + Chunks). Der TF-IDF-Raum wird
beim Laden **deterministisch aus den gespeicherten Chunk-Texten rekonstruiert**
(``scikit-learn``) – es werden bewusst keine sklearn/scipy-Objekte serialisiert
(kein pickle, keine Versions-Kopplung). Grundsatz:
docs/adr/0005-graphrag-index-backend-open.md.

Determinismus: ``TfidfVectorizer`` ist bei gleicher Eingabe/Konfiguration deterministisch;
Ties werden über die ``chunk_id`` stabil gebrochen.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper

SCHEMA_VERSION = "0.3.0"
"""Version des Index-Schemas. ``0.2.0 -> 0.3.0``: ``papers`` um die JSON-Spalte
``identifiers`` (DOI/arXiv) erweitert, damit ``get_paper`` zitierfähige Identifikatoren aus der
Source of Truth liefert (siehe docs/adr/0009-mcp-server-stdio-phase5.md). ``0.1.0 -> 0.2.0``:
Chunk-Provenienz um ``section_title`` ergänzt (siehe
docs/adr/0008-retrieval-and-query-router-phase4.md). Voller Re-Index genügt (keine Migration)."""

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE papers (
    paper_id      TEXT PRIMARY KEY,
    source_uri    TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    n_pages       INTEGER NOT NULL,
    identifiers   TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE chunks (
    chunk_id      TEXT PRIMARY KEY,
    paper_id      TEXT NOT NULL,
    page_number   INTEGER NOT NULL,
    text          TEXT NOT NULL,
    char_count    INTEGER NOT NULL,
    section_title TEXT NOT NULL DEFAULT '',
    row_index     INTEGER NOT NULL,
    FOREIGN KEY (paper_id) REFERENCES papers (paper_id)
);
"""


@dataclass(frozen=True)
class Hit:
    """Ein Retrieval-Treffer mit Provenienz."""

    chunk_id: str
    paper_id: str
    page_number: int
    score: float
    snippet: str
    source_uri: str
    section_title: str = ""


@dataclass(frozen=True)
class _ChunkRef:
    """Interne Chunk-Referenz inkl. Provenienz (Reihenfolge = TF-IDF-Zeile)."""

    chunk_id: str
    paper_id: str
    page_number: int
    text: str
    source_uri: str
    section_title: str = ""


def _snippet(text: str, limit: int = 200) -> str:
    """Erzeugt einen einzeiligen, gekürzten Ausschnitt (für die Antwort-Anzeige)."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _hit(ref: _ChunkRef, score: float) -> Hit:
    """Bildet eine interne Chunk-Referenz und einen Score auf einen :class:`Hit` ab."""
    return Hit(
        chunk_id=ref.chunk_id,
        paper_id=ref.paper_id,
        page_number=ref.page_number,
        score=score,
        snippet=_snippet(ref.text),
        source_uri=ref.source_uri,
        section_title=ref.section_title,
    )


def build_index(papers: Sequence[CanonicalPaper], db_path: str | Path) -> int:
    """Baut den Index (voller Re-Index) aus den nicht-leeren Chunks der Papers.

    Args:
        papers: Extrahierte Papers (siehe :mod:`research_graphrag.extraction.pdf`).
        db_path: Zielpfad der SQLite-Index-Datei; Elternordner wird angelegt.

    Returns:
        Anzahl der indexierten (nicht-leeren) Chunks.

    Raises:
        DomainError: ``invalid_input``, wenn keine indexierbaren (nicht-leeren) Chunks
            vorhanden sind (siehe docs/error-model.md).
    """
    indexable = [(chunk, paper) for paper in papers for chunk in paper.chunks if chunk.text.strip()]
    if not indexable:
        raise DomainError(ErrorCode.INVALID_INPUT, "Keine indexierbaren (nicht-leeren) Chunks.")

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()  # voller Re-Index (Standard, siehe Roadmap.md)

    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,)
        )
        seen_papers: set[str] = set()
        for _chunk, paper in indexable:
            if paper.paper_id in seen_papers:
                continue
            seen_papers.add(paper.paper_id)
            connection.execute(
                "INSERT INTO papers (paper_id, source_uri, source_sha256, n_pages, identifiers) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    paper.paper_id,
                    paper.source_uri,
                    paper.source_sha256,
                    paper.n_pages,
                    json.dumps(
                        {key: paper.identifiers[key] for key in sorted(paper.identifiers)},
                        ensure_ascii=False,
                    ),
                ),
            )
        for row_index, (chunk, _paper) in enumerate(indexable):
            connection.execute(
                "INSERT INTO chunks "
                "(chunk_id, paper_id, page_number, text, char_count, section_title, row_index) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk.chunk_id,
                    chunk.paper_id,
                    chunk.page_number,
                    chunk.text,
                    chunk.char_count,
                    chunk.section_title,
                    row_index,
                ),
            )
        connection.commit()
    finally:
        connection.close()

    return len(indexable)


class TfidfIndex:
    """Geladener Index: rekonstruierter TF-IDF-Raum über den SQLite-Chunks."""

    def __init__(self, refs: tuple[_ChunkRef, ...], vectorizer: Any, matrix: Any) -> None:
        self._refs = refs
        self._vectorizer = vectorizer
        self._matrix = matrix

    @property
    def size(self) -> int:
        """Anzahl der indexierten Chunks."""
        return len(self._refs)

    @classmethod
    def load(cls, db_path: str | Path) -> TfidfIndex:
        """Lädt den Index aus SQLite und rekonstruiert den TF-IDF-Raum.

        Raises:
            DomainError: ``not_found`` wenn die Index-Datei fehlt; ``constraint_violation``
                wenn der Index keine Chunks enthält (siehe docs/error-model.md).
        """
        path = Path(db_path)
        if not path.is_file():
            raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")

        connection = sqlite3.connect(str(path))
        try:
            rows = connection.execute(
                "SELECT c.chunk_id, c.paper_id, c.page_number, c.text, p.source_uri, "
                "c.section_title "
                "FROM chunks c JOIN papers p ON p.paper_id = c.paper_id "
                "ORDER BY c.row_index"
            ).fetchall()
        finally:
            connection.close()

        if not rows:
            raise DomainError(ErrorCode.CONSTRAINT_VIOLATION, "Index enthält keine Chunks.")

        refs = tuple(
            _ChunkRef(
                chunk_id=str(row[0]),
                paper_id=str(row[1]),
                page_number=int(row[2]),
                text=str(row[3]),
                source_uri=str(row[4]),
                section_title=str(row[5]),
            )
            for row in rows
        )
        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform([ref.text for ref in refs])
        return cls(refs=refs, vectorizer=vectorizer, matrix=matrix)

    def search(self, query: str, k: int = 5, *, paper_ids: set[str] | None = None) -> list[Hit]:
        """Liefert die Top-k-Chunks per Kosinus-Ähnlichkeit (TF-IDF) mit Provenienz.

        Args:
            query: Natürlichsprachige Anfrage.
            k: Maximale Trefferzahl (> 0).
            paper_ids: Optionaler Filter – nur Chunks dieser Paper werden berücksichtigt
                (z. B. Local-Fan-out je Nachbarpaper oder DRIFT innerhalb einer Community).

        Returns:
            Absteigend sortierte Treffer mit Score > 0; leere Liste ohne Übereinstimmung.

        Raises:
            DomainError: ``invalid_input`` bei leerer Anfrage oder ``k <= 0``.
        """
        if not query.strip():
            raise DomainError(ErrorCode.INVALID_INPUT, "Leere Suchanfrage.")
        if k <= 0:
            raise DomainError(ErrorCode.INVALID_INPUT, "k muss > 0 sein.")

        query_vector = self._vectorizer.transform([query])
        scores = linear_kernel(query_vector, self._matrix).ravel()
        order = sorted(
            range(len(self._refs)),
            key=lambda i: (-float(scores[i]), self._refs[i].chunk_id),
        )

        hits: list[Hit] = []
        for i in order:
            if len(hits) >= k:
                break
            ref = self._refs[i]
            if paper_ids is not None and ref.paper_id not in paper_ids:
                continue
            score = float(scores[i])
            if score <= 0.0:
                continue
            hits.append(_hit(ref, score))
        return hits

    def neighbors_of_chunk(self, chunk_id: str, k: int = 5) -> list[Hit]:
        """Liefert die nächsten Chunks zu einem gegebenen Chunk (Chunk↔Chunk-Kosinus).

        Grundlage der Local-Search-Chunk-Nachbarschaft: bewertet die Ähnlichkeit des
        angegebenen Chunks zu allen anderen Chunks und liefert die Top-k **ohne** den
        Chunk selbst, absteigend sortiert (Tie-Break über ``chunk_id``).

        Args:
            chunk_id: Ausgangs-Chunk (muss im Index liegen).
            k: Maximale Nachbarzahl (> 0).

        Returns:
            Absteigend sortierte Nachbar-Treffer mit Score > 0; leer ohne Übereinstimmung.

        Raises:
            DomainError: ``invalid_input`` bei ``k <= 0``; ``not_found`` wenn die ``chunk_id``
                unbekannt ist.
        """
        if k <= 0:
            raise DomainError(ErrorCode.INVALID_INPUT, "k muss > 0 sein.")
        seed_row = next((i for i, ref in enumerate(self._refs) if ref.chunk_id == chunk_id), None)
        if seed_row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"Chunk nicht gefunden: {chunk_id}")

        scores = linear_kernel(self._matrix[seed_row], self._matrix).ravel()
        order = sorted(
            range(len(self._refs)),
            key=lambda i: (-float(scores[i]), self._refs[i].chunk_id),
        )

        hits: list[Hit] = []
        for i in order:
            if len(hits) >= k:
                break
            if i == seed_row:
                continue
            score = float(scores[i])
            if score <= 0.0:
                continue
            hits.append(_hit(self._refs[i], score))
        return hits
