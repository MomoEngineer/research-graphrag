"""Tests für die CLI der Metadaten-Auflösung (Phase 12 / K2, ADR 0026)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import pytest
from scripts import resolve_metadata

from research_graphrag.bibliography.model import (
    ORIGIN_MANUAL,
    ORIGIN_RESOLVED,
    REVIEW_UNRESOLVABLE,
    MetadataRecord,
    Rejection,
)
from research_graphrag.bibliography.store import (
    add_rejection,
    load_records,
    load_reviews,
    save_records,
    set_review_status,
)
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


# --------------------------------------------------------------------------------------
# Phase 17 / A1: Ablehnungsvermerk und Prüfstatus (ADR 0042)
# --------------------------------------------------------------------------------------


class _OpenAlexOnly(_FakeClient):
    """Wie ``_FakeClient``, aber der arXiv-Feed kennt das Werk nicht (HTTP 404)."""

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        if "arxiv.org" in url:
            self.urls.append(url)
            return HttpResponse(status=404, headers={}, body=b"")
        return super().get(url, accept=accept)


def test_a_second_run_does_not_bring_back_a_rejected_hit(
    workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Die Akzeptanz aus A1: Ein verworfener Treffer wird nicht wieder eingespielt."""
    db, data, store = workspace
    rejection = Rejection(
        doi=f"10.48550/arxiv.{_ARXIV}", title=_TITLE, reason="Fremd-Paper", date="2026-09-24"
    )
    save_records(store, [], reviews=add_rejection({}, "aaaa0001", rejection))
    monkeypatch.setattr(resolve_metadata, "create_client", lambda **_kwargs: _OpenAlexOnly())

    code = _run(["--index", str(db), "--data", str(data), "--metadaten", str(store)])

    assert code == 0
    assert load_records(store) == ()
    assert load_reviews(store)["aaaa0001"].rejections == (rejection,)
    log = (data / "metadata_log.md").read_text(encoding="utf-8")
    assert "Ablehnungsvermerk verworfen" in log


def test_a_paper_marked_unresolvable_is_not_queried(
    workspace: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ein ausgewiesener Status wird respektiert – keine erneute Abfrage."""
    db, data, store = workspace
    save_records(
        store, [], reviews=set_review_status({}, "aaaa0001", REVIEW_UNRESOLVABLE, "nur Poster")
    )
    client = _FakeClient()
    monkeypatch.setattr(resolve_metadata, "create_client", lambda **_kwargs: client)

    code = _run(["--index", str(db), "--data", str(data), "--metadaten", str(store)])

    assert code == 0
    assert client.urls == []
    assert "Nichts aufzulösen" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# Phase 17 / A2, Punkt 4: fortsetzbarer Lauf
# --------------------------------------------------------------------------------------

_TITLES = (
    "Graph Retrieval for Scientific Corpora at Scale",
    "Benchmarking Retrieval Pipelines in Practice Today",
    "Hybrid Ranking with Reciprocal Rank Fusion Revisited",
)


@pytest.fixture
def three_papers(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Index mit drei Papern ohne Autoren – je eine DOI-Abfrage pro Paper."""
    papers = [
        _paper(f"p{index}", title, {"doi": f"10.1145/{index}000"})
        for index, title in enumerate(_TITLES, start=1)
    ]
    data = tmp_path / "data"
    db = data / "index" / "index.sqlite"
    build_index(papers, db)
    build_metadata_index(papers, db)
    return db, data, tmp_path / "metadata" / "paper_metadata.json"


class _ScriptedClient:
    """Antwortet der Reihe nach: Werk, dann ein vorgegebenes Verhalten ab der n-ten Abfrage."""

    def __init__(self, *, fail_from: int, status: int = 200, error: Exception | None = None):
        self.urls: list[str] = []
        self._fail_from = fail_from
        self._status = status
        self._error = error

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        self.urls.append(url)
        if len(self.urls) >= self._fail_from:
            if self._error is not None:
                raise self._error
            return HttpResponse(status=self._status, headers={}, body=b"{}")
        work = dict(_WORK, title=_TITLES[0], doi="https://doi.org/10.1145/1000")
        return HttpResponse(status=200, headers={}, body=json.dumps(work).encode())


def test_the_run_stops_at_an_exhausted_quota_and_keeps_its_progress(
    three_papers: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """HTTP 429 hält den Lauf an; das bis dahin Erreichte ist gespeichert."""
    db, data, store = three_papers
    client = _ScriptedClient(fail_from=2, status=429)
    monkeypatch.setattr(resolve_metadata, "create_client", lambda **_kwargs: client)

    code = _run(["--index", str(db), "--data", str(data), "--metadaten", str(store)])

    assert code == 0
    assert [record.paper_id for record in load_records(store)] == ["p1"]
    assert len(client.urls) == 2
    assert "Kontingent erschöpft" in capsys.readouterr().out


def test_a_failure_mid_run_keeps_the_progress(
    three_papers: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ein Netzfehler beim zweiten Paper lässt das erste gespeichert – der Lauf ist fortsetzbar."""
    from research_graphrag.errors import DomainError, ErrorCode

    db, data, store = three_papers
    client = _ScriptedClient(
        fail_from=2, error=DomainError(ErrorCode.DEPENDENCY_ERROR, "Verbindung abgebrochen")
    )
    monkeypatch.setattr(resolve_metadata, "create_client", lambda **_kwargs: client)

    code = _run(["--index", str(db), "--data", str(data), "--metadaten", str(store)])

    assert code == 1
    assert [record.paper_id for record in load_records(store)] == ["p1"]
    assert "Bis dahin gespeichert: 1 Paper" in capsys.readouterr().out


def test_the_intermediate_state_is_saved_every_few_papers(
    three_papers: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auch ohne Abbruch entsteht der Zwischenstand in Etappen."""
    db, data, store = three_papers
    saves: list[int] = []
    original = resolve_metadata.save_records

    def _counting_save(*args: object, **kwargs: object) -> int:
        saves.append(1)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(resolve_metadata, "SAVE_EVERY", 1)
    monkeypatch.setattr(resolve_metadata, "save_records", _counting_save)
    monkeypatch.setattr(
        resolve_metadata, "create_client", lambda **_kwargs: _ScriptedClient(fail_from=99)
    )

    _run(["--index", str(db), "--data", str(data), "--metadaten", str(store)])

    assert len(saves) == 4  # je Paper einmal, dazu der Abschluss
