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


@dataclass(frozen=True)
class Citation:
    """Belegte Quelle auf **Chunk-Ebene** (Paper · Abschnitt · Seite · Chunk).

    ``section_title`` ist die (heuristische) Abschnittsüberschrift des Chunks; leer, wenn
    keine Section erkannt wurde (siehe docs/adr/0006-canonical-model-phase2-scope.md).
    """

    paper_id: str
    page_number: int
    chunk_id: str
    score: float
    source_uri: str
    snippet: str
    section_title: str = ""

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
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Zitat (Output-Schema der Retrieval-Tools)."""
        return {
            "paper_id": self.paper_id,
            "section_title": self.section_title,
            "page_number": self.page_number,
            "chunk_id": self.chunk_id,
            "score": self.score,
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
