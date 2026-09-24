"""Gemeinsame Test-Fixtures.

Asynchrone Tests laufen über das ``anyio``-Pytest-Plugin (siehe
docs/adr/0003-offline-test-and-coverage-tooling.md); als Backend wird ``asyncio``
fixiert. ``make_pdf`` erzeugt kleine PDF-Fixtures (reportlab) für Extraktions-Tests.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Fixiert das anyio-Backend auf ``asyncio`` für alle async-Tests."""
    return "asyncio"


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    """Factory: erzeugt ein PDF mit je einem Textblock pro Seite.

    Args:
        pages: Seitentexte (ein Eintrag pro Seite; Zeilenumbrüche je Seite erlaubt).
        name: Dateiname innerhalb des tmp-Verzeichnisses.

    Returns:
        Pfad zum erzeugten PDF.
    """

    def _make(pages: Sequence[str], name: str = "sample.pdf") -> Path:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(path), pagesize=A4)
        for page_text in pages:
            lines = page_text.splitlines() or [""]
            for index, line in enumerate(lines):
                pdf.drawString(72, 780 - index * 14, line)
            pdf.showPage()
        pdf.save()
        return path

    return _make


@pytest.fixture
def make_person_index(tmp_path: Path) -> Callable[..., Path]:
    """Factory: kleiner Index mit Personenebene (Phase 17 / A4).

    Geteilt von ``tests/retrieval/test_authors.py`` und ``tests/mcp_server/test_person_tools.py``,
    damit Funktions- und Contract-Tests dieselbe Faktenlage prüfen. Sechs Volltexte:

    * ``aaaa0001`` (2024): Akari Asai (A5023888391), Zeqiu Wu, Hannaneh Hajishirzi (A5000000003).
    * ``aaaa0002`` (2025): „Asai, Akari“ (A5023888391), Bert Muster, Zeqiu Wu; zitiert
      ``aaaa0001`` (Selbstzitat) und ``cccc0001``.
    * ``bbbb0001`` (2023): „Akari Asai“ **ohne** Kennung (Namensidentität); zitiert ``aaaa0001``.
    * ``cccc0001`` (2022): Bert Muster, Hannaneh Hajishirzi (A5000000003); zitiert ``aaaa0001``
      und ``aaaa0002``.
    * ``dddd0001``: Asai (A5023888391), aber nur ``weak`` belegt – gehört nicht zur Person.
    * ``eeee0001``: ohne Zitierdaten.

    Die Personenebene deckt damit vier von sechs Volltexten ab.

    Args (des Aufrufs):
        graph: Ähnlichkeitsgraph samt Communities bauen.
        citations: Zitationsgraph bauen.
        authors: Autorenindex bauen (ohne: Index von vor Phase 17 / A3).
    """
    from research_graphrag.bibliography.model import (
        CONFIDENCE_STRONG,
        CONFIDENCE_WEAK,
        ORIGIN_RESOLVED,
        MetadataRecord,
    )
    from research_graphrag.bibliography.store import save_records
    from research_graphrag.extraction.model import (
        SECTION_KIND_BODY,
        SECTION_KIND_REFERENCES,
        Section,
    )
    from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
    from research_graphrag.indexing.author_index import build_author_index
    from research_graphrag.indexing.citation_graph import build_citation_graph
    from research_graphrag.indexing.graph_index import build_graph
    from research_graphrag.indexing.metadata_index import build_metadata_index
    from research_graphrag.indexing.tfidf_index import build_index

    def _paper(paper_id: str, text: str, doi: str = "", references: str = "") -> CanonicalPaper:
        # Die eigene DOI muss auf der Titelseite stehen, sonst ist das Paper kein Kantenziel.
        body = f"{text} doi:{doi}" if doi else text
        texts = [body] + ([references] if references else [])
        sections = [
            Section("s-body", "Introduction", SECTION_KIND_BODY, 1, 1, 0),
            Section("s-refs", "References", SECTION_KIND_REFERENCES, 1, 2, 1),
        ]
        return CanonicalPaper(
            paper_id=paper_id,
            source_uri=f"file:///{paper_id}.pdf",
            source_sha256="0" * 64,
            n_pages=len(texts),
            chunks=tuple(
                Chunk(
                    chunk_id=f"{paper_id}-c{index:04d}",
                    paper_id=paper_id,
                    page_number=index + 1,
                    text=chunk_text,
                    char_count=len(chunk_text),
                    section_id=sections[index].section_id,
                    section_title=sections[index].title,
                )
                for index, chunk_text in enumerate(texts)
            ),
            quality_flags=(),
            sections=tuple(sections[: len(texts)]),
            identifiers={"doi": doi} if doi else {},
        )

    def _record(
        paper_id: str,
        title: str,
        year: int,
        authors: Sequence[str],
        ids: Sequence[str],
        doi: str = "",
        confidence: str = CONFIDENCE_STRONG,
    ) -> MetadataRecord:
        return MetadataRecord(
            paper_id=paper_id,
            origin=ORIGIN_RESOLVED,
            title=title,
            authors=tuple(authors),
            year=year,
            doi=doi,
            confidence=confidence,
            author_ids=tuple(ids),
        )

    def _build(*, graph: bool = True, citations: bool = True, authors: bool = True) -> Path:
        papers = [
            _paper(
                "aaaa0001",
                "retrieval augmented generation with self reflection attention critique tokens",
                doi="10.1000/selfrag",
            ),
            _paper(
                "aaaa0002",
                "reflection tokens attention retrieval augmented language model training",
                doi="10.1000/reflect",
                references="[1] Self-RAG. doi:10.1000/selfrag [2] Muster. doi:10.1000/muster",
            ),
            _paper(
                "bbbb0001",
                "graph neural network message passing community detection",
                references="[1] Self-RAG. doi:10.1000/selfrag",
            ),
            _paper(
                "cccc0001",
                "graph community detection louvain modularity clustering",
                doi="10.1000/muster",
                references="[1] doi:10.1000/selfrag [2] doi:10.1000/reflect",
            ),
            _paper(
                "dddd0001",
                "attention attention attention transformer encoder attention heads",
            ),
            _paper("eeee0001", "graph clustering benchmark dataset communities evaluation"),
        ]
        metadata = tmp_path / "person" / "paper_metadata.json"
        save_records(
            metadata,
            [
                _record(
                    "aaaa0001",
                    "Self-RAG: Learning to Retrieve, Generate, and Critique",
                    2024,
                    ["Akari Asai", "Zeqiu Wu", "Hannaneh Hajishirzi"],
                    ["A5023888391", "", "A5000000003"],
                    doi="10.1000/selfrag",
                ),
                _record(
                    "aaaa0002",
                    "Reflection Tokens for Retrieval",
                    2025,
                    ["Asai, Akari", "Bert Muster", "Zeqiu Wu"],
                    ["A5023888391", "", ""],
                    doi="10.1000/reflect",
                ),
                _record("bbbb0001", "Message Passing on Graphs", 2023, ["Akari Asai"], [""]),
                _record(
                    "cccc0001",
                    "Louvain Communities Revisited",
                    2022,
                    ["Bert Muster", "Hannaneh Hajishirzi"],
                    ["", "A5000000003"],
                    doi="10.1000/muster",
                ),
                _record(
                    "dddd0001",
                    "Attention Heads",
                    2021,
                    ["Akari Asai"],
                    ["A5023888391"],
                    confidence=CONFIDENCE_WEAK,
                ),
            ],
        )
        db = tmp_path / "person" / "index" / "index.sqlite"
        build_index(papers, db)
        if graph:
            build_graph(papers, db)
        if citations:
            build_citation_graph(papers, db)
        build_metadata_index(papers, db, metadata_file=metadata)
        if authors:
            build_author_index(db)
        return db

    return _build
