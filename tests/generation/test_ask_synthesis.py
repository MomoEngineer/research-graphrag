"""Test für den CLI-Synthese-Pfad (``scripts.ask --synthese``, Phase 7 / A1, ADR 0012).

Prüft :func:`scripts.ask._render_synthesis` in beiden Fällen: mit einem sampling-fähigen
Provider (belegte Antwort) und mit dem Noop-Fallback (sichtbare Degradation bei voller Evidenz).
Die CLI selbst nutzt offline stets den Noop-Provider – ein Modell steht dort nicht zur Verfügung.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from scripts.ask import _render_synthesis

from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.generation.provider import (
    GenerationRequest,
    GenerationResult,
    NoopGenerationProvider,
    SamplingGenerationProvider,
)
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index

_PAPERS = {
    "aaaa0001": ["transformer attention mechanism self attention", "multi head attention encoder"],
    "aaaa0002": ["self attention transformer architecture", "transformer encoder attention heads"],
}


def _paper(paper_id: str, texts: Sequence[str]) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index + 1:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_title="Introduction",
        )
        for index, text in enumerate(texts)
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=len(texts),
        chunks=chunks,
        quality_flags=(),
    )


@pytest.fixture
def index_db(tmp_path: Path) -> str:
    """Kleiner Index samt Graph für die CLI-Renderer."""
    db = tmp_path / "index" / "index.sqlite"
    papers = [_paper(pid, texts) for pid, texts in _PAPERS.items()]
    build_index(papers, db)
    build_graph(papers, db)
    return str(db)


def test_noop_degrades_visibly_but_keeps_evidence(
    index_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ohne Modell erscheint der Hinweis auf die Degradation – die Belege bleiben vollständig."""
    _render_synthesis("basic", index_db, "transformer attention", 3, NoopGenerationProvider())

    out = capsys.readouterr().out
    assert "Keine generierte Antwort" in out
    assert "[ask] Belege (basic):" in out
    assert "[1] Paper aaaa" in out
    assert "Quelle: file:///aaaa" in out


def test_generated_answer_is_printed_with_model(
    index_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mit Sampling erscheinen Antwort, Modellname und weiterhin alle Belege."""
    seen: list[GenerationRequest] = []

    def sampler(request: GenerationRequest) -> GenerationResult:
        seen.append(request)
        return GenerationResult(text="Aufmerksamkeit ist zentral [1].", generated=True, model="m-1")

    _render_synthesis(
        "basic", index_db, "transformer attention", 3, SamplingGenerationProvider(sampler)
    )

    out = capsys.readouterr().out
    assert "[ask] Antwort (m-1):" in out
    assert "Aufmerksamkeit ist zentral [1]." in out
    assert "[ask] Belege (basic):" in out
    assert "[1] " in seen[0].context


def test_no_match_reports_missing_evidence(
    index_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ohne Treffer wird das ehrlich gemeldet, statt eine Antwort zu erfinden."""
    _render_synthesis("basic", index_db, "zzzqqqwww xxyyzzq", 3, NoopGenerationProvider())

    out = capsys.readouterr().out
    assert "Keine belegten Treffer" in out


@pytest.mark.parametrize("mode", ["basic", "local", "global", "drift"])
def test_all_modes_are_supported(
    index_db: str, mode: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Der Synthese-Pfad steht für alle vier Modi bereit."""
    _render_synthesis(mode, index_db, "transformer attention", 3, NoopGenerationProvider())

    assert capsys.readouterr().out
