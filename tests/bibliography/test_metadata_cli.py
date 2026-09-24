"""Tests für die CLIs der Phase 17 / A1: ``verify_metadata`` und ``metadata_worklist`` (ADR 0042).

Geprüft wird vor allem, was die Roadmap als Akzeptanz nennt: ``--dry-run`` ändert nachweislich
nichts, ein Import ohne Bestätigung schreibt keinen Wert, und jede Entscheidung steht im
Protokoll.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

import pytest
from scripts import metadata_worklist, verify_metadata

from research_graphrag.bibliography import titlepage
from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_RESOLVED,
    REVIEW_UNRESOLVABLE,
    MetadataRecord,
)
from research_graphrag.bibliography.store import load_records, load_reviews, save_records
from research_graphrag.bibliography.titlepage import Calibration
from research_graphrag.extraction.model import SECTION_KIND_BODY, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.metadata_index import build_metadata_index
from research_graphrag.indexing.tfidf_index import build_index

MakePdf = Callable[..., Path]

_OWN = "Graph Retrieval for Scientific Corpora at Scale"
_VICTIM = "Visual Retrieval Augmented Generation over Documents"


def _paper(paper_id: str, title: str) -> CanonicalPaper:
    """Ein Canonical-Paper, dessen Dateiname der Titel ist."""
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


@pytest.fixture
def workspace(make_pdf: MakePdf, tmp_path: Path) -> dict[str, Path]:
    """Index, Datenordner, Korpus-Ordner und Metadatendatei mit zwei schwachen Papern."""
    make_pdf([f"{_OWN}\nAnna Beispiel, Bert Muster"], f"papers/{_OWN}.pdf")
    make_pdf([f"{_VICTIM}\nCarla Neu, Dirk Alt"], f"papers/{_VICTIM}.pdf")
    metadata = tmp_path / "metadata" / "paper_metadata.json"
    save_records(
        metadata,
        [
            MetadataRecord(
                paper_id="aaaa0001",
                origin=ORIGIN_RESOLVED,
                title=_OWN,
                authors=("Anna Beispiel", "Bert Muster"),
                doi="10.1145/1111",
                confidence=CONFIDENCE_WEAK,
            ),
            MetadataRecord(
                paper_id="bbbb0001",
                origin=ORIGIN_RESOLVED,
                title="GPT-4 Technical Report of a Model",
                authors=("OpenAI Team",),
                doi="10.1145/2222",
                confidence=CONFIDENCE_WEAK,
            ),
        ],
    )
    papers = [_paper("aaaa0001", _OWN), _paper("bbbb0001", _VICTIM)]
    data = tmp_path / "data"
    db = data / "index" / "index.sqlite"
    build_index(papers, db)
    build_metadata_index(papers, db, metadata_file=metadata)
    return {"db": db, "data": data, "papers": tmp_path / "papers", "metadata": metadata}


def _common(workspace: dict[str, Path]) -> list[str]:
    """Die Pfad-Argumente beider CLIs."""
    return [
        "--index",
        str(workspace["db"]),
        "--data",
        str(workspace["data"]),
        "--papers",
        str(workspace["papers"]),
        "--metadaten",
        str(workspace["metadata"]),
    ]


def _run(module: object, name: str, args: list[str]) -> int:
    """Ruft eine CLI mit den gegebenen Argumenten auf."""
    original = sys.argv
    sys.argv = [name, *args]
    try:
        return int(module.main())  # type: ignore[attr-defined]
    finally:
        sys.argv = original


def test_verify_dry_run_changes_nothing(workspace: dict[str, Path]) -> None:
    """``--dry-run`` misst und berichtet, schreibt aber weder Metadaten noch Protokoll."""
    before = workspace["metadata"].read_bytes()

    code = _run(verify_metadata, "verify_metadata", [*_common(workspace), "--dry-run"])

    assert code == 0
    assert workspace["metadata"].read_bytes() == before
    assert not (workspace["data"] / "metadata_log.md").exists()


def test_verify_without_calibration_only_measures_but_logs(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Vor der Kalibrierung ändert der Lauf nichts, protokolliert die Messung aber."""
    before = workspace["metadata"].read_bytes()

    code = _run(verify_metadata, "verify_metadata", _common(workspace))

    assert code == 0
    assert workspace["metadata"].read_bytes() == before
    assert "Kalibrierung aus A0" in capsys.readouterr().out
    log = (workspace["data"] / "metadata_log.md").read_text(encoding="utf-8")
    assert "## Seite-1-Prüfung" in log
    assert "**nicht kalibriert**" in log


