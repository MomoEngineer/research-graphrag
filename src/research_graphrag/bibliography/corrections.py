"""Korrektur bibliografischer Metadaten in der Herkunft ``manual`` (ADR 0039, ADR 0040).

Erstes schreibendes Werkzeug der MCP-Oberfläche: Ein Aufruf ergänzt oder überschreibt einzelne
Felder des ``manual``-Records eines Papers in ``metadata/paper_metadata.json`` – der bereits
höchsten Herkunft der bestehenden Auflösungskette
(docs/adr/0025-citable-paper-metadata.md). Geschrieben wird über die bestehende, atomare
Persistenz aus :mod:`research_graphrag.bibliography.store`; es entsteht **kein** neues
Speicherformat.

Ein vorhandener ``manual``-Record desselben Papers wird vor dem Schreiben geladen und nur um die
übergebenen Felder ergänzt (Feld-Merge) – sonst würde ``upsert_records`` (das den ganzen
``(paper_id, "manual")``-Record ersetzt) eine frühere Korrektur an einem anderen Feld
stillschweigend löschen.

Neben dem Setzen eines Wertes (``fields``) kann ein Feld auch **explizit geleert** werden
(``clear_fields``, ADR 0040-explicit-field-clearing.md): Das markiert das Feld in
:attr:`~research_graphrag.bibliography.model.MetadataRecord.cleared_fields` als "geprüft: hat
wirklich keinen Wert" statt "nie geprüft" – eine niedrigerrangige, ggf. falsche Herkunft
(typischerweise ``extracted``) scheint dann nicht mehr durch die feldweise Auflösung
(:mod:`research_graphrag.bibliography.resolve`) durch. Ein Feld darf pro Aufruf nicht gleichzeitig
gesetzt und geleert werden.

Wirksam wird eine Korrektur **nicht sofort**: ``get_paper``/``get_reference``/``answer_question``
lesen bibliografische Daten ausschließlich aus der im Index gebauten Tabelle ``paper_metadata``,
die erst der nächste ``python -m scripts.ingest``-Lauf neu aus dieser Datei baut – dieselbe
Verzögerung wie beim bestehenden ``python -m scripts.resolve_metadata``
(docs/adr/0026-online-metadata-resolution.md). Jeder Aufruf wird zusätzlich append-only in
``data/corrections_log.md`` protokolliert (Muster aus :mod:`research_graphrag.online.report`).

Ein OS-Schreibfehler beim Speichern (gesperrte Datei, fehlende Schreibrechte, falsch
konfiguriertes Arbeitsverzeichnis des MCP-Server-Prozesses) wird als ``internal_error`` **mit**
Exception-Typ und -Meldung gemeldet, statt in der nichtssagenden generischen Absicherung von
``mcp_server.server._guard`` zu verschwinden – derselbe Grundsatz wie beim OS-Lesefehler in
:func:`research_graphrag.extraction.pdf.extract_pdf` (ADR 0039, Nachtrag 2026-09-19).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    METADATA_FIELDS,
    ORIGIN_MANUAL,
    MetadataRecord,
)
from research_graphrag.bibliography.store import load_records, save_records, upsert_records
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.online.report import append_section, escape_markdown

LOG_NAME = "corrections_log.md"
"""Dateiname des append-only Korrektur-Protokolls unterhalb des Datenverzeichnisses."""

EFFECTIVE_AFTER = "python -m scripts.ingest"
"""Fester Hinweis in jeder Antwort: Wann eine Korrektur in den übrigen Werkzeugen sichtbar wird."""

CLEARED_MARKER = "(explizit geleert)"
"""Protokoll-Vermerk für ein über ``clear_fields`` explizit geleertes Feld (ADR 0040)."""

_MIN_YEAR = 1000
_TEXT_FIELDS = ("title", "venue", "doi", "arxiv_id", "url")
_LOG_VALUE_LIMIT = 300

_LOG_HEADER = (
    "# Korrekturen",
    "",
    "Append-only Protokoll von `correct_paper_metadata` (docs/adr/0039-correction-tool-and-"
    "pdf-file-access.md, docs/adr/0040-explicit-field-clearing.md). Jeder Eintrag nennt die",
    "geänderten Felder samt altem und neuem Wert (oder dem Vermerk "
    f"`{CLEARED_MARKER}`, wenn ein Feld",
    "über `clear_fields` explizit auf leer gesetzt wurde) sowie den angegebenen Beleg. Wirksam",
    "wird eine Korrektur erst mit dem nächsten `python -m scripts.ingest`-Lauf.",
    "",
)


@dataclass(frozen=True)
class CorrectionResult:
    """Ergebnis eines Korrektur-Aufrufs (siehe specs/correct_paper_metadata.md)."""

    paper_id: str
    applied_fields: tuple[str, ...]
    previous: dict[str, Any]
    record: MetadataRecord
    log_path: Path

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (Output-Schema des Tools ``correct_paper_metadata``)."""
        return {
            "paper_id": self.paper_id,
            "applied_fields": list(self.applied_fields),
            "previous": self.previous,
            "record": self.record.to_dict(),
            "log_path": str(self.log_path),
            "effective_after": EFFECTIVE_AFTER,
        }


