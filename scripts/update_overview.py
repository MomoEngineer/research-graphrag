"""CLI: Übersicht-Entwürfe erzeugen (Phase 2, Option B).

Erzeugt aus den Canonical-Papern deterministische, extraktive **Entwurfszeilen** für noch nicht
gelistete Paper und hängt sie **append-only** an die kuratierte ``Übersicht.md`` an (byte-erhaltend
und atomar, wertende Spalten bleiben leer). Dass die Übersicht die einzige Senke ist, entscheidet
docs/adr/0019-corpus-intake-new-papers-phase8.md; dieser Nachpflege-Pfad bleibt für PDFs bestehen,
die direkt in ``papers/`` abgelegt wurden.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.update_overview
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.overview.drafts import append_overview_rows

_REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    """Erzeugt Entwurfszeilen und gibt einen Kurzreport auf stdout aus."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description="Übersicht-Entwürfe (Option B).")
    parser.add_argument(
        "--data",
        default=str(_REPO_ROOT / "data"),
        help="Datenordner mit canonical/ und manifest.json",
    )
    parser.add_argument(
        "--uebersicht",
        default=str(_REPO_ROOT / "Übersicht.md"),
        help="Kuratierte Übersicht (wird append-only ergänzt)",
    )
    args = parser.parse_args()

    try:
        report = append_overview_rows(data_dir=args.data, target_path=args.uebersicht)
    except DomainError as exc:
        print(f"[overview] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    print(
        f"[overview] geschrieben={report.written} "
        f"bereits-gelistet={report.skipped_known} Paper={report.n_papers}"
    )
    if report.row_ids:
        print(f"[overview] neue IDs: {', '.join(report.row_ids)}")
    print(f"[overview] Übersicht: {report.target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
