"""Phase-6-Regression: Drop-in-Freshness & atomarer Index-Swap.

Sichert die Definition of Done von Phase 6 ab (siehe [Roadmap.md](../../Roadmap.md) und
docs/adr/0010-drop-in-workflow-and-qa-phase6.md): Nach dem Ablegen einer neuen PDF und
erneutem ``ingest`` liefert die **On-Read**-Retrieval-Kette sofort das neue Paper (ohne
Cache-Reset), während unveränderte PDFs übersprungen werden. Der Index-Neuaufbau erfolgt
**atomar** (Build nach ``*.tmp`` + ``os.replace``), sodass ein Fehler den bestehenden Index
nicht beschädigt.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from research_graphrag import pipeline
from research_graphrag.pipeline import ingest
from research_graphrag.retrieval.basic import search_basic

MakePdf = Callable[..., Path]


def test_reingest_serves_new_paper_and_skips_unchanged(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Neue PDF ablegen → ingest → sofort per On-Read abfragbar; unveränderte übersprungen."""
    make_pdf(["graph retrieval augmented generation baseline method"], "papers/a.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    index = data / "index" / "index.sqlite"

    ingest(papers, data)
    # Der distinktive Begriff des neuen Papers ist anfangs nicht auffindbar.
    before = search_basic(index, "zylophon", k=5)
    assert all("zylophon" not in citation.snippet.lower() for citation in before.citations)

    # Neue PDF ablegen und erneut ingest ausführen (voller Re-Index, atomarer Swap).
    make_pdf(["zylophon quantum entanglement singular distinctive topic"], "papers/c.pdf")
    report = ingest(papers, data)

    assert report.extracted == 1  # nur das neue Paper
    assert report.skipped == 1  # unverändertes a.pdf übersprungen
    assert report.n_papers == 2

    # Dieselbe On-Read-Kette (frischer TfidfIndex.load pro Aufruf) sieht das neue Paper sofort.
    after = search_basic(index, "zylophon quantum entanglement", k=5)
    assert after.citations
    assert any("zylophon" in citation.snippet.lower() for citation in after.citations)


def test_ingest_leaves_no_tmp_index_file(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Nach erfolgreichem Ingest existiert keine Temporärdatei des atomaren Swaps."""
    make_pdf(["content for atomic swap check"], "papers/a.pdf")
    data = tmp_path / "data"

    ingest(tmp_path / "papers", data)

    index = data / "index" / "index.sqlite"
    assert index.is_file()
    assert not index.with_name(index.name + ".tmp").exists()


def test_failed_reindex_preserves_previous_index(
    make_pdf: MakePdf, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Schlägt der Index-Bau fehl, bleibt der bestehende Index intakt und abfragbar."""
    make_pdf(["stable alpha content token method"], "papers/a.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    index = data / "index" / "index.sqlite"

    ingest(papers, data)
    assert search_basic(index, "alpha", k=3).citations

    # Eine geänderte PDF erzwingt Re-Extraktion; der Graph-Bau wird zum Scheitern gebracht.
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulierter Graph-Fehler")

    monkeypatch.setattr(pipeline, "build_graph", _boom)
    make_pdf(["changed beta content token method"], "papers/a.pdf")

    with pytest.raises(RuntimeError):
        ingest(papers, data)

    # Alt-Index unverändert vorhanden, weiterhin abfragbar; keine Temporärdatei übrig.
    assert index.is_file()
    assert not index.with_name(index.name + ".tmp").exists()
    assert search_basic(index, "alpha", k=3).citations