def _validate_known_paper(db_path: Path, paper_id: str) -> None:
    """Prüft, dass ``paper_id`` nicht leer und im Index bekannt ist."""
    if not paper_id.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leere paper_id.")
    if not db_path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {db_path}")
    connection = sqlite3.connect(str(db_path))
    try:
        row = connection.execute("SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise DomainError(ErrorCode.NOT_FOUND, f"Paper nicht gefunden: {paper_id}")


def _validate_request(fields: dict[str, Any], clear_fields: Sequence[str]) -> None:
    """Prüft Feldnamen und -werte der angeforderten Korrektur (Setzen **und** explizites Leeren)."""
    if not fields and not clear_fields:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            "Mindestens ein Korrekturfeld (setzen oder über clear_fields explizit leeren) "
            "muss angegeben werden.",
        )
    overlap = set(fields) & set(clear_fields)
    if overlap:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            f"Feld(er) gleichzeitig gesetzt und geleert: {', '.join(sorted(overlap))}.",
        )
    for name in fields:
        if name not in METADATA_FIELDS:
            raise DomainError(ErrorCode.INVALID_INPUT, f"Unbekanntes Feld: {name}.")
    for name in clear_fields:
        if name not in METADATA_FIELDS:
            raise DomainError(ErrorCode.INVALID_INPUT, f"Unbekanntes Feld in clear_fields: {name}.")

    for name in _TEXT_FIELDS:
        if name in fields and not str(fields[name]).strip():
            raise DomainError(ErrorCode.INVALID_INPUT, f"Leeres Feld: {name}.")

    if "authors" in fields and not fields["authors"]:
        raise DomainError(ErrorCode.INVALID_INPUT, "Leere Autorenliste.")

    if "year" in fields:
        year = int(fields["year"])
        current_year = datetime.now(UTC).year
        if not (_MIN_YEAR <= year <= current_year + 1):
            raise DomainError(
                ErrorCode.INVALID_INPUT,
                f"Unplausibles Jahr: {year} (erwartet {_MIN_YEAR}..{current_year + 1}).",
            )


def _base_values(current: MetadataRecord | None) -> dict[str, Any]:
    """Die aktuellen Feldwerte eines ``manual``-Records (leer, wenn keiner existiert)."""
    if current is None:
        return {
            name: (0 if name == "year" else () if name == "authors" else "")
            for name in METADATA_FIELDS
        }
    return {name: current.value_of(name) for name in METADATA_FIELDS}


def _empty_value_for(name: str) -> Any:
    """Der typkorrekte "leere" Wert eines Feldes für ein explizites Leeren (``clear_fields``)."""
    if name == "year":
        return 0
    if name == "authors":
        return ()
    return ""


def _render_entry(
    timestamp: str,
    paper_id: str,
    fields: dict[str, Any],
    clear_fields: Sequence[str],
    previous: dict[str, Any],
    evidence: str,
) -> list[str]:
    """Rendert einen Protokoll-Eintrag (siehe :data:`_LOG_HEADER`)."""
    lines = [f"## {timestamp} · `{paper_id}`", ""]
    cleared = set(clear_fields)
    for name in sorted(set(fields) | cleared):
        old = escape_markdown(str(previous[name]), limit=_LOG_VALUE_LIMIT) or "(leer)"
        new = (
            CLEARED_MARKER
            if name in cleared
            else escape_markdown(str(fields[name]), limit=_LOG_VALUE_LIMIT)
        )
        lines.append(f"- `{name}`: {old} → {new}")
    lines.append(f"- Beleg: {escape_markdown(evidence, limit=_LOG_VALUE_LIMIT)}")
    lines.append("")
    return lines


