"""CLI: Übersicht-Entwürfe erzeugen (Phase 2, Option B).

Erzeugt aus den Canonical-Papern deterministische, extraktive **Entwurfszeilen** für noch nicht
kuratierte Paper und hängt sie append-only an ``data/overview_drafts.md`` an. Die kuratierte
``Übersicht.md`` bleibt unangetastet (siehe docs/adr/0006-canonical-model-phase2-scope.md).

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.update_overview
"""

from __future__ import annotations

import argparse
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.overview.drafts import generate_drafts

_REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    """Erzeugt Entwurfszeilen und gibt einen Kurzreport auf stdout aus."""
    parser = argparse.ArgumentParser(description="Übersicht-Entwürfe (Option B).")
    parser.add_argument(
        "--data",
        default=str(_REPO_ROOT / "data"),
        help="Datenordner mit canonical/ und manifest.json",
    )
    parser.add_argument(
        "--uebersicht",
        default=str(_REPO_ROOT / "Übersicht.md"),
        help="Kuratierte Übersicht (nur gelesen)",
    )
    parser.add_argument(
        "--drafts",
        default=str(_REPO_ROOT / "data" / "overview_drafts.md"),
        help="Ziel-Staging-Datei (append-only)",
    )
    args = parser.parse_args()

    try:
        report = generate_drafts(
            data_dir=args.data,
            uebersicht_path=args.uebersicht,
            drafts_path=args.drafts,
        )
    except DomainError as exc:
        print(f"[overview] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    print(
        f"[overview] geschrieben={report.written} "
        f"kuratiert-übersprungen={report.skipped_curated} "
        f"bereits-entworfen={report.skipped_existing} Paper={report.n_papers}"
    )
    print(f"[overview] Entwürfe: {report.drafts_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
