"""Provenienz-Assembler & gemeinsame Zitat-Typen (Phase 4, Offline-Hybrid, Option B).

Bündelt die von allen Retrieval-Modi (Basic/Local/Global/DRIFT) genutzten Provenienz-Typen:
:class:`Citation` (Chunk-Ebene inkl. ``section_title``) und :class:`PaperRef` (Paper-Ebene).
Der :class:`ProvenanceAssembler` stellt Paper-Provenienz **direkt aus dem Index** zusammen
(``source_uri`` + Leit-Snippet), ohne den TF-IDF-Raum zu rekonstruieren. Grundsatz:
docs/adr/0008-retrieval-and-query-router-phase4.md.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from research_graphrag.bibliography.model import PaperMetadata, empty_metadata
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import DOCUMENT_KIND_FULL
from research_graphrag.indexing.metadata_index import load_paper_metadata
from research_graphrag.indexing.tfidf_index import Hit

_SNIPPET_LIMIT = 200


def _snippet(text: str, limit: int = _SNIPPET_LIMIT) -> str:
    """Erzeugt einen einzeiligen, gekürzten Ausschnitt (für Paper-Leit-Snippets)."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


REFERENCE_PAGE_LABEL = "ohne Seite (Abstract)"
"""Anzeigeform der Provenienz eines Referenz-Eintrags ohne Volltext.

„Seite 1" wäre dort eine **falsche Aussage über die Herkunft**; die fehlende Seitenangabe steht
deshalb als ``page_number = 0`` im Datenmodell selbst
(docs/adr/0030-reference-entries-in-corpus-phase13.md).
"""

REFERENCE_EVIDENCE_MARKER = "Referenz-Eintrag ohne Volltext"
"""Klartext-Kennzeichnung eines Belegs, der nur auf Titel und Abstract beruht.

Steht in jedem Ausgabekanal an derselben Stelle – im Provenienz-Label. Die fehlende Seite allein
reicht als Hinweis nicht: Sie sagt, *wo* der Beleg herkommt, nicht, dass der Volltext **fehlt**
(docs/adr/0031-reference-contract-and-guardrail-phase13.md).
"""


def page_label(page_number: int, page_end: int) -> str:
    """Anzeigeform der Seiten-Provenienz: „Seite 7" bzw. „Seiten 7–8".

    Single Source of Truth für alle Ausgabekanäle (CLI, QS-Harness, Evidenz-Aufbereitung),
    seit ein Chunk über einen Seitenumbruch laufen darf
    (docs/adr/0013-chunking-refinement-phase7.md). Ein Chunk **ohne** Seite – also ein
    Referenz-Eintrag – wird als solcher benannt statt mit einer erfundenen Seite
    (docs/adr/0030-reference-entries-in-corpus-phase13.md).
    """
    if page_number <= 0:
        return REFERENCE_PAGE_LABEL
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

    ``identifiers`` (DOI/arXiv/URL) und ``citation_key`` machen den Beleg **extern auflösbar**;
    ohne sie zeigt ein Zitat nur auf eine interne ``paper_id`` und einen lokalen Dateipfad
    (siehe docs/adr/0025-citable-paper-metadata.md). Die vollständige Literaturangabe liefert
    bewusst nicht jedes Zitat, sondern ``answer_question``, ``get_paper`` und ``get_reference``.

    ``document_kind`` sagt, **worauf** der Beleg beruht: ``full`` auf einem Volltext,
    ``reference`` auf einem Referenz-Eintrag aus Titel und Abstract. Ohne dieses Feld sieht ein
    Abstract-Zitat aus wie ein Volltext-Beleg – die Unvollständigkeit wäre unsichtbar
    (docs/adr/0031-reference-contract-and-guardrail-phase13.md).
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
    identifiers: Mapping[str, str] = field(default_factory=dict)
    citation_key: str = ""
    document_kind: str = DOCUMENT_KIND_FULL

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
            identifiers=hit.identifiers,
            citation_key=hit.citation_key,
            document_kind=hit.document_kind,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Zitat (Output-Schema der Retrieval-Tools)."""
        return {
            "paper_id": self.paper_id,
            "document_kind": self.document_kind,
            "section_title": self.section_title,
            "page_number": self.page_number,
            "page_end": self.page_end,
            "chunk_id": self.chunk_id,
            "score": self.score,
            "score_tfidf": self.score_tfidf,
            "score_bm25": self.score_bm25,
            "source_uri": self.source_uri,
            "identifiers": dict(self.identifiers),
            "citation_key": self.citation_key,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class PaperRef:
    """Belegte Quelle auf **Paper-Ebene** (für Global-/Community-Provenienz).

    Trägt ``source_uri`` und ein extraktives Leit-Snippet (Text des ersten Chunks); es gibt
    hier bewusst **keinen** Seiten-/Chunk-Anker, da corpusweite Synthese nicht auf eine
    einzelne Passage zurückführbar ist. ``identifiers`` und ``citation_key`` machen die
    Referenz extern auflösbar (docs/adr/0025-citable-paper-metadata.md). ``document_kind``
    weist Referenz-Einträge ohne Volltext aus
    (docs/adr/0031-reference-contract-and-guardrail-phase13.md).
    """

    paper_id: str
    source_uri: str
    snippet: str = ""
    identifiers: Mapping[str, str] = field(default_factory=dict)
    citation_key: str = ""
    document_kind: str = DOCUMENT_KIND_FULL

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Paper-Referenz."""
        return {
            "paper_id": self.paper_id,
            "document_kind": self.document_kind,
            "source_uri": self.source_uri,
            "identifiers": dict(self.identifiers),
            "citation_key": self.citation_key,
            "snippet": self.snippet,
        }


