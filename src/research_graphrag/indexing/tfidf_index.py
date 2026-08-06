"""Lexikalischer Chunk-Index über SQLite (Offline-Hybrid, Option B).

Die **SQLite-Datei ist die Source of Truth** (Papers + Chunks). Die Bewertungsräume werden
beim Laden **deterministisch aus den gespeicherten Chunk-Texten rekonstruiert**
(``scikit-learn``) – es werden bewusst keine sklearn/scipy-Objekte serialisiert
(kein pickle, keine Versions-Kopplung). Grundsatz:
docs/adr/0005-graphrag-index-backend-open.md.

Über **einer** Tokenisierung (``CountVectorizer``) stehen zwei Wertungen: der bisherige
**TF-IDF-Kosinus** (via ``TfidfTransformer`` – dieselbe Pipeline, die ``TfidfVectorizer``
intern bildet) und die handimplementierte **BM25**-Wertung
(:mod:`research_graphrag.indexing.bm25`). Beide werden per Reciprocal Rank Fusion
(:mod:`research_graphrag.indexing.fusion`) zur Standard-Wertung ``hybrid`` verbunden; siehe
docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md. Der Klassenname :class:`TfidfIndex` bleibt
aus Gründen der Stabilität bestehen (er ist in Spezifikationen und älteren ADRs referenziert).

Determinismus: Vektorisierer und Gewichte sind bei gleicher Eingabe/Konfiguration deterministisch;
Ties werden über die ``chunk_id`` stabil gebrochen.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer
from sklearn.metrics.pairwise import linear_kernel

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper
from research_graphrag.indexing import bm25
from research_graphrag.indexing.fusion import fuse_rankings

Scoring = Literal["hybrid", "tfidf", "bm25"]
"""Wählbare Wertung: Rang-Fusion beider Verfahren, nur TF-IDF-Kosinus oder nur BM25."""

DEFAULT_SCORING: Scoring = "hybrid"
"""Standard-Wertung aller Chunk-Modi (docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)."""

_SCORINGS: frozenset[str] = frozenset(("hybrid", "tfidf", "bm25"))

SCHEMA_VERSION = "0.4.0"
"""Version des Index-Schemas. ``0.3.0 -> 0.4.0``: ``chunks`` um ``page_end`` erweitert – die
Seite ist keine Chunk-Grenze mehr, sondern eine Provenienz-Range (siehe
docs/adr/0013-chunking-refinement-phase7.md). ``0.2.0 -> 0.3.0``: ``papers`` um die JSON-Spalte
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
    page_end      INTEGER NOT NULL DEFAULT 0,
    text          TEXT NOT NULL,
    char_count    INTEGER NOT NULL,
    section_title TEXT NOT NULL DEFAULT '',
    row_index     INTEGER NOT NULL,
    FOREIGN KEY (paper_id) REFERENCES papers (paper_id)
);
"""


@dataclass(frozen=True)
class Hit:
    """Ein Retrieval-Treffer mit Provenienz (``page_number`` = Start-, ``page_end`` = Endseite).

    ``score`` ist der Wert der **verwendeten** Wertung: bei ``hybrid`` der Fusionswert (ein
    Rangmaß, **keine** Ähnlichkeit), sonst der Rohwert des gewählten Verfahrens.
    ``score_tfidf``/``score_bm25`` weisen die Beiträge beider Verfahren aus
    (docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).

    ``identifiers`` und ``citation_key`` stammen aus der Tabelle ``paper_metadata`` und machen
    jeden Treffer **extern auflösbar** (docs/adr/0025-citable-paper-metadata.md); sie sind leer,
    wenn zu dem Paper nichts bekannt ist oder der Index vor Phase 12 gebaut wurde.
    """

    chunk_id: str
    paper_id: str
    page_number: int
    score: float
    snippet: str
    source_uri: str
    section_title: str = ""
    page_end: int = 0
    score_tfidf: float = 0.0
    score_bm25: float = 0.0
    identifiers: Mapping[str, str] = field(default_factory=dict)
    citation_key: str = ""


@dataclass(frozen=True)
class _ChunkRef:
    """Interne Chunk-Referenz inkl. Provenienz (Reihenfolge = TF-IDF-Zeile)."""

    chunk_id: str
    paper_id: str
    page_number: int
    text: str
    source_uri: str
    section_title: str = ""
    page_end: int = 0
    identifiers: Mapping[str, str] = field(default_factory=dict)
    citation_key: str = ""


def _snippet(text: str, limit: int = 200) -> str:
    """Erzeugt einen einzeiligen, gekürzten Ausschnitt (für die Antwort-Anzeige)."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _hit(ref: _ChunkRef, score: float, *, score_tfidf: float = 0.0, score_bm25: float = 0.0) -> Hit:
    """Bildet eine interne Chunk-Referenz und ihre Scores auf einen :class:`Hit` ab."""
    return Hit(
        chunk_id=ref.chunk_id,
        paper_id=ref.paper_id,
        page_number=ref.page_number,
        score=score,
        snippet=_snippet(ref.text),
        source_uri=ref.source_uri,
        section_title=ref.section_title,
        page_end=ref.page_end,
        score_tfidf=score_tfidf,
        score_bm25=score_bm25,
        identifiers=ref.identifiers,
        citation_key=ref.citation_key,
    )


