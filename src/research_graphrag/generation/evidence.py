"""Adapter: Retrieval-Ergebnisse → mode-agnostische :class:`Evidence` (Phase 7 / A1).

Übersetzt die vier Modus-Ergebnisse (Basic/Local/Global/DRIFT) **deterministisch** in eine
einheitliche Beleg-Sammlung, die :func:`research_graphrag.generation.synthesis.synthesize_answer`
konsumiert. Chunk-Belege (Basic/Local/DRIFT) tragen Abschnitts-/Seiten-Provenienz; Community-
Belege (Global) liefern die repräsentativen Paper der Top-Communities. Damit sieht ein Aufrufer
über alle Modi hinweg **dasselbe** Beleg-Schema
(docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research_graphrag.bibliography.styles import reference_payload
from research_graphrag.generation.synthesis import Evidence, EvidenceSource
from research_graphrag.indexing.metadata_index import load_paper_metadata
from research_graphrag.retrieval.basic import BasicSearchResult
from research_graphrag.retrieval.drift import DriftSearchResult
from research_graphrag.retrieval.global_search import GlobalSearchResult
from research_graphrag.retrieval.local import LocalSearchResult
from research_graphrag.retrieval.provenance import Citation, PaperRef, page_label


def _citation_entry(citation: Citation) -> EvidenceSource:
    """Bildet ein Chunk-Zitat auf einen Beleg mit Abschnitts-/Seiten-Label ab."""
    section = f" · Abschnitt {citation.section_title}" if citation.section_title else ""
    pages = page_label(citation.page_number, citation.page_end)
    label = f"Paper {citation.paper_id}{section} · {pages}"
    return EvidenceSource(
        paper_id=citation.paper_id,
        label=label,
        snippet=citation.snippet,
        source_uri=citation.source_uri,
        identifiers=citation.identifiers,
        citation_key=citation.citation_key,
    )


def _paper_entry(ref: PaperRef, community_id: int) -> EvidenceSource:
    """Bildet ein repräsentatives Paper einer Community auf einen Beleg ab."""
    return EvidenceSource(
        paper_id=ref.paper_id,
        label=f"Paper {ref.paper_id} · Community #{community_id}",
        snippet=ref.snippet,
        source_uri=ref.source_uri,
        identifiers=ref.identifiers,
        citation_key=ref.citation_key,
    )


def evidence_from_basic(result: BasicSearchResult) -> Evidence:
    """Baut die Evidenz aus einem Basic-Ergebnis (Top-k-Chunk-Zitate)."""
    return Evidence.build(
        result.query, "basic", tuple(_citation_entry(c) for c in result.citations)
    )


def evidence_from_local(result: LocalSearchResult) -> Evidence:
    """Baut die Evidenz aus einem Local-Ergebnis (Seeds, Nachbarschaft, Fan-out-Belege)."""
    entries: list[EvidenceSource] = [_citation_entry(citation) for citation in result.seeds]
    entries.extend(_citation_entry(c) for c in result.neighborhood)
    entries.extend(
        _citation_entry(neighbor.citation)
        for neighbor in result.fan_out
        if neighbor.citation is not None
    )
    return Evidence.build(result.query, "local", tuple(entries))


def evidence_from_global(result: GlobalSearchResult) -> Evidence:
    """Baut die Evidenz aus einem Global-Ergebnis (repräsentative Paper je Top-Community)."""
    entries: list[EvidenceSource] = []
    for match in result.communities:
        entries.extend(_paper_entry(ref, match.community_id) for ref in match.representatives)
    return Evidence.build(result.query, "global", tuple(entries))


def evidence_from_drift(result: DriftSearchResult) -> Evidence:
    """Baut die Evidenz aus einem DRIFT-Ergebnis (lokal verfeinerte Chunk-Belege)."""
    return Evidence.build(
        result.query, "drift", tuple(_citation_entry(c) for c in result.citations)
    )


def references_for(db_path: str | Path, evidence: Evidence) -> tuple[dict[str, Any], ...]:
    """Stellt die vollständigen Literaturangaben der belegten Paper zusammen.

    Jedes Paper erscheint **einmal**, in der Reihenfolge seines ersten Belegs – damit ist die
    Liste stabil und ohne Dubletten (docs/adr/0025-citable-paper-metadata.md, Punkt 5).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        evidence: Die bereits nummerierte Beleg-Sammlung.

    Returns:
        Je Paper einen Datensatz inklusive Harvard- und APA-Angabe.
    """
    ordered: list[str] = []
    for item in evidence.items:
        if item.paper_id not in ordered:
            ordered.append(item.paper_id)
    if not ordered:
        return ()
    metadata = load_paper_metadata(db_path)
    return tuple(
        reference_payload(metadata[paper_id]) for paper_id in ordered if paper_id in metadata
    )
