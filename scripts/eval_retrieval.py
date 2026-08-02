"""CLI: Quantitative, offline Retrieval-Evaluation (Hit@k/MRR) gegen ein versioniertes Gold-Set.

Das Skript ist eine **dünne Hülle** um das Paket
:mod:`research_graphrag.evaluation`; die Logik liegt dort (typgeprüft, getestet und aus
[scripts/qa.py](qa.py) wiederverwendbar). Gemessen werden zwei Ebenen:

* **Primitive** (Default, schnell) – die geteilte lexikalische Chunk-Suche, die Basic, der
  Local-Seed, der Local-Fan-out und die DRIFT-Verfeinerung gemeinsam nutzen.
* **Modi als Ganzes** (``--modi``, spürbar langsamer) – zusätzlich Local-Fan-out,
  Community-Auswahl und DRIFT-Deckelung.

Die Labels sind **mechanisch aus dem Chunk-Text abgeleitet** und über ``--verify-labels``
nachrechenbar; ``--write-baseline``/``--check`` frieren den Stand ein und melden Regressionen
**qid-genau** (docs/adr/0016-quantitative-retrieval-evaluation-phase7.md).

Exit-Codes: ``0`` unauffällig · ``1`` Befund (Regression, nicht reproduzierbare Labels, Fehler)
· ``2`` Baseline nicht vergleichbar. Aufruf vom Repository-Wurzelverzeichnis::

    python -m scripts.eval_retrieval
    python -m scripts.eval_retrieval --k 10 --scoring tfidf
    python -m scripts.eval_retrieval --verify-labels
    python -m scripts.eval_retrieval --modi
    python -m scripts.eval_retrieval --write-baseline
    python -m scripts.eval_retrieval --check
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.evaluation import (
    MODES,
    RunParameters,
    build_baseline,
    compare,
    evaluate_all,
    evaluate_primitive,
    load_baseline,
    load_gold_set,
    precheck,
    read_fingerprint,
    render_comparison,
    render_modes,
    render_report,
    save_baseline,
    verify_labels,
)
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, TfidfIndex

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_GOLD = _REPO_ROOT / "eval" / "retrieval-gold.json"
_DEFAULT_BASELINE = _REPO_ROOT / "eval" / "retrieval-baseline.json"


def _parse_labels(raw: str) -> tuple[str, ...]:
    """Zerlegt die ``--modi``-Angabe in Ebenen-Bezeichner (Reihenfolge bleibt erhalten)."""
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def main(argv: list[str] | None = None) -> int:
    """Führt die Evaluation aus (CLI-Einstiegspunkt)."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(
        description="Quantitative Retrieval-Evaluation (Hit@k/MRR) gegen das Gold-Set."
    )
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-Datei.")
    parser.add_argument("--gold", default=str(_DEFAULT_GOLD), help="Pfad zum Gold-Set (JSON).")
    parser.add_argument(
        "--baseline", default=str(_DEFAULT_BASELINE), help="Pfad zur Baseline-Datei (JSON)."
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

    gold = load_gold_set(args.gold)
    params = RunParameters(k=args.k, scoring=args.scoring)

    if args.verify_labels:
        findings = verify_labels(args.index, gold)
        for finding in findings:
            print(f"  ! {finding}")
        print(f"Labels: {len(gold.questions) - len(findings)}/{len(gold.questions)} reproduzierbar")
        return 1 if findings else 0

    try:
        if args.write_baseline:
            reports = evaluate_all(args.index, gold, params)
            fingerprint = read_fingerprint(args.index, gold, params)
            baseline = build_baseline(reports, fingerprint, created=date.today().isoformat())
            save_baseline(baseline, args.baseline)
            print(render_modes(reports, gold))
            print()
            print(f"Baseline eingefroren: {args.baseline}")
            return 0

        if args.check:
            # Vergleichbarkeit zuerst prüfen – ein voller Modus-Lauf dauert Minuten.
            baseline = load_baseline(args.baseline)
            fingerprint = read_fingerprint(args.index, gold, params)
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
