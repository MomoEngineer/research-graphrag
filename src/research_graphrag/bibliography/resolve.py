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


IDENTITY_ORIGIN_KEY = "author_ids"
"""Schlüssel in ``origins``, der die Herkunft der Personenkennungen ausweist (ADR 0041)."""


def _identities_for(
    authors: tuple[str, ...],
    author_source: MetadataRecord | None,
    ordered: Sequence[MetadataRecord],
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """Bestimmt die Personenkennungen zur gewonnenen Autorenliste.

    Die Kennungen reisen **mit** der Namensliste: Zuerst gelten die des Datensatzes, der
    ``authors`` gewonnen hat. Trägt er keine, darf ein anderer Datensatz sie liefern, aber **nur**,
    wenn seine Namensliste Position für Position identisch ist. So erhält etwa ein
    Referenz-Eintrag die Kennungen aus einer Rohantwort (Nachtrag, A2, Punkt 3), ohne dass je
    eine Kennung an einen fremden Namen gerät (docs/adr/0041-author-identity-and-schema.md).

    Returns:
        ``(author_ids, author_orcids, Herkunft der Kennungen)``; ohne Kennung ``((), (), "")``.
    """
    if not authors:
        return (), (), ""
    candidates = [author_source] if author_source is not None else []
    candidates += [record for record in ordered if record is not author_source]
    for record in candidates:
        if record is None or record.authors != authors:
            continue
        if record.author_ids or record.author_orcids:
            return record.author_ids, record.author_orcids, record.origin
    return (), (), ""


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
    author_source: MetadataRecord | None = None
    for record in _ordered(relevant):
        contributed = False
        for name in METADATA_FIELDS:
            if name in values or not record.has(name):
                continue
            values[name] = record.value_of(name)
            origins[name] = record.origin
            contributed = True
            if name == "authors":
                author_source = record
        if contributed:
            contributing.append(record.confidence)

    author_ids, author_orcids, id_origin = _identities_for(
        tuple(values.get("authors", ()) or ()), author_source, _ordered(relevant)
    )
    if id_origin:
        origins[IDENTITY_ORIGIN_KEY] = id_origin

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
        author_ids=author_ids,
        author_orcids=author_orcids,
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