def apply_manual_correction(
    db_path: str | Path,
    metadata_path: str | Path,
    data_dir: str | Path,
    paper_id: str,
    fields: dict[str, Any],
    evidence: str,
    clear_fields: Sequence[str] = (),
) -> CorrectionResult:
    """Schreibt eine ``manual``-Korrektur für ein Paper (siehe specs/correct_paper_metadata.md).

    Args:
        db_path: Pfad zur SQLite-Index-Datei (zur Existenzprüfung der ``paper_id``).
        metadata_path: Pfad zu ``metadata/paper_metadata.json``.
        data_dir: Datenverzeichnis für das append-only Protokoll (üblicherweise ``data/``).
        paper_id: Stabile Paper-ID (kein Datei-Pfad).
        fields: Zu setzende Felder, beschränkt auf
            :data:`~research_graphrag.bibliography.model.METADATA_FIELDS`.
        evidence: Nicht-leerer Beleg für die Korrektur.
        clear_fields: Felder, die **explizit als leer bestätigt** werden sollen (ADR 0040) –
            markiert das Feld in
            :attr:`~research_graphrag.bibliography.model.MetadataRecord.cleared_fields`, statt
            nur seinen Wert zu setzen. Ein Feld darf nicht gleichzeitig in ``fields`` und
            ``clear_fields`` stehen. Wird dasselbe Feld in einem späteren Aufruf **gesetzt**,
            verlässt es ``cleared_fields`` wieder.

    Returns:
        Ein :class:`CorrectionResult` mit den geänderten Feldern (gesetzt oder geleert), ihren
        vorherigen Werten und dem vollständigen, jetzt gespeicherten ``manual``-Record.

    Raises:
        DomainError: ``invalid_input`` bei leerer ``paper_id``/``evidence``, keinem, einem
            unbekannten oder einem ungültigen Feld, oder einem Feld, das gleichzeitig gesetzt
            und geleert werden soll; ``not_found``, wenn der Index fehlt oder ``paper_id``
            unbekannt ist; ``internal_error`` mit Exception-Typ und -Meldung im Text, wenn
            ``metadata_path`` nicht lesbar oder nicht schreibbar ist, oder das Protokoll unter
            ``data_dir`` nicht schreibbar ist (z. B. gesperrte Datei, fehlende Schreibrechte,
            nicht existierendes Verzeichnis wegen eines falsch konfigurierten
            Arbeitsverzeichnisses) – anders als der generische Catch-all in
            ``mcp_server.server._guard`` ist dieser Fall **erwartet** (Analogie zu
            :func:`research_graphrag.extraction.pdf.extract_pdf`) und liefert deshalb Details
            statt einer nichtssagenden Meldung (siehe docs/error-model.md).
    """
    resolved_db = Path(db_path)
    _validate_known_paper(resolved_db, paper_id)
    _validate_request(fields, clear_fields)
    if not evidence.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leerer Beleg (evidence).")

    resolved_metadata = Path(metadata_path)
    try:
        existing = load_records(resolved_metadata)
    except OSError as exc:
        raise DomainError(
            ErrorCode.INTERNAL_ERROR,
            f"Bestehende Metadaten nicht lesbar ({type(exc).__name__}): {exc}",
            {"metadata_path": str(resolved_metadata)},
        ) from exc
    current_manual = next(
        (r for r in existing if r.paper_id == paper_id and r.origin == ORIGIN_MANUAL), None
    )

    base = _base_values(current_manual)
    touched = set(fields) | set(clear_fields)
    previous = {name: (list(base[name]) if name == "authors" else base[name]) for name in touched}

    merged = {**base, **fields}
    for name in clear_fields:
        merged[name] = _empty_value_for(name)

    previous_cleared = current_manual.cleared_fields if current_manual is not None else frozenset()
    new_cleared = (previous_cleared - set(fields)) | set(clear_fields)

    merged_evidence = evidence.strip()
    if current_manual is not None and current_manual.evidence.strip():
        merged_evidence = f"{current_manual.evidence.strip()}; {merged_evidence}"

    new_record = MetadataRecord(
        paper_id=paper_id,
        origin=ORIGIN_MANUAL,
        title=str(merged["title"]),
        authors=tuple(str(name) for name in merged["authors"]),
        year=int(merged["year"]),
        venue=str(merged["venue"]),
        doi=str(merged["doi"]),
        arxiv_id=str(merged["arxiv_id"]),
        url=str(merged["url"]),
        confidence=CONFIDENCE_STRONG,
        evidence=merged_evidence,
        cleared_fields=frozenset(new_cleared),
    )

    try:
        save_records(resolved_metadata, upsert_records(existing, [new_record]))
    except OSError as exc:
        raise DomainError(
            ErrorCode.INTERNAL_ERROR,
            f"Korrektur nicht speicherbar ({type(exc).__name__}): {exc}",
            {"metadata_path": str(resolved_metadata)},
        ) from exc

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_target = Path(data_dir) / LOG_NAME
    try:
        log_path = append_section(
            log_target,
            _render_entry(timestamp, paper_id, fields, clear_fields, previous, evidence.strip()),
            _LOG_HEADER,
        )
    except OSError as exc:
        raise DomainError(
            ErrorCode.INTERNAL_ERROR,
            f"Korrektur-Protokoll nicht schreibbar ({type(exc).__name__}): {exc}. Der "
            f"manual-Record in {resolved_metadata} wurde bereits gespeichert.",
            {"log_path": str(log_target)},
        ) from exc

    return CorrectionResult(
        paper_id=paper_id,
        applied_fields=tuple(sorted(touched)),
        previous=previous,
        record=new_record,
        log_path=log_path,
    )
