"""Tests für den Seite-1-Beleg (Phase 17 / A1, ADR 0042).

Geprüft werden drei Dinge getrennt: die **Messung** (Titel-Ähnlichkeit und Nachnamen-Anteil auf
Seite 1), das **Urteil** unter einer gegebenen Kalibrierung und die Regel, dass ohne
Kalibrierung weder aufgewertet noch verworfen wird.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from research_graphrag.bibliography import titlepage
from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_RESOLVED,
    MetadataRecord,
    Rejection,
)
from research_graphrag.bibliography.titlepage import (
    EVIDENCE_TITLE_PAGE,
    VERDICT_CONFIRMED,
    VERDICT_FOREIGN,
    VERDICT_UNCONFIRMED,
    VERDICT_UNREADABLE,
    Calibration,
    TitlePageCheck,
    check_front_pages,
    check_pdf,
    is_rejected,
    pdf_path_for,
    rejection_for,
    upgrade,
)

MakePdf = Callable[..., Path]

_TITLE = "Graph Retrieval for Scientific Corpora at Scale"
_PAGE = (
    "Graph Retrieval for Scientific Corpora at Scale\n"
    "Anna Beispiel, Bert Müller, Chen Li\n"
    "University of Somewhere\n"
    "Abstract. We study retrieval over graphs."
)
_CALIBRATED = Calibration(min_author_share=0.5, max_share_for_rejection=0.0, source="Test")


def test_the_own_title_and_authors_are_found_on_page_one() -> None:
    """Titel über den Intake-Mechanismus, Nachnamen als ganze Wörter, Umlaute gefaltet."""
    check = check_front_pages(
        [_PAGE], _TITLE, ["Beispiel, Anna", "Bert Müller", "Chen Li", "Dora Fremd"]
    )

    assert check.readable
    assert check.title_found
    assert (check.surnames_checked, check.surnames_found) == (4, 3)
    assert check.author_share == pytest.approx(0.75)
    assert check.summary() == "Titel 1.00, Autoren 3/4 auf S. 1"


def test_a_foreign_record_finds_neither_title_nor_authors() -> None:
    """Der Befund-3-Fall: Die Kennung stammte aus dem Literaturverzeichnis."""
    check = check_front_pages(
        [_PAGE], "GPT-4 Technical Report of a Large Multimodal Model", ["OpenAI"]
    )

    assert not check.title_found
    assert check.author_share == 0.0


def test_a_surname_must_match_as_a_whole_word() -> None:
    """„Li“ steckt in „Library“, zählt dort aber nicht."""
    check = check_front_pages(["A Library of Graph Retrieval Methods for Everyone"], "", ["Wei Li"])

    assert check.surnames_found == 0


def test_only_the_first_ten_surnames_are_checked() -> None:
    """Lange Kollaborationslisten stehen oft nicht vollständig auf Seite 1."""
    authors = [f"Vorname Name{index}" for index in range(30)]

    check = check_front_pages([_PAGE], _TITLE, authors)

    assert check.surnames_checked == titlepage.MAX_CHECKED_SURNAMES


def test_an_empty_page_is_unreadable() -> None:
    """Ohne Text auf Seite 1 ist kein Urteil möglich – das wird ausgewiesen, nicht geraten."""
    check = check_front_pages(["   "], _TITLE, ["Anna Beispiel"])

    assert check == TitlePageCheck(readable=False)
    assert check.verdict(_CALIBRATED) == VERDICT_UNREADABLE
    assert check.summary() == "S. 1 ohne lesbaren Text"


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (TitlePageCheck(True, 0.95, 4, 3), VERDICT_CONFIRMED),
        (TitlePageCheck(True, 0.95, 4, 1), VERDICT_UNCONFIRMED),
        (TitlePageCheck(True, 0.95, 0, 0), VERDICT_UNCONFIRMED),
        (TitlePageCheck(True, 0.30, 4, 0), VERDICT_FOREIGN),
        (TitlePageCheck(True, 0.30, 4, 3), VERDICT_UNCONFIRMED),
        (TitlePageCheck(True, 0.30, 0, 0), VERDICT_UNCONFIRMED),
    ],
)
def test_the_verdict_follows_the_calibration(check: TitlePageCheck, expected: str) -> None:
    """Titel fehlt, Autoren stehen – das deutet auf eine unleserliche Titelzeile, nicht auf fremd."""
    assert check.verdict(_CALIBRATED) == expected


def test_without_calibration_nothing_is_confirmed_or_rejected() -> None:
    """Der Rückfall des A0-Abbruchkriteriums: keine automatische Entscheidung."""
    assert not titlepage.CALIBRATION.calibrated
    assert TitlePageCheck(True, 1.0, 5, 5).verdict() == VERDICT_UNCONFIRMED
    assert TitlePageCheck(True, 0.0, 5, 0).verdict() == VERDICT_UNCONFIRMED


def test_the_calibration_is_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Die geltende Kalibrierung ist **eine** Stelle im Code – keine eingefrorenen Defaults."""
    monkeypatch.setattr(titlepage, "CALIBRATION", _CALIBRATED)

    assert TitlePageCheck(True, 1.0, 5, 5).verdict() == VERDICT_CONFIRMED


