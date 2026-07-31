"""Integrations-Durchstich (Roadmap M1): 1 PDF → Ingestion → belegte Antwort.

Prüft die gesamte Offline-Hybrid-Kette (pypdf → TF-IDF/SQLite → Basic Search) end-to-end
und stellt sicher, dass eine Detailfrage die korrekte **Seiten-Provenienz** liefert.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

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
