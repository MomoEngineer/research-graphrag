"""Basic Search: TF-IDF-Top-k mit Provenienz (Offline-Hybrid, Option B).

Kapselt das Laden des Index und die Suche zu einem stabilen, MCP-tauglichen Ergebnis
(:class:`BasicSearchResult`). Entspricht dem GraphRAG-Suchmodus **Basic** (Top-k auf
Chunks); Local/Global/DRIFT ergänzen dies in Phase 4 (siehe
docs/adr/0008-retrieval-and-query-router-phase4.md). Die eigentliche natürlichsprachige
Antwort formuliert der aufrufende Agent (Copilot) über die LLM-Bridge (ADR 0004) aus den
hier gelieferten, belegten Zitaten.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.indexing.tfidf_index import TfidfIndex
from research_graphrag.retrieval.provenance import Citation

__all__ = ["BasicSearchResult", "Citation", "search_basic"]


@dataclass(frozen=True)
class BasicSearchResult:
    """Ergebnis der Basic Search: Anfrage plus absteigend sortierte, belegte Zitate."""

    query: str
    citations: tuple[Citation, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema des Tools ``search_basic``)."""
        return {
            "query": self.query,
            "citations": [citation.to_dict() for citation in self.citations],
        }


def search_basic(db_path: str | Path, query: str, k: int = 5) -> BasicSearchResult:
    """Beantwortet eine Frage über Basic Search (TF-IDF) mit Provenienz.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        query: Natürlichsprachige Anfrage (nicht leer).
        k: Maximale Trefferzahl (> 0).

    Returns:
        :class:`BasicSearchResult` mit belegten Zitaten (Paper, Seite, Score, Snippet).

    Raises:
        DomainError: ``not_found``/``constraint_violation`` wenn kein Index vorliegt;
            ``invalid_input`` bei leerer Anfrage oder ``k <= 0`` (siehe docs/error-model.md).
    """
    index = TfidfIndex.load(db_path)
    hits = index.search(query, k)
    citations = tuple(Citation.from_hit(hit) for hit in hits)
    return BasicSearchResult(query=query, citations=citations)