def test_a_real_pdf_is_checked_through_the_intake_reader(make_pdf: MakePdf) -> None:
    """Ende zu Ende über ``read_front_pages``: dieselbe Leselogik wie Intake und S2."""
    pdf = make_pdf([_PAGE, "Seite zwei"], "papers/paper.pdf")

    check = check_pdf(pdf, _TITLE, ["Anna Beispiel", "Chen Li"])

    assert check.title_found
    assert check.surnames_found == 2


def test_a_broken_pdf_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    """Ein defektes PDF darf den Lauf über den ganzen Bestand nicht abbrechen."""
    broken = tmp_path / "kaputt.pdf"
    broken.write_bytes(b"%PDF-1.4 kein echtes pdf")

    assert check_pdf(broken, _TITLE, ["Anna Beispiel"]).readable is False
    assert check_pdf(tmp_path / "fehlt.pdf", _TITLE, []).readable is False


def test_the_pdf_is_found_in_the_corpus_folder_first(tmp_path: Path) -> None:
    """Der Korpus kann seit der Extraktion umgezogen sein; der Dateiname bleibt gleich."""
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "Ein Paper.pdf").write_bytes(b"%PDF-1.4")
    moved_uri = "file:///alter/ort/Ein%20Paper.pdf"

    assert pdf_path_for(moved_uri, papers) == papers / "Ein Paper.pdf"
    assert pdf_path_for(moved_uri, tmp_path / "leer") is None
    assert pdf_path_for((papers / "Ein Paper.pdf").as_uri()) == papers / "Ein Paper.pdf"
    assert pdf_path_for("file:///papers/Eintrag.refjson", papers) is None


def _record(**fields: object) -> MetadataRecord:
    """Ein gespeicherter Treffer mit sinnvollen Vorgaben."""
    base: dict[str, object] = {
        "paper_id": "aaaa0001",
        "origin": ORIGIN_RESOLVED,
        "title": _TITLE,
        "authors": ("Anna Beispiel",),
        "doi": "10.1145/1234",
        "confidence": CONFIDENCE_WEAK,
        "evidence": "OpenAlex über Titel-Ähnlichkeit 0.91",
    }
    base.update(fields)
    return MetadataRecord(**base)  # type: ignore[arg-type]


def test_an_upgrade_keeps_the_origin_and_extends_the_evidence() -> None:
    """Die Herkunft bleibt ``resolved``; der Beleg sagt, wie der Treffer gefunden **und** belegt wurde."""
    upgraded = upgrade(_record(), TitlePageCheck(True, 0.97, 2, 2))

    assert upgraded.origin == ORIGIN_RESOLVED
    assert upgraded.confidence == CONFIDENCE_STRONG
    assert upgraded.evidence == (
        f"OpenAlex über Titel-Ähnlichkeit 0.91; {EVIDENCE_TITLE_PAGE} (Titel 0.97, Autoren 2/2 auf S. 1)"
    )


def test_a_rejection_blocks_the_same_hit_by_any_key() -> None:
    """DOI (ohne Groß-/Kleinschreibung), arXiv-ID oder normalisierter Titel genügen je allein."""
    rejection = rejection_for(
        _record(arxiv_id="2303.08774"), TitlePageCheck(True, 0.2, 1, 0), "2026-09-24"
    )

    assert rejection.date == "2026-09-24"
    assert "Fremd-Paper" in rejection.reason
    assert is_rejected(_record(doi="10.1145/1234".upper()), [rejection])
    assert is_rejected(_record(doi="", title="", arxiv_id="2303.08774"), [rejection])
    assert is_rejected(_record(doi="", title=_TITLE.upper() + "!"), [rejection])
    assert not is_rejected(_record(doi="10.1/anders", title="Ganz anders"), [rejection])
    assert not is_rejected(_record(), [Rejection()])
