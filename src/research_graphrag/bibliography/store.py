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

Seit Phase 17 / A1 trägt dieselbe Datei unter ``reviews`` den **Prüfstand** je Paper:
Ablehnungsvermerke und einen ausgewiesenen Status wie „nicht auflösbar“. Datensätze und Vermerke
liegen bewusst in **einer** Datei. Das Verwerfen eines Treffers und sein Vermerk entstehen dadurch
in einem atomaren Schreibvorgang. Zwei Dateien könnten nach einem Abbruch den Datensatz ohne Vermerk
zurücklassen, und der nächste Lauf spielte den Treffer wieder ein
(docs/adr/0042-title-page-evidence-and-rejections.md). Der Schlüssel ist additiv: Er erscheint nur,
wenn es einen Prüfstand gibt, und eine alte Datei lädt unverändert.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from research_graphrag.atomic_write import atomic_write_bytes
from research_graphrag.bibliography.model import (
    ORIGIN_PRECEDENCE,
    REVIEW_STATUSES,
    MetadataRecord,
    PaperReview,
    Rejection,
)
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


REVIEWS_KEY = "reviews"
"""Schlüssel des Prüfstands je Paper in der Metadatendatei (additiv, Phase 17 / A1)."""


def _read_document(file_path: Path) -> dict[str, Any]:
    """Liest und prüft das Dokument (Objekt, Schema-Version)."""
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
    return payload


def load_reviews(path: str | Path) -> dict[str, PaperReview]:
    """Liest den Prüfstand je Paper (fehlende Datei oder fehlender Schlüssel ⇒ leer).

    Args:
        path: Pfad zur Metadatendatei.

    Returns:
        Prüfstände nach ``paper_id``; leere Einträge entfallen.

    Raises:
        DomainError: ``parse_error``/``constraint_violation`` wie :func:`load_records`, dazu
            ``constraint_violation``, wenn ``reviews`` kein Objekt ist.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    raw = _read_document(file_path).get(REVIEWS_KEY, {})
    if not isinstance(raw, dict):
        raise DomainError(ErrorCode.CONSTRAINT_VIOLATION, f"Feld '{REVIEWS_KEY}' ist kein Objekt.")
    reviews = {
        str(paper_id): PaperReview.from_dict(str(paper_id), entry)
        for paper_id, entry in raw.items()
        if isinstance(entry, Mapping)
    }
    return {paper_id: review for paper_id, review in reviews.items() if not review.is_empty}


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
    payload = _read_document(file_path)
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


def save_records(
    path: str | Path,
    records: Iterable[MetadataRecord],
    *,
    reviews: Mapping[str, PaperReview] | None = None,
) -> int:
    """Schreibt die Datensätze deterministisch und atomar.

    Args:
        path: Zielpfad; der Elternordner wird angelegt.
        records: Zu speichernde Datensätze (Reihenfolge unerheblich).
        reviews: Prüfstand je Paper. ``None`` **behält** den Prüfstand der vorhandenen Datei.
            Jeder Aufrufer, der nur Datensätze schreibt (Auflösungslauf, Korrektur-Tool), kann
            dadurch keinen Ablehnungsvermerk verlieren. Leere Prüfstände werden nicht geschrieben.

    Returns:
        Anzahl der geschriebenen Datensätze.
    """
    file_path = Path(path)
    kept = load_reviews(file_path) if reviews is None else reviews
    ordered = _sorted(records)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in ordered:
        grouped.setdefault(record.paper_id, []).append(record.to_dict())

    document: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "papers": grouped}
    written_reviews = {
        paper_id: review.to_dict() for paper_id, review in kept.items() if not review.is_empty
    }
    if written_reviews:
        document[REVIEWS_KEY] = written_reviews
    text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    # write als Bytes (nicht write_text): verhindert die Windows-Umsetzung von \n auf \r\n und
    # hält die Datei damit über Plattformen hinweg byte-identisch. atomic_write_bytes legt den
    # Elternordner bei Bedarf selbst an (mit Retry) und schließt zusätzlich die Absturzgefahr
    # zweier nahezu gleichzeitiger Schreibversuche (z. B. zwei correct_paper_metadata-Aufrufe
    # ohne Warten auf die erste Antwort) – siehe dessen Modul-Doku (ADR 0039, Nachträge).
    atomic_write_bytes(file_path, text.encode("utf-8"))
    return len(ordered)


def add_rejection(
    reviews: Mapping[str, PaperReview], paper_id: str, rejection: Rejection
) -> dict[str, PaperReview]:
    """Ergänzt einen Ablehnungsvermerk (ein identischer Vermerk wird nicht doppelt geführt)."""
    merged = dict(reviews)
    current = merged.get(paper_id, PaperReview(paper_id=paper_id))
    if rejection not in current.rejections:
        current = replace(current, rejections=(*current.rejections, rejection))
    merged[paper_id] = current
    return merged


def set_review_status(
    reviews: Mapping[str, PaperReview], paper_id: str, status: str, reason: str
) -> dict[str, PaperReview]:
    """Setzt (oder mit ``status=""`` löscht) den Prüfstatus eines Papers.

    Raises:
        DomainError: ``invalid_input`` bei unbekanntem Status oder fehlendem Grund.
    """
    if status and status not in REVIEW_STATUSES:
        raise DomainError(ErrorCode.INVALID_INPUT, f"Unbekannter Prüfstatus {status!r}.")
    if status and not reason.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Ein Prüfstatus braucht einen Grund.")
    merged = dict(reviews)
    current = merged.get(paper_id, PaperReview(paper_id=paper_id))
    merged[paper_id] = replace(current, status=status, reason=reason.strip() if status else "")
    return merged


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
