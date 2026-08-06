"""get_reference: fertige Literaturangabe zu einem Paper (Phase 12 / K1).

Liefert den aufgelösten bibliografischen Datensatz eines Papers **inklusive** der fertigen
Angaben in Harvard und APA sowie der zugehörigen Kurzbelege. Damit entfällt der Schritt, einen
Identifikator erst von Hand aufzulösen und die Angabe selbst zu bauen
(docs/adr/0025-citable-paper-metadata.md).

Ist der Datensatz unvollständig (es fehlen Autoren, Titel oder Jahr), wird das **ausgewiesen**
statt geraten: ``citable = false`` samt Klartext-Hinweis, welche Felder fehlen und wie sie
ergänzt werden.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.bibliography.model import (
    CITABLE_FIELDS,
    PaperMetadata,
    empty_metadata,
)
from research_graphrag.bibliography.styles import STYLES, reference_payload
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.metadata_index import load_paper_metadata

_FIELD_LABELS = {"title": "Titel", "authors": "Autoren", "year": "Jahr"}

COMPLETION_HINT = (
    "Fehlende Felder ergänzt der Auflösungslauf `python -m scripts.resolve_metadata` "
    "oder ein Eintrag der Herkunft 'manual' in metadata/paper_metadata.json."
)
"""Handlungsleitender Hinweis bei unvollständigen Datensätzen."""


@dataclass(frozen=True)
class ReferenceResult:
    """Die Literaturangabe eines Papers samt Vollständigkeits-Diagnose."""

    paper_id: str
    source_uri: str
    metadata: PaperMetadata
    missing: tuple[str, ...]

    @property
    def note(self) -> str:
        """Klartext-Diagnose: leer bei vollständigem Datensatz, sonst der fehlende Teil."""
        if not self.missing:
            return ""
        labels = ", ".join(_FIELD_LABELS.get(name, name) for name in self.missing)
        return f"Unvollständige Angabe – es fehlen: {labels}. {COMPLETION_HINT}"

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema des Tools ``get_reference``)."""
        return {
            "paper_id": self.paper_id,
            "source_uri": self.source_uri,
            "styles": list(STYLES),
            "reference": reference_payload(self.metadata),
            "missing": list(self.missing),
            "note": self.note,
        }


def _missing_fields(metadata: PaperMetadata) -> tuple[str, ...]:
    """Ermittelt die für eine vollständige Angabe fehlenden Pflichtfelder."""
    missing: list[str] = []
    for name in CITABLE_FIELDS:
        value = getattr(metadata, name)
        if not value:
            missing.append(name)
    return tuple(missing)


def get_reference(db_path: str | Path, paper_id: str) -> ReferenceResult:
    """Stellt die Literaturangabe eines Papers zusammen.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        paper_id: Stabile Paper-ID (kein Datei-Pfad).

    Returns:
        Ein :class:`ReferenceResult` mit beiden Stilen und der Vollständigkeits-Diagnose.

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
        row = connection.execute(
            "SELECT source_uri FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise DomainError(ErrorCode.NOT_FOUND, f"Paper nicht gefunden: {paper_id}")

    metadata = load_paper_metadata(path).get(paper_id, empty_metadata(paper_id))
    return ReferenceResult(
        paper_id=paper_id,
        source_uri=str(row[0]),
        metadata=metadata,
        missing=_missing_fields(metadata),
    )
