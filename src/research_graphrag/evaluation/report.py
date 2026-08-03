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
from research_graphrag.evaluation.multihop import (
    CITING_BUCKETS,
    MultiHopGoldSet,
    RecallBounds,
)
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

MULTIHOP_LIMITATION = (
    "Aussagegrenze: Die Labels stammen aus dem Intra-Korpus-Zitationsgraphen. Gemessen wird, "
    "ob die zitierenden Paper eines Ankers gefunden werden - nicht, ob der Graph vollständig "
    "ist. Treffer mit der Diagnose ':ref' stammen aus einem Referenzabschnitt, also aus der "
    "Bibliografie des zitierenden Papers, und sind damit lexikalisch erkauft."
)
"""Deklarierte Grenze der Multi-Hop-Messung (steht in jedem Multi-Hop-Bericht)."""

MULTIHOP_UPPER_BOUND = (
    "get_citations liest dieselbe Tabelle wie die Labels - Hit 1,000 per Konstruktion. "
    "Es ist deshalb der triviale Oberwert dieser Messung und keine Kennzahl."
)
"""Bezugsgröße, ohne die die Multi-Hop-Zahlen überinterpretiert würden."""


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


def render_multihop_report(
    reports: Mapping[str, EvaluationReport],
    gold: MultiHopGoldSet,
    bounds: RecallBounds | None = None,
) -> str:
    """Formatiert die Multi-Hop-Messung: Ebenen, Diagnosen, Lift und Recall-Schranken.

    Der Bericht nennt bewusst drei Bezugsgrößen mit: den **trivialen Oberwert**
    (``get_citations``), die **Zufalls-Baseline** der strukturellen Auswahl und die
    **strukturellen Grenzen** des Zitationsgraphen. Ohne sie wären die Zahlen nicht lesbar
    (docs/adr/0023-multihop-citation-evaluation-phase10.md).
    """
    first = next(iter(reports.values()), None)
    lines = [
        f"Multi-Hop-Gold-Set {gold.version} · {len(gold.questions)} Anker "
        f"· Wertung = {first.scoring if first else '-'} · Labels = Zitationsgraph",
        "",
    ]
    for label, report in reports.items():
        diagnosis = ", ".join(f"{name} {count}" for name, count in report.by_diagnosis().items())
        suffix = f"   [{diagnosis}]" if diagnosis else ""
        lines.append(
            f"  {label:12s} (k={report.k:2d}): Hit {report.hit_rate:.3f} "
            f"· MRR {report.mrr:.3f}{suffix}"
        )

    buckets = [name for _threshold, name in reversed(CITING_BUCKETS)]
    lines.append("")
    lines.append("  Hit@k nach Zitationshäufigkeit des Ankers:")
    lines.append(f"    {'Ebene':12s}" + "".join(f"{name:>14s}" for name in buckets))
    for label, report in reports.items():
        by_kind = report.by_kind()
        cells = "".join(
            f"{by_kind[name][0]:14.3f}" if name in by_kind else f"{'-':>14s}" for name in buckets
        )
        lines.append(f"    {label:12s}{cells}")

    coverage = [stats for report in reports.values() for stats in report.coverage]
    if coverage:
        lines.append("")
        lines.append("  Strukturelle Auswahl (Coverage ist nur mit Selektivität lesbar):")
        for stats in coverage:
            lines.append(
                f"    {stats.label:14s}: Coverage {stats.coverage:.3f} "
                f"· Selektivität {stats.selectivity:.3f} · Lift {stats.lift:.2f}"
            )

    if bounds is not None:
        lines.append("")
        lines.append("  Strukturelle Grenzen des Zitationsgraphen (obere Schranke, kein Recall):")
        lines.append(
            f"    ohne erkannten Referenzabschnitt (können nicht zitieren): "
            f"{len(bounds.without_reference_section)} von {bounds.n_papers}"
        )
        lines.append(
            f"    ohne Titel-Schlüssel: {len(bounds.without_title_key)} "
            f"· ohne Identifikator-Schlüssel: {len(bounds.without_identifier_key)}"
        )
        lines.append(
            f"    als Ziel unerreichbar (weder noch): "
            f"{len(bounds.unreachable_targets)} von {bounds.n_papers}"
        )

    lines.append("")
    lines.append(f"  {MULTIHOP_UPPER_BOUND}")
    lines.append("")
    lines.append(f"  {MULTIHOP_LIMITATION}")
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
