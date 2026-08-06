"""CLI: Zitationsdaten der Korpus-Paper online auflösen (Phase 12 / K2).

Ergänzt die lokal **nicht** gewinnbaren Felder – Autoren, Venue und den Publikationsjahrgang –
über OpenAlex (Rückfall: arXiv-Feed) und schreibt sie nach ``metadata/paper_metadata.json``.
Wirksam wird das Ergebnis beim nächsten ``python -m scripts.ingest``; der Ingest selbst bleibt
netzfrei (docs/adr/0026-online-metadata-resolution.md).

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.resolve_metadata --dry-run
    python -m scripts.resolve_metadata --limit 25
    python -m scripts.resolve_metadata --paper <paper_id>

Standardmäßig werden nur Paper mit **unvollständiger** Angabe abgefragt. Jeder belegte Treffer
wird automatisch übernommen; wie stark der Beleg ist, weist die Konfidenz aus und protokolliert
``data/metadata_log.md``. Von Hand gepflegte Einträge (Herkunft ``manual``) bleiben unangetastet,
ebenso die kuratierte Übersicht – sie steht in der Auflösungskette **über** dieser Quelle.

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

from research_graphrag.bibliography.model import CONFIDENCE_STRONG, MetadataRecord
from research_graphrag.bibliography.store import (
    load_records,
    metadata_path,
    save_records,
    upsert_records,
)
from research_graphrag.errors import DomainError
from research_graphrag.online.metadata import (
    Resolution,
    ResolutionTarget,
    filter_pending,
    resolve_target,
    targets_from_index,
)
from research_graphrag.online.report import append_resolutions, store_raw
from research_graphrag.online.transport import create_client

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_DATA = _REPO_ROOT / "data"

DEFAULT_LIMIT = 50
"""Obergrenze der Paper je Lauf – schont das Kontingent der abgefragten Dienste."""


def _print_targets(targets: Sequence[ResolutionTarget]) -> None:
    """Zeigt die ausgewählten Paper samt fehlender Felder."""
    for target in targets:
        identifier = target.doi or target.arxiv_id or "(kein Identifikator)"
        missing = ", ".join(target.missing) or "(nichts)"
        print(f"  · {target.paper_id} · {identifier} · fehlt: {missing}")
        print(f"     {target.title[:88]}")


def _print_resolutions(resolutions: Sequence[Resolution], target_file: Path, log: Path) -> None:
    """Fasst den Lauf auf stdout zusammen."""
    resolved = [item for item in resolutions if item.record is not None]
    weak = [
        item
        for item in resolved
        if item.record is not None and item.record.confidence != CONFIDENCE_STRONG
    ]
    for item in resolutions:
        status = "übernommen" if item.resolved else "offen"
        print(f"  · {item.target.paper_id} · {status} · {item.note}")
    print(
        f"[resolve] {len(resolved)} von {len(resolutions)} aufgelöst "
        f"(davon {len(weak)} schwach belegt)"
    )
    print(f"[resolve] Metadaten: {target_file}")
    print(f"[resolve] Protokoll: {log}")
    print("[resolve] Wirksam wird das Ergebnis beim nächsten `python -m scripts.ingest`.")


def main() -> int:
    """Löst die Zitationsdaten auf und schreibt sie in die versionierte Metadatendatei."""
    # Robuste Unicode-Ausgabe (fremde Titel/Autoren enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Zitationsdaten online auflösen (Phase 12 / K2).")
    parser.add_argument(
        "--paper",
        action="append",
        metavar="PAPER_ID",
        help="Nur diese Paper auflösen (mehrfach möglich)",
    )
    parser.add_argument(
        "--alle",
        action="store_true",
        help="Auch bereits vollständige Datensätze erneut abfragen",
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="Höchstzahl der Paper je Lauf"
    )
    parser.add_argument("--proxy", help="Proxy als host:port (sonst RESEARCH_GRAPHRAG_PROXY)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur die Auswahl zeigen – ohne Abfrage, ohne Schreiben",
    )
    parser.add_argument("--ohne-rohdaten", action="store_true", help="Rohantworten nicht ablegen")
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    parser.add_argument("--data", default=str(_DEFAULT_DATA), help="Pfad zum Datenverzeichnis")
    parser.add_argument(
        "--metadaten", default=None, help="Pfad zu metadata/paper_metadata.json (optional)"
    )
    args = parser.parse_args()

    data_path = Path(args.data)
    target_file = Path(args.metadaten) if args.metadaten else metadata_path(data_path.parent)

    try:
        targets = targets_from_index(Path(args.index), only_incomplete=not args.alle)
        if args.paper:
            wanted = set(args.paper)
            targets = tuple(target for target in targets if target.paper_id in wanted)
        # Bereits gespeicherte Ergebnisse ausblenden: Die Auswahl stammt aus dem Index, der sie
        # erst nach dem nächsten Ingest kennt (sonst fragt ein zweiter Lauf dieselben Paper ab).
        stored = load_records(target_file)
        targets = filter_pending(targets, stored)[: max(args.limit, 0)]

        if not targets:
            print("[resolve] Nichts aufzulösen – alle ausgewählten Datensätze sind vollständig.")
            return 0

        print(f"[resolve] {len(targets)} Paper ausgewählt:")
        _print_targets(targets)
        if args.dry_run:
            print("[resolve] Vorschau: keine Abfrage, kein Schreiben, kein Kontingentverbrauch.")
            return 0

        client = create_client(proxy=args.proxy)
        resolutions = [resolve_target(client, target) for target in targets]

        records: list[MetadataRecord] = [
            item.record for item in resolutions if item.record is not None
        ]
        save_records(target_file, upsert_records(stored, records))

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        if not args.ohne_rohdaten:
            store_raw(data_path, timestamp, tuple(raw for item in resolutions for raw in item.raw))
        log = append_resolutions(data_path, timestamp, resolutions)
    except DomainError as exc:
        print(f"[resolve] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    _print_resolutions(resolutions, target_file, log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
