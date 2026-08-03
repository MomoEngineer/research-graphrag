"""Adapter: Retrieval-Ergebnisse → mode-agnostische :class:`Evidence` (Phase 7 / A1).

Übersetzt die vier Modus-Ergebnisse (Basic/Local/Global/DRIFT) **deterministisch** in eine
einheitliche Beleg-Sammlung, die :func:`research_graphrag.generation.synthesis.synthesize_answer`
konsumiert. Chunk-Belege (Basic/Local/DRIFT) tragen Abschnitts-/Seiten-Provenienz; Community-
Belege (Global) liefern die repräsentativen Paper der Top-Communities. Damit sieht ein Aufrufer
über alle Modi hinweg **dasselbe** Beleg-Schema
(docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md).
"""

from __future__ import annotations

from research_graphrag.generation.synthesis import Evidence
from research_graphrag.retrieval.basic import BasicSearchResult
from research_graphrag.retrieval.drift import DriftSearchResult
from research_graphrag.retrieval.global_search import GlobalSearchResult
from research_graphrag.retrieval.local import LocalSearchResult
from research_graphrag.retrieval.provenance import Citation, PaperRef, page_label

_Entry = tuple[str, str, str, str]


def _citation_entry(citation: Citation) -> _Entry:
    """Bildet ein Chunk-Zitat auf einen Beleg mit Abschnitts-/Seiten-Label ab."""
    section = f" · Abschnitt {citation.section_title}" if citation.section_title else ""
    pages = page_label(citation.page_number, citation.page_end)
    label = f"Paper {citation.paper_id}{section} · {pages}"
    return citation.paper_id, label, citation.snippet, citation.source_uri


def _paper_entry(ref: PaperRef, community_id: int) -> _Entry:
    """Bildet ein repräsentatives Paper einer Community auf einen Beleg ab."""
    label = f"Paper {ref.paper_id} · Community #{community_id}"
    return ref.paper_id, label, ref.snippet, ref.source_uri


def evidence_from_basic(result: BasicSearchResult) -> Evidence:
    """Baut die Evidenz aus einem Basic-Ergebnis (Top-k-Chunk-Zitate)."""
    return Evidence.build(
        result.query, "basic", tuple(_citation_entry(c) for c in result.citations)
    )


def evidence_from_local(result: LocalSearchResult) -> Evidence:
    """Baut die Evidenz aus einem Local-Ergebnis (Seeds, Nachbarschaft, Fan-out-Belege)."""
    entries: list[_Entry] = [_citation_entry(citation) for citation in result.seeds]
    entries.extend(_citation_entry(c) for c in result.neighborhood)
    entries.extend(
        _citation_entry(neighbor.citation)
        for neighbor in result.fan_out
        if neighbor.citation is not None
    )
    return Evidence.build(result.query, "local", tuple(entries))


def evidence_from_global(result: GlobalSearchResult) -> Evidence:
    """Baut die Evidenz aus einem Global-Ergebnis (repräsentative Paper je Top-Community)."""
    entries: list[_Entry] = []
    for match in result.communities:
        entries.extend(_paper_entry(ref, match.community_id) for ref in match.representatives)
    return Evidence.build(result.query, "global", tuple(entries))


def evidence_from_drift(result: DriftSearchResult) -> Evidence:
    """Baut die Evidenz aus einem DRIFT-Ergebnis (lokal verfeinerte Chunk-Belege)."""
    return Evidence.build(
        result.query, "drift", tuple(_citation_entry(c) for c in result.citations)
    )
