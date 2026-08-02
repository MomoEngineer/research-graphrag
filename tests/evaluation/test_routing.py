"""Tests für die Router-Messung gegen den dokumentierten Contract (Phase 7 / A7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.eval_retrieval import main as eval_main

from research_graphrag.evaluation.report import render_router_report
from research_graphrag.evaluation.routing import (
    CONTRACT_MODES,
    RouterGoldSet,
    RouterQuestion,
    RouterReport,
    RouterScore,
    evaluate_router,
    load_router_gold,
    signal_coverage,
    verify_router_labels,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROUTER_GOLD = _REPO_ROOT / "eval" / "router-gold.json"

EXPECTED_MISSES = ("R83",)
"""Eingefrorener Stand: der einzige bewusst dokumentierte Fehlgriff (Gleichstand → Fallback)."""


@pytest.fixture(scope="module")
def gold() -> RouterGoldSet:
    """Das reale Router-Gold-Set (die Datei ist die Single Source of Truth)."""
    return load_router_gold(_ROUTER_GOLD)


def _question(qid: str, query: str, kind: str) -> RouterQuestion:
    """Baut eine Gold-Frage mit vertragskonformer Modus-Menge."""
    return RouterQuestion(
        qid=qid,
        query=query,
        kind=kind,
        language="de",
        expected_modes=CONTRACT_MODES[kind],
    )


def test_gold_set_loads_with_version_and_questions(gold: RouterGoldSet) -> None:
    """Das Gold-Set trägt eine Version und Fragen in Dateireihenfolge."""
    assert gold.version
    assert len(gold.questions) > 50
    assert gold.questions[0].qid == "R01"
    assert {question.language for question in gold.questions} == {"de", "en"}


def test_gold_labels_follow_the_documented_contract(gold: RouterGoldSet) -> None:
    """Jede eingefrorene Modus-Menge ist aus dem Fragetyp ableitbar (mechanisch prüfbar)."""
    assert verify_router_labels(gold) == ()


def test_every_signal_is_covered_by_at_least_one_question(gold: RouterGoldSet) -> None:
    """Kein Signal bleibt ungeprüft – die Vorabmessung fand 9 von 51 überhaupt getroffen."""
    assert signal_coverage(gold) == ()


def test_all_contract_kinds_are_represented(gold: RouterGoldSet) -> None:
    """Das Gold-Set deckt alle Fragetypen der README-Tabelle ab."""
    assert {question.kind for question in gold.questions} == set(CONTRACT_MODES)


def test_router_hits_the_contract_except_the_documented_limit(gold: RouterGoldSet) -> None:
    """Regression qid-genau: nur der dokumentierte Gleichstand fällt aus dem Contract."""
    report = evaluate_router(gold)
    assert tuple(score.qid for score in report.misses) == EXPECTED_MISSES
    assert report.accuracy == pytest.approx(
        (len(gold.questions) - len(EXPECTED_MISSES)) / len(gold.questions)
    )


def test_confidence_strong_never_misses(gold: RouterGoldSet) -> None:
    """Die Konfidenzstufe ist aussagekräftig: ``strong`` liegt immer im Contract."""
    report = evaluate_router(gold)
    strong = [score for score in report.scores if score.confidence == "strong"]
    assert strong
    assert all(score.hit for score in strong)


def test_report_aggregates_by_kind_and_confidence(gold: RouterGoldSet) -> None:
    """Die Aggregate zählen jede Frage genau einmal."""
    report = evaluate_router(gold)
    assert sum(count for _rate, count in report.by_kind().values()) == len(gold.questions)
    assert sum(count for _rate, count in report.by_confidence().values()) == len(gold.questions)


def test_confusion_lists_only_misses(gold: RouterGoldSet) -> None:
    """Die Verwechslungsmatrix enthält ausschließlich Fehlgriffe."""
    report = evaluate_router(gold)
    assert sum(report.confusion().values()) == len(report.misses)
    for kind, mode in report.confusion():
        assert mode not in CONTRACT_MODES[kind]


def test_verify_router_labels_detects_a_manipulated_label() -> None:
    """Eine von Hand gesetzte Modus-Menge fällt auf."""
    broken = RouterGoldSet(
        version="0.0.1",
        questions=(
            RouterQuestion(
                qid="X01",
                query="Welche Themen gibt es?",
                kind="synthesis",
                language="de",
                expected_modes=("drift",),
            ),
        ),
    )
    findings = verify_router_labels(broken)
    assert len(findings) == 1
    assert "X01" in findings[0]


def test_verify_router_labels_detects_an_unknown_kind() -> None:
    """Ein Fragetyp ohne Contract-Eintrag ist ein Befund."""
    broken = RouterGoldSet(
        version="0.0.1",
        questions=(
            RouterQuestion(
                qid="X02",
                query="beliebig",
                kind="telepathie",
                language="de",
                expected_modes=("basic",),
            ),
        ),
    )
    assert "unbekannter Fragetyp" in verify_router_labels(broken)[0]


def test_empty_report_has_no_accuracy() -> None:
    """Ein leerer Bericht liefert 0.0 statt einer Division durch null."""
    assert RouterReport(version="0.0.1", scores=()).accuracy == 0.0


def test_score_hit_uses_the_whole_contract_set() -> None:
    """Detailfragen gelten mit ``local`` **und** ``basic`` als vertragstreu."""
    score = RouterScore(
        qid="X03",
        kind="detail",
        expected_modes=CONTRACT_MODES["detail"],
        actual_mode="basic",
        confidence="none",
        signals=(),
    )
    assert score.hit


def test_load_router_gold_reads_optional_note(tmp_path: Path) -> None:
    """Die Notiz ist optional und wird sonst leer geführt."""
    path = tmp_path / "router-gold.json"
    path.write_text(
        json.dumps(
            {
                "router_gold_version": "0.0.1",
                "questions": [
                    {
                        "qid": "X04",
                        "query": "Welche Themen gibt es?",
                        "kind": "synthesis",
                        "language": "de",
                        "expected_modes": ["global"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = load_router_gold(path)
    assert loaded.questions[0].note == ""


def test_render_router_report_shows_treue_and_limitation(gold: RouterGoldSet) -> None:
    """Der Bericht nennt Treue, Fragetypen, Konfidenz, Fehlgriffe und die Aussagegrenze."""
    rendered = render_router_report(evaluate_router(gold), gold)
    assert "Contract-Treue" in rendered
    assert "synthesis" in rendered
    assert "Konfidenz strong" in rendered
    assert "R83" in rendered
    assert "Aussagegrenze" in rendered


def test_render_router_report_without_misses_omits_the_section() -> None:
    """Ohne Fehlgriff entfällt der Abschnitt – der Bericht bleibt knapp."""
    clean = RouterGoldSet(
        version="0.0.1",
        questions=(_question("X05", "Welche Themen gibt es?", "synthesis"),),
    )
    rendered = render_router_report(evaluate_router(clean), clean)
    assert "Fehlgriffe" not in rendered


def test_cli_router_prints_the_report(capsys: pytest.CaptureFixture[str]) -> None:
    """``--router`` misst ohne Index und meldet keinen Fehler."""
    assert eval_main(["--router"]) == 0
    assert "Contract-Treue" in capsys.readouterr().out


def test_cli_router_verify_labels_is_green(capsys: pytest.CaptureFixture[str]) -> None:
    """``--router --verify-labels`` bestätigt Labels und Signal-Abdeckung."""
    assert eval_main(["--router", "--verify-labels"]) == 0
    assert "Signal-Abdeckung vollständig" in capsys.readouterr().out
