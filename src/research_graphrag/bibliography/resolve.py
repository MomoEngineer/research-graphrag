"""Feldweise Auflösung der Metadaten-Datensätze (Phase 12 / K1).

Setzt die Autoritätskette aus docs/adr/0025-citable-paper-metadata.md um: Für **jedes** Feld
gewinnt die erste Herkunft aus :data:`research_graphrag.bibliography.model.ORIGIN_PRECEDENCE`,
die einen nicht-leeren Wert liefert. Das ist nötig, weil die Quellen komplementär sind – die
kuratierte Übersicht kennt den Publisher-DOI, aber weder Autoren noch Venue; die
Online-Auflösung kennt beides.

Das Modul ist rein funktional (keine Datei-, Netz- oder Index-Zugriffe).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from research_graphrag.bibliography.model import (
    METADATA_FIELDS,
    ORIGIN_PRECEDENCE,
    MetadataRecord,
    PaperMetadata,
    empty_metadata,
    lowest_confidence,
)


def _ordered(records: Iterable[MetadataRecord]) -> list[MetadataRecord]:
    """Sortiert die Datensätze nach Herkunfts-Vorrang (unbekannte Herkunft zuletzt, stabil)."""
    return sorted(
        records,
        key=lambda record: (
            ORIGIN_PRECEDENCE.index(record.origin)
            if record.origin in ORIGIN_PRECEDENCE
            else len(ORIGIN_PRECEDENCE),
            record.origin,
        ),
    )


def resolve_metadata(paper_id: str, records: Sequence[MetadataRecord]) -> PaperMetadata:
    """Führt die Datensätze eines Papers zu einem zitierfähigen Datensatz zusammen.

    Args:
        paper_id: Stabile Paper-ID des Korpus.
        records: Datensätze **dieses** Papers (Reihenfolge unerheblich).

    Returns:
        Ein :class:`PaperMetadata`; ohne Datensätze ein leerer (siehe
        :func:`research_graphrag.bibliography.model.empty_metadata`).
    """
    relevant = [record for record in records if record.paper_id == paper_id]
    if not relevant:
        return empty_metadata(paper_id)

    values: dict[str, Any] = {}
    origins: dict[str, str] = {}
    contributing: list[str] = []
    for record in _ordered(relevant):
        contributed = False
        for name in METADATA_FIELDS:
            if name in values or not record.has(name):
                continue
            values[name] = record.value_of(name)
            origins[name] = record.origin
            contributed = True
        if contributed:
            contributing.append(record.confidence)

    return PaperMetadata(
        paper_id=paper_id,
        title=str(values.get("title", "")),
        authors=tuple(values.get("authors", ()) or ()),
        year=int(values.get("year", 0) or 0),
        venue=str(values.get("venue", "")),
        doi=str(values.get("doi", "")),
        arxiv_id=str(values.get("arxiv_id", "")),
        url=str(values.get("url", "")),
        origins=origins,
        confidence=lowest_confidence(contributing),
    )


def resolve_all(
    records: Iterable[MetadataRecord], paper_ids: Iterable[str]
) -> dict[str, PaperMetadata]:
    """Löst mehrere Paper in einem Durchgang auf (Paper ohne Datensatz bleiben leer)."""
    grouped: dict[str, list[MetadataRecord]] = {}
    for record in records:
        grouped.setdefault(record.paper_id, []).append(record)
    return {
        paper_id: resolve_metadata(paper_id, grouped.get(paper_id, [])) for paper_id in paper_ids
    }
