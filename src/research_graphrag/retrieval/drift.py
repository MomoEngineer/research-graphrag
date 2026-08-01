"""DRIFT Search: pragmatischer Global→Local-Hybrid (Offline-Hybrid, Option B, Phase 4).

Für Widerspruchs-/Vergleichsfragen: zuerst die thematisch passendste **Community** bestimmen
(Global-Ranking), dann **innerhalb** ihrer Mitglieds-Paper die query-relevantesten Chunks
suchen (lokale Verfeinerung). So verbindet DRIFT den corpusweiten Kontext mit belegten
Einzelpassagen. Bewusst **kein** echtes iteratives Multi-Step-DRIFT (right-sized, siehe
docs/adr/0008-retrieval-and-query-router-phase4.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, Scoring, TfidfIndex
from research_graphrag.retrieval.global_search import (
    CommunityMatch,
    build_community_match,
    rank_communities,
)
from research_graphrag.retrieval.provenance import Citation, ProvenanceAssembler

DEFAULT_K = 6
"""Standardzahl der lokal verfeinerten Chunk-Belege innerhalb der Community."""


@dataclass(frozen=True)
class DriftSearchResult:
    """Ergebnis der DRIFT Search: gewählte Community (Kontext) + lokale Chunk-Belege."""

    query: str
    community: CommunityMatch | None
    citations: tuple[Citation, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema des Tools ``search_drift``)."""
        return {
            "query": self.query,
            "community": self.community.to_dict() if self.community is not None else None,
            "citations": [citation.to_dict() for citation in self.citations],
        }


def search_drift(
    db_path: str | Path, query: str, *, k: int = DEFAULT_K, scoring: Scoring = DEFAULT_SCORING
) -> DriftSearchResult:
    """Beantwortet eine Widerspruchs-/Vergleichsfrage über den DRIFT-Hybrid mit Provenienz.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        query: Natürlichsprachige Anfrage (nicht leer).
        k: Maximale Zahl der lokal verfeinerten Chunk-Belege (> 0).
        scoring: Wertung der lokalen Verfeinerung – ``hybrid`` (Default), ``tfidf`` oder
            ``bm25``. Die Community-Auswahl bleibt davon unberührt (siehe
            docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).

    Returns:
        Ein :class:`DriftSearchResult`; ``community`` ist ``None`` und ``citations`` leer,
        wenn keine Community zur Anfrage passt.

    Raises:
        DomainError: ``invalid_input`` bei leerer Anfrage, ``k <= 0`` oder unbekannter Wertung;
            ``not_found`` wenn
            die Index-Datei fehlt; ``constraint_violation`` wenn kein Graph/keine Communities
            vorliegen (siehe docs/error-model.md).
    """
    ranked = rank_communities(db_path, query, 1)  # validiert Anfrage; wählt Top-Community
    if k <= 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "k muss > 0 sein.")
    if not ranked:
        return DriftSearchResult(query=query, community=None, citations=())

    community, score = ranked[0]
    assembler = ProvenanceAssembler.load(db_path)
    match = build_community_match(community, score, assembler)

    index = TfidfIndex.load(db_path)
    hits = index.search(query, k, paper_ids=set(community.members), scoring=scoring)
    citations = tuple(Citation.from_hit(hit) for hit in hits)
    return DriftSearchResult(query=query, community=match, citations=citations)
