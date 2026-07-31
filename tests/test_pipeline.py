"""Tests für die Drop-in-Ingestion (AP4, Offline-Hybrid)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.pipeline import ingest
from research_graphrag.retrieval.basic import search_basic

MakePdf = Callable[..., Path]


def test_ingest_extracts_indexes_and_is_queryable(make_pdf: MakePdf, tmp_path: Path) -> None:
    """papers/ → Canonical + Index; anschließend per Basic Search mit Provenienz abfragbar."""
    make_pdf(["alpha attention transformer method"], "papers/a.pdf")
    make_pdf(["beta dataset evaluation reports F1"], "papers/b.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"

    report = ingest(papers, data)

    assert report.extracted == 2
    assert report.skipped == 0
    assert report.n_papers == 2
    assert report.indexed_chunks == 2
    assert (data / "manifest.json").is_file()
    assert (data / "index" / "index.sqlite").is_file()

    result = search_basic(data / "index" / "index.sqlite", "dataset evaluation", k=3)
    assert result.citations
    assert result.citations[0].source_uri.startswith("file:")


def test_ingest_skips_unchanged_on_second_run(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Ein zweiter Lauf ohne Änderungen extrahiert nichts neu (Dedup)."""
    make_pdf(["stable content for dedup"], "papers/a.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"

    ingest(papers, data)
    report = ingest(papers, data)

    assert report.extracted == 0
    assert report.skipped == 1
    assert report.n_papers == 1


def test_ingest_missing_papers_dir_raises_not_found(tmp_path: Path) -> None:
    """Fehlender papers-Ordner -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        ingest(tmp_path / "nope", tmp_path / "data")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_ingest_empty_papers_dir_raises_invalid_input(tmp_path: Path) -> None:
    """Leerer papers-Ordner -> invalid_input (nichts zu indexieren)."""
    papers = tmp_path / "papers"
    papers.mkdir()
    with pytest.raises(DomainError) as excinfo:
        ingest(papers, tmp_path / "data")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_ingest_reextracts_and_cleans_stale_on_change(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Ändert sich eine PDF, wird neu extrahiert und das veraltete Canonical entfernt."""
    make_pdf(["first version alpha token"], "papers/a.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    ingest(papers, data)

    make_pdf(["second version beta gamma token"], "papers/a.pdf")
    report = ingest(papers, data)

    assert report.extracted == 1
    assert report.skipped == 0
    assert report.n_papers == 1  # kein verwaistes Canonical
    stale = search_basic(data / "index" / "index.sqlite", "alpha", k=5)
    assert stale.citations == ()


def test_ingest_reextracts_when_canonical_missing(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Fehlt das Canonical trotz Manifest, wird erneut extrahiert."""
    make_pdf(["stable content delta"], "papers/a.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    ingest(papers, data)

    for canonical in (data / "canonical").glob("*.json"):
        canonical.unlink()
    report = ingest(papers, data)

    assert report.extracted == 1


def test_ingest_indexes_only_non_empty_pages(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Leere Seiten werden nicht indexiert (nur nicht-leere Chunks)."""
    make_pdf(["real content on page one", ""], "papers/a.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"

    report = ingest(papers, data)

    assert report.n_papers == 1
    assert report.indexed_chunks == 1


def test_ingest_writes_quality_report(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Der Ingest schreibt einen Qualitätsreport (JSON + Markdown) und zählt Flags."""
    make_pdf(["short page"], "papers/a.pdf")
    data = tmp_path / "data"

    report = ingest(tmp_path / "papers", data)

    assert (data / "quality_report.json").is_file()
    assert (data / "quality_report.md").is_file()
    payload = json.loads((data / "quality_report.json").read_text(encoding="utf-8"))
    assert payload["n_papers"] == report.n_papers
    assert report.flagged_papers >= 1
    assert report.total_flags >= report.flagged_papers


def test_ingest_reextracts_on_schema_upgrade(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Ein Canonical mit veralteter Schema-Version wird neu extrahiert."""
    make_pdf(["stable content for schema test"], "papers/a.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    ingest(papers, data)

    for canonical in (data / "canonical").glob("*.json"):
        obj = json.loads(canonical.read_text(encoding="utf-8"))
        obj["schema_version"] = "0.1.0"
        canonical.write_text(json.dumps(obj), encoding="utf-8")

    report = ingest(papers, data)

    assert report.extracted == 1
    assert report.skipped == 0
