"""Tests für die Triage schwach belegter Datensätze (Phase 17 / A1, ADR 0042).

Ein kleiner echter Index mit echten PDFs bildet die drei Befund-3-Lagen nach: ein eigener, nur
schwach belegter Treffer (wird bestätigt), ein **fremder** Treffer aus dem Literaturverzeichnis
(wird verworfen) und ein Paper ohne gespeicherten Treffer (nicht prüfbar).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

import pytest

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_RESOLVED,
    REVIEW_UNRESOLVABLE,
    MetadataRecord,
)
from research_graphrag.bibliography.store import (
    load_records,
    load_reviews,
    save_records,
    set_review_status,
)
from research_graphrag.bibliography.titlepage import EVIDENCE_TITLE_PAGE, Calibration
from research_graphrag.bibliography.triage import (
    ACTION_NOT_CHECKABLE,
    ACTION_REJECTED,
    ACTION_UNCHANGED,
    ACTION_UPGRADED,
    TriageRun,
    load_indexed_papers,
    open_weak,
    render_triage,
    triage_stored_records,
)
from research_graphrag.extraction.model import SECTION_KIND_BODY, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.metadata_index import build_metadata_index, load_paper_metadata
from research_graphrag.indexing.tfidf_index import build_index

MakePdf = Callable[..., Path]

_OWN = "Graph Retrieval for Scientific Corpora at Scale"
_VICTIM = "Visual Retrieval Augmented Generation over Documents"
_ORPHAN = "Benchmarking Retrieval Pipelines in Practice Today"
_CALIBRATED = Calibration(min_author_share=0.5, max_share_for_rejection=0.0, source="Test")


def _paper(paper_id: str, title: str) -> CanonicalPaper:
    """Ein Canonical-Paper, dessen Dateiname der Titel ist (Korpus-Konvention)."""
    body = f"{title} untersucht retrieval augmented generation im Korpus."
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///anderswo/{quote(title)}.pdf",
        source_sha256="0" * 64,
        n_pages=1,
        chunks=(
            Chunk(
                chunk_id=f"{paper_id}-c0001",
                paper_id=paper_id,
                page_number=1,
                text=body,
                char_count=len(body),
                section_id="s-body",
                section_title="Introduction",
            ),
        ),
        quality_flags=(),
        sections=(
            Section(
                section_id="s-body",
                title="Introduction",
                kind=SECTION_KIND_BODY,
                level=1,
                page_number=1,
                order=0,
            ),
        ),
    )


def _weak(paper_id: str, title: str, authors: tuple[str, ...], doi: str) -> MetadataRecord:
    """Ein online aufgelöster, schwach belegter Treffer."""
    return MetadataRecord(
        paper_id=paper_id,
        origin=ORIGIN_RESOLVED,
        title=title,
        authors=authors,
        year=2024,
        doi=doi,
        confidence=CONFIDENCE_WEAK,
        evidence="OpenAlex über doi (Identifikator lokal nicht belegt)",
    )


@pytest.fixture
def corpus(make_pdf: MakePdf, tmp_path: Path) -> tuple[Path, Path, Path]:
    """Index, Metadatendatei und Korpus-Ordner mit drei Papern."""
    make_pdf([f"{_OWN}\nAnna Beispiel, Bert Muster\nAbstract text."], f"papers/{_OWN}.pdf")
    make_pdf([f"{_VICTIM}\nCarla Neu, Dirk Alt\nAbstract text."], f"papers/{_VICTIM}.pdf")
    make_pdf([f"{_ORPHAN}\nEva Solo\nAbstract text."], f"papers/{_ORPHAN}.pdf")
    papers = [_paper("aaaa0001", _OWN), _paper("bbbb0001", _VICTIM), _paper("cccc0001", _ORPHAN)]
    metadata = tmp_path / "metadata" / "paper_metadata.json"
    save_records(
        metadata,
        [
            _weak("aaaa0001", _OWN, ("Anna Beispiel", "Bert Muster"), "10.1/own"),
            _weak("bbbb0001", "GPT-4 Technical Report of a Model", ("OpenAI Team",), "10.1/gpt4"),
            MetadataRecord(
                paper_id="cccc0001",
                origin=ORIGIN_RESOLVED,
                title=_ORPHAN,
                authors=("Eva Solo",),
                confidence=CONFIDENCE_WEAK,
            ),
        ],
    )
    db = tmp_path / "data" / "index" / "index.sqlite"
    build_index(papers, db)
    build_metadata_index(papers, db, metadata_file=metadata)
    return db, metadata, tmp_path / "papers"


def _triage(corpus: tuple[Path, Path, Path], calibration: Calibration | None) -> TriageRun:
    """Triage über alle offen schwachen Paper mit der gegebenen Kalibrierung."""
    db, metadata, papers_dir = corpus
    reviews = load_reviews(metadata)
    return triage_stored_records(
        load_records(metadata),
        reviews,
        open_weak(load_indexed_papers(db), reviews),
        papers_dir=papers_dir,
        today="2026-09-24",
        calibration=calibration,
    )


def test_own_hits_are_upgraded_and_foreign_hits_rejected(corpus: tuple[Path, Path, Path]) -> None:
    """Die beiden Befund-3-Lagen – bestätigt und fremd – werden getrennt entschieden."""
    run = _triage(corpus, _CALIBRATED)
    actions = {decision.paper_id: decision.action for decision in run.decisions}
    records = {record.paper_id: record for record in run.records}

    assert actions["aaaa0001"] == ACTION_UPGRADED
    assert records["aaaa0001"].confidence == CONFIDENCE_STRONG
    assert EVIDENCE_TITLE_PAGE in records["aaaa0001"].evidence
    assert actions["bbbb0001"] == ACTION_REJECTED
    assert "bbbb0001" not in records
    rejection = run.reviews["bbbb0001"].rejections[0]
    assert (rejection.doi, rejection.date) == ("10.1/gpt4", "2026-09-24")


def test_without_calibration_the_run_only_measures(corpus: tuple[Path, Path, Path]) -> None:
    """Vor A0, Punkt 3, wird nichts aufgewertet und nichts verworfen – nur gemessen."""
    run = _triage(corpus, Calibration())

    assert {decision.action for decision in run.decisions} == {ACTION_UNCHANGED}
    assert run.reviews == {}


def test_papers_without_a_stored_hit_or_pdf_are_not_checkable(
    corpus: tuple[Path, Path, Path],
) -> None:
    """Nur ein gespeicherter ``resolved``-Treffer mit lokalem PDF ist prüfbar."""
    db, metadata, papers_dir = corpus
    (papers_dir / f"{_ORPHAN}.pdf").unlink()
    records = [record for record in load_records(metadata) if record.paper_id != "aaaa0001"]
    reviews = load_reviews(metadata)
    run = triage_stored_records(
        records,
        reviews,
        open_weak(load_indexed_papers(db), reviews),
        papers_dir=papers_dir,
        today="2026-09-24",
        calibration=_CALIBRATED,
    )
    notes = {decision.paper_id: decision for decision in run.decisions}

    assert notes["aaaa0001"].action == ACTION_NOT_CHECKABLE
    assert "resolve_metadata" in notes["aaaa0001"].note
    assert notes["cccc0001"].action == ACTION_NOT_CHECKABLE
    assert notes["cccc0001"].note == "PDF nicht gefunden"


def test_a_paper_with_status_leaves_the_open_set(corpus: tuple[Path, Path, Path]) -> None:
    """Kein stilles ``weak``: Ein ausgewiesener Status zählt als erledigt."""
    db, metadata, _ = corpus
    reviews = set_review_status({}, "cccc0001", REVIEW_UNRESOLVABLE, "nur als Poster")

    open_ids = {paper.paper_id for paper in open_weak(load_indexed_papers(db), reviews)}

    assert open_ids == {"aaaa0001", "bbbb0001"}


def test_the_status_reaches_the_index(corpus: tuple[Path, Path, Path]) -> None:
    """Ein ausgewiesener Status erscheint in ``PaperMetadata.review`` (und damit im Werkzeug)."""
    db, metadata, _ = corpus
    save_records(
        metadata,
        load_records(metadata),
        reviews=set_review_status({}, "cccc0001", REVIEW_UNRESOLVABLE, "nur als Poster"),
    )
    papers = [_paper("aaaa0001", _OWN), _paper("bbbb0001", _VICTIM), _paper("cccc0001", _ORPHAN)]
    build_metadata_index(papers, db, metadata_file=metadata)

    item = load_paper_metadata(db)["cccc0001"]

    assert item.review == {"status": REVIEW_UNRESOLVABLE, "reason": "nur als Poster"}
    assert load_paper_metadata(db)["aaaa0001"].review is None


def test_the_log_names_the_calibration_state(corpus: tuple[Path, Path, Path]) -> None:
    """Das Protokoll sagt, ob entschieden oder nur gemessen wurde."""
    measured = render_triage("20260924T100000Z", _triage(corpus, Calibration()), Calibration())
    decided = render_triage("20260924T100000Z", _triage(corpus, _CALIBRATED), _CALIBRATED)

    assert "**nicht kalibriert**" in "\n".join(measured)
    assert "kalibriert (Test)" in "\n".join(decided)
    assert "### Verworfen (Fremd-Paper, Ablehnungsvermerk gesetzt)" in decided
