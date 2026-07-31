"""PDF-Extraktion in ein kanonisches Paper-Modell (Offline-Hybrid, Option B).

Nutzt ``pypdf`` (offline, siehe docs/adr/0005-graphrag-index-backend-open.md) und liefert
je Seite einen retrievbaren ``Chunk`` mit Seiten-Provenienz. Das Ergebnis ist ein
deterministisches, serialisierbares :class:`CanonicalPaper` (Canonical JSON), das die
Indexierung konsumiert.

Chunk-Granularität in Phase 0b: **eine Seite = ein Chunk** (feinere Chunking-Strategien
folgen in Phase 2).
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from research_graphrag.errors import DomainError, ErrorCode

SCHEMA_VERSION = "0.1.0"
"""Version des Canonical-JSON-Schemas (für spätere Migrationen)."""


@dataclass(frozen=True)
class Chunk:
    """Kleinste retrievbare Einheit mit Provenienz (Phase 0b: eine Seite)."""

    chunk_id: str
    paper_id: str
    page_number: int
    text: str
    char_count: int


@dataclass(frozen=True)
class CanonicalPaper:
    """Kanonische, serialisierbare Repräsentation eines extrahierten Papers."""

    paper_id: str
    source_uri: str
    source_sha256: str
    n_pages: int
    chunks: tuple[Chunk, ...]
    quality_flags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Paper als Canonical-JSON-kompatibles Dict."""
        return {
            "schema_version": SCHEMA_VERSION,
            "paper_id": self.paper_id,
            "source_uri": self.source_uri,
            "source_sha256": self.source_sha256,
            "n_pages": self.n_pages,
            "quality_flags": list(self.quality_flags),
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "paper_id": chunk.paper_id,
                    "page_number": chunk.page_number,
                    "text": chunk.text,
                    "char_count": chunk.char_count,
                }
                for chunk in self.chunks
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CanonicalPaper:
        """Rekonstruiert ein :class:`CanonicalPaper` aus Canonical JSON."""
        chunks = tuple(
            Chunk(
                chunk_id=str(entry["chunk_id"]),
                paper_id=str(entry["paper_id"]),
                page_number=int(entry["page_number"]),
                text=str(entry["text"]),
                char_count=int(entry["char_count"]),
            )
            for entry in data["chunks"]
        )
        return cls(
            paper_id=str(data["paper_id"]),
            source_uri=str(data["source_uri"]),
            source_sha256=str(data["source_sha256"]),
            n_pages=int(data["n_pages"]),
            chunks=chunks,
            quality_flags=tuple(str(flag) for flag in data.get("quality_flags", [])),
        )

    def save_json(self, path: str | Path) -> None:
        """Schreibt das Canonical JSON (UTF-8) und legt Elternordner an."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load_json(cls, path: str | Path) -> CanonicalPaper:
        """Lädt ein Canonical JSON und rekonstruiert das :class:`CanonicalPaper`."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


def extract_pdf(path: str | Path, *, source_uri: str | None = None) -> CanonicalPaper:
    """Extrahiert ein PDF in ein :class:`CanonicalPaper` (eine Seite = ein Chunk).

    Args:
        path: Dateisystempfad zur PDF-Datei.
        source_uri: Optionale Quell-URI für die Provenienz; Standard ist die ``file://``-URI
            des aufgelösten Pfads.

    Returns:
        Ein :class:`CanonicalPaper` mit Seiten-Chunks, Rohbyte-SHA-256 und Qualitäts-Flags.

    Raises:
        DomainError: ``invalid_input`` bei leerem Pfad; ``not_found`` wenn die Datei fehlt;
            ``parse_error`` wenn das PDF nicht parsebar ist; ``internal_error`` bei
            OS-Lesefehlern (siehe docs/error-model.md).
    """
    if not str(path).strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leerer PDF-Pfad.")

    pdf_path = Path(path)
    uri = source_uri or pdf_path.resolve().as_uri()

    if not pdf_path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"PDF nicht gefunden: {pdf_path}", {"uri": uri})

    try:
        raw = pdf_path.read_bytes()
    except OSError as exc:
        raise DomainError(
            ErrorCode.INTERNAL_ERROR, f"PDF nicht lesbar: {exc}", {"uri": uri}
        ) from exc

    source_sha256 = hashlib.sha256(raw).hexdigest()
    paper_id = source_sha256[:16]

    try:
        reader = PdfReader(io.BytesIO(raw))
        page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    except PyPdfError as exc:
        raise DomainError(
            ErrorCode.PARSE_ERROR, f"PDF nicht parsebar: {exc}", {"uri": uri}
        ) from exc

    chunks: list[Chunk] = []
    quality_flags: list[str] = []
    for index, text in enumerate(page_texts):
        page_number = index + 1
        if not text:
            quality_flags.append(f"empty_page:{page_number}")
        chunks.append(
            Chunk(
                chunk_id=f"{paper_id}-p{page_number}",
                paper_id=paper_id,
                page_number=page_number,
                text=text,
                char_count=len(text),
            )
        )

    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=uri,
        source_sha256=source_sha256,
        n_pages=len(page_texts),
        chunks=tuple(chunks),
        quality_flags=tuple(quality_flags),
    )
