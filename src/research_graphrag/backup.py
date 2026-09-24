"""Sicherung des Korpus: Quelle sichern, Ableitung verwerfen (Phase 11 / B1).

``papers/`` und ``data/`` sind bewusst nicht versioniert – der gesamte Bestand hängt damit an
einem Ordner auf einer Maschine. Dieses Modul sichert genau den Teil, der **nicht** reproduzierbar
ist, und lässt alles Abgeleitete draußen
(docs/adr/0027-corpus-backup-phase11.md).

Gesichert werden der PDF-Korpus, die kuratierte Übersicht, die Zitationsdaten sowie das Manifest
und die append-only Protokolle. **Nicht** gesichert werden ``data/canonical/``, ``data/index/``
und die Qualitätsberichte: Sie entstehen deterministisch neu aus ``papers/``. Der Grund ist
Korrektheit, nicht Platz – ein mitgesicherter Index verleitet dazu, ihn zurückzuspielen, obwohl
er zum wiederhergestellten Korpus nicht passen muss. Der Weg zurück ist deshalb genau einer:
Dateien zurückkopieren, dann ``python -m scripts.ingest``.

Der Lauf ist **idempotent**: Eine Datei, die am Ziel bereits mit identischem sha256 liegt, wird
übersprungen. ``dry_run`` verändert nichts, und :func:`verify_backup` rechnet einen vorhandenen
Sicherungsstand gegen sein Manifest nach.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode

BACKUP_MANIFEST_NAME = "backup_manifest.json"
"""Prüfnachweis im Zielverzeichnis: sha256 und Größe je gesicherter Datei."""

BACKUP_SCHEMA_VERSION = "0.1.0"
"""Version des Manifest-Formats (eigenständig, unabhängig vom Index-Schema)."""

SOURCE_DIRECTORIES: tuple[str, ...] = ("papers", "metadata/llm_answers")
"""Vollständig (rekursiv) gesicherte Verzeichnisse; ein fehlendes wird übersprungen.

``metadata/llm_answers/`` hält die abgelegten LLM-Antworten der Metadaten-Arbeitsliste
(Phase 17 / A1). Sie sind aus keiner Quelle rekonstruierbar, anders als die Arbeitslisten
selbst, die jederzeit neu entstehen (docs/adr/0042-title-page-evidence-and-rejections.md)."""

SOURCE_FILES: tuple[str, ...] = (
    "Übersicht.md",
    "metadata/paper_metadata.json",
    "metadata/curation.json",
    "new_papers/referenzen.txt",
    "data/manifest.json",
    "data/intake_log.md",
    "data/metadata_log.md",
    "data/online_candidates.md",
    "data/references_log.md",
)
"""Einzeln gesicherte Dateien; fehlende gelten als ``missing``, nicht als Fehler.

``new_papers/referenzen.txt`` ist die kuratierte Kennungsliste der Referenz-Einträge und aus
keiner Quelle rekonstruierbar; ``data/references_log.md`` ist – wie die übrigen Protokolle –
append-only (docs/adr/0029-reference-stub-resolution-phase13.md). ``metadata/curation.json``
trägt seit Phase 15 / G4 das einzige menschliche Relevanzurteil (vormals in ``Übersicht.md``);
``Übersicht.md`` selbst bleibt gesichert, weil sie als historischer Stand weiterhin Kontext trägt
(docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md).
"""

REQUIRED_DIRECTORY = "papers"
"""Ohne dieses Verzeichnis gibt es nichts zu sichern (``not_found``)."""

ACTION_COPIED = "copied"
ACTION_UNCHANGED = "unchanged"
ACTION_MISSING = "missing"

_CHUNK_BYTES = 1024 * 1024

ProgressCallback = Callable[[str, int, int], None]
"""Rückruf ``(relativer Pfad, erledigt, gesamt)`` für eine Fortschrittsanzeige."""


@dataclass(frozen=True)
class BackupItem:
    """Das Ergebnis für **eine** Datei des Sicherungsumfangs."""

    relative_path: str
    action: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Eintrag für das Manifest."""
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size": self.size,
        }


@dataclass(frozen=True)
class BackupReport:
    """Bilanz eines Sicherungslaufs."""

    root: Path
    target: Path
    dry_run: bool
    items: tuple[BackupItem, ...]

    @property
    def n_copied(self) -> int:
        """Zahl der neu geschriebenen Dateien."""
        return sum(1 for item in self.items if item.action == ACTION_COPIED)

    @property
    def n_unchanged(self) -> int:
        """Zahl der übersprungenen (bereits identischen) Dateien."""
        return sum(1 for item in self.items if item.action == ACTION_UNCHANGED)

    @property
    def n_missing(self) -> int:
        """Zahl der Artefakte, die es in dieser Arbeitskopie (noch) nicht gibt."""
        return sum(1 for item in self.items if item.action == ACTION_MISSING)

    @property
    def total_bytes(self) -> int:
        """Umfang des Sicherungsstandes in Byte (ohne die fehlenden Artefakte)."""
        return sum(item.size for item in self.items if item.action != ACTION_MISSING)


