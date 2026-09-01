"""Kuratiertes Relevanzurteil aus der Literaturübersicht (Phase 15 / G4).

Liest die **wertenden** Spalten ``Themenfokus``, ``Relevanz fuer Expose`` und
``SRQ-Zuordnung`` der kuratierten Zeilen aus [Übersicht.md](../../../Übersicht.md) und
überführt sie nach ``metadata/curation.json`` – dem einzigen Ort im Repo, an dem ein
**menschliches** Relevanzurteil steht, das aus keiner anderen Quelle rekonstruierbar ist
(docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md).

Anders als die kuratierten Identifikatoren aus
:mod:`research_graphrag.bibliography.curated` (Herkunft ``curated`` der Zitationskette) ist
dieses Urteil **kein** bibliografischer Datensatz und läuft deshalb nicht in die
``manual > curated > resolved > extracted``-Auflösung ein – es ist ein eigenständiges,
themenfokus-/SRQ-bezogenes Artefakt für die Auswahl in
[Phase 14](../../../Roadmap.md#phase-14--referenz-ernte-externe-verweise-aus-dem-eigenen-bestand).

Das Format ist bewusst **verlustfrei**: Jede kuratierte Zelle wird als Freitext übernommen
(``SRQ-Zuordnung`` zusätzlich als Liste einzelner SRQ-Kennungen), nicht auf eine Kategorie
reduziert – „kein kuratierter Wert geht verloren" ist die Akzeptanzbedingung von G4, nicht nur
eine Empfehlung.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.overview.drafts import DRAFT_ID_PREFIX, column_index, link_column, split_row

SCHEMA_VERSION = "0.1.0"
"""Version des Speicherformats von ``metadata/curation.json``."""

CURATION_DIR = "metadata"
"""Versionierter Ordner, in dem die Datei liegt (Geschwister von ``paper_metadata.json``)."""

CURATION_FILENAME = "curation.json"
"""Dateiname der überführten Relevanzurteile."""

THEMENFOKUS_COLUMN_LABEL = "themenfokus"
RELEVANZ_COLUMN_LABEL = "relevanz fuer expose"
SRQ_COLUMN_LABEL = "srq-zuordnung"
NAME_COLUMN_LABEL = "name"

_DRAFT_ID = re.compile(rf"^{DRAFT_ID_PREFIX}\d+$")


@dataclass(frozen=True)
class CurationEntry:
    """Eine kuratierte Übersichtszeile in maschinenlesbarer Form.

    Attributes:
        row_id: ID der Zeile (Themencluster-Kennung, z. B. ``A3``).
        filename: Dateiname des Papers aus der Spalte ``Interner Link`` (dekodiert).
        title: Inhalt der Spalte ``Name``.
        themenfokus: Wörtlicher Inhalt der Spalte ``Themenfokus``.
        relevanz: Wörtlicher Inhalt der Spalte ``Relevanz fuer Expose``.
        srq: Einzelne SRQ-Kennungen der Spalte ``SRQ-Zuordnung`` (kommagetrennt zerlegt).
    """

    row_id: str
    filename: str
    title: str = ""
    themenfokus: str = ""
    relevanz: str = ""
    srq: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Eintrag für ``metadata/curation.json``."""
        return {
            "row_id": self.row_id,
            "filename": self.filename,
            "title": self.title,
            "themenfokus": self.themenfokus,
            "relevanz": self.relevanz,
            "srq": list(self.srq),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CurationEntry:
        """Rekonstruiert einen Eintrag aus einem JSON-Objekt."""
        return cls(
            row_id=str(data.get("row_id", "")),
            filename=str(data.get("filename", "")),
            title=str(data.get("title", "")),
            themenfokus=str(data.get("themenfokus", "")),
            relevanz=str(data.get("relevanz", "")),
            srq=tuple(str(item) for item in data.get("srq", ())),
        )


def _filename_from_cell(cell: str) -> str:
    """Liest den (dekodierten) Dateinamen aus einer ``[Quelle](papers/…)``-Zelle."""
    match = re.search(r"\]\((.+)\)", cell)
    if not match:
        return ""
    target = match.group(1).strip()
    name = target.split("/", 1)[1] if "/" in target else target
    return unquote(name)


def _split_srq(cell: str) -> tuple[str, ...]:
    """Zerlegt die ``SRQ-Zuordnung``-Zelle in einzelne, getrimmte Kennungen."""
    return tuple(part.strip() for part in cell.split(",") if part.strip())


def parse_curation_rows(markdown: str) -> dict[str, CurationEntry]:
    """Liest die kuratierten Relevanzurteile der Übersicht (Dateiname → Eintrag).

    Args:
        markdown: Inhalt der Übersichtsdatei.

    Returns:
        Die kuratierten Einträge je Dateiname; Entwurfszeilen (``Z…``) und Zeilen ohne internen
        Link werden übersprungen. Ohne erkennbaren Tabellenkopf ist das Ergebnis leer.
    """
    internal = link_column(markdown)
    if internal is None:
        return {}
    themenfokus_col = column_index(markdown, THEMENFOKUS_COLUMN_LABEL)
    relevanz_col = column_index(markdown, RELEVANZ_COLUMN_LABEL)
    srq_col = column_index(markdown, SRQ_COLUMN_LABEL)
    name_col = column_index(markdown, NAME_COLUMN_LABEL)

    entries: dict[str, CurationEntry] = {}
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = split_row(line)
        if internal >= len(cells):
            continue
        row_id = cells[0].strip()
        if not row_id or _DRAFT_ID.match(row_id) or row_id.lower() == "id":
            continue
        filename = _filename_from_cell(cells[internal])
        if not filename:
            continue
        entries[filename] = CurationEntry(
            row_id=row_id,
            filename=filename,
            title=(
                " ".join(cells[name_col].split())
                if name_col is not None and name_col < len(cells)
                else ""
            ),
            themenfokus=(
                cells[themenfokus_col].strip()
                if themenfokus_col is not None and themenfokus_col < len(cells)
                else ""
            ),
            relevanz=(
                cells[relevanz_col].strip()
                if relevanz_col is not None and relevanz_col < len(cells)
                else ""
            ),
            srq=(
                _split_srq(cells[srq_col]) if srq_col is not None and srq_col < len(cells) else ()
            ),
        )
    return entries


def load_curation_rows(path: str | Path) -> dict[str, CurationEntry]:
    """Liest die kuratierten Einträge aus einer Übersichtsdatei (fehlende Datei ⇒ leer)."""
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    return parse_curation_rows(file_path.read_text(encoding="utf-8"))


def migrate_from_overview(
    entries: dict[str, CurationEntry], paper_ids_by_filename: dict[str, str]
) -> dict[str, CurationEntry]:
    """Bildet die kuratierten Einträge auf ``paper_id`` als Schlüssel ab.

    Args:
        entries: Ergebnis von :func:`parse_curation_rows`.
        paper_ids_by_filename: Zuordnung Dateiname → ``paper_id`` (aus den Canonical-Papern).

    Returns:
        Einträge je ``paper_id``; Zeilen ohne zuordenbares Korpus-Paper werden ausgelassen (mit
        einem Befund im aufrufenden Skript, nicht stillschweigend).
    """
    return {
        paper_id: entry
        for filename, entry in entries.items()
        if (paper_id := paper_ids_by_filename.get(filename)) is not None
    }


def curation_path(root: str | Path = ".") -> Path:
    """Liefert den Pfad zur Kurations-Datei unterhalb eines Repository-Wurzelverzeichnisses."""
    return Path(root) / CURATION_DIR / CURATION_FILENAME


def load_curation(path: str | Path) -> dict[str, CurationEntry]:
    """Liest ``metadata/curation.json`` (fehlende Datei ⇒ leer).

    Raises:
        DomainError: ``parse_error`` bei defektem JSON; ``constraint_violation`` bei
            unbekannter Schema-Version oder unerwarteter Struktur (siehe docs/error-model.md).
    """
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DomainError(
            ErrorCode.PARSE_ERROR, f"Kurationsdatei nicht lesbar: {file_path} ({exc})"
        ) from exc
    if not isinstance(payload, dict):
        raise DomainError(ErrorCode.CONSTRAINT_VIOLATION, "Kurationsdatei ist kein Objekt.")
    version = str(payload.get("schema_version", ""))
    if version != SCHEMA_VERSION:
        raise DomainError(
            ErrorCode.CONSTRAINT_VIOLATION,
            f"Unerwartete Schema-Version {version!r} (erwartet {SCHEMA_VERSION!r}).",
        )
    papers = payload.get("papers", {})
    if not isinstance(papers, dict):
        raise DomainError(ErrorCode.CONSTRAINT_VIOLATION, "Feld 'papers' ist kein Objekt.")

    result: dict[str, CurationEntry] = {}
    for paper_id, entry in papers.items():
        if not isinstance(entry, Mapping):
            raise DomainError(ErrorCode.CONSTRAINT_VIOLATION, f"Defekter Datensatz bei {paper_id}.")
        result[str(paper_id)] = CurationEntry.from_dict(entry)
    return result


def save_curation(entries_by_paper_id: dict[str, CurationEntry], path: str | Path) -> int:
    """Schreibt die Relevanzurteile deterministisch und atomar.

    Args:
        entries_by_paper_id: Einträge, geschlüsselt über ``paper_id``.
        path: Zielpfad; der Elternordner wird angelegt.

    Returns:
        Anzahl der geschriebenen Datensätze.
    """
    document = {
        "schema_version": SCHEMA_VERSION,
        "papers": {paper_id: entry.to_dict() for paper_id, entry in entries_by_paper_id.items()},
    }
    text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_name(file_path.name + ".tmp")
    try:
        # write_bytes statt write_text: verhindert die Windows-Umsetzung von \n auf \r\n und
        # hält die Datei damit über Plattformen hinweg byte-identisch.
        tmp_path.write_bytes(text.encode("utf-8"))
        os.replace(tmp_path, file_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return len(entries_by_paper_id)
