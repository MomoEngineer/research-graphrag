"""Tests für die CLI der Metadaten-Auflösung (Phase 12 / K2, ADR 0026)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import pytest
from scripts import resolve_metadata

from research_graphrag.bibliography.model import ORIGIN_MANUAL, ORIGIN_RESOLVED, MetadataRecord
from research_graphrag.bibliography.store import load_records, save_records
from research_graphrag.extraction.model import SECTION_KIND_BODY, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.metadata_index import build_metadata_index
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.online.transport import HttpResponse

_TITLE = "Graph Retrieval for Scientific Corpora at Scale"
_ARXIV = "2401.00001"

_WORK = {
    "id": "https://openalex.org/W1",
    "doi": f"https://doi.org/10.48550/arxiv.{_ARXIV}",
    "title": _TITLE,
    "publication_year": 2024,
    "authorships": [{"author": {"display_name": "Anna Beispiel"}}],
    "primary_location": {"source": {"display_name": "Proceedings of ACL"}},
    "open_access": {"oa_url": "https://example.org/w1.pdf"},
}


class _FakeClient:
    """Beantwortet jede Abfrage mit demselben Werk und zählt die Aufrufe."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        self.urls.append(url)
        return HttpResponse(status=200, headers={}, body=json.dumps(_WORK).encode())


def _paper(paper_id: str, title: str, identifiers: dict[str, str]) -> CanonicalPaper:
    """Baut ein minimales Canonical-Paper mit Titelseiten-Beleg."""
    body = f"{title} " + " ".join(f"{key}:{value}" for key, value in identifiers.items())
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{quote(title)}.pdf",
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
        identifiers=identifiers,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Legt Index, Datenverzeichnis und Metadatendatei an."""
    papers = [_paper("aaaa0001", _TITLE, {"arxiv": _ARXIV})]
    data = tmp_path / "data"
    db = data / "index" / "index.sqlite"
    build_index(papers, db)
    build_metadata_index(papers, db)
    return db, data, tmp_path / "metadata" / "paper_metadata.json"


def _run(args: list[str]) -> int:
    """Ruft die CLI mit den gegebenen Argumenten auf."""
    import sys

    original = sys.argv
    sys.argv = ["resolve_metadata", *args]
    try:
        return resolve_metadata.main()
    finally:
        sys.argv = original


def test_dry_run_opens_no_connection_and_writes_nothing(
    workspace: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Die Vorschau zeigt die Auswahl, ohne Netz zu berühren oder zu schreiben."""
    db, data, store = workspace

    def _forbidden(**_kwargs: object) -> object:
        raise AssertionError("Die Vorschau darf keinen Client erzeugen.")

    monkeypatch.setattr(resolve_metadata, "create_client", _forbidden)

    code = _run(["--dry-run", "--index", str(db), "--data", str(data), "--metadaten", str(store)])

    assert code == 0
    assert not store.exists()
    assert "Vorschau" in capsys.readouterr().out


def test_run_writes_records_and_the_log(
    workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ein Lauf übernimmt den Treffer und protokolliert ihn append-only."""
    db, data, store = workspace
    monkeypatch.setattr(resolve_metadata, "create_client", lambda **_kwargs: _FakeClient())

    code = _run(["--index", str(db), "--data", str(data), "--metadaten", str(store)])

    records = load_records(store)
    assert code == 0
    assert len(records) == 1
    assert records[0].origin == ORIGIN_RESOLVED
    assert records[0].authors == ("Anna Beispiel",)
    assert records[0].venue == "Proceedings of ACL"

    log = (data / "metadata_log.md").read_text(encoding="utf-8")
    assert "Metadaten-Auflösung" in log
    assert "aaaa0001" in log


def test_manual_records_survive_a_run(
    workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Handpflege wird nicht überschrieben (sie steht in der Kette darüber)."""
    db, data, store = workspace
    save_records(
        store,
        [MetadataRecord(paper_id="aaaa0001", origin=ORIGIN_MANUAL, title="von Hand")],
    )
    monkeypatch.setattr(resolve_metadata, "create_client", lambda **_kwargs: _FakeClient())

    _run(["--index", str(db), "--data", str(data), "--metadaten", str(store)])

    origins = {record.origin: record.title for record in load_records(store)}
    assert origins[ORIGIN_MANUAL] == "von Hand"
    assert origins[ORIGIN_RESOLVED] == _TITLE


def test_limit_caps_the_selection(
    workspace: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--limit 0`` wählt nichts aus und meldet das."""
    db, data, store = workspace
    monkeypatch.setattr(resolve_metadata, "create_client", lambda **_kwargs: _FakeClient())

    code = _run(
        ["--limit", "0", "--index", str(db), "--data", str(data), "--metadaten", str(store)]
    )

    assert code == 0
    assert "Nichts aufzulösen" in capsys.readouterr().out


def test_unknown_paper_filter_selects_nothing(
    workspace: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ein Filter auf ein unbekanntes Paper führt zu keiner Abfrage."""
    db, data, store = workspace
    monkeypatch.setattr(resolve_metadata, "create_client", lambda **_kwargs: _FakeClient())

    code = _run(
        [
            "--paper",
            "gibtesnicht",
            "--index",
            str(db),
            "--data",
            str(data),
            "--metadaten",
            str(store),
        ]
    )

    assert code == 0
    assert "Nichts aufzulösen" in capsys.readouterr().out


def test_missing_index_is_reported_as_a_domain_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ein fehlender Index endet mit einer Meldung nach dem Fehlermodell, nicht mit Traceback."""
    code = _run(["--index", str(tmp_path / "fehlt.sqlite"), "--data", str(tmp_path)])

    assert code == 1
    assert "[resolve] Fehler [not_found]" in capsys.readouterr().out
