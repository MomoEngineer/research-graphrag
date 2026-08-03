"""CLI: Online-Kandidatensuche auf Metadatenebene (Phase 9 / S1).

Sucht bei arXiv und OpenAlex nach Literatur zu einer Anfrage **aus dem eigenen Bestand**,
dedupliziert die Treffer gegen den Korpus und hängt das Ergebnis an
``data/online_candidates.md`` an. Es werden **keine** Volltexte geladen und keine Dateien in den
Korpus geschrieben – der Weg dorthin führt ausschließlich über ``new_papers/`` und
``python -m scripts.intake`` (docs/adr/0020-online-candidate-search-phase9.md).

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.discover --community 2
    python -m scripts.discover --seed <paper_id> --seit 2023

Mit ``--dry-run`` werden nur die gebildeten Anfragen gezeigt – ohne Netzzugriff, ohne Bericht.

Der Modus ist **separat startbar** und bewusst kein MCP-Werkzeug: Netzverkehr soll beobachtet
angestoßen werden, nicht beiläufig durch einen Agenten. Führt der Weg nach außen über einen
Proxy, wird er über ``RESEARCH_GRAPHRAG_PROXY=host:port`` oder ``--proxy`` angegeben.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.online.report import DiscoveryReport, append_report
from research_graphrag.online.search import (
    DEFAULT_TERM_COUNT,
    discover,
    query_from_community,
    query_from_seed,
)
from research_graphrag.online.sources import DEFAULT_LIMIT, SearchQuery
from research_graphrag.online.transport import create_client

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_DATA = _REPO_ROOT / "data"


def _build_queries(db_path: Path, args: argparse.Namespace) -> list[SearchQuery]:
    """Bildet die Anfragen aus Communities und Seed-Papern des eigenen Bestands."""
    queries: list[SearchQuery] = []
    for community_id in args.community or []:
        queries.append(query_from_community(db_path, community_id, terms=args.begriffe))
    for paper_id in args.seed or []:
        queries.append(query_from_seed(db_path, str(paper_id), terms=args.begriffe))
    return queries


def _print_queries(queries: Sequence[SearchQuery]) -> None:
    """Zeigt die gebildeten Anfragen mit Suchbegriffen und Herkunft."""
    for query in queries:
        print(f"[discover] Anfrage {query.query_id}: {', '.join(query.terms)} — {query.reason}")


def _print_report(report: DiscoveryReport, target: Path) -> None:
    """Fasst den Lauf auf stdout zusammen."""
    _print_queries(report.queries)
    for source in report.sources:
        note = f" — {source.note}" if source.note else ""
        print(f"[discover] {source.source}: HTTP {source.status}{note}")
    print(
        f"[discover] {report.found} Treffer · {len(report.known)} bereits im Korpus · "
        f"{report.dropped_old} vor {report.min_year} · {len(report.fresh)} neu"
    )
    for candidate in report.fresh:
        identifier = candidate.identifier or "(kein Identifikator)"
        print(f"  · {candidate.title[:88]}")
        print(
            f"     {identifier} · {candidate.year or 'Jahr unbekannt'} · "
            f"{', '.join(candidate.sources)}"
        )
    for note in report.notes:
        print(f"[discover] Hinweis: {note}")
    if report.raw_dir is not None:
        print(f"[discover] Rohantworten: {report.raw_dir}")
    print(f"[discover] Bericht: {target}")


def main() -> int:
    """Führt einen Suchlauf aus und hängt das Ergebnis an den Bericht an."""
    # Robuste Unicode-Ausgabe (fremde Titel enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Online-Kandidatensuche ohne Download (Phase 9 / S1)."
    )
    parser.add_argument(
        "--community",
        action="append",
        type=int,
        metavar="ID",
        help="Community-Kennung aus scripts.graph_info (mehrfach möglich)",
    )
    parser.add_argument(
        "--seed",
        action="append",
        metavar="PAPER_ID",
        help='Seed-Paper für „mehr wie dieses" (mehrfach möglich)',
    )
    parser.add_argument(
        "--seit", type=int, metavar="JAHR", help="Frühestes Erscheinungsjahr (Default: letzte 5)"
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="Treffer je Quelle und Anfrage"
    )
    parser.add_argument(
        "--begriffe", type=int, default=DEFAULT_TERM_COUNT, help="Suchbegriffe je Anfrage"
    )
    parser.add_argument("--proxy", help="Proxy als host:port (sonst RESEARCH_GRAPHRAG_PROXY)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur die gebildeten Anfragen zeigen – ohne Abfrage und ohne Bericht",
    )
    parser.add_argument("--ohne-rohdaten", action="store_true", help="Rohantworten nicht ablegen")
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    parser.add_argument("--data", default=str(_DEFAULT_DATA), help="Pfad zum Datenverzeichnis")
    args = parser.parse_args()

    if not args.community and not args.seed:
        print("[discover] Bitte mindestens --community oder --seed angeben.")
        return 2

    db_path = Path(args.index)
    data_path = Path(args.data)
    try:
        queries = _build_queries(db_path, args)
        if args.dry_run:
            _print_queries(queries)
            print("[discover] Vorschau: keine Abfrage, kein Bericht, kein Kontingentverbrauch.")
            return 0
        client = create_client(proxy=args.proxy)
        report = discover(
            db_path,
            data_path,
            queries,
            client,
            limit=args.limit,
            min_year=args.seit,
            keep_raw=not args.ohne_rohdaten,
        )
        target = append_report(data_path, report)
    except DomainError as exc:
        print(f"[discover] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    _print_report(report, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
