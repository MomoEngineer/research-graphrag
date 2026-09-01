"""CLI: Quantitative, offline Evaluation von Retrieval (Hit@k/MRR) und Query-Router.

Das Skript ist eine **dünne Hülle** um das Paket
:mod:`research_graphrag.evaluation`; die Logik liegt dort (typgeprüft, getestet und aus
[scripts/qa.py](qa.py) wiederverwendbar). Gemessen werden drei Ebenen:

* **Primitive** (Default, schnell) – die geteilte lexikalische Chunk-Suche, die Basic, der
  Local-Seed, der Local-Fan-out und die DRIFT-Verfeinerung gemeinsam nutzen.
* **Modi als Ganzes** (``--modi``, spürbar langsamer) – zusätzlich Local-Fan-out,
  Community-Auswahl und DRIFT-Deckelung.
* **Query-Router** (``--router``, ohne Index) – die Treue zum dokumentierten
  Fragetyp→Modus-Contract (docs/adr/0017-router-hardening-phase7.md).
* **Multi-Hop** (``--zitationen``, eigenes Gold-Set) – der Fragetyp „Zitations-/Methodennetze"
  gegen die ``CITES``-Kanten: die einzige **nicht-lexikalische** Label-Quelle
  (docs/adr/0023-multihop-citation-evaluation-phase10.md).

Die Labels sind **mechanisch abgeleitet** – aus dem Chunk-Text, aus der Fragetyp-Zuordnung der
README bzw. aus dem Zitationsgraphen – und über ``--verify-labels`` nachrechenbar;
``--write-baseline``/``--check`` frieren den Stand ein und melden Regressionen
**qid-genau** (docs/adr/0016-quantitative-retrieval-evaluation-phase7.md). Retrieval und
Multi-Hop haben dabei **getrennte** Baseline-Artefakte, damit ein Regressions-Check nicht
unnötig lange dauert.

Exit-Codes: ``0`` unauffällig · ``1`` Befund (Regression, nicht reproduzierbare Labels, Fehler)
· ``2`` Baseline nicht vergleichbar. Aufruf vom Repository-Wurzelverzeichnis::

    python -m scripts.eval_retrieval
    python -m scripts.eval_retrieval --k 10 --scoring tfidf
    python -m scripts.eval_retrieval --verify-labels
    python -m scripts.eval_retrieval --modi
    python -m scripts.eval_retrieval --router
    python -m scripts.eval_retrieval --router --verify-labels
    python -m scripts.eval_retrieval --write-baseline
    python -m scripts.eval_retrieval --check
    python -m scripts.eval_retrieval --zitationen
    python -m scripts.eval_retrieval --zitationen --verify-labels
    python -m scripts.eval_retrieval --zitationen --write-gold
    python -m scripts.eval_retrieval --zitationen --write-baseline
    python -m scripts.eval_retrieval --zitationen --check
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.evaluation import (
    MODES,
    Comparison,
    MultiHopParameters,
    RunParameters,
    build_baseline,
    build_multihop_gold,
    compare,
    evaluate_all,
    evaluate_multihop,
    evaluate_primitive,
    evaluate_router,
    load_baseline,
    load_gold_set,
    load_multihop_gold,
    load_router_gold,
    precheck,
    read_fingerprint,
    recall_bounds,
    relabel_gold_set,
    render_comparison,
    render_modes,
    render_multihop_report,
    render_report,
    render_router_report,
    save_baseline,
    save_gold_set,
    save_multihop_gold,
    signal_coverage,
    unlabelled_questions,
    verify_labels,
    verify_questions,
    verify_router_labels,
)
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, TfidfIndex

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_GOLD = _REPO_ROOT / "eval" / "retrieval-gold.json"
_DEFAULT_ROUTER_GOLD = _REPO_ROOT / "eval" / "router-gold.json"
_DEFAULT_BASELINE = _REPO_ROOT / "eval" / "retrieval-baseline.json"
_DEFAULT_CITATION_GOLD = _REPO_ROOT / "eval" / "citation-gold.json"
_DEFAULT_CITATION_BASELINE = _REPO_ROOT / "eval" / "citation-baseline.json"

_NEXT_GOLD_VERSION = "1.5.0"
"""Default für ``--write-gold`` (Minor-Schritt: Fragen bleiben, Labels sind neu). War seit dem
1.4.0-Freeze (2026-08-09) veraltet, weil dort ``--gold-version`` explizit statt über diesen
Default gesetzt wurde (Phase 15 / G5, 2026-09-01) - vor dem nächsten ``--write-gold`` erneut auf
die dann nächste Minor-Version anheben."""


def _parse_labels(raw: str) -> tuple[str, ...]:
    """Zerlegt die ``--modi``-Angabe in Ebenen-Bezeichner (Reihenfolge bleibt erhalten)."""
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _run_router(path: str, *, verify: bool) -> int:
    """Führt die Router-Messung aus – wahlweise nur die Label-/Abdeckungs-Prüfung."""
    gold = load_router_gold(path)
    if verify:
        findings = list(verify_router_labels(gold))
        uncovered = signal_coverage(gold)
        if uncovered:
            findings.append(f"Signale ohne Gold-Frage: {', '.join(uncovered)}")
        for finding in findings:
            print(f"  ! {finding}")
        print(
            f"Router-Labels: {len(gold.questions)} Fragen gegen den Contract geprüft · "
            f"Signal-Abdeckung {'vollständig' if not uncovered else 'unvollständig'}"
        )
        return 1 if findings else 0
    print(render_router_report(evaluate_router(gold), gold))
    return 0


def _run_multihop(args: argparse.Namespace) -> int:
    """Führt die Multi-Hop-Messung aus (eigenes Gold-Set, eigenes Baseline-Artefakt)."""
    params = MultiHopParameters(k=args.k, scoring=args.scoring)
    if args.write_gold:
        gold = build_multihop_gold(args.index, params)
        save_multihop_gold(gold, args.citation_gold, params)
        print(f"Multi-Hop-Gold-Set erzeugt: {args.citation_gold} ({len(gold.questions)} Anker)")
        return 0

    gold = load_multihop_gold(args.citation_gold)
    if args.verify_labels:
        findings = verify_questions(args.index, gold, params)
        for finding in findings:
            print(f"  ! {finding}")
        print(
            f"Multi-Hop-Labels: {len(gold.questions)} Anker gegen den Zitationsgraphen "
            f"geprüft · {len(findings)} Befund(e)"
        )
        return 1 if findings else 0

    if args.write_baseline:
        reports = evaluate_multihop(args.index, gold, params)
        fingerprint = read_fingerprint(args.index, gold.version, params.to_dict())
        baseline = build_baseline(reports, fingerprint, created=date.today().isoformat())
        save_baseline(baseline, args.citation_baseline)
        print(render_multihop_report(reports, gold, recall_bounds(args.index)))
        print()
        print(f"Baseline eingefroren: {args.citation_baseline}")
        return 0

    if args.check:
        # Vergleichbarkeit zuerst prüfen - ein voller Multi-Hop-Lauf dauert Minuten.
        baseline = load_baseline(args.citation_baseline)
        fingerprint = read_fingerprint(args.index, gold.version, params.to_dict())
        blocked = precheck(baseline, fingerprint)
        if blocked is None and (findings := verify_questions(args.index, gold, params)):
            # Exakter als eine Kantenzahl im Fingerprint: ändert sich der Zitationsgraph
            # ohne Korpusänderung, fällt es nur hier auf.
            blocked = Comparison(
                comparable=False,
                reason=(
                    "Die eingefrorenen Zitations-Labels sind nicht mehr reproduzierbar - "
                    + "; ".join(findings[:3])
                ),
                changes=(),
            )
        if blocked is not None:
            print(render_comparison(blocked, baseline))
            return blocked.exit_code
        reports = evaluate_multihop(args.index, gold, params)
        comparison = compare(baseline, reports, fingerprint)
        print(render_comparison(comparison, baseline))
        return comparison.exit_code

    reports = evaluate_multihop(args.index, gold, params)
    print(render_multihop_report(reports, gold, recall_bounds(args.index)))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Führt die Evaluation aus (CLI-Einstiegspunkt)."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(
        description="Quantitative Retrieval-Evaluation (Hit@k/MRR) gegen das Gold-Set."
    )
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-Datei.")
    parser.add_argument("--gold", default=str(_DEFAULT_GOLD), help="Pfad zum Gold-Set (JSON).")
    parser.add_argument(
        "--router-gold",
        default=str(_DEFAULT_ROUTER_GOLD),
        help="Pfad zum Router-Gold-Set (JSON).",
    )
    parser.add_argument(
        "--baseline", default=str(_DEFAULT_BASELINE), help="Pfad zur Baseline-Datei (JSON)."
    )
    parser.add_argument(
        "--citation-gold",
        default=str(_DEFAULT_CITATION_GOLD),
        help="Pfad zum Multi-Hop-Gold-Set (JSON).",
    )
    parser.add_argument(
        "--citation-baseline",
        default=str(_DEFAULT_CITATION_BASELINE),
        help="Pfad zur Multi-Hop-Baseline (JSON).",
    )
    parser.add_argument("--k", type=int, default=5, help="Rang-Tiefe für Hit@k/MRR@k.")
    parser.add_argument(
        "--scoring",
        choices=("hybrid", "tfidf", "bm25"),
        default=DEFAULT_SCORING,
        help="Zu messende Wertung (Default 'hybrid').",
    )
    parser.add_argument(
        "--verify-labels",
        action="store_true",
        help="Nur die Labels gegen den Index nachrechnen (kein Retrieval).",
    )
    parser.add_argument(
        "--modi",
        nargs="?",
        const=",".join(MODES),
        default=None,
        metavar="LISTE",
        help=f"Modi als Ganzes messen (Default alle: {', '.join(MODES)}); langsam.",
    )
    parser.add_argument(
        "--router",
        action="store_true",
        help="Contract-Treue des Query-Routers messen (ohne Index, sofort).",
    )
    parser.add_argument(
        "--zitationen",
        action="store_true",
        help="Multi-Hop-Ebenen gegen den Zitationsgraphen messen; langsam.",
    )
    parser.add_argument(
        "--write-gold",
        action="store_true",
        help=(
            "Die Labels des Gold-Sets aus dem Index neu ableiten (nach einem Korpuswechsel); "
            "mit --zitationen wird stattdessen das Multi-Hop-Gold-Set neu erzeugt."
        ),
    )
    parser.add_argument(
        "--gold-version",
        default=_NEXT_GOLD_VERSION,
        help="Version, unter der ein mit --write-gold neu abgeleitetes Gold-Set abgelegt wird.",
    )
    parser.add_argument(
        "--notiz",
        default="Labels nach einem Korpuswechsel mechanisch neu abgeleitet.",
        help="Begründung des neuen Gold-Set-Standes (landet in 'updated_for').",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Primitive und alle Modi messen und als Baseline einfrieren.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Gegen die eingefrorene Baseline prüfen (Exit-Code 1 bei Regression).",
    )
    args = parser.parse_args(argv)

    if args.router:
        return _run_router(args.router_gold, verify=args.verify_labels)

    if args.zitationen:
        try:
            return _run_multihop(args)
        except DomainError as exc:
            print(f"  ! [{exc.code.value}] {exc.message}")
            return 1

    gold = load_gold_set(args.gold)
    params = RunParameters(k=args.k, scoring=args.scoring)

    if args.write_gold:
        updated = relabel_gold_set(args.index, gold, version=args.gold_version)
        save_gold_set(args.index, updated, args.gold, note=args.notiz)
        orphans = unlabelled_questions(updated)
        changed = sum(
            1
            for before, after in zip(gold.questions, updated.questions, strict=True)
            if before.expected_paper_ids != after.expected_paper_ids
        )
        print(
            f"Gold-Set neu abgeleitet: {args.gold} (Version {updated.version}, "
            f"{len(updated.questions)} Fragen, {changed} mit geänderten Zielen)"
        )
        if orphans:
            print(f"  ! Ohne jedes Ziel im aktuellen Korpus: {', '.join(orphans)}")
            return 1
        return 0

    if args.verify_labels:
        findings = verify_labels(args.index, gold)
        for finding in findings:
            print(f"  ! {finding}")
        print(f"Labels: {len(gold.questions) - len(findings)}/{len(gold.questions)} reproduzierbar")
        return 1 if findings else 0

    try:
        if args.write_baseline:
            reports = evaluate_all(args.index, gold, params)
            fingerprint = read_fingerprint(args.index, gold.version, params.to_dict())
            baseline = build_baseline(reports, fingerprint, created=date.today().isoformat())
            save_baseline(baseline, args.baseline)
            print(render_modes(reports, gold))
            print()
            print(f"Baseline eingefroren: {args.baseline}")
            return 0

        if args.check:
            # Vergleichbarkeit zuerst prüfen – ein voller Modus-Lauf dauert Minuten.
            baseline = load_baseline(args.baseline)
            fingerprint = read_fingerprint(args.index, gold.version, params.to_dict())
            blocked = precheck(baseline, fingerprint)
            if blocked is not None:
                print(render_comparison(blocked, baseline))
                return blocked.exit_code
            reports = evaluate_all(args.index, gold, params)
            comparison = compare(baseline, reports, fingerprint)
            print(render_comparison(comparison, baseline))
            return comparison.exit_code

        if args.modi is not None:
            reports = evaluate_all(args.index, gold, params, _parse_labels(args.modi))
            print(render_modes(reports, gold))
            return 0

        index = TfidfIndex.load(args.index)
        print(render_report(evaluate_primitive(index, gold, params), gold))
    except DomainError as exc:
        print(f"  ! [{exc.code.value}] {exc.message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
