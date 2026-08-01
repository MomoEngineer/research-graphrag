"""CLI: Read-only-Übersicht der Intra-Korpus-Zitationen eines Papers (Phase 7 / A2).

Beantwortet „welche Paper zitiert X?" und „welche Paper bauen auf X auf?" aus den beim
Ingest erzeugten ``CITES``-Kanten – jeweils mit Quelle (``source_uri``) und dem Kriterium,
über das die Kante erkannt wurde (``doi``/``arxiv``/``title``). Grundsatz und Grenzen (nur
Intra-Korpus, Präzision vor Recall): docs/adr/0011-intra-corpus-citation-graph-phase7.md.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.citations <paper_id>

Die ``paper_id`` stammt aus ``python -m scripts.ask`` (Provenienz der Treffer) oder aus
``python -m scripts.graph_info`` (Vertreter je Community).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.retrieval.citations import CitationLink, get_citations

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"


def _print_links(heading: str, links: tuple[CitationLink, ...]) -> None:
    """Gibt eine Zitationsrichtung mit Provenienz aus."""
    if not links:
        print(f"[citations] {heading}: (keine)")
        return
    print(f"[citations] {heading} ({len(links)}):")
    for link in links:
        print(f"  · Paper {link.paper.paper_id} · Match: {link.method}")
        print(f"     Quelle: {link.paper.source_uri}")
        if link.paper.snippet:
            print(f"     {link.paper.snippet}")


def main() -> int:
    """Gibt ausgehende und eingehende Zitationen eines Papers auf stdout aus."""
    # Robuste Unicode-Ausgabe (Dateinamen enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Intra-Korpus-Zitationen eines Papers (Phase 7 / A2)."
    )
    parser.add_argument("paper_id", help="Stabile Paper-ID (aus scripts.ask / scripts.graph_info)")
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    args = parser.parse_args()

    try:
        result = get_citations(args.index, args.paper_id)
    except DomainError as exc:
        print(f"[citations] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    print(f"[citations] Paper {result.paper.paper_id}")
    print(f"     Quelle: {result.paper.source_uri}")
    _print_links("zitiert", result.cites)
    _print_links("wird zitiert von", result.cited_by)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
