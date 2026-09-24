"""CLI: Schwach belegte Zitierdaten gegen die Titelseite prüfen (Phase 17 / A1, Punkte 1–2).

Prüft jeden gespeicherten ``resolved``-Datensatz eines schwach belegten Volltexts mit dem
deterministischen **Seite-1-Beleg**: Stehen Titel und Autoren des Treffers auf Seite 1 des PDFs?

* **bestätigt** ⇒ Aufwertung auf ``strong`` (Beleg „Titel und Autoren auf S. 1 belegt“),
* **fremd** ⇒ Datensatz entfernt, **Ablehnungsvermerk** gesetzt; der nächste
  ``resolve_metadata``-Lauf löst das Paper neu auf und spielt den Treffer nicht wieder ein,
* **sonst** ⇒ unverändert; weiter über ``python -m scripts.metadata_worklist export``.

Bis A0, Punkt 3, die Schwellen kalibriert hat, ist der Lauf eine reine **Messung**: Er bestätigt
und verwirft nichts, sondern weist die Befunde aus
(docs/adr/0042-title-page-evidence-and-rejections.md).
Kein Netzzugriff. Wirksam wird eine Änderung beim nächsten ``python -m scripts.ingest``.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.verify_metadata --dry-run
    python -m scripts.verify_metadata
    python -m scripts.verify_metadata --paper <paper_id>
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from research_graphrag.bibliography import titlepage
from research_graphrag.bibliography.store import (
    load_records,
    load_reviews,
    metadata_path,
    save_records,
)
from research_graphrag.bibliography.triage import (
    ACTION_NOT_CHECKABLE,
    ACTION_REJECTED,
    ACTION_UNCHANGED,
    ACTION_UPGRADED,
    load_indexed_papers,
    open_weak,
    render_triage,
    triage_stored_records,
)
from research_graphrag.errors import DomainError
from research_graphrag.online.report import append_metadata_section

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_DATA = _REPO_ROOT / "data"
_DEFAULT_PAPERS = _REPO_ROOT / "papers"


def main() -> int:
    """Führt die Seite-1-Prüfung aus und schreibt Datensätze und Vermerke atomar."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Schwach belegte Zitierdaten gegen die Titelseite prüfen (Phase 17 / A1)."
    )
    parser.add_argument("--paper", action="append", metavar="PAPER_ID", help="Nur diese Paper")
    parser.add_argument(
        "--dry-run", action="store_true", help="Nur prüfen und berichten – nichts schreiben"
    )
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    parser.add_argument("--data", default=str(_DEFAULT_DATA), help="Pfad zum Datenverzeichnis")
    parser.add_argument("--papers", default=str(_DEFAULT_PAPERS), help="Ordner mit den PDFs")
    parser.add_argument(
        "--metadaten", default=None, help="Pfad zu metadata/paper_metadata.json (optional)"
    )
    args = parser.parse_args()

    data_path = Path(args.data)
    target_file = Path(args.metadaten) if args.metadaten else metadata_path(data_path.parent)
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")

    try:
        calibration = titlepage.CALIBRATION
        records = load_records(target_file)
        reviews = load_reviews(target_file)
        candidates = open_weak(load_indexed_papers(Path(args.index)), reviews)
        if args.paper:
            wanted = set(args.paper)
            candidates = tuple(paper for paper in candidates if paper.paper_id in wanted)
        run = triage_stored_records(
            records,
            reviews,
            candidates,
            papers_dir=Path(args.papers),
            today=now.date().isoformat(),
            calibration=calibration,
        )
        if not calibration.calibrated:
            print(
                "[verify] Kalibrierung aus A0, Punkt 3, fehlt: reine Messung – es wird nichts "
                "aufgewertet und nichts verworfen."
            )
        print(
            f"[verify] {len(run.decisions)} schwach belegte Paper geprüft: "
            f"aufgewertet={run.count(ACTION_UPGRADED)} verworfen={run.count(ACTION_REJECTED)} "
            f"unverändert={run.count(ACTION_UNCHANGED)} "
            f"nicht prüfbar={run.count(ACTION_NOT_CHECKABLE)}"
        )
        for decision in run.decisions:
            print(f"  · {decision.paper_id} · {decision.action} · {decision.note}")
        if args.dry_run:
            print("[verify] Vorschau: nichts geschrieben.")
            return 0
        if run.count(ACTION_UPGRADED) or run.count(ACTION_REJECTED):
            save_records(target_file, run.records, reviews=run.reviews)
        log = append_metadata_section(data_path, render_triage(timestamp, run, calibration))
    except DomainError as exc:
        print(f"[verify] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    print(f"[verify] Metadaten: {target_file}")
    print(f"[verify] Protokoll: {log}")
    print("[verify] Wirksam wird das Ergebnis beim nächsten `python -m scripts.ingest`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
