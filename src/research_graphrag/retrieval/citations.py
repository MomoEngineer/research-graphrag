"""Zitations-Abfrage mit Paper-Provenienz (Phase 7 / A2, Offline-Hybrid, Option B).

Reichert die rohen ``CITES``-Kanten aus :mod:`research_graphrag.indexing.citation_graph`
um **Paper-Provenienz** an (``source_uri`` + Leit-Snippet), sodass die Antwort auf „welche
Paper bauen auf X auf?" ohne Folgeaufrufe zitierfähig ist. Die Schichtung entspricht
``graph_index`` ↔ ``retrieval`` aus Phase 4: die Indexschicht liefert IDs und Struktur, die
Retrieval-Schicht die Provenienz. Grundsatz und Grenzen (nur Intra-Korpus, Präzision vor
Recall): docs/adr/0011-intra-corpus-citation-graph-phase7.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.citation_graph import load_citations
from research_graphrag.limits import MAX_RESULT_COUNT, check_max_count
from research_graphrag.retrieval.provenance import PaperRef, ProvenanceAssembler


@dataclass(frozen=True)
class CitationLink:
    """Eine belegte Zitationsbeziehung: Gegenüber-Paper plus Match-Methode.

    ``method`` (``doi``/``arxiv``/``title``) macht sichtbar, **woran** die Kante erkannt
    wurde, und damit wie belastbar sie ist.
    """

    paper: PaperRef
    method: str

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Beziehung (Provenienz flach, direkt zitierbar)."""
        return {**self.paper.to_dict(), "method": self.method}


@dataclass(frozen=True)
class CitationsResult:
    """Zitations-Nachbarschaft eines Papers in beide Richtungen.

    ``cites``/``cited_by`` sind auf ``limit`` Einträge gedeckelt; ``cites_total``/
    ``cited_by_total`` nennen die tatsächliche Kantenzahl **vor** der Deckelung, damit eine
    Kürzung sichtbar bleibt statt stillschweigend zu geschehen
    (docs/adr/0037-mcp-tool-response-size-ceiling.md).
    """

    paper: PaperRef
    cites: tuple[CitationLink, ...]
    cites_total: int
    cited_by: tuple[CitationLink, ...]
    cited_by_total: int

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema von ``get_citations``)."""
        return {
            "paper": self.paper.to_dict(),
            "cites": [link.to_dict() for link in self.cites],
            "cites_total": self.cites_total,
            "cited_by": [link.to_dict() for link in self.cited_by],
            "cited_by_total": self.cited_by_total,
        }


def get_citations(
    db_path: str | Path, paper_id: str, *, limit: int = MAX_RESULT_COUNT
) -> CitationsResult:
    """Liefert die Intra-Korpus-Zitationen eines Papers mit Provenienz.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        paper_id: Stabile Paper-ID (nicht leer).
        limit: Maximale Zahl der Einträge **je Richtung** (``0 < limit <= MAX_RESULT_COUNT``);
            Default :data:`research_graphrag.limits.MAX_RESULT_COUNT`.

    Returns:
        Ein :class:`CitationsResult`; ``cites`` (zitiert) und ``cited_by`` (wird zitiert von)
        sind stabil nach der ``paper_id`` des Gegenübers sortiert, auf ``limit`` Einträge
        gedeckelt und können leer sein.

    Raises:
        DomainError: ``invalid_input`` bei leerer ``paper_id``, ``limit <= 0`` oder
            ``limit > MAX_RESULT_COUNT`` (ADR 0037); ``not_found`` wenn Index oder Paper fehlen;
            ``constraint_violation`` wenn der Index keinen Zitationsgraphen enthält (siehe
            docs/error-model.md).
    """
    if limit <= 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "limit muss > 0 sein.")
    check_max_count("limit", limit)

    view = load_citations(db_path, paper_id)
    assembler = ProvenanceAssembler.load(db_path)
    cites = tuple(
        CitationLink(assembler.paper_ref(edge.target_paper_id), edge.method) for edge in view.cites
    )
    cited_by = tuple(
        CitationLink(assembler.paper_ref(edge.source_paper_id), edge.method)
        for edge in view.cited_by
    )
    return CitationsResult(
        paper=assembler.paper_ref(paper_id),
        cites=cites[:limit],
        cites_total=len(cites),
        cited_by=cited_by[:limit],
        cited_by_total=len(cited_by),
    )
