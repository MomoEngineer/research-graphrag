"""Global Search: Query→Community-Ranking (Offline-Hybrid, Option B, Phase 4).

Beantwortet Cross-Paper-/Themenfragen als Offline-Analog zum GraphRAG-„Global"-Map-Reduce:
Jede Louvain-Community (Phase 3) wird über die **Hybrid-Chunk-Scores ihrer Mitgliederpaper**
bewertet – der Community-Score ist der Mittelwert der :data:`MEMBER_TOP_K` höchsten
Mitglieds-Chunk-Scores der Anfrage (Phase 10 / V4, docs/adr/0036). Keywords und Summary bleiben
Teil von :class:`CommunityMatch` für die Anzeige, tragen aber seit V4 nicht mehr das Ranking –
sie sind zehn Stichworte plus ein Satz und damit zu dünn, um die Textmasse der Mitglieder zu
vertreten (siehe Roadmap.md, Phase 10 / V4, Befund). Grundsatz:
docs/adr/0008-retrieval-and-query-router-phase4.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.graph_index import CommunityView, load_communities
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, TfidfIndex
from research_graphrag.retrieval.provenance import PaperRef, ProvenanceAssembler

DEFAULT_TOP_COMMUNITIES = 5
"""Standardzahl der zurückgegebenen Communities."""

MEMBER_TOP_K = 5
"""Zahl der stärksten Mitglieds-Chunk-Scores, deren Mittel den Community-Score bildet.

Der Wert folgt der bestehenden ``k=5``-Konvention der übrigen Modi (Basic/Local/DRIFT/
Global-``n``) statt eines separat optimierten Parameters – eine Wegwerf-Messung gegen das
34-Fragen-Gold-Set zeigte *top_k*∈{3,5,10} als praktisch gleichwertig (Unterschied ≤ 1 Frage);
ein am Gold-Set noch besserer Wert wäre Overfitting auf eine kleine Stichprobe gewesen (dieselbe
Zurückhaltung wie bei DRIFTs Community-Zahl, ADR 0022). Eine reine **Summe** statt des Mittels
wurde verworfen: Sie bevorzugt große Communities strukturell (Selektivität stieg auf 0,276 bei
gesunkenem Lift 1,91 gegenüber 3,2–3,5 der Top-k-Mittel-Varianten) – siehe Roadmap.md,
Phase 10 / V4."""


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


def _aggregate_member_score(member_scores: list[float]) -> float:
    """Mittelt die :data:`MEMBER_TOP_K` höchsten Chunk-Scores einer Community (0.0 ohne Treffer)."""
    if not member_scores:
        return 0.0
    top = sorted(member_scores, reverse=True)[:MEMBER_TOP_K]
    return sum(top) / len(top)


def rank_communities(
    db_path: str | Path, query: str, n: int = DEFAULT_TOP_COMMUNITIES
) -> list[tuple[CommunityView, float]]:
    """Ordnet die Communities nach dem Mittel ihrer stärksten Mitglieds-Chunk-Scores.

    Der Community-Score aggregiert die **Hybrid-Chunk-Scores** (BM25 + TF-IDF, Rang-Fusion)
    der Mitgliederpaper über dieselbe Wertung, die Basic/Local/DRIFT teilen – statt wie vor
    Phase 10 / V4 aus einem separaten TF-IDF-Raum über Keywords + Summary.

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
    index = TfidfIndex.load(db_path)
    scores_by_paper = index.score_chunks_by_paper(query, scoring=DEFAULT_SCORING)

    scored = [
        (
            community,
            _aggregate_member_score(
                [
                    score
                    for paper_id in community.members
                    for score in scores_by_paper.get(paper_id, ())
                ]
            ),
        )
        for community in communities
    ]

    order = sorted(
        range(len(scored)),
        key=lambda i: (-scored[i][1], scored[i][0].community_id),
    )
    ranked: list[tuple[CommunityView, float]] = []
    for i in order:
        if len(ranked) >= n:
            break
        community, score = scored[i]
        if score <= 0.0:
            continue
        ranked.append((community, score))
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
