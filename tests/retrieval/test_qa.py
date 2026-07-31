"""Phase-6-QS-Regression: das feste Prüf-Fragen-Set liefert wohlgeformte Provenienz.

Prüft die Mechanik der QS-Harness (``scripts/qa.py``) deterministisch gegen einen kleinen
Fixture-Korpus: Jede Prüf-Frage läuft im erwarteten Modus, liefert – sofern nicht leer –
**gültige** Provenienz (existierende ``paper_id``, Seite ≥ 1, ``file:``-Quelle), und
Global/DRIFT liefern auf jedem nicht-leeren Korpus mindestens eine Community. Der reale
145-Paper-Durchlauf bleibt die separate, manuelle Stichprobe (eval/pruef-fragen.md).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from scripts.qa import QUESTIONS, Question, run_question

from research_graphrag.pipeline import ingest
from research_graphrag.retrieval.router import MODES

MakePdf = Callable[..., Path]


@pytest.fixture
def qa_index(make_pdf: MakePdf, tmp_path: Path) -> Path:
    """Baut einen kleinen Fixture-Index, dessen Text die Prüf-Fragen-Begriffe abdeckt."""
    make_pdf(
        [
            "graph retrieval augmented generation evaluated on datasets with F1 score metrics",
            "the graphrag workflow has key stages indexing retrieval and generation",
        ],
        "papers/a.pdf",
    )
    make_pdf(
        ["knowledge graph methods support repository level code generation approach"],
        "papers/b.pdf",
    )
    make_pdf(
        ["comparison of vector retrieval versus graph retrieval for agentic search"],
        "papers/c.pdf",
    )
    make_pdf(
        ["louvain community detection modularity clustering over citation networks"],
        "papers/d.pdf",
    )
    data = tmp_path / "data"
    ingest(tmp_path / "papers", data)
    return data / "index" / "index.sqlite"


def _index_paper_ids(db_path: Path) -> set[str]:
    """Liest die Paper-IDs des Index (zur Provenienz-Validierung)."""
    connection = sqlite3.connect(str(db_path))
    try:
        return {str(row[0]) for row in connection.execute("SELECT paper_id FROM papers")}
    finally:
        connection.close()


def test_questions_cover_all_modes_with_unique_ids() -> None:
    """Das Frageset deckt alle vier Modi ab und hat eindeutige IDs (Single Source of Truth)."""
    assert {question.mode for question in QUESTIONS} == set(MODES)
    assert all(question.mode in MODES for question in QUESTIONS)
    assert len({question.qid for question in QUESTIONS}) == len(QUESTIONS)


def test_each_question_yields_wellformed_provenance(qa_index: Path) -> None:
    """Jede Frage liefert – sofern nicht leer – gültige Provenienz und stürzt nie ab."""
    paper_ids = _index_paper_ids(qa_index)
    for question in QUESTIONS:
        result = run_question(qa_index, question, k=5)
        for entry in result.provenance:
            if entry["kind"] == "chunk":
                assert entry["paper_id"] in paper_ids
                assert entry["page_number"] >= 1
                assert entry["source_uri"].startswith("file:")
            else:
                assert entry["kind"] == "community"
                assert entry["size"] >= 1
                assert set(entry["representatives"]) <= paper_ids


def test_global_and_drift_surface_communities_for_matching_query(qa_index: Path) -> None:
    """Eine fixture-nahe Anfrage liefert im Global- und DRIFT-Modus mindestens eine Community.

    Die korpus-spezifischen QUESTIONS (z. B. S1 „research directions") teilen bewusst kein
    Vokabular mit dem winzigen Fixture-Korpus; ``rank_communities`` filtert dann korrekt auf
    Score > 0. Dieser Test belegt daher das End-to-End-Surfacing mit einer passenden Anfrage.
    """
    for mode in ("global", "drift"):
        question = Question("X", "graph retrieval approaches", mode, "fixture-nahe Anfrage")
        result = run_question(qa_index, question, k=5)
        assert any(entry["kind"] == "community" for entry in result.provenance), mode


def test_basic_questions_return_citations(qa_index: Path) -> None:
    """Mindestens eine Basic-Frage liefert Chunk-Belege (Fixture enthält 'datasets'/'F1')."""
    answered = sum(
        1
        for question in QUESTIONS
        if question.mode == "basic" and run_question(qa_index, question, k=5).provenance
    )
    assert answered >= 1


def test_global_provenance_is_community_only(qa_index: Path) -> None:
    """Global-Fragen liefern ausschließlich Community-Provenienz (keine Chunk-Belege)."""
    for question in QUESTIONS:
        if question.mode == "global":
            result = run_question(qa_index, question, k=3)
            assert all(entry["kind"] == "community" for entry in result.provenance)
