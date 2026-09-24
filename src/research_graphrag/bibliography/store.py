"""Persistenz der bibliografischen Datensätze (Phase 12 / K1).

Verwaltet die **versionierte** Datei ``metadata/paper_metadata.json``. Sie liegt bewusst nicht
unter ``data/``: Dieser Ordner ist als „abgeleitet, regenerierbar" definiert, während kuratierte
und extern aufgelöste Zitationsdaten sich aus den PDFs nicht rekonstruieren lassen
(docs/adr/0025-citable-paper-metadata.md, Punkt 1).

Geschrieben wird **deterministisch** (sortierte Schlüssel, feste Feldreihenfolge, ``\\n`` als
Zeilenende auch unter Windows) und **atomar** über
:func:`research_graphrag.atomic_write.atomic_write_bytes` (Temporärdatei + ``os.replace`` mit
Windows-Retry) – damit ein abgebrochener Lauf keine halbe Datei hinterlässt, ein erneuter Lauf
byte-identisch schreibt und zwei nahezu gleichzeitige Schreibversuche nicht abstürzen.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from research_graphrag.atomic_write import atomic_write_bytes
from research_graphrag.bibliography.model import ORIGIN_PRECEDENCE, MetadataRecord
from research_graphrag.errors import DomainError, ErrorCode

SCHEMA_VERSION = "0.1.0"
"""Version des Speicherformats von ``metadata/paper_metadata.json``."""

METADATA_DIR = "metadata"
"""Versionierter Ordner der bibliografischen Daten (Geschwister von ``eval/``)."""

METADATA_FILENAME = "paper_metadata.json"
"""Dateiname der Metadatenquelle."""

WRITABLE_ORIGINS: tuple[str, ...] = ("manual", "resolved")
"""Herkünfte, die in der Datei gespeichert werden.

``extracted`` und ``curated`` werden bei jedem Index-Bau **neu abgeleitet** (aus dem Canonical
bzw. der Übersicht) und daher nicht dupliziert – sonst gäbe es zwei Wahrheiten.
"""


def metadata_path(root: str | Path = ".") -> Path:
    """Liefert den Pfad zur Metadatendatei unterhalb eines Repository-Wurzelverzeichnisses."""
    return Path(root) / METADATA_DIR / METADATA_FILENAME


def load_records(path: str | Path) -> tuple[MetadataRecord, ...]:
    """Liest alle gespeicherten Datensätze (fehlende Datei ⇒ leeres Ergebnis).

    Args:
        path: Pfad zur Metadatendatei.

    Returns:
        Die Datensätze, sortiert nach ``paper_id`` und Herkunfts-Vorrang.

    Raises:
        DomainError: ``parse_error`` bei defektem JSON; ``constraint_violation`` bei
            unbekannter Schema-Version oder unerwarteter Struktur (siehe docs/error-model.md).
    """
    file_path = Path(path)
    if not file_path.is_file():
        return ()
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DomainError(
            ErrorCode.PARSE_ERROR, f"Metadatendatei nicht lesbar: {file_path} ({exc})"
        ) from exc
    if not isinstance(payload, dict):
        raise DomainError(ErrorCode.CONSTRAINT_VIOLATION, "Metadatendatei ist kein Objekt.")
    version = str(payload.get("schema_version", ""))
    if version != SCHEMA_VERSION:
        raise DomainError(
            ErrorCode.CONSTRAINT_VIOLATION,
            f"Unerwartete Schema-Version {version!r} (erwartet {SCHEMA_VERSION!r}).",
        )
    papers = payload.get("papers", {})
    if not isinstance(papers, dict):
        raise DomainError(ErrorCode.CONSTRAINT_VIOLATION, "Feld 'papers' ist kein Objekt.")

    records: list[MetadataRecord] = []
    for paper_id, entries in papers.items():
        if not isinstance(entries, list):
            raise DomainError(
                ErrorCode.CONSTRAINT_VIOLATION, f"Datensätze von {paper_id} sind keine Liste."
            )
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise DomainError(
                    ErrorCode.CONSTRAINT_VIOLATION, f"Defekter Datensatz bei {paper_id}."
                )
            records.append(MetadataRecord.from_dict(str(paper_id), entry))
    return _sorted(records)


def _sorted(records: Iterable[MetadataRecord]) -> tuple[MetadataRecord, ...]:
    """Sortiert deterministisch nach ``paper_id`` und Herkunfts-Vorrang."""
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.paper_id,
                ORIGIN_PRECEDENCE.index(record.origin)
                if record.origin in ORIGIN_PRECEDENCE
                else len(ORIGIN_PRECEDENCE),
                record.origin,
            ),
        )
    )


def save_records(path: str | Path, records: Iterable[MetadataRecord]) -> int:
    """Schreibt die Datensätze deterministisch und atomar.

    Args:
        path: Zielpfad; der Elternordner wird angelegt.
        records: Zu speichernde Datensätze (Reihenfolge unerheblich).

    Returns:
        Anzahl der geschriebenen Datensätze.
    """
    ordered = _sorted(records)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in ordered:
        grouped.setdefault(record.paper_id, []).append(record.to_dict())

    document = {"schema_version": SCHEMA_VERSION, "papers": grouped}
    text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    file_path = Path(path)
    # write als Bytes (nicht write_text): verhindert die Windows-Umsetzung von \n auf \r\n und
    # hält die Datei damit über Plattformen hinweg byte-identisch. atomic_write_bytes legt den
    # Elternordner bei Bedarf selbst an (mit Retry) und schließt zusätzlich die Absturzgefahr
    # zweier nahezu gleichzeitiger Schreibversuche (z. B. zwei correct_paper_metadata-Aufrufe
    # ohne Warten auf die erste Antwort) – siehe dessen Modul-Doku (ADR 0039, Nachträge).
    atomic_write_bytes(file_path, text.encode("utf-8"))
    return len(ordered)


def upsert_records(
    existing: Iterable[MetadataRecord], updates: Iterable[MetadataRecord]
) -> tuple[MetadataRecord, ...]:
    """Ersetzt Datensätze je ``(paper_id, origin)`` und behält alle übrigen unverändert.

    Damit überschreibt ein erneuter Auflösungslauf seine eigenen Ergebnisse, lässt aber von
    Hand gepflegte Datensätze (``manual``) unangetastet.
    """
    merged: dict[tuple[str, str], MetadataRecord] = {
        (record.paper_id, record.origin): record for record in existing
    }
    for record in updates:
        merged[(record.paper_id, record.origin)] = record
    return _sorted(merged.values())
