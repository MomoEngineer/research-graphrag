"""Tests für die CLI der Referenz-Auflösung (Phase 13 / R1, ADR 0029).

Der Netzzugang wird ersetzt – die Tests laufen wie alle anderen **ohne Netz**.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import resolve_references as cli

from research_graphrag.online.references import STUB_SUFFIX
from research_graphrag.online.transport import HttpResponse

_ARXIV = "2404.16130"
_TITLE = "GraphRAG: From Local to Global"

_WORK = json.dumps(
    {
        "id": "https://openalex.org/W1",
        "doi": f"https://doi.org/10.48550/arXiv.{_ARXIV}",
        "title": _TITLE,
        "publication_year": 2024,
        "authorships": [{"author": {"display_name": "Anna Beispiel"}}],
        "primary_location": {"source": {"display_name": "Proceedings of ACL"}},
        "open_access": {"oa_url": "https://example.org/w1.pdf"},
        "abstract_inverted_index": {"Ein": [0], "Abstract.": [1]},
    }
).encode()


class _FakeClient:
    """Antwortet immer mit demselben Werk und zählt die Abfragen."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        self.urls.append(url)
        return HttpResponse(status=200, headers={}, body=_WORK)


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Eingangsordner mit Kennungsliste und leeres Datenverzeichnis."""
    inbox = tmp_path / "new_papers"
    inbox.mkdir()
    listing = inbox / "referenzen.txt"
    listing.write_bytes(
        f"# Kuratierte Kennungen\r\narXiv:{_ARXIV}   # weil oft zitiert\r\n".encode()
    )
    data_path = tmp_path / "data"
    data_path.mkdir()
    return inbox, listing, data_path


def _argv(inbox: Path, data_path: Path, *extra: str) -> list[str]:
    """Baut die Argumentliste eines Laufs."""
    return ["resolve_references", "--new", str(inbox), "--data", str(data_path), *extra]


def test_dry_run_touches_neither_network_nor_disk(
    workspace: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Die Vorschau zeigt die geplanten Abfragen – ohne Client, ohne Datei, ohne Protokoll."""
    inbox, listing, data_path = workspace
    before = listing.read_bytes()

    def _forbidden(**_: object) -> _FakeClient:
        raise AssertionError("In der Vorschau darf kein Client entstehen.")

    monkeypatch.setattr(cli, "create_client", _forbidden)
    monkeypatch.setattr("sys.argv", _argv(inbox, data_path, "--dry-run"))

    code = cli.main()

    assert code == 0
    output = capsys.readouterr().out
    assert "weil oft zitiert" in output
    assert "Vorschau" in output
    assert list(inbox.glob(f"*{STUB_SUFFIX}")) == []
    assert not (data_path / "references_log.md").exists()
    assert not (data_path / "online_raw").exists()
    assert listing.read_bytes() == before


def test_a_run_writes_one_stub_a_log_and_the_raw_answer(
    workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Der reguläre Lauf erzeugt genau eine Stub-Datei samt Protokoll und Rohantwort."""
    inbox, listing, data_path = workspace
    client = _FakeClient()
    monkeypatch.setattr(cli, "create_client", lambda **_: client)
    monkeypatch.setattr("sys.argv", _argv(inbox, data_path))

    code = cli.main()

    stubs = list(inbox.glob(f"*{STUB_SUFFIX}"))
    assert code == 0
    assert len(stubs) == 1
    assert stubs[0].name == f"ref-graphrag-arxiv-{_ARXIV}{STUB_SUFFIX}"
    assert json.loads(stubs[0].read_text(encoding="utf-8"))["abstract"] == "Ein Abstract."
    log = (data_path / "references_log.md").read_text(encoding="utf-8")
    assert "# Referenz-Einträge" in log
    assert f"arxiv:{_ARXIV}" in log
    assert list((data_path / "online_raw").iterdir())
    assert listing.read_bytes().endswith(b"\r\n")


def test_a_second_run_asks_nothing_and_writes_nothing(
    workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Die Akzeptanz der Phase: der Wiederholungslauf ist folgenlos."""
    inbox, _, data_path = workspace
    first = _FakeClient()
    monkeypatch.setattr(cli, "create_client", lambda **_: first)
    monkeypatch.setattr("sys.argv", _argv(inbox, data_path))
    cli.main()
    stubs_after_first = {path.name for path in inbox.glob(f"*{STUB_SUFFIX}")}

    second = _FakeClient()
    monkeypatch.setattr(cli, "create_client", lambda **_: second)
    code = cli.main()

    assert code == 0
    assert second.urls == []
    assert {path.name for path in inbox.glob(f"*{STUB_SUFFIX}")} == stubs_after_first


def test_a_missing_list_ends_with_a_clear_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ohne Liste endet der Lauf handlungsleitend – kein Stacktrace."""
    monkeypatch.setattr("sys.argv", _argv(tmp_path / "leer", tmp_path / "data"))

    code = cli.main()

    assert code == 1
    assert "not_found" in capsys.readouterr().out


def test_the_limit_defers_the_remaining_identifiers(
    workspace: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--limit`` schont das Kontingent; der Rest bleibt für den nächsten Lauf liegen."""
    inbox, listing, data_path = workspace
    listing.write_text(f"arXiv:{_ARXIV}\narXiv:2501.00002\n", encoding="utf-8")
    monkeypatch.setattr(cli, "create_client", lambda **_: _FakeClient())
    monkeypatch.setattr("sys.argv", _argv(inbox, data_path, "--limit", "1", "--ohne-rohdaten"))

    code = cli.main()

    assert code == 0
    assert "vertagt" in capsys.readouterr().out
    assert not (data_path / "online_raw").exists()


def test_an_unreadable_line_is_reported_instead_of_stopping_the_run(
    workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eine nicht deutbare Zeile ist ein Befund im Protokoll, kein Abbruch."""
    inbox, listing, data_path = workspace
    listing.write_text(f"das ist keine kennung\narXiv:{_ARXIV}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "create_client", lambda **_: _FakeClient())
    monkeypatch.setattr("sys.argv", _argv(inbox, data_path, "--ohne-rohdaten"))

    code = cli.main()

    log = (data_path / "references_log.md").read_text(encoding="utf-8")
    assert code == 0
    assert "Nicht aufgelöst" in log
    assert "keine deutbare" in log
    assert len(list(inbox.glob(f"*{STUB_SUFFIX}"))) == 1