def test_verify_with_calibration_upgrades_and_rejects(
    workspace: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nach der Kalibrierung: eigener Treffer ``strong``, fremder verworfen samt Vermerk."""
    monkeypatch.setattr(titlepage, "CALIBRATION", Calibration(0.5, 0.0, "Test"))

    code = _run(verify_metadata, "verify_metadata", _common(workspace))

    records = {record.paper_id: record for record in load_records(workspace["metadata"])}
    assert code == 0
    assert records["aaaa0001"].confidence == CONFIDENCE_STRONG
    assert "bbbb0001" not in records
    assert load_reviews(workspace["metadata"])["bbbb0001"].rejections[0].doi == "10.1145/2222"


def test_worklist_state_and_export(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """``stand`` zählt die offen schwachen Paper, ``export`` schreibt die Liste unter ``data/``."""
    assert _run(metadata_worklist, "metadata_worklist", [*_common(workspace), "stand"]) == 0
    assert "offen schwach belegt: 2" in capsys.readouterr().out

    assert _run(metadata_worklist, "metadata_worklist", [*_common(workspace), "export"]) == 0

    lists = list((workspace["data"] / "worklists").glob("*/arbeitsliste.md"))
    assert len(lists) == 1


def test_worklist_export_dry_run_writes_nothing(workspace: dict[str, Path]) -> None:
    """Die Vorschau erzeugt keine Arbeitsliste."""
    code = _run(
        metadata_worklist, "metadata_worklist", [*_common(workspace), "export", "--dry-run"]
    )

    assert code == 0
    assert not (workspace["data"] / "worklists").exists()


def test_import_dry_run_opens_no_connection_and_writes_nothing(
    workspace: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Die Vorschau prüft nur das Format – ohne Client, ohne Ablage der Antwort."""
    answer = tmp_path / "antwort.json"
    answer.write_text(
        json.dumps({"antworten": [{"paper_id": "bbbb0001", "doi": "10.1145/9999"}]}),
        encoding="utf-8",
    )
    before = workspace["metadata"].read_bytes()

    def _forbidden(**_kwargs: object) -> object:
        raise AssertionError("Die Vorschau darf keinen Client erzeugen.")

    monkeypatch.setattr(metadata_worklist, "create_client", _forbidden)

    code = _run(
        metadata_worklist,
        "metadata_worklist",
        [*_common(workspace), "import", str(answer), "--dry-run"],
    )

    assert code == 0
    assert workspace["metadata"].read_bytes() == before
    assert not (workspace["metadata"].parent / "llm_answers").exists()


def test_mark_and_unmark_as_unresolvable(workspace: dict[str, Path]) -> None:
    """Der Status ist eine menschliche, begründete Entscheidung – und wieder aufhebbar."""
    args = [*_common(workspace), "markieren", "bbbb0001", "--grund", "nur als Poster"]
    assert _run(metadata_worklist, "metadata_worklist", args) == 0
    assert load_reviews(workspace["metadata"])["bbbb0001"].status == REVIEW_UNRESOLVABLE

    clear = [*_common(workspace), "markieren", "bbbb0001", "--aufheben"]
    assert _run(metadata_worklist, "metadata_worklist", clear) == 0
    assert load_reviews(workspace["metadata"]) == {}


def test_marking_without_a_reason_is_refused(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """„Nicht auflösbar“ ohne Grund wäre ein stilles ``weak`` mit anderem Namen."""
    code = _run(
        metadata_worklist, "metadata_worklist", [*_common(workspace), "markieren", "bbbb0001"]
    )

    assert code == 1
    assert "invalid_input" in capsys.readouterr().out


def test_marking_an_unknown_paper_is_refused(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Ein Tippfehler in der Paper-ID ergäbe einen verwaisten Status – das gemeinte Paper bliebe
    still schwach. Aufheben bleibt möglich, damit sich ein solcher Eintrag aufräumen lässt."""
    before = workspace["metadata"].read_bytes()
    args = [*_common(workspace), "markieren", "ffff0001", "--grund", "Tippfehler"]

    assert _run(metadata_worklist, "metadata_worklist", args) == 1

    assert "Fehler [not_found]" in capsys.readouterr().out
    assert workspace["metadata"].read_bytes() == before
    clear = [*_common(workspace), "markieren", "ffff0001", "--aufheben"]
    assert _run(metadata_worklist, "metadata_worklist", clear) == 0
