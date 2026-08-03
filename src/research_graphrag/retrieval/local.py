"""Local Search: Chunk-Nachbarschaft + Paper-Fan-out (Offline-Hybrid, Option B, Phase 4).

Beantwortet Detailfragen zu einem Paper **und** Zitations-/Methodennetz-Fragen (Multi-Hop),
indem beide „Local"-Aspekte kombiniert werden (siehe
docs/adr/0008-retrieval-and-query-router-phase4.md):

1. **Seeds** – die zur Anfrage besten Chunks (Top-*m* der Chunk-Wertung).
2. **Chunk-Nachbarschaft** – die ähnlichsten Chunks **je Seed** (Chunk↔Chunk-Kosinus zur
   Abfragezeit aus der rekonstruierten TF-IDF-Matrix; kein persistierter Chunk-Graph), per
   Reciprocal Rank Fusion zu **einer** Liste verbunden.
3. **Paper-Fan-out** – Nachbarpaper des **Ankerpapers** (Paper des ersten Seeds) über den
   persistierten Paper-Ähnlichkeitsgraphen (Phase 3); je Nachbar der query-relevanteste Chunk
   als Beleg.

Die Verankerung an mehreren Seeds löst die ursprüngliche an **einem** Seed ab: Ein falscher
Top-1-Treffer machte zuvor das gesamte Bündel wertlos – gemessen 17 von 34 Gold-Fragen mit
Seed-Treffer gegenüber 30 von 34 bei Basic (siehe
docs/adr/0021-local-multi-seed-phase10.md).

Die natürlichsprachige Antwort formuliert der aufrufende Agent über die LLM-Bridge (ADR 0004)
aus den hier gelieferten, belegten Zitaten.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.fusion import fuse_rankings
from research_graphrag.indexing.graph_index import load_neighbors
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, Hit, Scoring, TfidfIndex
from research_graphrag.retrieval.provenance import Citation

DEFAULT_SEEDS = 5
"""Standardzahl der Seed-Chunks (Aspekt 1).

Der Wert stammt aus der Vorabmessung zu V1: Er ist das kleinste *m*, mit dem Local der Basic
Search auf Hit@5 **und** MRR@5 nicht unterlegen ist
(docs/adr/0021-local-multi-seed-phase10.md)."""

DEFAULT_NEIGHBORHOOD = 5
"""Standardzahl der Chunk-Nachbarn insgesamt (Aspekt 2), nicht je Seed."""

DEFAULT_FANOUT = 5
"""Standardzahl der Graph-Nachbarpaper (Aspekt 3)."""


@dataclass(frozen=True)
class NeighborPaper:
    """Ein Fan-out-Nachbarpaper (Graph-Kante) mit query-relevantem Beleg."""

    paper_id: str
    weight: float
    citation: Citation | None

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Nachbarpaper (Kantengewicht + optionaler Chunk-Beleg)."""
        return {
            "paper_id": self.paper_id,
            "weight": self.weight,
            "citation": self.citation.to_dict() if self.citation is not None else None,
        }


