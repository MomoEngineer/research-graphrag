"""Tests der CLI ``python -m scripts.authors`` (Phase 17 / A4, ADR 0043).

Jeder Unterbefehl gibt das Ergebnis des zugehörigen Werkzeugs aus und endet mit der Abdeckung;
ein fachlicher Fehler ergibt Exit-Code 1 und eine Klartextmeldung.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from scripts import authors

ASAI = "A5023888391"


def _run(db: Path, *args: str) -> int:
    """Ruft die CLI mit dem gegebenen Index und Argumenten auf."""
    original = sys.argv
    sys.argv = ["authors", "--index", str(db), *args]
    try:
        return authors.main()
    finally:
        sys.argv = original


@pytest.fixture
def person_db(make_person_index: Callable[..., Path]) -> Path:
    """Vollständiger Personen-Index."""
    return make_person_index()


def test_search_lists_candidates_and_flags_ambiguity(
    person_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``suchen`` nennt Schlüssel, Identität, Paperzahl und die Mehrdeutigkeit."""
    assert _run(person_db, "suchen", "Asai") == 0

    out = capsys.readouterr().out
    assert "2 Kandidat(en)" in out
    assert "Mehrdeutig" in out
    assert f"{ASAI} · openalex · 2 Paper · 2024–2025" in out
    assert "name:akari asai · name · 1 Paper" in out
    assert "Abdeckung: Nur 4 von 6 Volltexten" in out


def test_profile_lists_papers_communities_and_coauthors(
    person_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``profil`` zeigt Paper mit Position, Communities und Mitautoren."""
    assert _run(person_db, "profil", ASAI) == 0

    out = capsys.readouterr().out
    assert "aaaa0002 · 2025 · Reflection Tokens for Retrieval · Position 1" in out
    assert "Communities (1)" in out
    assert "name:zeqiu wu · name · 2 gemeinsam · Zeqiu Wu" in out


def test_papers_search_shows_page_and_snippet(
    person_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``paper`` zeigt die belegten Treffer in den Papern der Person."""
    assert _run(person_db, "paper", ASAI, "attention", "-k", "2") == 0

    out = capsys.readouterr().out
    assert "2 Treffer zu „attention“ in 2 Papern" in out
    assert "aaaa0002 · Introduction · Seite 1" in out
    assert "dddd0001" not in out


def test_citations_mark_self_citations(person_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``zitationen`` zeigt beide Richtungen und markiert Selbstzitate."""
    assert _run(person_db, "zitationen", ASAI) == 0

    out = capsys.readouterr().out
    assert "zitiert (2):" in out
    assert "wird zitiert von (3):" in out
    assert (
        "aaaa0001 · 2024 · Self-RAG: Learning to Retrieve, Generate, and Critique · Selbstzitat"
        in out
    )
    assert "über aaaa0001, aaaa0002 · Match: doi" in out
    assert "Nur Zitationen innerhalb des Korpus." in out


def test_domain_error_yields_exit_code_one(
    person_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ein unbekannter Schlüssel endet mit Exit-Code 1 und nennt die Fehlerkategorie."""
    assert _run(person_db, "profil", "A999") == 1

    assert "Fehler [not_found]" in capsys.readouterr().out
