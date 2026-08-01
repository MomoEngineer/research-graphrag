"""CLI: Read-only-Übersicht der Graph-Communities (Option B, Phase 3).

Zeigt die per Ingestion gebauten Louvain-Communities mit Keywords, repräsentativen Papern
und extraktiver Zusammenfassung. Dient als Phase-3-Nachweis (statt der offline nicht
existierenden „GraphRAG-CLI"); das spätere ``list_topics``-MCP-Tool folgt in Phase 5.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.graph_info
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.indexing.graph_index import load_communities

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"


def main() -> int:
    """Gibt eine kompakte Übersicht der Communities auf stdout aus."""
    # Robuste Unicode-Ausgabe (Keywords/Auszüge enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Community-Übersicht (Option B, Phase 3).")
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    parser.add_argument("-n", type=int, default=0, help="Nur die n größten Communities (0 = alle)")
    args = parser.parse_args()

    try:
        communities = load_communities(args.index)
    except DomainError as exc:
        print(f"[graph_info] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    shown = communities[: args.n] if args.n > 0 else communities
    print(f"[graph_info] {len(communities)} Communities (zeige {len(shown)}):")
    for community in shown:
        keywords = ", ".join(community.keywords) or "(keine)"
        representatives = ", ".join(community.representatives) or "(keine)"
        print(f"  #{community.community_id} · {community.size} Paper · Keywords: {keywords}")
        print(f"     Vertreter: {representatives}")
        if community.summary:
            print(f"     Auszug: {community.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
