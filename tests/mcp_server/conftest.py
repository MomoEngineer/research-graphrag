"""Gemeinsame Fixtures der MCP-Server-Tests (Contract- und Beispiel-Tests).

``index_db`` baut einen kleinen, deterministischen Index samt Ähnlichkeits- und
Zitationsgraph aus vier synthetischen Papern (zwei zum Thema Attention/Transformer,
zwei zum Thema Graph/Community-Detection) und richtet den Server per Env darauf aus.
Er wird sowohl von ``test_server.py`` (Contract-Tests) als auch von
``test_spec_examples.py`` (Beispiel-Regression, siehe ``templates/tool-spec.md``
Abschnitt 10) genutzt, damit beide dieselbe Faktenlage teilen statt sie zu duplizieren.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from research_graphrag.extraction.model import (
    SECTION_KIND_BODY,
    SECTION_KIND_REFERENCES,
    Section,
)
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.citation_graph import build_citation_graph
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.metadata_index import build_metadata_index
from research_graphrag.indexing.tfidf_index import build_index


def make_paper(
    paper_id: str,
    texts: Sequence[str],
    *,
    identifiers: dict[str, str] | None = None,
    references: str = "",
) -> CanonicalPaper:
    """Baut ein kleines, deterministisches :class:`CanonicalPaper` für Tests.

    Args:
        paper_id: Stabile Paper-ID.
        texts: Ein Chunk-Text je Seite (Seite 1..n).
        identifiers: Optionale DOI/arXiv-Identifikatoren.
        references: Optionaler Referenzabschnitt-Text (erzeugt eine zusätzliche Seite
            mit ``section_title = "References"`` – Grundlage für ``get_citations``).
    """
    chunks = [
        Chunk(
            chunk_id=f"{paper_id}-c{index:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_id="s-body",
            section_title="Introduction" if index == 0 else "Methods",
        )
        for index, text in enumerate(texts)
    ]
    sections = [
        Section(
            section_id="s-body",
            title="Introduction",
            kind=SECTION_KIND_BODY,
            level=1,
            page_number=1,
            order=0,
        )
    ]
    if references:
        sections.append(
            Section(
                section_id="s-refs",
                title="References",
                kind=SECTION_KIND_REFERENCES,
                level=1,
                page_number=len(texts) + 1,
                order=1,
            )
        )
        chunks.append(
            Chunk(
                chunk_id=f"{paper_id}-c{len(texts):04d}",
                paper_id=paper_id,
                page_number=len(texts) + 1,
                text=references,
                char_count=len(references),
                section_id="s-refs",
                section_title="References",
            )
        )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=len(chunks),
        chunks=tuple(chunks),
        quality_flags=(),
        sections=tuple(sections),
        identifiers=identifiers or {},
    )


@pytest.fixture
def make_paper_fn() -> Callable[..., CanonicalPaper]:
    """Fixture-Zugriff auf :func:`make_paper` für Tests außerhalb dieses Moduls.

    Folgt demselben Factory-Fixture-Muster wie ``make_pdf`` in ``tests/conftest.py``.
    """
    return make_paper


@pytest.fixture
def index_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Baut einen kleinen Index + Graphen und richtet den Server per Env darauf aus.

    Vier Paper: ``aaaa0001``/``aaaa0002`` (Attention/Transformer, ``aaaa0002`` zitiert
    ``aaaa0001`` über die DOI im Referenzabschnitt) und ``bbbb0001``/``bbbb0002``
    (Graph/Community-Detection) – zwei thematisch getrennte Louvain-Communities.
    """
    papers = [
        make_paper(
            "aaaa0001",
            [
                "transformer attention mechanism self attention encoder doi:10.1145/1234",
                "multi head attention transformer sequence model",
            ],
            identifiers={"arxiv": "2405.20455", "doi": "10.1145/1234"},
        ),
        make_paper(
            "aaaa0002",
            [
                "self attention transformer architecture heads",
                "transformer encoder attention pretraining language",
            ],
            references="[1] Vorarbeit zur Aufmerksamkeit. doi:10.1145/1234",
        ),
        make_paper(
            "bbbb0001",
            [
                "graph neural network message passing nodes",
                "graph community detection louvain modularity",
            ],
        ),
        make_paper(
            "bbbb0002",
            [
                "citation graph clustering communities dataset",
                "dataset benchmark evaluation metric accuracy graph",
            ],
        ),
    ]
    db = tmp_path / "index" / "index.sqlite"
    build_index(papers, db)
    build_graph(papers, db)
    build_citation_graph(papers, db)
    build_metadata_index(papers, db)
    monkeypatch.setenv("RESEARCH_GRAPHRAG_INDEX", str(db))
    monkeypatch.setenv(
        "RESEARCH_GRAPHRAG_METADATA", str(tmp_path / "metadata" / "paper_metadata.json")
    )
    monkeypatch.setenv("RESEARCH_GRAPHRAG_DATA", str(tmp_path / "data"))
    return db
