"""Global Search: Query→Community-Ranking (Offline-Hybrid, Option B, Phase 4).

Beantwortet Cross-Paper-/Themenfragen als Offline-Analog zum GraphRAG-„Global"-Map-Reduce:
Jede Louvain-Community (Phase 3) wird über ihre aggregierten **Keywords + Summary** zu einem
Dokument verdichtet; die Anfrage wird per TF-IDF dagegen gescort und die Top-Communities mit
**repräsentativer Paper-Provenienz** zurückgegeben. Grundsatz:
docs/adr/0008-retrieval-and-query-router-phase4.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.graph_index import CommunityView, load_communities
from research_graphrag.retrieval.provenance import PaperRef, ProvenanceAssembler

DEFAULT_TOP_COMMUNITIES = 5
"""Standardzahl der zurückgegebenen Communities."""


@dataclass(frozen=True)
class CommunityMatch:
    """Eine zur Anfrage passende Community mit repräsentativer Paper-Provenienz."""

    community_id: int
    score: float
    size: int
    keywords: tuple[str, ...]
    representatives: tuple[PaperRef, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Community-Treffer (Teil des Output-Schemas)."""
        return {
            "community_id": self.community_id,
            "score": self.score,
            "size": self.size,
            "keywords": list(self.keywords),
            "representatives": [ref.to_dict() for ref in self.representatives],
        }


@dataclass(frozen=True)
class GlobalSearchResult:
    """Ergebnis der Global Search: Anfrage plus absteigend sortierte Community-Treffer."""

    query: str
    communities: tuple[CommunityMatch, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema des Tools ``search_global``)."""
        return {
            "query": self.query,
            "communities": [match.to_dict() for match in self.communities],
        }


def _community_document(community: CommunityView) -> str:
    """Verdichtet Keywords + Summary einer Community zu einem Dokument (Query-Ranking)."""
    return " ".join(community.keywords) + " " + community.summary


def rank_communities(
    db_path: str | Path, query: str, n: int = DEFAULT_TOP_COMMUNITIES
) -> list[tuple[CommunityView, float]]:
    """Ordnet die Communities nach Query-Ähnlichkeit (TF-IDF über Keywords + Summary).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        query: Natürlichsprachige Anfrage (nicht leer).
        n: Maximale Zahl der Communities (> 0).

    Returns:
        Bis zu ``n`` Paare ``(community, score)`` mit Score > 0, absteigend sortiert
        (Tie-Break: kleinere ``community_id``); leer, wenn keine Community passt.

    Raises:
        DomainError: ``invalid_input`` bei leerer Anfrage oder ``n <= 0``; ``not_found`` wenn
            die Index-Datei fehlt; ``constraint_violation`` wenn kein Graph/keine Communities
            vorliegen (siehe docs/error-model.md).
    """
    if not query.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leere Suchanfrage.")
    if n <= 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "n muss > 0 sein.")

    communities = load_communities(db_path)
    documents = [_community_document(community) for community in communities]
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(documents)
    query_vector = vectorizer.transform([query])
    scores = linear_kernel(query_vector, matrix).ravel()

    order = sorted(
        range(len(communities)),
        key=lambda i: (-float(scores[i]), communities[i].community_id),
    )
    ranked: list[tuple[CommunityView, float]] = []
    for i in order:
        if len(ranked) >= n:
            break
        score = float(scores[i])
        if score <= 0.0:
            continue
        ranked.append((communities[i], score))
    return ranked


def build_community_match(
    community: CommunityView, score: float, assembler: ProvenanceAssembler
) -> CommunityMatch:
    """Reichert eine gerankte Community mit repräsentativer Paper-Provenienz an.

    Gemeinsam von Global und DRIFT genutzt (einheitliche Community-Provenienz).
    """
    return CommunityMatch(
        community_id=community.community_id,
        score=score,
        size=community.size,
        keywords=community.keywords,
        representatives=tuple(
            assembler.paper_ref(paper_id) for paper_id in community.representatives
        ),
    )


def search_global(
    db_path: str | Path, query: str, n: int = DEFAULT_TOP_COMMUNITIES
) -> GlobalSearchResult:
    """Beantwortet eine Cross-Paper-/Themenfrage über Global Search mit Provenienz.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        query: Natürlichsprachige Anfrage (nicht leer).
        n: Maximale Zahl der Communities (> 0).

    Returns:
        Ein :class:`GlobalSearchResult`; ``communities`` ist leer, wenn nichts passt.

    Raises:
        DomainError: siehe :func:`rank_communities` (``invalid_input``/``not_found``/
            ``constraint_violation``).
    """
    ranked = rank_communities(db_path, query, n)
    if not ranked:
        return GlobalSearchResult(query=query, communities=())

    assembler = ProvenanceAssembler.load(db_path)
    matches = tuple(
        build_community_match(community, score, assembler) for community, score in ranked
    )
    return GlobalSearchResult(query=query, communities=matches)
