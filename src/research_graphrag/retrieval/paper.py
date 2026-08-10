"""get_paper: Paper-Detailabruf aus dem Index (Phase 5, Offline-Hybrid, Option B).

Liefert die Metadaten eines einzelnen Papers **direkt aus der Index-SQLite** (Source of
Truth) – ``paper_id``-basiert, ohne Datei-Pfad und ohne den gitignorierten Canonical-Cache
zu lesen. Ausgabe für einen Agenten: Quelle, Identifikatoren (DOI/arXiv), Umfang,
Abschnittstitel und ein Leit-Snippet. Grundsatz: docs/adr/0009-mcp-server-stdio-phase5.md.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from research_graphrag.bibliography.model import PaperMetadata, empty_metadata
from research_graphrag.bibliography.styles import reference_payload
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import DOCUMENT_KIND_FULL
from research_graphrag.indexing.metadata_index import load_paper_metadata

_SNIPPET_LIMIT = 200


def _snippet(text: str, limit: int = _SNIPPET_LIMIT) -> str:
    """Erzeugt einen einzeiligen, gekürzten Ausschnitt (Leit-Snippet)."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


@dataclass(frozen=True)
class PaperDetail:
    """Metadaten eines Papers (Paper-Ebene), zusammengestellt aus dem Index.

    ``sections`` sind die eindeutigen (heuristischen) Abschnittstitel in Dokument-Reihenfolge;
    ``snippet`` ist der Ausschnitt des ersten nicht-leeren Chunks (extraktiver Anker).
    ``identifiers`` bleibt die **extrahierte** Rohsicht aus der Tabelle ``papers``; der
    aufgelöste, zitierfähige Datensatz steht in ``reference``
    (docs/adr/0025-citable-paper-metadata.md).

    ``document_kind`` trennt Volltexte von **Referenz-Einträgen**. Gerade hier ist das Feld
    unverzichtbar: ``n_pages = 0`` und ``n_chunks = 1`` sähen sonst nach einem defekten
    Volltext aus statt nach einem bewusst unvollständigen Eintrag
    (docs/adr/0031-reference-contract-and-guardrail-phase13.md).
    """

    paper_id: str
    source_uri: str
    identifiers: dict[str, str]
    n_pages: int
    n_chunks: int
    sections: tuple[str, ...]
    snippet: str
    reference: PaperMetadata = field(default_factory=lambda: empty_metadata(""))
    document_kind: str = DOCUMENT_KIND_FULL

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Paper-Metadaten (Output-Schema des Tools ``get_paper``)."""
        return {
            "paper_id": self.paper_id,
            "document_kind": self.document_kind,
            "source_uri": self.source_uri,
            "identifiers": dict(self.identifiers),
            "n_pages": self.n_pages,
            "n_chunks": self.n_chunks,
            "sections": list(self.sections),
            "snippet": self.snippet,
            "reference": reference_payload(self.reference),
        }


def get_paper(db_path: str | Path, paper_id: str) -> PaperDetail:
    """Lädt die Metadaten eines Papers aus dem Index (``paper_id``-basiert).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        paper_id: Stabile Paper-ID (kein Datei-Pfad).

    Returns:
        Ein :class:`PaperDetail` mit Quelle, Identifikatoren, Umfang, Abschnittstiteln und
        Leit-Snippet.

    Raises:
        DomainError: ``invalid_input`` bei leerer ``paper_id``; ``not_found`` wenn die
            Index-Datei fehlt oder die ``paper_id`` unbekannt ist (siehe docs/error-model.md).
    """
    if not paper_id.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leere paper_id.")

    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")

    connection = sqlite3.connect(str(path))
    try:
        paper_row = connection.execute(
            "SELECT source_uri, n_pages, identifiers, document_kind FROM papers WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()
        if paper_row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"Paper nicht gefunden: {paper_id}")
        chunk_rows = connection.execute(
            "SELECT text, section_title FROM chunks WHERE paper_id = ? ORDER BY row_index",
            (paper_id,),
        ).fetchall()
    finally:
        connection.close()

    identifiers = {str(key): str(value) for key, value in json.loads(str(paper_row[2])).items()}

    sections: list[str] = []
    seen_sections: set[str] = set()
    leading = ""
    for text, section_title in chunk_rows:
        if not leading and str(text).strip():
            leading = _snippet(str(text))
        title = str(section_title)
        if title and title not in seen_sections:
            seen_sections.add(title)
            sections.append(title)

    return PaperDetail(
        paper_id=paper_id,
        source_uri=str(paper_row[0]),
        identifiers=identifiers,
        n_pages=int(paper_row[1]),
        n_chunks=len(chunk_rows),
        sections=tuple(sections),
        snippet=leading,
        reference=load_paper_metadata(path).get(paper_id, empty_metadata(paper_id)),
        document_kind=str(paper_row[3]),
    )
