"""CLI: Referenz-Einträge aus einer DOI-/arXiv-Liste erzeugen (Phase 13 / R1).

Liest die kuratierte Liste ``new_papers/referenzen.txt``, löst jede Kennung über OpenAlex
(Rückfall: arXiv-Feed) auf und legt je Kennung **eine** Stub-Datei ``*.refjson`` im
Eingangsordner ab. Es wird **kein** Volltext geladen und nichts nach ``papers/`` geschrieben –
der Weg in den Korpus führt ausschließlich über ``python -m scripts.intake``
(docs/adr/0029-reference-stub-resolution-phase13.md).

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.resolve_references --dry-run
    python -m scripts.resolve_references
    python -m scripts.resolve_references --limit 5

Mit ``--dry-run`` werden nur Auswahl und geplante Abfragen gezeigt – ohne Netzzugriff, ohne
Kontingentverbrauch, ohne Datei. Ein zweiter Lauf stellt für bereits erledigte Kennungen **keine**
Abfrage: Geprüft wird vorab gegen den Korpus, gegen die Stub-Dateien im Eingang und gegen die
Quarantäne ``new_papers/_duplikate/``.

Der Lauf ist **separat startbar** und bewusst kein MCP-Werkzeug: Er schreibt und benötigt Netz.
Führt der Weg nach außen über einen Proxy, wird er über ``RESEARCH_GRAPHRAG_PROXY=host:port``
oder ``--proxy`` angegeben.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.intake import load_corpus
from research_graphrag.online.references import (
    ACTION_SKIPPED,
    ACTION_WRITTEN,
    DEFAULT_LIMIT,
    REFERENCE_LIST_NAME,
    ReferenceOutcome,
    ReferenceRequest,
    plan,
    process,
    read_reference_list,
    stub_identifiers,
)
from research_graphrag.online.report import append_references, store_raw
from research_graphrag.online.transport import create_client

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_NEW = _REPO_ROOT / "new_papers"
_DEFAULT_DATA = _REPO_ROOT / "data"


def _print_settled(settled: Sequence[ReferenceOutcome]) -> None:
    """Zeigt die vorab entschiedenen Einträge (übersprungen oder nicht deutbar)."""
    for item in settled:
        print(f"  · {item.request.label} · {item.action} · {item.note}")


def _print_pending(pending: Sequence[ReferenceRequest]) -> None:
    """Zeigt die Kennungen, die abgefragt würden."""
    for request in pending:
        comment = f" — {request.comment}" if request.comment else ""
        print(f"  · Zeile {request.line_number}: {request.label}{comment}")


def _print_outcomes(outcomes: Sequence[ReferenceOutcome], inbox: Path, log: Path) -> None:
    """Fasst den Lauf auf stdout zusammen."""
    written = [item for item in outcomes if item.action == ACTION_WRITTEN]
    skipped = [item for item in outcomes if item.action == ACTION_SKIPPED]
    without_abstract = [item for item in written if not item.has_abstract]
    for item in outcomes:
        if item.action == ACTION_WRITTEN and item.path is not None:
            marker = "" if item.has_abstract else "  (ohne Abstract – bitte nachtragen)"
            print(f"  · {item.request.label} → {item.path.name}{marker}")
    print(
        f"[referenzen] {len(written)} Stub-Dateien geschrieben "
        f"(davon {len(without_abstract)} ohne Abstract) · "
        f"{len(skipped)} übersprungen · {len(outcomes) - len(written) - len(skipped)} offen"
    )
    print(f"[referenzen] Eingang: {inbox}")
    print(f"[referenzen] Protokoll: {log}")
    print("[referenzen] Übernahme in den Korpus: `python -m scripts.intake` (ab Phase 13 / R2).")


def main() -> int:
    """Erzeugt die Stub-Dateien und hängt das Ergebnis an das Protokoll an."""
    # Robuste Unicode-Ausgabe (fremde Titel enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Referenz-Einträge ohne Volltext erzeugen (Phase 13 / R1)."
    )
    parser.add_argument(
        "--liste",
        default=None,
        help=f"Pfad der Kennungsliste (Default: new_papers/{REFERENCE_LIST_NAME})",
    )
    parser.add_argument("--new", default=str(_DEFAULT_NEW), help="Eingangsordner new_papers/")
    parser.add_argument("--data", default=str(_DEFAULT_DATA), help="Pfad zum Datenverzeichnis")
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="Höchstzahl der Abfragen je Lauf"
    )
    parser.add_argument("--proxy", help="Proxy als host:port (sonst RESEARCH_GRAPHRAG_PROXY)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur Auswahl und geplante Abfragen zeigen – ohne Abfrage und ohne Datei",
    )
    parser.add_argument("--ohne-rohdaten", action="store_true", help="Rohantworten nicht ablegen")
    args = parser.parse_args()

    inbox = Path(args.new)
    data_path = Path(args.data)
    list_path = Path(args.liste) if args.liste else inbox / REFERENCE_LIST_NAME

    try:
        requests = read_reference_list(list_path)
        pending, settled = plan(requests, load_corpus(data_path), stub_identifiers(inbox))
        limited = pending[: max(args.limit, 0)]

        print(f"[referenzen] {len(requests)} Einträge gelesen aus {list_path}")
        if settled:
            _print_settled(settled)
        if not limited:
            print("[referenzen] Nichts abzufragen – alle Kennungen sind bereits erledigt.")
            return 0
        print(f"[referenzen] {len(limited)} Kennungen werden abgefragt:")
        _print_pending(limited)
        if len(limited) < len(pending):
            print(f"[referenzen] {len(pending) - len(limited)} weitere durch --limit vertagt.")
        if args.dry_run:
            print("[referenzen] Vorschau: keine Abfrage, keine Datei, kein Kontingentverbrauch.")
            return 0

        client = create_client(proxy=args.proxy)
        outcomes = [*settled, *(process(client, request, inbox) for request in limited)]

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        if not args.ohne_rohdaten:
            store_raw(data_path, timestamp, tuple(raw for item in outcomes for raw in item.raw))
        log = append_references(data_path, timestamp, outcomes)
    except DomainError as exc:
        print(f"[referenzen] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    _print_outcomes(outcomes, inbox, log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
