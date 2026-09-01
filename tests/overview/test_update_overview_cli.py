"""Tests für den Retirement-Hinweis von ``scripts/update_overview.py`` (Phase 15 / G4)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from scripts import update_overview as cli

_UEBERSICHT = (
    "# Übersicht\n\n"
    "| ID | Name | Themenfokus | Keyword | Kompakte Zusammenfassung | Interner Link "
    "| Relevanz fuer Expose | SRQ-Zuordnung | Externer Link/Indetifikator |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)


def test_refuses_to_run_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ohne ``--force`` bleibt die Übersicht unverändert und der Lauf meldet Exit 1."""
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_text(_UEBERSICHT, encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["update_overview", "--data", str(tmp_path / "data"), "--uebersicht", str(uebersicht)],
    )

    exit_code = cli.main()

    assert exit_code == 1
    assert uebersicht.read_text(encoding="utf-8") == _UEBERSICHT
    assert "außer Dienst" in capsys.readouterr().out


def test_force_still_appends_as_an_escape_hatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--force`` bleibt als Notfall-Werkzeug erreichbar (unterliegende Funktion unverändert)."""
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_text(_UEBERSICHT, encoding="utf-8")
    data = tmp_path / "data"
    (data / "canonical").mkdir(parents=True)
    monkeypatch.setattr(
        sys,
        "argv",
        ["update_overview", "--data", str(data), "--uebersicht", str(uebersicht), "--force"],
    )

    exit_code = cli.main()

    assert exit_code == 0
