"""Provenienz-Assembler & gemeinsame Zitat-Typen (Phase 4, Offline-Hybrid, Option B).

Bündelt die von allen Retrieval-Modi (Basic/Local/Global/DRIFT) genutzten Provenienz-Typen:
:class:`Citation` (Chunk-Ebene inkl. ``section_title``) und :class:`PaperRef` (Paper-Ebene).
Der :class:`ProvenanceAssembler` stellt Paper-Provenienz **direkt aus dem Index** zusammen
(``source_uri`` + Leit-Snippet), ohne den TF-IDF-Raum zu rekonstruieren. Grundsatz:
docs/adr/0008-retrieval-and-query-router-phase4.md.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.tfidf_index import Hit

_SNIPPET_LIMIT = 200


def _snippet(text: str, limit: int = _SNIPPET_LIMIT) -> str:
    """Erzeugt einen einzeiligen, gekürzten Ausschnitt (für Paper-Leit-Snippets)."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def page_label(page_number: int, page_end: int) -> str:
    """Anzeigeform der Seiten-Provenienz: „Seite 7" bzw. „Seiten 7–8".

    Single Source of Truth für alle Ausgabekanäle (CLI, QS-Harness, Evidenz-Aufbereitung),
    seit ein Chunk über einen Seitenumbruch laufen darf
    (docs/adr/0013-chunking-refinement-phase7.md).
    """
    if page_end <= page_number:
        return f"Seite {page_number}"
    return f"Seiten {page_number}–{page_end}"


@dataclass(frozen=True)
class Citation:
    """Belegte Quelle auf **Chunk-Ebene** (Paper · Abschnitt · Seite · Chunk).

    ``page_number`` ist die Startseite, ``page_end`` die Endseite des Chunks; beide sind
    identisch, solange der Chunk auf einer Seite liegt (Seiten-Range statt harter Seitengrenze,
    siehe docs/adr/0013-chunking-refinement-phase7.md). ``section_title`` ist die (heuristische)
    Abschnittsüberschrift des Chunks; leer, wenn keine Section erkannt wurde (siehe
    docs/adr/0006-canonical-model-phase2-scope.md).

    ``score`` ist der Wert der verwendeten Wertung – bei der Standard-Wertung ``hybrid`` also
    ein **Fusionswert** und keine Ähnlichkeit; er ist nur *innerhalb* einer Antwort
    vergleichbar. ``score_tfidf`` und ``score_bm25`` weisen die Beiträge der beiden Verfahren
    aus (siehe docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).
    """

    paper_id: str
    page_number: int
    chunk_id: str
    score: float
    source_uri: str
    snippet: str
    section_title: str = ""
    page_end: int = 0
    score_tfidf: float = 0.0
    score_bm25: float = 0.0

    def __post_init__(self) -> None:
        """Normalisiert die Seiten-Range: ``page_end`` fällt auf die Startseite zurück."""
        if self.page_end < self.page_number:
            object.__setattr__(self, "page_end", self.page_number)

    @classmethod
    def from_hit(cls, hit: Hit) -> Citation:
        """Bildet einen Index-:class:`Hit` auf ein stabiles Zitat ab."""
        return cls(
            paper_id=hit.paper_id,
            page_number=hit.page_number,
            chunk_id=hit.chunk_id,
            score=hit.score,
            source_uri=hit.source_uri,
            snippet=hit.snippet,
            section_title=hit.section_title,
            page_end=hit.page_end,
            score_tfidf=hit.score_tfidf,
            score_bm25=hit.score_bm25,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Zitat (Output-Schema der Retrieval-Tools)."""
        return {
            "paper_id": self.paper_id,
            "section_title": self.section_title,
            "page_number": self.page_number,
            "page_end": self.page_end,
            "chunk_id": self.chunk_id,
            "score": self.score,
            "score_tfidf": self.score_tfidf,
            "score_bm25": self.score_bm25,
            "source_uri": self.source_uri,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class PaperRef:
    """Belegte Quelle auf **Paper-Ebene** (für Global-/Community-Provenienz).

    Trägt ``source_uri`` und ein extraktives Leit-Snippet (Text des ersten Chunks); es gibt
    hier bewusst **keinen** Seiten-/Chunk-Anker, da corpusweite Synthese nicht auf eine
    einzelne Passage zurückführbar ist.
    """

    paper_id: str
    source_uri: str
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Paper-Referenz."""
        return {
            "paper_id": self.paper_id,
            "source_uri": self.source_uri,
            "snippet": self.snippet,
        }


class ProvenanceAssembler:
    """Stellt Paper-Provenienz direkt aus der Index-Datei zusammen (ohne ``sklearn``).

    Lädt einmalig je Paper die ``source_uri`` und das **Leit-Snippet** (Text des ersten
    Chunks, geordnet nach ``row_index``) und beantwortet daraus :class:`PaperRef`-Anfragen.
    """

    def __init__(self, source_uris: dict[str, str], leading_snippets: dict[str, str]) -> None:
        self._source_uris = source_uris
        self._leading_snippets = leading_snippets

    @classmethod
    def load(cls, db_path: str | Path) -> ProvenanceAssembler:
        """Lädt die Paper-Provenienz aus dem Index.

        Args:
            db_path: Pfad zur SQLite-Index-Datei.

        Returns:
            Ein einsatzbereiter :class:`ProvenanceAssembler`.

        Raises:
            DomainError: ``not_found`` wenn die Index-Datei fehlt (siehe docs/error-model.md).
        """
        path = Path(db_path)
        if not path.is_file():
            raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")

        connection = sqlite3.connect(str(path))
        try:
            uri_rows = connection.execute("SELECT paper_id, source_uri FROM papers").fetchall()
            snippet_rows = connection.execute(
                "SELECT c.paper_id, c.text FROM chunks c "
                "JOIN (SELECT paper_id, MIN(row_index) AS rmin FROM chunks GROUP BY paper_id) m "
                "ON c.paper_id = m.paper_id AND c.row_index = m.rmin"
            ).fetchall()
        finally:
            connection.close()

        source_uris = {str(pid): str(uri) for pid, uri in uri_rows}
        leading = {str(pid): _snippet(str(text)) for pid, text in snippet_rows}
        return cls(source_uris, leading)

    def paper_ref(self, paper_id: str) -> PaperRef:
        """Erzeugt einen :class:`PaperRef` (``source_uri`` + Leit-Snippet).

        Raises:
            DomainError: ``not_found`` wenn das Paper nicht im Index liegt.
        """
        if paper_id not in self._source_uris:
            raise DomainError(ErrorCode.NOT_FOUND, f"Paper nicht im Index: {paper_id}")
        return PaperRef(
            paper_id=paper_id,
            source_uri=self._source_uris[paper_id],
            snippet=self._leading_snippets.get(paper_id, ""),
        )
