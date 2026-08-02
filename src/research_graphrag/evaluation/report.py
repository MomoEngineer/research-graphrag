"""Textausgabe der Evaluation – die Präsentation liegt an einer Stelle (Phase 7 / A6).

Die Renderer sind bewusst nüchtern: Sie zeigen Kennzahlen **mit ihren Bezugsgrößen** (Coverage
nie ohne Selektivität, Coverage nie ohne Trivial-Baselines) und benennen die Aussagegrenze der
Messung, damit einzelne Zahlen nicht überinterpretiert werden
(docs/adr/0016-quantitative-retrieval-evaluation-phase7.md).
"""

from __future__ import annotations

from collections.abc import Mapping

from research_graphrag.evaluation.baseline import REGRESSION, Baseline, Comparison
from research_graphrag.evaluation.gold import GoldSet
from research_graphrag.evaluation.metrics import EvaluationReport
from research_graphrag.evaluation.routing import RouterGoldSet, RouterReport

LIMITATION = (
    "Aussagegrenze: Das Gold-Set ist fakt-orientiert (lexikalischer Anker je Frage). Gemessen "
    "wird, ob die thematisch richtige Nachbarschaft oben landet – nicht die Güte einer "
    "corpusweiten Synthese."
)
"""Deklarierte Grenze der Messung (steht in jedem Modus-Bericht)."""

ROUTER_LIMITATION = (
    "Aussagegrenze: Gemessen wird die Treue zum dokumentierten Fragetyp→Modus-Contract, "
    "nicht die Güte der gelieferten Antwort. Eine Optimierung auf Hit@k/MRR hätte das "
    "triviale Optimum 'immer basic'."
)
"""Deklarierte Grenze der Router-Messung (steht in jedem Router-Bericht)."""


def render_report(report: EvaluationReport, gold: GoldSet) -> str:
    """Formatiert einen Bericht ausführlich: eine Zeile je Frage plus Aggregate."""
    lines = [
        f"Gold-Set {gold.version} · {len(report.scores)} Fragen · k = {report.k} "
        f"· Wertung = {report.scoring} · Ebene = {report.label}",
        "",
    ]
    for score, question in zip(report.scores, gold.questions, strict=True):
        rank = str(score.first_rank) if score.first_rank is not None else "-"
        lines.append(
            f"  {score.qid} [{score.kind:10s}] Rang {rank:>2s} · RR {score.reciprocal_rank:.3f} "
            f"· {question.query}"
        )
    lines.append("")
    for kind, (hit_rate, mrr, count) in report.by_kind().items():
        lines.append(f"  {kind:10s} (n={count:2d}): Hit@{report.k} {hit_rate:.3f} · MRR {mrr:.3f}")
    lines.append("")
    lines.append(
        f"  GESAMT     (n={len(report.scores):2d}): "
        f"Hit@{report.k} {report.hit_rate:.3f} · MRR {report.mrr:.3f}"
    )
    return "\n".join(lines)


def render_modes(reports: Mapping[str, EvaluationReport], gold: GoldSet) -> str:
    """Formatiert den Modus-Vergleich samt Diagnosen und Community-Baselines."""
    first = next(iter(reports.values()), None)
    lines = [
        f"Modus-Ebene · Gold-Set {gold.version} · {len(gold.questions)} Fragen "
        f"· Wertung = {first.scoring if first else '-'}",
        "",
    ]
    for label, report in reports.items():
        diagnosis = ", ".join(f"{name} {count}" for name, count in report.by_diagnosis().items())
        suffix = f"   [{diagnosis}]" if diagnosis else ""
        lines.append(
            f"  {label:10s} (k={report.k:2d}): Hit {report.hit_rate:.3f} "
            f"· MRR {report.mrr:.3f}{suffix}"
        )

    coverage = [stats for report in reports.values() for stats in report.coverage]
    if coverage:
        lines.append("")
        lines.append("  Community-Auswahl (Coverage ist nur mit Selektivität lesbar):")
        for stats in coverage:
            lines.append(
                f"    {stats.label:12s}: Coverage {stats.coverage:.3f} "
                f"· Selektivität {stats.selectivity:.3f} · Lift {stats.lift:.2f}"
            )
    lines.append("")
    lines.append(f"  {LIMITATION}")
    return "\n".join(lines)


def render_router_report(report: RouterReport, gold: RouterGoldSet) -> str:
    """Formatiert die Router-Messung: Contract-Treue je Fragetyp, Konfidenz und Fehlgriffe."""
    lines = [
        f"Router-Gold-Set {gold.version} · {len(report.scores)} Fragen "
        f"· Contract-Treue {report.accuracy:.3f} "
        f"({len(report.scores) - len(report.misses)}/{len(report.scores)})",
        "",
    ]
    for kind, (rate, count) in report.by_kind().items():
        lines.append(f"  {kind:10s} (n={count:2d}): Treue {rate:.3f}")
    lines.append("")
    for level, (rate, count) in report.by_confidence().items():
        lines.append(f"  Konfidenz {level:7s} (n={count:2d}): Treue {rate:.3f}")
    if report.misses:
        lines.append("")
        lines.append("  Fehlgriffe:")
        for score in report.misses:
            expected = "|".join(score.expected_modes)
            lines.append(
                f"    ! {score.qid} [{score.kind:9s}] erwartet {expected:12s} "
                f"· geroutet {score.actual_mode} ({score.confidence})"
            )
    lines.append("")
    lines.append(f"  {ROUTER_LIMITATION}")
    return "\n".join(lines)


def render_comparison(comparison: Comparison, baseline: Baseline) -> str:
    """Formatiert den Regressions-Check (qid-genau, zwei Schweregrade)."""
    if not comparison.comparable:
        return "\n".join(
            [
                "Regressions-Check: nicht vergleichbar.",
                f"  ! {comparison.reason}",
                "  Bewusst neu einfrieren mit '--write-baseline'.",
            ]
        )
    lines = [f"Regressions-Check gegen die Baseline vom {baseline.created}:", ""]
    if not comparison.changes:
        lines.append("  Keine Abweichung – alle Ränge unverändert.")
        return "\n".join(lines)
    for change in comparison.changes:
        marker = "!" if change.severity == REGRESSION else " "
        before = str(change.before) if change.before is not None else "kein Treffer"
        after = str(change.after) if change.after is not None else "kein Treffer"
        lines.append(
            f"  {marker} {change.severity:17s} {change.label:10s} {change.qid}: {before} → {after}"
        )
    lines.append("")
    lines.append(
        f"  {len(comparison.regressions)} Regression(en) · "
        f"{len(comparison.changes) - len(comparison.regressions)} weitere Abweichung(en)"
    )
    return "\n".join(lines)
