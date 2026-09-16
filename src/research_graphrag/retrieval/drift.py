"""DRIFT Search: pragmatischer Global→Local-Hybrid (Offline-Hybrid, Option B, Phase 4).

Für Widerspruchs-/Vergleichsfragen: zuerst die thematisch passendsten **Communities** bestimmen
(Global-Ranking), dann in der **Vereinigung** ihrer Mitglieds-Paper die query-relevantesten
Chunks suchen (lokale Verfeinerung). So verbindet DRIFT den corpusweiten Kontext mit belegten
Einzelpassagen. Bewusst **kein** echtes iteratives Multi-Step-DRIFT (right-sized, siehe
docs/adr/0008-retrieval-and-query-router-phase4.md).

Liefert dieser Pfad **keine** Belege, fällt die Suche sichtbar auf die Chunk-Suche ohne
Paper-Filter zurück (``fallback``). Der Grund ist gemessen: Für 12 von 34 Gold-Fragen scort
überhaupt keine Community über 0 – DRIFT antwortete dort leer
(docs/adr/0022-drift-community-union-and-fallback-phase10.md). Ein **defekter** Index (kein
Graph, keine Communities) wird davon bewusst nicht aufgefangen, sondern bleibt ein Fehler.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, Scoring, TfidfIndex
from research_graphrag.limits import check_max_count
from research_graphrag.retrieval.global_search import (
    CommunityMatch,
    build_community_match,
    rank_communities,
)
from research_graphrag.retrieval.provenance import Citation, ProvenanceAssembler

DEFAULT_K = 6
"""Standardzahl der lokal verfeinerten Chunk-Belege innerhalb der Communities."""

DEFAULT_COMMUNITIES = 5
"""Standardzahl der berücksichtigten Communities.

Der Wert entspricht dem Default der Global Search: Beide Modi sehen damit dieselbe Auswahl, und
DRIFTs erreichbare Deckelung ist per Konstruktion Globals Trefferzahl. Ein am Gold-Set besser
messender Wert wurde bewusst **nicht** gewählt (Overfitting auf 34 Fragen, siehe
docs/adr/0022-drift-community-union-and-fallback-phase10.md)."""


@dataclass(frozen=True)
class DriftSearchResult:
    """Ergebnis der DRIFT Search: gewählte Communities (Kontext) + lokale Chunk-Belege."""

    query: str
    communities: tuple[CommunityMatch, ...]
    citations: tuple[Citation, ...]
    fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema des Tools ``search_drift``)."""
        return {
            "query": self.query,
            "communities": [match.to_dict() for match in self.communities],
            "fallback": self.fallback,
            "citations": [citation.to_dict() for citation in self.citations],
        }


def search_drift(
    db_path: str | Path,
    query: str,
    *,
    k: int = DEFAULT_K,
    communities: int = DEFAULT_COMMUNITIES,
    scoring: Scoring = DEFAULT_SCORING,
) -> DriftSearchResult:
    """Beantwortet eine Widerspruchs-/Vergleichsfrage über den DRIFT-Hybrid mit Provenienz.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        query: Natürlichsprachige Anfrage (nicht leer).
        k: Maximale Zahl der lokal verfeinerten Chunk-Belege (``0 < k <= MAX_RESULT_COUNT``).
        communities: Maximale Zahl der berücksichtigten Communities
            (``0 < communities <= MAX_RESULT_COUNT``); Default :data:`DEFAULT_COMMUNITIES`. Ihre
            Mitglieder bilden **eine** Kandidatenmenge; die Rangfolge der Communities wirkt nur
            über die Zugehörigkeit, nicht über die Reihenfolge der Belege.
        scoring: Wertung der lokalen Verfeinerung – ``hybrid`` (Default), ``tfidf`` oder
            ``bm25``. Die Community-Auswahl bleibt davon unberührt (siehe
            docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).

    Returns:
        Ein :class:`DriftSearchResult`. Liefert der Community-Pfad keine Belege, ist
        ``fallback`` gesetzt und die ``citations`` stammen aus der corpusweiten Chunk-Suche
        (identisch zur Basic Search); ``communities`` ist leer, wenn keine Community passte.
        Findet auch die corpusweite Suche nichts, bleibt ``citations`` leer.

    Raises:
        DomainError: ``invalid_input`` bei leerer Anfrage, ``k <= 0``, ``communities <= 0``,
            einem der beiden Parameter über ``MAX_RESULT_COUNT`` (ADR 0037) oder unbekannter
            Wertung; ``not_found`` wenn die Index-Datei fehlt; ``constraint_violation`` wenn
            kein Graph/keine Communities vorliegen (siehe docs/error-model.md).
    """
    if k <= 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "k muss > 0 sein.")
    check_max_count("k", k)
    if communities <= 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "communities muss > 0 sein.")
    check_max_count("communities", communities)

    ranked = rank_communities(db_path, query, communities)  # validiert Anfrage und den Graphen
    index = TfidfIndex.load(db_path)

    members = {paper_id for community, _score in ranked for paper_id in community.members}
    hits = index.search(query, k, paper_ids=members, scoring=scoring) if members else []

    fallback = not hits
    if fallback:
        # Gemessener Regelfall: keine Community trägt die Anfrage. Die corpusweite Suche ist
        # derselbe Pfad wie in der Basic Search – der Rückfall wird ausgewiesen, nicht versteckt.
        hits = index.search(query, k, scoring=scoring)

    matches: tuple[CommunityMatch, ...] = ()
    if ranked:
        assembler = ProvenanceAssembler.load(db_path)
        matches = tuple(
            build_community_match(community, score, assembler) for community, score in ranked
        )

    return DriftSearchResult(
        query=query,
        communities=matches,
        citations=tuple(Citation.from_hit(hit) for hit in hits),
        fallback=fallback,
    )
