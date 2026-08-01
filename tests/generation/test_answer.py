"""Tests für die Antwort-Orchestrierung (Router → Evidenz → Synthese, Phase 7 / A1)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.generation.answer import answer_question, resolve_mode
from research_graphrag.generation.provider import (
    GenerationRequest,
    GenerationResult,
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
def index_db(tmp_path: Path) -> Path:
    """Kleiner Index samt Graph."""
    db = tmp_path / "index" / "index.sqlite"
    papers = [_paper(pid, texts) for pid, texts in _PAPERS.items()]
    build_index(papers, db)
    build_graph(papers, db)
    return db


def test_resolve_mode_uses_router_for_auto() -> None:
    """``auto`` wird über die Heuristik aufgelöst (hier: Vergleichsfrage → DRIFT)."""
    assert resolve_mode("Wo widersprechen sich die Ergebnisse?", "auto") == "drift"


def test_resolve_mode_keeps_explicit_mode() -> None:
    """Ein expliziter Modus bleibt unverändert."""
    assert resolve_mode("beliebig", "global") == "global"


def test_resolve_mode_rejects_unknown_mode() -> None:
    """Ein unbekannter Modus meldet ``invalid_input`` mit Aufzählung der erlaubten Werte."""
    with pytest.raises(DomainError) as excinfo:
        resolve_mode("beliebig", "telepathie")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT
    assert "basic" in excinfo.value.message


def test_answer_question_returns_evidence_without_provider(index_db: Path) -> None:
    """Ohne Provider entsteht keine Antwort, aber vollständige, nummerierte Evidenz."""
    result = answer_question(index_db, "transformer attention", mode="basic", k=3)

    assert result.generated is False
    assert result.answer == ""
    assert result.mode == "basic"
    assert [item.index for item in result.evidence.items] == [1, 2, 3]


def test_answer_question_routes_automatically(index_db: Path) -> None:
    """Ohne expliziten Modus entscheidet der Router und meldet den genutzten Modus."""
    result = answer_question(index_db, "Welcher F1-Score wird berichtet?", k=2)

    assert result.mode in {"basic", "local", "global", "drift"}


def test_answer_question_uses_injected_provider(index_db: Path) -> None:
    """Ein sampling-fähiger Provider liefert Antwort und Modell zurück."""

    def sampler(request: GenerationRequest) -> GenerationResult:
        return GenerationResult(text="Antwort [1].", generated=True, model="m-1")

    result = answer_question(
        index_db,
        "transformer attention",
        mode="basic",
        k=2,
        provider=SamplingGenerationProvider(sampler),
    )

    assert result.generated is True
    assert result.answer == "Antwort [1]."
    assert result.model == "m-1"


def test_answer_question_propagates_invalid_k(index_db: Path) -> None:
    """``k <= 0`` wird von der Retrieval-Schicht als ``invalid_input`` gemeldet."""
    with pytest.raises(DomainError) as excinfo:
        answer_question(index_db, "transformer", mode="basic", k=0)

    assert excinfo.value.code is ErrorCode.INVALID_INPUT
