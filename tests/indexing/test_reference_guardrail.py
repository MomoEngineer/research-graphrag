"""Guardrail: Referenz-Einträge sind nachrangige Treffer der Chunk-Suche (Phase 13 / R3).

Die Regel ist bewusst schmal: Sie ändert die **Reihenfolge** innerhalb der Trefferliste, nicht
die **Auswahl**. Beides zu ändern hätte in der Vorabmessung genau den Nutzen zerstört, für den
die Referenz-Einträge existieren (docs/adr/0031-reference-contract-and-guardrail-phase13.md).
"""

from __future__ import annotations

from research_graphrag.extraction.model import DOCUMENT_KIND_FULL, DOCUMENT_KIND_REFERENCE
from research_graphrag.indexing.tfidf_index import Hit, demote_references


def _hit(paper_id: str, score: float, kind: str) -> Hit:
    """Baut einen minimalen Treffer für die Sortierprüfung."""
    return Hit(
        chunk_id=f"{paper_id}-c0000",
        paper_id=paper_id,
        page_number=1,
        score=score,
        snippet="…",
        source_uri=f"file:///{paper_id}",
        document_kind=kind,
    )


def test_reference_entries_move_behind_full_text_hits() -> None:
    """Ein besser bewerteter Referenz-Eintrag rutscht hinter den Volltext-Treffer."""
    hits = [
        _hit("stub1", 0.9, DOCUMENT_KIND_REFERENCE),
        _hit("full1", 0.5, DOCUMENT_KIND_FULL),
        _hit("stub2", 0.4, DOCUMENT_KIND_REFERENCE),
        _hit("full2", 0.3, DOCUMENT_KIND_FULL),
    ]

    assert [hit.paper_id for hit in demote_references(hits)] == [
        "full1",
        "full2",
        "stub1",
        "stub2",
    ]


def test_guardrail_keeps_the_selection_unchanged() -> None:
    """Nachrangig heißt umsortieren, nicht aussortieren – die Menge bleibt gleich."""
    hits = [
        _hit("stub1", 0.9, DOCUMENT_KIND_REFERENCE),
        _hit("full1", 0.5, DOCUMENT_KIND_FULL),
    ]

    assert {hit.paper_id for hit in demote_references(hits)} == {"stub1", "full1"}


def test_reference_entry_stays_first_without_full_text_competition() -> None:
    """Ohne Volltext-Treffer bleibt der Referenz-Eintrag vorn – dafür ist er da."""
    hits = [
        _hit("stub1", 0.9, DOCUMENT_KIND_REFERENCE),
        _hit("stub2", 0.4, DOCUMENT_KIND_REFERENCE),
    ]

    assert [hit.paper_id for hit in demote_references(hits)] == ["stub1", "stub2"]


def test_guardrail_is_stable_within_each_group() -> None:
    """Innerhalb von Volltext und Referenz bleibt die Wertungsreihenfolge erhalten."""
    hits = [
        _hit("full1", 0.9, DOCUMENT_KIND_FULL),
        _hit("full2", 0.8, DOCUMENT_KIND_FULL),
        _hit("full3", 0.7, DOCUMENT_KIND_FULL),
    ]

    assert demote_references(hits) == hits


def test_guardrail_is_idempotent() -> None:
    """Zweimal angewandt ändert sich nichts mehr (die Suche darf sie mehrfach durchlaufen)."""
    hits = [
        _hit("stub1", 0.9, DOCUMENT_KIND_REFERENCE),
        _hit("full1", 0.5, DOCUMENT_KIND_FULL),
    ]
    once = demote_references(hits)

    assert demote_references(once) == once
