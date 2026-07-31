"""Integrations-Durchstich (Roadmap M1): 1 PDF → Ingestion → belegte Antwort.

Prüft die gesamte Offline-Hybrid-Kette (pypdf → TF-IDF/SQLite → Basic Search) end-to-end
und stellt sicher, dass eine Detailfrage die korrekte **Seiten-Provenienz** liefert.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from research_graphrag.indexing.graph_index import load_communities
from research_graphrag.pipeline import ingest
from research_graphrag.retrieval.basic import search_basic

MakePdf = Callable[..., Path]


def test_m1_durchstich_answers_with_page_provenance(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Eine Frage nach dem F1-Score verweist auf die korrekte Seite (Provenienz)."""
    make_pdf(
        [
            "The proposed method uses a transformer attention mechanism.",
            "Evaluation on the benchmark dataset reports an F1 score of 0.87.",
        ],
        "papers/paper.pdf",
    )
    papers = tmp_path / "papers"
    data = tmp_path / "data"

    report = ingest(papers, data)
    result = search_basic(data / "index" / "index.sqlite", "reported F1 score", k=3)

    assert report.n_papers == 1
    assert report.indexed_chunks == 2
    assert result.citations, "Es sollte mindestens ein belegter Treffer vorhanden sein."
    top = result.citations[0]
    assert top.page_number == 2  # die F1-Aussage steht auf Seite 2
    assert top.score > 0.0
    assert top.source_uri.startswith("file:")


def test_phase3_ingest_builds_graph_and_graph_info_lists_communities(
    make_pdf: MakePdf,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-End (Phase 3): Ingestion baut den Graphen; graph_info listet die Communities."""
    make_pdf(
        ["transformer attention mechanism encoder", "self attention transformer heads"],
        "papers/a.pdf",
    )
    make_pdf(
        ["citation network louvain community detection", "graph clustering modularity communities"],
        "papers/b.pdf",
    )
    data = tmp_path / "data"

    report = ingest(tmp_path / "papers", data)
    db = data / "index" / "index.sqlite"

    assert report.n_nodes == 2
    assert report.n_communities >= 1
    communities = load_communities(db)
    assert communities

    from scripts.graph_info import main

    monkeypatch.setattr("sys.argv", ["graph_info", "--index", str(db)])
    exit_code = main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Communities" in output
