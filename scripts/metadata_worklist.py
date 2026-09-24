"""CLI: LLM-Arbeitsliste für schwach belegte Zitierdaten (Phase 17 / A1, Punkte 3–4).

Vier Unterbefehle:

* ``stand`` – zeigt, wie viele Paper noch **offen schwach** sind (ohne ausgewiesenen Status).
* ``export`` – schreibt die Arbeitsliste nach ``data/worklists/<Zeitstempel>/`` (JSON + Markdown
  mit Auftrag). Kein Netz, kein Eingriff in die Metadaten.
* ``import <antwort.json>`` – validiert die LLM-Antwort, legt sie unter ``metadata/llm_answers/``
  ab, löst jeden Vorschlag online auf und übernimmt **nur**, was der Seite-1-Beleg bestätigt.
  Benötigt Netz (wie ``resolve_metadata``); ``--dry-run`` prüft nur das Format, ohne Client.
* ``markieren <paper_id> --grund "…"`` – weist ein Paper ausdrücklich als **nicht auflösbar**
  aus. Das ist eine menschliche Entscheidung und kein LLM-Schritt; ``--aufheben`` löscht den Status.

Grundsatz: Das LLM schlägt vor, das Skript prüft
(docs/adr/0042-title-page-evidence-and-rejections.md). Paper, die in keiner Quelle stehen, werden
über ``correct_paper_metadata`` (``manual``) korrigiert, nach Freigabe des Nutzers je Charge.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.metadata_worklist stand
    python -m scripts.metadata_worklist export
    python -m scripts.metadata_worklist import antwort.json --dry-run
    python -m scripts.metadata_worklist import antwort.json
    python -m scripts.metadata_worklist markieren <paper_id> --grund "nur als Buchkapitel ohne DOI"
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from research_graphrag.bibliography.model import REVIEW_UNRESOLVABLE
from research_graphrag.bibliography.store import (
    load_records,
    load_reviews,
    metadata_path,
    save_records,
    set_review_status,
)
from research_graphrag.bibliography.titlepage import check_pdf
from research_graphrag.bibliography.triage import load_indexed_papers, open_weak
from research_graphrag.bibliography.worklist import (
    OUTCOME_ACCEPTED,
    build_worklist,
    import_suggestions,
    parse_answers,
    render_import,
    store_answers,
    write_worklist,
)
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.online.report import append_metadata_section, store_raw
from research_graphrag.online.transport import create_client

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_DATA = _REPO_ROOT / "data"
_DEFAULT_PAPERS = _REPO_ROOT / "papers"


def _parser() -> argparse.ArgumentParser:
    """Baut den Argument-Parser mit den vier Unterbefehlen."""
    parser = argparse.ArgumentParser(
        description="LLM-Arbeitsliste für schwach belegte Zitierdaten (Phase 17 / A1)."
    )
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    parser.add_argument("--data", default=str(_DEFAULT_DATA), help="Pfad zum Datenverzeichnis")
    parser.add_argument("--papers", default=str(_DEFAULT_PAPERS), help="Ordner mit den PDFs")
    parser.add_argument(
        "--metadaten", default=None, help="Pfad zu metadata/paper_metadata.json (optional)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("stand", help="Offen schwach belegte Paper zählen")
    export = commands.add_parser("export", help="Arbeitsliste schreiben")
    export.add_argument("--limit", type=int, default=0, help="Höchstzahl der Paper (0 = alle)")
    export.add_argument("--dry-run", action="store_true", help="Nur zählen, nichts schreiben")
    answers = commands.add_parser("import", help="LLM-Antwort prüfen und übernehmen")
    answers.add_argument("antwort", help="Pfad zur Antwortdatei (JSON)")
    answers.add_argument("--dry-run", action="store_true", help="Nur das Format prüfen")
    answers.add_argument("--proxy", help="Proxy als host:port (sonst RESEARCH_GRAPHRAG_PROXY)")
    answers.add_argument("--ohne-rohdaten", action="store_true", help="Rohantworten nicht ablegen")
    mark = commands.add_parser("markieren", help="Paper als nicht auflösbar ausweisen")
    mark.add_argument("paper_id", help="Stabile Paper-ID")
    mark.add_argument("--grund", default="", help="Begründung (Pflicht beim Setzen)")
    mark.add_argument("--aufheben", action="store_true", help="Status wieder entfernen")
    return parser


def main() -> int:
    """Führt den gewählten Unterbefehl aus."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args()
    data_path = Path(args.data)
    target_file = Path(args.metadaten) if args.metadaten else metadata_path(data_path.parent)
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")

    try:
        reviews = load_reviews(target_file)
        if args.command == "markieren":
            status = "" if args.aufheben else REVIEW_UNRESOLVABLE
            # Ein Tippfehler in der Paper-ID ergäbe sonst einen verwaisten Status, und das gemeinte
            # Paper bliebe still schwach. Aufheben bleibt ohne Prüfung möglich (Aufräumen).
            if not args.aufheben and args.paper_id not in {
                paper.paper_id for paper in load_indexed_papers(Path(args.index))
            }:
                raise DomainError(
                    ErrorCode.NOT_FOUND,
                    f"Paper nicht im Index: {args.paper_id} – die Paper-ID aus `stand` bzw. der "
                    "Arbeitsliste übernehmen.",
                )
            updated = set_review_status(reviews, args.paper_id, status, args.grund)
            save_records(target_file, load_records(target_file), reviews=updated)
            action = "aufgehoben" if args.aufheben else "als nicht auflösbar ausgewiesen"
            print(f"[worklist] {args.paper_id}: {action}.")
            print("[worklist] Wirksam wird das Ergebnis beim nächsten `python -m scripts.ingest`.")
            return 0

        papers = load_indexed_papers(Path(args.index))
        pending = open_weak(papers, reviews)
        if args.command == "stand":
            print(f"[worklist] offen schwach belegt: {len(pending)} Paper")
            for paper in pending:
                print(f"  · {paper.paper_id} · {paper.metadata.title[:88]}")
            return 0

        if args.command == "export":
            chosen = pending[: args.limit] if args.limit > 0 else pending
            print(f"[worklist] {len(chosen)} von {len(pending)} offen schwach belegten Papern.")
            if args.dry_run:
                print("[worklist] Vorschau: nichts geschrieben.")
                return 0
            entries = build_worklist(chosen, papers_dir=Path(args.papers))
            json_path, md_path = write_worklist(data_path, entries, timestamp)
            print(f"[worklist] Arbeitsliste: {md_path}")
            print(f"[worklist] Maschinenlesbar: {json_path}")
            return 0

        raw = Path(args.antwort).read_bytes()
        suggestions, findings = parse_answers(raw, {paper.paper_id for paper in pending})
        print(f"[worklist] {len(suggestions)} gültige Vorschläge, {len(findings)} ungültig.")
        for finding in findings:
            print(f"  · {finding}")
        if args.dry_run:
            print("[worklist] Vorschau: kein Client, keine Abfrage, nichts geschrieben.")
            return 0
        answers_path = store_answers(target_file.parent, raw, timestamp)
        run = import_suggestions(
            create_client(proxy=args.proxy),
            suggestions,
            records=load_records(target_file),
            reviews=reviews,
            papers={paper.paper_id: paper for paper in papers},
            papers_dir=Path(args.papers),
            timestamp=timestamp,
            today=now.date().isoformat(),
            checker=check_pdf,
        )
        save_records(target_file, run.records, reviews=run.reviews)
        if not args.ohne_rohdaten and run.raw:
            store_raw(data_path, timestamp, run.raw)
        log = append_metadata_section(
            data_path, render_import(timestamp, run, findings, answers_path)
        )
    except (DomainError, OSError) as exc:
        code = exc.code.value if isinstance(exc, DomainError) else "internal_error"
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        print(f"[worklist] Fehler [{code}]: {message}")
        return 1

    print(f"[worklist] übernommen: {run.count(OUTCOME_ACCEPTED)} von {len(run.outcomes)}")
    print(f"[worklist] LLM-Antwort abgelegt: {answers_path}")
    print(f"[worklist] Protokoll: {log}")
    print("[worklist] Wirksam wird das Ergebnis beim nächsten `python -m scripts.ingest`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
