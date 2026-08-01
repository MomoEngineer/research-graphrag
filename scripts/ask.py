"""CLI: Frage über die Retrieval-Modi (Basic/Local/Global/DRIFT) mit Provenienz beantworten.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.ask "Welche Methode nutzt Paper X?"
    python -m scripts.ask "Welche Forschungsrichtungen zeichnen sich ab?" --mode global
    python -m scripts.ask "Welche Datensätze werden genutzt?" --synthese

Ohne ``--mode`` (bzw. ``--mode auto``) wählt ein schlanker Heuristik-Router den Modus
(siehe docs/adr/0008-retrieval-and-query-router-phase4.md). Die natürlichsprachige Antwort
formuliert anschließend der aufrufende Agent (Copilot) aus den hier gelieferten, belegten
Treffern. ``-k`` steuert die Trefferzahl je Modus (Basic: Chunks, Local: Chunk-Nachbarn,
Global: Communities, DRIFT: lokale Belege).

``--scoring`` wählt die Wertung der Chunk-Modi: ``hybrid`` (Default, Rang-Fusion aus BM25 und
TF-IDF), ``tfidf`` oder ``bm25`` – gedacht für Vergleichsläufe und als Notausgang
(docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md). Bei ``--mode global`` bleibt sie ohne
Wirkung, weil dort Communities und keine Chunks gerankt werden.

``--synthese`` zeigt zusätzlich den Synthese-Pfad der LLM-Bridge
(docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md): Die Belege werden modus-unabhängig
nummeriert an den Generierungs-Port gereicht. In der CLI steht offline **kein** Modell zur
Verfügung; sie nutzt daher den ``NoopGenerationProvider`` und degradiert **sichtbar** – die
volle Evidenz bleibt erhalten. Eine wirklich generierte Antwort liefert das MCP-Tool
``answer_question`` mit ``synthesize = true`` (Client-Modell via MCP-Sampling).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.generation.answer import answer_question
from research_graphrag.generation.provider import GenerationProvider, NoopGenerationProvider
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, Scoring
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.drift import search_drift
from research_graphrag.retrieval.global_search import search_global
from research_graphrag.retrieval.local import search_local
from research_graphrag.retrieval.provenance import Citation, page_label
from research_graphrag.retrieval.router import MODES, route

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"


def _print_citation(rank: int, citation: Citation) -> None:
    """Gibt ein Chunk-Zitat inkl. Abschnitts-/Seiten-Provenienz und Teil-Scores aus."""
    section = f" · Abschnitt {citation.section_title}" if citation.section_title else ""
    pages = page_label(citation.page_number, citation.page_end)
    print(f"  {rank}. Paper {citation.paper_id} · {pages}{section} · Score {citation.score:.4f}")
    print(f"     TF-IDF {citation.score_tfidf:.3f} · BM25 {citation.score_bm25:.2f}")
    print(f"     {citation.snippet}")
    print(f"     Quelle: {citation.source_uri}")


def _render_basic(index: str, query: str, k: int, scoring: Scoring) -> None:
    """Basic Search: Top-k-Chunk-Zitate."""
    result = search_basic(index, query, k, scoring=scoring)
    if not result.citations:
        print(f"[ask] Keine belegten Treffer für: {query!r}")
        return
    print(f"[ask] Basic-Treffer für {query!r}:")
    for rank, citation in enumerate(result.citations, start=1):
        _print_citation(rank, citation)


def _render_local(index: str, query: str, k: int, scoring: Scoring) -> None:
    """Local Search: Seed-Chunk, Chunk-Nachbarschaft und Paper-Fan-out."""
    result = search_local(index, query, k=k, scoring=scoring)
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


def _render_global(index: str, query: str, k: int, _scoring: Scoring) -> None:
    """Global Search: query-relevante Communities mit repräsentativer Paper-Provenienz.

    Die Chunk-Wertung ist hier ohne Wirkung – Global rankt Communities.
    """
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


def _render_drift(index: str, query: str, k: int, scoring: Scoring) -> None:
    """DRIFT Search: gewählte Community (Kontext) + lokale Chunk-Belege."""
    result = search_drift(index, query, k=k, scoring=scoring)
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


_RENDERERS: dict[str, Callable[[str, str, int, Scoring], None]] = {
    "basic": _render_basic,
    "local": _render_local,
    "global": _render_global,
    "drift": _render_drift,
}


def _render_synthesis(
    mode: str, index: str, query: str, k: int, provider: GenerationProvider, scoring: Scoring
) -> None:
    """Synthese-Pfad: nummerierte Belege plus – falls ein Modell verfügbar ist – die Antwort."""
    result = answer_question(index, query, mode=mode, k=k, provider=provider, scoring=scoring)

    if result.generated:
        model = result.model or "Client-Modell"
        print(f"[ask] Antwort ({model}):")
        print(result.answer)
    else:
        print(
            "[ask] Keine generierte Antwort (kein Sampling-fähiges Modell) – "
            "die Belege bleiben maßgeblich."
        )

    if result.evidence.is_empty():
        print(f"[ask] Keine belegten Treffer für: {query!r}")
        return
    print(f"[ask] Belege ({result.mode}):")
    for item in result.evidence.items:
        print(f"  [{item.index}] {item.label}")
        print(f"      {item.snippet}")
        print(f"      Quelle: {item.source_uri}")


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
    parser.add_argument(
        "--scoring",
        choices=("hybrid", "tfidf", "bm25"),
        default=DEFAULT_SCORING,
        help="Wertung der Chunk-Modi (Default 'hybrid'); ohne Wirkung bei --mode global.",
    )
    parser.add_argument(
        "--synthese",
        action="store_true",
        help="Belege nummeriert über die LLM-Bridge aufbereiten (CLI ohne Modell: Noop-Fallback).",
    )
    args = parser.parse_args()

    mode = args.mode
    if mode == "auto":
        decision = route(args.query)
        mode = decision.mode
        print(f"[ask] Router: {decision.rationale}")

    try:
        if args.synthese:
            _render_synthesis(
                mode, args.index, args.query, args.k, NoopGenerationProvider(), args.scoring
            )
        else:
            _RENDERERS[mode](args.index, args.query, args.k, args.scoring)
    except DomainError as exc:
        print(f"[ask] Fehler [{exc.code.value}]: {exc.message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
