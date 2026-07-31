"""CLI: Frage über Basic Search (mit Provenienz) beantworten (Option B).

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.ask "Welche Methode nutzt Paper X?"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.retrieval.basic import search_basic

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"


def main() -> int:
    """Beantwortet eine Frage über den gebauten Index und zeigt die Provenienz."""
    parser = argparse.ArgumentParser(description="Basic Search mit Provenienz (Option B).")
    parser.add_argument("query", help="Natürlichsprachige Frage")
    parser.add_argument("-k", type=int, default=5, help="Maximale Trefferzahl")
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    args = parser.parse_args()

    try:
        result = search_basic(args.index, args.query, args.k)
    except DomainError as exc:
        print(f"[ask] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    if not result.citations:
        print(f"[ask] Keine belegten Treffer für: {args.query!r}")
        return 0

    print(f"[ask] Treffer für {args.query!r}:")
    for rank, citation in enumerate(result.citations, start=1):
        print(
            f"  {rank}. Paper {citation.paper_id} · Seite {citation.page_number} "
            f"· Score {citation.score:.3f}"
        )
        print(f"     {citation.snippet}")
        print(f"     Quelle: {citation.source_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
