"""CLI: Übersicht-Entwürfe erzeugen (Phase 2, Option B) – seit Phase 15 / G4 außer Dienst.

``Übersicht.md`` bekommt seit G4 **keine** neuen Zeilen mehr; das einzige menschliche
Relevanzurteil (Themenfokus, Relevanz, SRQ-Zuordnung) liegt maschinenlesbar in
``metadata/curation.json``
(docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md). Der Befehl verweigert
deshalb standardmäßig den Lauf; die zugrundeliegende Funktion
:func:`research_graphrag.overview.drafts.append_overview_rows` bleibt als Notfall-Werkzeug
erhalten und ist nur über das ausdrückliche ``--force`` erreichbar.

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

_RETIREMENT_NOTICE = (
    "[overview] Übersicht.md ist seit Phase 15 / G4 außer Dienst und bekommt keine neuen "
    "Zeilen mehr - das kuratierte Relevanzurteil liegt in metadata/curation.json "
    "(docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md). "
    "Nur mit --force wird trotzdem eine Entwurfszeile angehängt."
)


def main() -> int:
    """Verweigert den Lauf (Retirement-Hinweis) oder hängt mit ``--force`` Entwurfszeilen an."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description="Übersicht-Entwürfe (Option B, außer Dienst).")
    parser.add_argument(
        "--data",
        default=str(_REPO_ROOT / "data"),
        help="Datenordner mit canonical/ und manifest.json",
    )
    parser.add_argument(
        "--uebersicht",
        default=str(_REPO_ROOT / "Übersicht.md"),
        help="Kuratierte Übersicht (außer Dienst; wird nur mit --force ergänzt)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ausdrückliches Opt-in: trotz Außerdienststellung Entwurfszeilen anhängen.",
    )
    args = parser.parse_args()

    if not args.force:
        print(_RETIREMENT_NOTICE)
        return 1

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
