"""CLI: Personenkennungen aus den abgelegten Rohantworten nachtragen (Phase 17 / A2, Punkt 3).

Die OpenAlex-Rohantworten unter ``data/online_raw/`` enthalten je Autor OpenAlex-ID und ORCID;
gespeichert wurde bis Phase 17 nur der Name. Dieser Lauf trägt die Kennungen **ohne Netzzugriff**
nach: zugeordnet über die DOI des Werks und **nur** bei identischer Namensliste. Widersprüchliche
Rohantworten werden ausgewiesen, nicht aufgelöst (docs/adr/0041-author-identity-and-schema.md).

Wirksam wird der Nachtrag beim nächsten ``python -m scripts.ingest``. Ein zweiter Lauf danach
ändert nichts mehr.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.backfill_author_ids --dry-run
    python -m scripts.backfill_author_ids
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from research_graphrag.bibliography.store import load_records, metadata_path, save_records
from research_graphrag.bibliography.triage import load_indexed_papers
from research_graphrag.errors import DomainError
from research_graphrag.online.backfill import (
    ACTION_ADDED,
    ACTION_CONFLICT,
    ACTION_MISMATCH,
    ACTION_UPDATED,
    backfill_identities,
    load_raw_authorships,
    render_backfill,
)
from research_graphrag.online.report import RAW_DIR_NAME, append_metadata_section

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_DATA = _REPO_ROOT / "data"


def main() -> int:
    """Trägt die Kennungen nach und schreibt die Metadatendatei atomar."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Personenkennungen aus den Rohantworten nachtragen (Phase 17 / A2)."
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur zählen – nichts schreiben")
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    parser.add_argument("--data", default=str(_DEFAULT_DATA), help="Pfad zum Datenverzeichnis")
    parser.add_argument(
        "--metadaten", default=None, help="Pfad zu metadata/paper_metadata.json (optional)"
    )
    args = parser.parse_args()

    data_path = Path(args.data)
    target_file = Path(args.metadaten) if args.metadaten else metadata_path(data_path.parent)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    try:
        raw, n_files, n_unreadable = load_raw_authorships(data_path / RAW_DIR_NAME)
        run = backfill_identities(
            load_indexed_papers(Path(args.index)),
            load_records(target_file),
            raw,
            n_raw_files=n_files,
            n_unreadable=n_unreadable,
        )
        print(
            f"[backfill] Rohantworten: {n_files} (unlesbar: {n_unreadable}) · "
            f"Werke mit Kennung: {len(raw)}"
        )
        print(
            f"[backfill] ergänzt: {run.count(ACTION_UPDATED)} Datensätze, "
            f"{run.count(ACTION_ADDED)} Kennungs-Datensätze · "
            f"Konflikte: {run.count(ACTION_CONFLICT)} · "
            f"andere Namensliste: {run.count(ACTION_MISMATCH)}"
        )
        if args.dry_run:
            print("[backfill] Vorschau: nichts geschrieben.")
            return 0
        if run.count(ACTION_UPDATED) or run.count(ACTION_ADDED):
            save_records(target_file, run.records)
        log = append_metadata_section(data_path, render_backfill(timestamp, run))
    except DomainError as exc:
        print(f"[backfill] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    print(f"[backfill] Metadaten: {target_file}")
    print(f"[backfill] Protokoll: {log}")
    print("[backfill] Wirksam wird das Ergebnis beim nächsten `python -m scripts.ingest`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