@dataclass(frozen=True)
class LocalSearchResult:
    """Ergebnis der Local Search: Seed-Chunks, Chunk-Nachbarschaft und Paper-Fan-out."""

    query: str
    seeds: tuple[Citation, ...]
    neighborhood: tuple[Citation, ...]
    fan_out: tuple[NeighborPaper, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema des Tools ``search_local``)."""
        return {
            "query": self.query,
            "seeds": [citation.to_dict() for citation in self.seeds],
            "neighborhood": [citation.to_dict() for citation in self.neighborhood],
            "fan_out": [neighbor.to_dict() for neighbor in self.fan_out],
        }


def _fused_neighborhood(
    index: TfidfIndex, seed_hits: Sequence[Hit], k: int
) -> tuple[Citation, ...]:
    """Führt die Chunk-Nachbarschaften aller Seeds zu **einer** Rangliste zusammen.

    Je Seed entsteht eine eigene Teilrangliste; verbunden werden sie über die Reciprocal Rank
    Fusion (:mod:`research_graphrag.indexing.fusion`), weil die Kosinuswerte verschiedener Seeds
    nicht auf einer gemeinsamen Skala liegen. Chunks, die selbst Seed sind, entfallen – ein
    Beleg erscheint nie doppelt. Bei genau einem Seed bleibt die ursprüngliche Reihenfolge
    erhalten (eine Teilrangliste, streng fallende Fusionswerte).

    ``score`` ist wie bei der Hybrid-Wertung der **Fusionswert** – nur so entspricht die
    angezeigte Zahl der Sortierung; der Kosinus zum best platzierten Seed bleibt in
    ``score_tfidf`` erhalten (docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).

    Args:
        index: Der geladene Index.
        seed_hits: Die Seed-Treffer in ihrer Rangfolge.
        k: Maximale Größe der **gesamten** Nachbarschaft.

    Returns:
        Die fusionierte Nachbarschaft als Zitate (Tie-Break über die ``chunk_id``).
    """
    seed_ids = {hit.chunk_id for hit in seed_hits}
    hit_of_chunk: dict[str, Hit] = {}
    row_of_chunk: dict[str, int] = {}
    rankings: list[list[int]] = []
    for seed in seed_hits:
        ranking: list[int] = []
        for hit in index.neighbors_of_chunk(seed.chunk_id, k):
            if hit.chunk_id in seed_ids:
                continue
            hit_of_chunk.setdefault(hit.chunk_id, hit)
            ranking.append(row_of_chunk.setdefault(hit.chunk_id, len(row_of_chunk)))
        rankings.append(ranking)

    fused = fuse_rankings(rankings)
    chunk_of_row = {row: chunk_id for chunk_id, row in row_of_chunk.items()}
    order = sorted(fused, key=lambda row: (-fused[row], chunk_of_row[row]))[:k]
    return tuple(
        replace(Citation.from_hit(hit_of_chunk[chunk_of_row[row]]), score=fused[row])
        for row in order
    )


def search_local(
    db_path: str | Path,
    query: str,
    *,
    k: int = DEFAULT_NEIGHBORHOOD,
    fan_out: int = DEFAULT_FANOUT,
    seeds: int = DEFAULT_SEEDS,
    scoring: Scoring = DEFAULT_SCORING,
) -> LocalSearchResult:
    """Beantwortet eine Detail-/Netz-Frage über Local Search mit Provenienz.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        query: Natürlichsprachige Anfrage (nicht leer).
        k: Maximale Zahl der Chunk-Nachbarn **insgesamt** (> 0), nicht je Seed.
        fan_out: Maximale Zahl der Graph-Nachbarpaper (>= 0). ``0`` überspringt den
            Fan-out und benötigt daher **keinen** gebauten Graphen.
        seeds: Maximale Zahl der Seed-Chunks (> 0); Default :data:`DEFAULT_SEEDS`.
        scoring: Wertung für Seeds und Fan-out-Belege – ``hybrid`` (Default), ``tfidf`` oder
            ``bm25``. Die Chunk-Nachbarschaft beruht unabhängig davon auf dem TF-IDF-Kosinus
            (siehe docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).

    Returns:
        Ein :class:`LocalSearchResult`; ``seeds`` ist leer, wenn nichts passt.

    Raises:
        DomainError: ``invalid_input`` bei leerer Anfrage, ``k <= 0``, ``fan_out < 0``,
            ``seeds <= 0`` oder unbekannter Wertung; ``not_found`` wenn die Index-Datei fehlt;
            ``constraint_violation`` wenn der Index keine Chunks enthält bzw. (bei
            ``fan_out > 0``) kein Graph gebaut wurde (siehe docs/error-model.md).
    """
    if fan_out < 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "fan_out muss >= 0 sein.")
    if seeds <= 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "seeds muss > 0 sein.")

    index = TfidfIndex.load(db_path)
    seed_hits = index.search(query, seeds, scoring=scoring)  # validiert Anfrage/k/Wertung intern
    if not seed_hits:
        return LocalSearchResult(query=query, seeds=(), neighborhood=(), fan_out=())

    neighborhood = _fused_neighborhood(index, seed_hits, k)  # validiert k intern

    neighbors: list[NeighborPaper] = []
    if fan_out > 0:
        anchor_paper_id = seed_hits[0].paper_id
        for neighbor_id, weight in load_neighbors(db_path, anchor_paper_id)[:fan_out]:
            best = index.search(query, 1, paper_ids={neighbor_id}, scoring=scoring)
            citation = Citation.from_hit(best[0]) if best else None
            neighbors.append(NeighborPaper(paper_id=neighbor_id, weight=weight, citation=citation))

    return LocalSearchResult(
        query=query,
        seeds=tuple(Citation.from_hit(hit) for hit in seed_hits),
        neighborhood=neighborhood,
        fan_out=tuple(neighbors),
    )