_NO_CITATION_DATA: tuple[Mapping[str, str], str] = ({}, "")


def _load_citation_data(
    connection: sqlite3.Connection,
) -> dict[str, tuple[Mapping[str, str], str]]:
    """Liest Identifikatoren und Zitierschlüssel je Paper aus ``paper_metadata``.

    Die Tabelle ist ein **additives** Teilschema (docs/adr/0025-citable-paper-metadata.md); ein
    vor Phase 12 gebauter Index kennt sie nicht. Ihr Fehlen ist deshalb kein Fehler – die
    Treffer tragen dann schlicht keine Zitationsdaten.
    """
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'paper_metadata'"
    ).fetchone()
    if exists is None:
        return {}
    data: dict[str, tuple[Mapping[str, str], str]] = {}
    for paper_id, doi, arxiv_id, url, citation_key in connection.execute(
        "SELECT paper_id, doi, arxiv_id, url, citation_key FROM paper_metadata"
    ):
        values = {"doi": str(doi), "arxiv": str(arxiv_id), "url": str(url)}
        data[str(paper_id)] = (
            {key: value for key, value in values.items() if value},
            str(citation_key),
        )
    return data


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
                "(chunk_id, paper_id, page_number, page_end, text, char_count, section_title, "
                "row_index) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk.chunk_id,
                    chunk.paper_id,
                    chunk.page_number,
                    chunk.page_end,
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
    """Geladener Index: TF-IDF- und BM25-Raum über einer gemeinsamen Tokenisierung."""

    def __init__(
        self,
        refs: tuple[_ChunkRef, ...],
        vectorizer: Any,
        transformer: Any,
        matrix: Any,
        bm25_weights: Any,
    ) -> None:
        self._refs = refs
        self._vectorizer = vectorizer
        self._transformer = transformer
        self._matrix = matrix
        self._bm25_weights = bm25_weights

    @property
    def size(self) -> int:
        """Anzahl der indexierten Chunks."""
        return len(self._refs)

    @classmethod
    def load(cls, db_path: str | Path) -> TfidfIndex:
        """Lädt den Index aus SQLite und rekonstruiert beide Bewertungsräume.

        Aus **einem** ``CountVectorizer``-Fit entstehen die TF-IDF-Matrix (über
        ``TfidfTransformer`` – identisch zum früheren ``TfidfVectorizer``) und die
        BM25-Gewichte. Beide teilen damit Vokabular und Tokenisierung.

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
                "c.section_title, c.page_end "
                "FROM chunks c JOIN papers p ON p.paper_id = c.paper_id "
                "ORDER BY c.row_index"
            ).fetchall()
            citation_data = _load_citation_data(connection)
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
                page_end=int(row[6]),
                identifiers=citation_data.get(str(row[1]), _NO_CITATION_DATA)[0],
                citation_key=citation_data.get(str(row[1]), _NO_CITATION_DATA)[1],
            )
            for row in rows
        )
        vectorizer = CountVectorizer()
        counts = vectorizer.fit_transform([ref.text for ref in refs])
        transformer = TfidfTransformer()
        matrix = transformer.fit_transform(counts)
        return cls(
            refs=refs,
            vectorizer=vectorizer,
            transformer=transformer,
            matrix=matrix,
            bm25_weights=bm25.build_weights(counts),
        )

    def _ranking(self, scores: Any) -> list[int]:
        """Absteigende Rangliste der Zeilen mit positivem Score (Tie-Break ``chunk_id``)."""
        positive = [i for i in range(len(self._refs)) if float(scores[i]) > 0.0]
        positive.sort(key=lambda i: (-float(scores[i]), self._refs[i].chunk_id))
        return positive

    def _scores(self, query: str) -> tuple[Any, Any]:
        """Bewertet die Anfrage mit beiden Verfahren (eine Tokenisierung, zwei Wertungen)."""
        query_counts = self._vectorizer.transform([query])
        tfidf_scores = linear_kernel(
            self._transformer.transform(query_counts), self._matrix
        ).ravel()
        return tfidf_scores, bm25.score(self._bm25_weights, query_counts)

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        paper_ids: set[str] | None = None,
        scoring: Scoring = DEFAULT_SCORING,
    ) -> list[Hit]:
        """Liefert die Top-k-Chunks der gewählten Wertung mit Provenienz.

        Args:
            query: Natürlichsprachige Anfrage.
            k: Maximale Trefferzahl (> 0).
            paper_ids: Optionaler Filter – nur Chunks dieser Paper werden berücksichtigt
                (z. B. Local-Fan-out je Nachbarpaper oder DRIFT innerhalb einer Community).
            scoring: ``hybrid`` (Default, Rang-Fusion aus BM25 und TF-IDF), ``tfidf``
                (nur Kosinus) oder ``bm25`` (nur BM25).

        Returns:
            Absteigend sortierte Treffer; ein Chunk erscheint nur, wenn mindestens eines der
            beteiligten Verfahren ihn positiv bewertet. Leere Liste ohne Übereinstimmung.

        Raises:
            DomainError: ``invalid_input`` bei leerer Anfrage, ``k <= 0`` oder unbekannter
                Wertung.
        """
        if not query.strip():
            raise DomainError(ErrorCode.INVALID_INPUT, "Leere Suchanfrage.")
        if k <= 0:
            raise DomainError(ErrorCode.INVALID_INPUT, "k muss > 0 sein.")
        if scoring not in _SCORINGS:
            raise DomainError(ErrorCode.INVALID_INPUT, f"Unbekannte Wertung: {scoring}")

        tfidf_scores, bm25_scores = self._scores(query)
        if scoring == "tfidf":
            order = self._ranking(tfidf_scores)
            ranked: dict[int, float] = {i: float(tfidf_scores[i]) for i in order}
        elif scoring == "bm25":
            order = self._ranking(bm25_scores)
            ranked = {i: float(bm25_scores[i]) for i in order}
        else:
            ranked = fuse_rankings([self._ranking(tfidf_scores), self._ranking(bm25_scores)])
            order = sorted(ranked, key=lambda i: (-ranked[i], self._refs[i].chunk_id))

        hits: list[Hit] = []
        for i in order:
            if len(hits) >= k:
                break
            ref = self._refs[i]
            if paper_ids is not None and ref.paper_id not in paper_ids:
                continue
            hits.append(
                _hit(
                    ref,
                    ranked[i],
                    score_tfidf=float(tfidf_scores[i]),
                    score_bm25=float(bm25_scores[i]),
                )
            )
        return hits

    def neighbors_of_chunk(self, chunk_id: str, k: int = 5) -> list[Hit]:
        """Liefert die nächsten Chunks zu einem gegebenen Chunk (Chunk↔Chunk-Kosinus).

        Grundlage der Local-Search-Chunk-Nachbarschaft: bewertet die Ähnlichkeit des
        angegebenen Chunks zu allen anderen Chunks und liefert die Top-k **ohne** den
        Chunk selbst, absteigend sortiert (Tie-Break über ``chunk_id``). Bewusst **ohne**
        BM25: Das ist ein Anfrage-Dokument-Modell und für Ähnlichkeit zwischen zwei
        Dokumenten nicht gedacht (docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).

        Args:
            chunk_id: Ausgangs-Chunk (muss im Index liegen).
            k: Maximale Nachbarzahl (> 0).

        Returns:
            Absteigend sortierte Nachbar-Treffer mit Score > 0; leer ohne Übereinstimmung.
            ``score`` und ``score_tfidf`` sind identisch, ``score_bm25`` ist ``0.0``.

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
            hits.append(_hit(self._refs[i], score, score_tfidf=score))
        return hits
