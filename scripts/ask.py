"""CLI: Frage über die Retrieval-Modi (Basic/Local/Global/DRIFT) mit Provenienz beantworten.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.ask "Welche Methode nutzt Paper X?"
    python -m scripts.ask "Welche Forschungsrichtungen zeichnen sich ab?" --mode global

Ohne ``--mode`` (bzw. ``--mode auto``) wählt ein schlanker Heuristik-Router den Modus
(siehe docs/adr/0008-retrieval-and-query-router-phase4.md). Die natürlichsprachige Antwort
formuliert anschließend der aufrufende Agent (Copilot) aus den hier gelieferten, belegten
Treffern. ``-k`` steuert die Trefferzahl je Modus (Basic: Chunks, Local: Chunk-Nachbarn,
Global: Communities, DRIFT: lokale Belege).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.drift import search_drift
from research_graphrag.retrieval.global_search import search_global
from research_graphrag.retrieval.local import search_local
from research_graphrag.retrieval.provenance import Citation
from research_graphrag.retrieval.router import MODES, route

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"


def _print_citation(rank: int, citation: Citation) -> None:
    """Gibt ein Chunk-Zitat inkl. Abschnitts-/Seiten-Provenienz aus."""
    section = f" · Abschnitt {citation.section_title}" if citation.section_title else ""
    print(
        f"  {rank}. Paper {citation.paper_id} · Seite {citation.page_number}{section} "
        f"· Score {citation.score:.3f}"
    )
    print(f"     {citation.snippet}")
    print(f"     Quelle: {citation.source_uri}")


def _render_basic(index: str, query: str, k: int) -> None:
    """Basic Search: Top-k-Chunk-Zitate."""
    result = search_basic(index, query, k)
    if not result.citations:
        print(f"[ask] Keine belegten Treffer für: {query!r}")
        return
    print(f"[ask] Basic-Treffer für {query!r}:")
    for rank, citation in enumerate(result.citations, start=1):
        _print_citation(rank, citation)


def _render_local(index: str, query: str, k: int) -> None:
    """Local Search: Seed-Chunk, Chunk-Nachbarschaft und Paper-Fan-out."""
    result = search_local(index, query, k=k)
    if result.seed is None:
        print(f"[ask] Kein Seed-Treffer für: {query!r}")
        return
    print(f"[ask] Local-Seed für {query!r}:")
    _print_citation(1, result.seed)
    if result.neighborhood:
        print("[ask] Chunk-Nachbarschaft:")
        for rank, citation in enumerate(result.neighborhood, start=1):
            _print_citation(rank, citation)
    if result.fan_out:
        print("[ask] Paper-Fan-out (Graph-Nachbarn):")
        for neighbor in result.fan_out:
            print(f"  · Paper {neighbor.paper_id} · Kantengewicht {neighbor.weight:.3f}")
            if neighbor.citation is not None:
                _print_citation(1, neighbor.citation)


def _render_global(index: str, query: str, k: int) -> None:
    """Global Search: query-relevante Communities mit repräsentativer Paper-Provenienz."""
    result = search_global(index, query, k)
    if not result.communities:
        print(f"[ask] Keine passende Community für: {query!r}")
        return
    print(f"[ask] Global-Communities für {query!r}:")
    for match in result.communities:
        keywords = ", ".join(match.keywords) or "(keine)"
        print(
            f"  #{match.community_id} · {match.size} Paper · Score {match.score:.3f} "
            f"· Keywords: {keywords}"
        )
        for ref in match.representatives:
            print(f"     Vertreter {ref.paper_id} · Quelle: {ref.source_uri}")
            if ref.snippet:
                print(f"       {ref.snippet}")


def _render_drift(index: str, query: str, k: int) -> None:
    """DRIFT Search: gewählte Community (Kontext) + lokale Chunk-Belege."""
    result = search_drift(index, query, k=k)
    if result.community is None:
        print(f"[ask] Keine passende Community für: {query!r}")
        return
    match = result.community
    keywords = ", ".join(match.keywords) or "(keine)"
    print(
        f"[ask] DRIFT-Kontext für {query!r}: Community #{match.community_id} "
        f"({match.size} Paper) · Keywords: {keywords}"
    )
    if not result.citations:
        print("[ask] Keine lokalen Belege innerhalb der Community.")
        return
    print("[ask] Lokale Belege:")
    for rank, citation in enumerate(result.citations, start=1):
        _print_citation(rank, citation)


_RENDERERS: dict[str, Callable[[str, str, int], None]] = {
    "basic": _render_basic,
    "local": _render_local,
    "global": _render_global,
    "drift": _render_drift,
}


def main() -> int:
    """Beantwortet eine Frage über den gewählten (oder gerouteten) Suchmodus."""
    # Robuste Unicode-Ausgabe (Snippets/Keywords enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Retrieval mit Provenienz (Option B, Phase 4).")
    parser.add_argument("query", help="Natürlichsprachige Frage")
    parser.add_argument("-k", type=int, default=5, help="Trefferzahl je Modus (> 0)")
    parser.add_argument(
        "--mode",
        choices=("auto", *MODES),
        default="auto",
        help="Suchmodus; 'auto' wählt ihn heuristisch (Default).",
    )
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    args = parser.parse_args()

    mode = args.mode
    if mode == "auto":
        decision = route(args.query)
        mode = decision.mode
        print(f"[ask] Router: {decision.rationale}")

    try:
        _RENDERERS[mode](args.index, args.query, args.k)
    except DomainError as exc:
        print(f"[ask] Fehler [{exc.code.value}]: {exc.message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