class ProvenanceAssembler:
    """Stellt Paper-Provenienz direkt aus der Index-Datei zusammen (ohne ``sklearn``).

    Lädt einmalig je Paper die ``source_uri``, das **Leit-Snippet** (Text des ersten Chunks,
    geordnet nach ``row_index``) und den bibliografischen Datensatz und beantwortet daraus
    :class:`PaperRef`-Anfragen.
    """

    def __init__(
        self,
        source_uris: dict[str, str],
        leading_snippets: dict[str, str],
        metadata: dict[str, PaperMetadata] | None = None,
        document_kinds: dict[str, str] | None = None,
    ) -> None:
        self._source_uris = source_uris
        self._leading_snippets = leading_snippets
        self._metadata = metadata or {}
        self._document_kinds = document_kinds or {}

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
            uri_rows = connection.execute(
                "SELECT paper_id, source_uri, document_kind FROM papers"
            ).fetchall()
            snippet_rows = connection.execute(
                "SELECT c.paper_id, c.text FROM chunks c "
                "JOIN (SELECT paper_id, MIN(row_index) AS rmin FROM chunks GROUP BY paper_id) m "
                "ON c.paper_id = m.paper_id AND c.row_index = m.rmin"
            ).fetchall()
        finally:
            connection.close()

        source_uris = {str(row[0]): str(row[1]) for row in uri_rows}
        kinds = {str(row[0]): str(row[2]) for row in uri_rows}
        leading = {str(pid): _snippet(str(text)) for pid, text in snippet_rows}
        return cls(source_uris, leading, load_paper_metadata(path), kinds)

    def metadata(self, paper_id: str) -> PaperMetadata:
        """Liefert den bibliografischen Datensatz eines Papers (unbekannt ⇒ leerer Datensatz)."""
        return self._metadata.get(paper_id, empty_metadata(paper_id))

    def paper_ref(self, paper_id: str) -> PaperRef:
        """Erzeugt einen :class:`PaperRef` (``source_uri`` + Leit-Snippet + Identifikatoren).

        Raises:
            DomainError: ``not_found`` wenn das Paper nicht im Index liegt.
        """
        if paper_id not in self._source_uris:
            raise DomainError(ErrorCode.NOT_FOUND, f"Paper nicht im Index: {paper_id}")
        metadata = self.metadata(paper_id)
        return PaperRef(
            paper_id=paper_id,
            source_uri=self._source_uris[paper_id],
            snippet=self._leading_snippets.get(paper_id, ""),
            identifiers=metadata.identifiers,
            citation_key=metadata.citation_key(),
            document_kind=self._document_kinds.get(paper_id, DOCUMENT_KIND_FULL),
        )
