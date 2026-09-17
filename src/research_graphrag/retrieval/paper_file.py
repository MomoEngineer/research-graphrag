"""get_paper_file: lokaler Dateipfad des Original-PDFs eines Papers (ADR 0039).

Liefert den Dateisystem-Pfad zum Original-PDF eines Papers, sofern lokal vorhanden – **ohne**
Datei-Bytes zu übertragen (kollidiert mit der gemessenen 1-MB-Antwortgrenze bei den meisten
realen Papern, docs/adr/0037-mcp-tool-response-size-ceiling.md). Referenz-Einträge ohne Volltext
und ein zwischenzeitlich verschobenes/gelöschtes ``papers/``-Verzeichnis (nicht versionierter
Symlink) werden einheitlich als ``available = false`` ausgewiesen, nicht als Fehler – dieselbe
„Abweichung sichtbar machen, nicht verstecken"-Regel wie beim DRIFT-``fallback`` oder
``list_topics``s ``truncated`` (docs/adr/0039-correction-tool-and-pdf-file-access.md).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import url2pathname

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import DOCUMENT_KIND_REFERENCE

REASON_REFERENCE_ONLY = "reference_only"
"""``reason``, wenn das Paper ein Referenz-Eintrag ohne Volltext ist."""

REASON_FILE_MISSING = "file_missing"
"""``reason``, wenn der Index ein Volltext-PDF verzeichnet, es aber lokal nicht auffindbar ist."""

_REFERENCE_NOTE = "Referenz-Eintrag ohne Volltext – kein lokales PDF vorhanden."


def _path_from_file_uri(uri: str) -> Path | None:
    """Wandelt eine ``file://``-URI in einen nativen Dateisystem-Pfad um (sonst ``None``).

    Nutzt ausschließlich Stdlib-Bausteine (``urlsplit`` + ``url2pathname``) statt eigenem
    URI-Parsing – korrekt sowohl für lokale Laufwerkspfade (``file:///C:/…``) als auch für
    UNC-Freigaben (``file://host/share/…``).
    """
    parts = urlsplit(uri)
    if parts.scheme != "file":
        return None
    netloc = f"//{parts.netloc}" if parts.netloc else ""
    return Path(url2pathname(netloc + parts.path))


@dataclass(frozen=True)
class PaperFileResult:
    """Ergebnis eines ``get_paper_file``-Aufrufs (siehe specs/get_paper_file.md)."""

    paper_id: str
    document_kind: str
    available: bool
    path: str
    source_uri: str
    size_bytes: int
    reason: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema des Tools ``get_paper_file``)."""
        return {
            "paper_id": self.paper_id,
            "document_kind": self.document_kind,
            "available": self.available,
            "path": self.path,
            "source_uri": self.source_uri,
            "size_bytes": self.size_bytes,
            "reason": self.reason,
            "note": self.note,
        }


def get_paper_file(db_path: str | Path, paper_id: str) -> PaperFileResult:
    """Löst den lokalen PDF-Pfad eines Papers auf (siehe specs/get_paper_file.md).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        paper_id: Stabile Paper-ID (kein Datei-Pfad).

    Returns:
        Ein :class:`PaperFileResult`. ``available = false`` bei Referenz-Einträgen oder einem
        lokal nicht auffindbaren PDF – das ist **kein** Fehler (siehe Moduldoc).

    Raises:
        DomainError: ``invalid_input`` bei leerer ``paper_id``; ``not_found``, wenn die
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
            "SELECT source_uri, document_kind FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise DomainError(ErrorCode.NOT_FOUND, f"Paper nicht gefunden: {paper_id}")

    source_uri = str(row[0])
    document_kind = str(row[1])

    if document_kind == DOCUMENT_KIND_REFERENCE:
        return PaperFileResult(
            paper_id=paper_id,
            document_kind=document_kind,
            available=False,
            path="",
            source_uri=source_uri,
            size_bytes=0,
            reason=REASON_REFERENCE_ONLY,
            note=_REFERENCE_NOTE,
        )

    native_path = _path_from_file_uri(source_uri)
    if native_path is not None and native_path.is_file():
        return PaperFileResult(
            paper_id=paper_id,
            document_kind=document_kind,
            available=True,
            path=str(native_path),
            source_uri=source_uri,
            size_bytes=native_path.stat().st_size,
            reason="",
            note="",
        )

    return PaperFileResult(
        paper_id=paper_id,
        document_kind=document_kind,
        available=False,
        path="",
        source_uri=source_uri,
        size_bytes=0,
        reason=REASON_FILE_MISSING,
        note=f"Volltext im Index verzeichnet, aber lokal nicht auffindbar: {source_uri}",
    )
