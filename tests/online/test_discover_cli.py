"""Tests für die CLI der Online-Kandidatensuche (Phase 9 / S1).

Der Netzzugang wird ersetzt – die Tests laufen wie alle anderen **ohne Netz**.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from scripts import discover as cli

from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.online.transport import HttpResponse

ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v1</id>
    <published>2025-01-02T10:00:00Z</published>
    <title>Ein Kandidat mit ﬁ-Ligatur und ∗ Sonderzeichen</title>
    <summary>Abstract eins.</summary>
    <link title="pdf" href="http://arxiv.org/pdf/2501.00001v1" rel="related"/>
  </entry>
</feed>
""".encode()

OPENALEX_PAYLOAD = json.dumps({"results": []}).encode()


class _FakeClient:
    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        body = ARXIV_FEED if "arxiv.org" in url else OPENALEX_PAYLOAD
        return HttpResponse(status=200, headers={}, body=body)


def _paper(paper_id: str, texts: Sequence[str], name: str) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index + 1:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
        )
        for index, text in enumerate(texts)
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{name}.pdf",
        source_sha256="0" * 64,
        n_pages=len(texts),
        chunks=chunks,
        quality_flags=(),
    )


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Legt einen kleinen Index samt Datenverzeichnis an."""
    data_path = tmp_path / "data"
    db = data_path / "index" / "index.sqlite"
    papers = [
        _paper("aaaa0001", ["graph retrieval augmented generation"], "Graph Retrieval Study"),
        _paper("bbbb0002", ["graph retrieval augmented entities"], "Another Graph Study"),
    ]
    build_index(papers, db)
    build_graph(papers, db)
    return db, data_path


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr(cli, "create_client", lambda **_: _FakeClient())
    monkeypatch.setattr("sys.argv", ["discover", *argv])
    return cli.main()


def test_cli_requires_a_query_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ohne Anfrage bricht die CLI mit einem Hinweis ab, statt blind zu suchen."""
    monkeypatch.setattr("sys.argv", ["discover"])

    assert cli.main() == 2


def test_cli_rejects_a_non_numeric_community(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Eine unbrauchbare Community-Kennung wird von argparse gemeldet – kein Stacktrace."""
    monkeypatch.setattr("sys.argv", ["discover", "--community", "abc"])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 2
    assert "--community" in capsys.readouterr().err


def test_dry_run_shows_the_queries_without_touching_the_network(
    workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Die Vorschau bildet die Anfrage, fragt aber nichts ab und schreibt nichts."""
    db, data_path = workspace

    def _forbidden(**_: object) -> _FakeClient:
        raise AssertionError("In der Vorschau darf kein Client entstehen.")

    monkeypatch.setattr(cli, "create_client", _forbidden)
    monkeypatch.setattr(
        "sys.argv",
        ["discover", "--community", "0", "--index", str(db), "--data", str(data_path), "--dry-run"],
    )

    code = cli.main()

    assert code == 0
    output = capsys.readouterr().out
    assert "[discover] Anfrage C0" in output
    assert "Vorschau" in output
    assert not (data_path / "online_candidates.md").exists()
    assert not (data_path / "online_raw").exists()


def test_dry_run_still_reports_domain_errors(
    workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Auch die Vorschau prüft die Anfrage – eine unbekannte Community endet mit Code 1."""
    db, data_path = workspace

    code = _run(
        monkeypatch,
        ["--community", "99", "--index", str(db), "--data", str(data_path), "--dry-run"],
    )

    assert code == 1
    assert "[discover] Fehler [not_found]" in capsys.readouterr().out


def test_cli_writes_report_and_summarises(
    workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ein Lauf schreibt den Bericht und fasst das Ergebnis zusammen."""
    db, data_path = workspace

    code = _run(
        monkeypatch,
        ["--community", "0", "--index", str(db), "--data", str(data_path), "--seit", "2021"],
    )

    assert code == 0
    output = capsys.readouterr().out
    assert "[discover] Anfrage C0" in output
    assert "1 Treffer" in output
    assert (data_path / "online_candidates.md").is_file()


def test_cli_reports_unknown_community(
    workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ein fachlicher Fehler endet mit Code 1 und klarer Meldung – kein Stacktrace."""
    db, data_path = workspace

    code = _run(monkeypatch, ["--community", "99", "--index", str(db), "--data", str(data_path)])

    assert code == 1
    assert "[discover] Fehler [not_found]" in capsys.readouterr().out


def test_cli_reports_missing_seed(
    workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Auch eine unbekannte Paper-Kennung wird sauber gemeldet."""
    db, data_path = workspace

    code = _run(monkeypatch, ["--seed", "fehlt", "--index", str(db), "--data", str(data_path)])

    assert code == 1
    assert "not_found" in capsys.readouterr().out


def test_cli_can_skip_raw_storage(
    workspace: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mit ``--ohne-rohdaten`` entsteht kein Ablageverzeichnis."""
    db, data_path = workspace

    code = _run(
        monkeypatch,
        [
            "--community",
            "0",
            "--index",
            str(db),
            "--data",
            str(data_path),
            "--ohne-rohdaten",
        ],
    )

    assert code == 0
    assert not (data_path / "online_raw").exists()
