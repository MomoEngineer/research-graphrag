"""CLI: Personen im Korpus recherchieren (Phase 17 / A4, read-only).

Gegenstück zu den vier MCP-Personen-Werkzeugen (docs/adr/0043-author-index-and-person-tools.md):

    python -m scripts.authors suchen "Asai"
    python -m scripts.authors profil A5023888391
    python -m scripts.authors paper A5023888391 "retrieval"
    python -m scripts.authors zitationen A5023888391

``suchen`` liefert die Personenschlüssel, die die übrigen Unterbefehle erwarten. Jede Ausgabe
endet mit der Abdeckung der Personenebene: Nur Paper mit belegten Zitierdaten tragen Autoren, ein
fehlender Treffer heißt deshalb nicht, dass die Person nichts im Korpus hat.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.limits import MAX_RESULT_COUNT
from research_graphrag.retrieval.authors import (
    DEFAULT_CANDIDATE_LIMIT,
    Coverage,
    PaperBrief,
    get_author,
    get_author_citations,
    search_author_papers,
    search_authors,
)
from research_graphrag.retrieval.provenance import page_label

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_PREFIX = "[authors]"


def _parser() -> argparse.ArgumentParser:
    """Baut den Argument-Parser mit den vier Unterbefehlen."""
    parser = argparse.ArgumentParser(description="Personen im Korpus (Phase 17 / A4).")
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("suchen", help="Personen-Kandidaten zu einem Namen")
    search.add_argument("name", help="Name oder Namensteil, z. B. „Asai, Akari“ oder „Y. Wang“")
    search.add_argument("--limit", type=int, default=DEFAULT_CANDIDATE_LIMIT, help="Höchstzahl")
    profile = commands.add_parser("profil", help="Paper, Communities und Mitautoren einer Person")
    profile.add_argument("person_key", help="Personenschlüssel aus `suchen`")
    profile.add_argument("--limit", type=int, default=MAX_RESULT_COUNT, help="Höchstzahl je Liste")
    papers = commands.add_parser("paper", help="Suche in den Papern einer Person")
    papers.add_argument("person_key", help="Personenschlüssel aus `suchen`")
    papers.add_argument("query", help="Anfrage")
    papers.add_argument("-k", type=int, default=5, help="Höchstzahl der Zitate")
    citations = commands.add_parser("zitationen", help="Wer zitiert die Person, wen zitiert sie?")
    citations.add_argument("person_key", help="Personenschlüssel aus `suchen`")
    citations.add_argument(
        "--limit", type=int, default=MAX_RESULT_COUNT, help="Höchstzahl je Richtung"
    )
    return parser


def _paper_line(brief: PaperBrief) -> str:
    """Eine Zeile je Paper: ID, Jahr, Titel."""
    year = str(brief.year) if brief.year else "o. J."
    title = brief.title or "(ohne Titel)"
    return f"{brief.paper_id} · {year} · {title[:88]}"


def _print_coverage(coverage: Coverage) -> None:
    """Schlusszeile: die Abdeckung der Personenebene."""
    print(f"{_PREFIX} Abdeckung: {coverage.note}")


def _search(index: str, name: str, limit: int) -> None:
    """Unterbefehl ``suchen``."""
    result = search_authors(index, name, limit=limit)
    shown = len(result.candidates)
    print(f"{_PREFIX} {result.total_matching} Kandidat(en) zu „{name}“ (gezeigt: {shown})")
    if result.ambiguous:
        print(f"{_PREFIX} Mehrdeutig: den passenden Personenschlüssel wählen.")
    for candidate in result.candidates:
        span = (
            f"{candidate.year_span[0]}–{candidate.year_span[1]}" if candidate.year_span else "o. J."
        )
        head = f"{candidate.person_key} · {candidate.identity}"
        print(f"  · {head} · {candidate.n_papers} Paper · {span}")
        print(f"     Schreibweisen: {', '.join(candidate.names)}")
        for title in candidate.sample_titles:
            print(f"     - {title[:88]}")
    _print_coverage(result.coverage)


def _profile(index: str, person_key: str, limit: int) -> None:
    """Unterbefehl ``profil``."""
    profile = get_author(index, person_key, limit=limit)
    print(f"{_PREFIX} {profile.person_key} · {profile.identity} · {', '.join(profile.names)}")
    if profile.orcid:
        print(f"{_PREFIX} ORCID: {profile.orcid}")
    print(f"{_PREFIX} Paper ({profile.papers_total}):")
    for entry in profile.papers:
        print(f"  · {_paper_line(entry.paper)} · Position {entry.position}")
    print(f"{_PREFIX} Communities ({profile.communities_total}):")
    for community in profile.communities:
        keywords = ", ".join(community.keywords)
        print(f"  · {community.community_id} · {community.n_papers} Paper · {keywords}")
    print(f"{_PREFIX} Mitautoren ({profile.coauthors_total}):")
    for coauthor in profile.coauthors:
        names = ", ".join(coauthor.names)
        head = f"{coauthor.person_key} · {coauthor.identity}"
        print(f"  · {head} · {coauthor.n_shared} gemeinsam · {names}")
    _print_coverage(profile.coverage)


def _papers(index: str, person_key: str, query: str, k: int) -> None:
    """Unterbefehl ``paper``."""
    result = search_author_papers(index, person_key, query, k=k)
    print(
        f"{_PREFIX} {len(result.citations)} Treffer zu „{query}“ in "
        f"{result.papers_searched} Papern von {result.person_key}"
    )
    for citation in result.citations:
        where = page_label(citation.page_number, citation.page_end)
        section = f" · {citation.section_title}" if citation.section_title else ""
        print(f"  · {citation.paper_id}{section} · {where} · Score {citation.score:.4f}")
        print(f"     {citation.snippet}")
    _print_coverage(result.coverage)


def _citations(index: str, person_key: str, limit: int) -> None:
    """Unterbefehl ``zitationen``."""
    result = get_author_citations(index, person_key, limit=limit)
    for heading, links, total in (
        ("zitiert", result.cites, result.cites_total),
        ("wird zitiert von", result.cited_by, result.cited_by_total),
    ):
        print(f"{_PREFIX} {heading} ({total}):")
        for link in links:
            marker = " · Selbstzitat" if link.self_citation else ""
            print(f"  · {_paper_line(link.paper)}{marker}")
            print(f"     über {', '.join(link.via)} · Match: {', '.join(link.methods)}")
    print(f"{_PREFIX} Nur Zitationen innerhalb des Korpus.")
    _print_coverage(result.coverage)


def main() -> int:
    """Führt den gewählten Unterbefehl aus."""
    # Robuste Unicode-Ausgabe (Namen und Titel enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args()
    try:
        if args.command == "suchen":
            _search(args.index, args.name, args.limit)
        elif args.command == "profil":
            _profile(args.index, args.person_key, args.limit)
        elif args.command == "paper":
            _papers(args.index, args.person_key, args.query, args.k)
        else:
            _citations(args.index, args.person_key, args.limit)
    except DomainError as exc:
        print(f"{_PREFIX} Fehler [{exc.code.value}]: {exc.message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
