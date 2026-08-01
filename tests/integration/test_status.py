"""Regression für den read-only Status inkl. Zitationsgraph (Phase 6 + ADR 0011).

Sichert ab, dass ``scripts.status`` den Index **vollständig** beschreibt: Nach einem Ingest
erscheinen Zitations-Teilschema und Kantenzahl neben Paper-/Chunk-/Community-Kennzahlen,
ohne dass etwas geschrieben wird.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scripts.status import collect_status, render

from research_graphrag.indexing.citation_graph import CITATION_SCHEMA_VERSION
from research_graphrag.pipeline import ingest

MakePdf = Callable[..., Path]


def test_status_reports_citation_graph(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Der Status meldet Zitations-Teilschema und Kantenzahl passend zum Ingest-Report."""
    make_pdf(
        ["graph retrieval augmented generation over scientific corpora"],
        "papers/Graph Retrieval Augmented Generation for Scientific Corpora.pdf",
    )
    make_pdf(
        [
            "Introduction\n\nwe benchmark retrieval pipelines end to end",
            "References\n\n[1] Graph Retrieval Augmented Generation for Scientific Corpora. 2026.",
        ],
        "papers/Benchmarking Retrieval Pipelines.pdf",
    )
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    report = ingest(papers, data)

    status = collect_status(data, papers)

    assert status.citation_schema_version == CITATION_SCHEMA_VERSION
    assert status.n_citation_edges == report.n_citation_edges == 1
    assert status.consistent
    assert any("Zitationskanten: 1" in line for line in render(status))


def test_status_without_index_reports_no_citation_schema(tmp_path: Path) -> None:
    """Ohne Index bleiben die Zitations-Kennzahlen leer (kein Fehler)."""
    status = collect_status(tmp_path / "data", tmp_path / "papers")

    assert status.index_present is False
    assert status.citation_schema_version is None
    assert status.n_citation_edges == 0