@dataclass(frozen=True)
class VerificationReport:
    """Ergebnis der Nachrechnung eines vorhandenen Sicherungsstandes."""

    target: Path
    n_checked: int
    mismatched: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Wahr, wenn jede Datei des Manifests unverändert vorliegt."""
        return not self.mismatched and not self.missing


def sha256_of(path: Path) -> str:
    """Bildet den sha256-Hash einer Datei blockweise (auch für große PDFs geeignet).

    Args:
        path: Pfad zur Datei.

    Returns:
        Hexadezimale Prüfsumme.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def collect_sources(root: Path) -> tuple[tuple[str, Path], ...]:
    """Bestimmt den Sicherungsumfang – deterministisch sortiert.

    Args:
        root: Wurzelverzeichnis der Arbeitskopie.

    Returns:
        Paare aus relativem Pfad (mit ``/`` als Trenner) und absolutem Pfad. Nicht vorhandene
        Einzeldateien sind enthalten, damit der Bericht sie als ``missing`` ausweisen kann.

    Raises:
        DomainError: ``not_found``, wenn das Korpus-Verzeichnis fehlt.
    """
    corpus = root / REQUIRED_DIRECTORY
    if not corpus.is_dir():
        raise DomainError(
            ErrorCode.NOT_FOUND,
            f"Kein Korpus-Verzeichnis gefunden: {corpus}. "
            "Ohne 'papers/' gibt es nichts zu sichern.",
        )

    found: list[tuple[str, Path]] = []
    for name in SOURCE_DIRECTORIES:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                found.append((path.relative_to(root).as_posix(), path))
    for name in SOURCE_FILES:
        found.append((name, root / name))
    return tuple(found)


def _ensure_target_outside(root: Path, target: Path) -> None:
    """Weist ein Ziel innerhalb der Arbeitskopie zurück (es würde sich selbst sichern)."""
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if resolved_target == resolved_root or resolved_target.is_relative_to(resolved_root):
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            f"Das Sicherungsziel darf nicht innerhalb der Arbeitskopie liegen: {resolved_target}.",
        )


def _write_manifest(target: Path, items: tuple[BackupItem, ...]) -> None:
    """Schreibt den Prüfnachweis binär und atomar (kein CRLF, kein halbfertiger Stand)."""
    payload = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": [item.to_dict() for item in items if item.action != ACTION_MISSING],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    destination = target / BACKUP_MANIFEST_NAME
    tmp_path = destination.with_suffix(destination.suffix + ".tmp")
    try:
        tmp_path.write_bytes(text.encode("utf-8"))
        os.replace(tmp_path, destination)
    finally:
        tmp_path.unlink(missing_ok=True)


def create_backup(
    root: str | Path,
    target: str | Path,
    *,
    dry_run: bool = False,
    progress: ProgressCallback | None = None,
) -> BackupReport:
    """Sichert den nicht reproduzierbaren Teil des Bestandes in ein Zielverzeichnis.

    Der Lauf ist idempotent: Eine Datei, die am Ziel bereits mit identischem sha256 liegt, wird
    übersprungen. ``dry_run`` trifft dieselben Entscheidungen, schreibt aber nichts.

    Args:
        root: Wurzelverzeichnis der Arbeitskopie.
        target: Zielverzeichnis der Sicherung; muss außerhalb von ``root`` liegen.
        dry_run: Wenn wahr, wird nichts geschrieben.
        progress: Optionaler Rückruf für eine Fortschrittsanzeige.

    Returns:
        Die Bilanz mit einem Eintrag je Artefakt des Sicherungsumfangs.

    Raises:
        DomainError: ``not_found`` (kein Korpus-Verzeichnis) oder ``invalid_input``
            (Ziel innerhalb der Arbeitskopie).
    """
    root_path = Path(root)
    target_path = Path(target)
    _ensure_target_outside(root_path, target_path)

    sources = collect_sources(root_path)
    total = len(sources)
    items: list[BackupItem] = []

    for index, (relative, source) in enumerate(sources, start=1):
        if not source.is_file():
            items.append(BackupItem(relative, ACTION_MISSING, "", 0))
        else:
            digest = sha256_of(source)
            size = source.stat().st_size
            destination = target_path / relative
            if destination.is_file() and sha256_of(destination) == digest:
                items.append(BackupItem(relative, ACTION_UNCHANGED, digest, size))
            else:
                if not dry_run:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                items.append(BackupItem(relative, ACTION_COPIED, digest, size))
        if progress is not None:
            progress(relative, index, total)

    frozen = tuple(items)
    if not dry_run:
        target_path.mkdir(parents=True, exist_ok=True)
        _write_manifest(target_path, frozen)
    return BackupReport(root_path, target_path, dry_run, frozen)


def verify_backup(target: str | Path) -> VerificationReport:
    """Rechnet einen vorhandenen Sicherungsstand gegen sein Manifest nach.

    Args:
        target: Zielverzeichnis einer früheren Sicherung.

    Returns:
        Der Befund mit den veränderten und den fehlenden Dateien.

    Raises:
        DomainError: ``not_found``, wenn kein Manifest vorliegt; ``parse_error``, wenn es
            nicht lesbar ist.
    """
    target_path = Path(target)
    manifest = target_path / BACKUP_MANIFEST_NAME
    if not manifest.is_file():
        raise DomainError(
            ErrorCode.NOT_FOUND,
            f"Kein Sicherungsstand gefunden: {manifest} fehlt.",
        )
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainError(
            ErrorCode.PARSE_ERROR,
            f"Das Manifest ist nicht lesbar: {manifest}.",
        ) from exc

    mismatched: list[str] = []
    missing: list[str] = []
    entries = payload.get("files", [])
    for entry in entries:
        relative = str(entry["relative_path"])
        path = target_path / relative
        if not path.is_file():
            missing.append(relative)
        elif sha256_of(path) != entry["sha256"]:
            mismatched.append(relative)
    return VerificationReport(target_path, len(entries), tuple(mismatched), tuple(missing))
