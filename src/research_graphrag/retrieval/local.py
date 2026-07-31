"""Local Search: Chunk-Nachbarschaft + Paper-Fan-out (Offline-Hybrid, Option B, Phase 4).

Beantwortet Detailfragen zu einem Paper **und** Zitations-/Methodennetz-Fragen (Multi-Hop),
indem beide „Local"-Aspekte kombiniert werden (siehe
docs/adr/0008-retrieval-and-query-router-phase4.md):

1. **Seed** – der zur Anfrage beste Chunk (TF-IDF-Top-1).
2. **Chunk-Nachbarschaft** – die ähnlichsten Chunks zum Seed-Chunk (Chunk↔Chunk-Kosinus zur
   Abfragezeit aus der rekonstruierten TF-IDF-Matrix; kein persistierter Chunk-Graph).
3. **Paper-Fan-out** – Nachbarpaper des Seed-Papers über den persistierten
   Paper-Ähnlichkeitsgraphen (Phase 3); je Nachbar der query-relevanteste Chunk als Beleg.

Die natürlichsprachige Antwort formuliert der aufrufende Agent über die LLM-Bridge (ADR 0004)
aus den hier gelieferten, belegten Zitaten.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.graph_index import load_neighbors
from research_graphrag.indexing.tfidf_index import TfidfIndex
from research_graphrag.retrieval.provenance import Citation

DEFAULT_NEIGHBORHOOD = 5
"""Standardzahl der Chunk-Nachbarn (Aspekt 2)."""

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
    """Ergebnis der Local Search: Seed-Chunk, Chunk-Nachbarschaft und Paper-Fan-out."""

    query: str
    seed: Citation | None
    neighborhood: tuple[Citation, ...]
    fan_out: tuple[NeighborPaper, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema des Tools ``search_local``)."""
        return {
            "query": self.query,
            "seed": self.seed.to_dict() if self.seed is not None else None,
            "neighborhood": [citation.to_dict() for citation in self.neighborhood],
            "fan_out": [neighbor.to_dict() for neighbor in self.fan_out],
        }


def search_local(
    db_path: str | Path,
    query: str,
    *,
    k: int = DEFAULT_NEIGHBORHOOD,
    fan_out: int = DEFAULT_FANOUT,
) -> LocalSearchResult:
    """Beantwortet eine Detail-/Netz-Frage über Local Search mit Provenienz.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        query: Natürlichsprachige Anfrage (nicht leer).
        k: Maximale Zahl der Chunk-Nachbarn (> 0).
        fan_out: Maximale Zahl der Graph-Nachbarpaper (>= 0). ``0`` überspringt den
            Fan-out und benötigt daher **keinen** gebauten Graphen.

    Returns:
        Ein :class:`LocalSearchResult`; ``seed`` ist ``None``, wenn nichts passt.

    Raises:
        DomainError: ``invalid_input`` bei leerer Anfrage, ``k <= 0`` oder ``fan_out < 0``;
            ``not_found`` wenn die Index-Datei fehlt; ``constraint_violation`` wenn der Index
            keine Chunks enthält bzw. (bei ``fan_out > 0``) kein Graph gebaut wurde
            (siehe docs/error-model.md).
    """
    if fan_out < 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "fan_out muss >= 0 sein.")

    index = TfidfIndex.load(db_path)
    seed_hits = index.search(query, 1)  # validiert Anfrage/k intern
    if not seed_hits:
        return LocalSearchResult(query=query, seed=None, neighborhood=(), fan_out=())

    seed_hit = seed_hits[0]
    neighbor_hits = index.neighbors_of_chunk(seed_hit.chunk_id, k)
    neighborhood = tuple(Citation.from_hit(hit) for hit in neighbor_hits)

    neighbors: list[NeighborPaper] = []
    if fan_out > 0:
        for neighbor_id, weight in load_neighbors(db_path, seed_hit.paper_id)[:fan_out]:
            best = index.search(query, 1, paper_ids={neighbor_id})
            citation = Citation.from_hit(best[0]) if best else None
            neighbors.append(NeighborPaper(paper_id=neighbor_id, weight=weight, citation=citation))

    return LocalSearchResult(
        query=query,
        seed=Citation.from_hit(seed_hit),
        neighborhood=neighborhood,
        fan_out=tuple(neighbors),
    )
