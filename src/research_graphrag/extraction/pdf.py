"""PDF-Extraktion in ein kanonisches Paper-Modell (Offline-Hybrid, Option B).

Orchestriert die Phase-2-Extraktion mit ``pypdf`` (offline, siehe
docs/adr/0005-graphrag-index-backend-open.md): Seitentext lesen → Struktur/Abschnitte erkennen
(:mod:`~research_graphrag.extraction.structure`) → größenbasiert chunken
(:mod:`~research_graphrag.extraction.chunking`) → Qualitäts-Gates
(:mod:`~research_graphrag.extraction.quality`). Das Ergebnis ist ein deterministisches,
serialisierbares :class:`CanonicalPaper` (Canonical JSON, Schema 0.3.0).

Umfang und Grenzen der Heuristik (keine Bounding-Boxes, kein tiefes Referenz-/Tabellen-Parsing):
docs/adr/0006-canonical-model-phase2-scope.md.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction import chunking, quality, structure
from research_graphrag.extraction.model import (
    SCHEMA_VERSION,
    CanonicalPaper,
    Chunk,
    Section,
)

__all__ = ["SCHEMA_VERSION", "CanonicalPaper", "Chunk", "Section", "extract_pdf"]


def extract_pdf(path: str | Path, *, source_uri: str | None = None) -> CanonicalPaper:
    """Extrahiert ein PDF in ein :class:`CanonicalPaper` (Struktur, Chunks, Qualität).

    Args:
        path: Dateisystempfad zur PDF-Datei.
        source_uri: Optionale Quell-URI für die Provenienz; Standard ist die ``file://``-URI
            des aufgelösten Pfads.

    Returns:
        Ein :class:`CanonicalPaper` mit Abschnitten, größenbasierten Chunks (Seiten-/Section-
        Provenienz), DOI/arXiv-Identifikatoren und Qualitäts-Flags.

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

    pages = [(index + 1, text) for index, text in enumerate(page_texts)]
    sectioning = structure.analyze(paper_id, pages)
    # Identifikatoren bevorzugt von der Titelseite lesen (die eigene DOI/arXiv-ID steht dort);
    # erst bei Fehlanzeige den Volltext heranziehen (dort meist nur zitierte Referenzen).
    identifiers = structure.extract_identifiers("\n".join(page_texts[:2])) or (
        structure.extract_identifiers("\n".join(page_texts))
    )
    chunks = chunking.build_chunks(paper_id, sectioning.blocks, sectioning.title_by_id())
    quality_flags = quality.assess(pages, sectioning.sections, chunks)

    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=uri,
        source_sha256=source_sha256,
        n_pages=len(page_texts),
        chunks=chunks,
        quality_flags=quality_flags,
        sections=sectioning.sections,
        identifiers=identifiers,
    )
