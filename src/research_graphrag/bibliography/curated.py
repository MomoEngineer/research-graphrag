"""Kuratierte Identifikatoren aus der Literaturübersicht (Phase 12 / K1).

Liest die Spalten ``Name``, ``Interner Link`` und ``Externer Link/Indetifikator`` der kuratierten
[Übersicht.md](../../../Übersicht.md) und macht sie als Metadaten-Datensätze der Herkunft
``curated`` verfügbar.

**Nur kuratierte Zeilen zählen.** Entwurfszeilen der ID-Reihe ``Z1``, ``Z2``, … stammen aus
:func:`research_graphrag.overview.drafts.build_draft_row` und tragen dort exakt die extrahierten
Identifikatoren – sie als eigene Quelle zu werten, wäre eine Scheinbestätigung derselben
Regex-Ausgabe (docs/adr/0025-citable-paper-metadata.md, Punkt 2).

Gemessene Ausgangslage (341 Paper, 2026-08-05): 129 der 131 kuratierten Zeilen tragen eine
externe Angabe, und **29** davon weichen von der Extraktion ab – teils legitim (Publisher-DOI
statt arXiv-ID), teils als echter Extraktionsfehler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    ORIGIN_CURATED,
    MetadataRecord,
)
from research_graphrag.overview.drafts import DRAFT_ID_PREFIX, column_index, link_column, split_row

EXTERNAL_COLUMN_LABEL = "externer link"
"""Kleingeschriebener Anfang der Kopfzelle der Identifikator-Spalte (Tippfehler im Original)."""

NAME_COLUMN_LABEL = "name"
"""Kopfzelle der Titel-Spalte."""

ARXIV_DOI_PREFIX = "10.48550/arxiv."
"""DataCite-DOI-Präfix von arXiv – daraus lässt sich die arXiv-ID direkt ableiten."""

_LINK_TARGET = re.compile(r"\]\((.+?)\)")
_DRAFT_ID = re.compile(rf"^{DRAFT_ID_PREFIX}\d+$")
_DOI_URL = re.compile(r"^https?://(?:dx\.)?doi\.org/(.+)$", re.IGNORECASE)
_ARXIV_URL = re.compile(r"^https?://arxiv\.org/(?:abs|pdf)/([^\s?#]+)$", re.IGNORECASE)
_BARE_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_ARXIV_VERSION = re.compile(r"v\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class CuratedEntry:
    """Eine kuratierte Übersichtszeile in maschinenlesbarer Form.

    Attributes:
        row_id: ID der Zeile (Themencluster-Kennung, z. B. ``A3``).
        filename: Dateiname des Papers aus der Spalte ``Interner Link`` (dekodiert).
        title: Inhalt der Spalte ``Name``.
        doi: DOI ohne URL-Präfix, sonst leer.
        arxiv_id: arXiv-Identifikator ohne Version, sonst leer.
        url: Sonstiger Link (z. B. OpenReview), sonst leer.
    """

    row_id: str
    filename: str
    title: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""

    def has_identifier(self) -> bool:
        """``True``, wenn mindestens ein extern auflösbarer Wert vorliegt."""
        return bool(self.doi or self.arxiv_id or self.url)


def _filename_from_cell(cell: str) -> str:
    """Liest den (dekodierten) Dateinamen aus einer ``[Quelle](papers/…)``-Zelle."""
    match = re.search(r"\]\((.+)\)", cell)
    if not match:
        return ""
    target = match.group(1).strip()
    name = target.split("/", 1)[1] if "/" in target else target
    return unquote(name)


def parse_identifier(cell: str) -> tuple[str, str, str]:
    """Zerlegt die Identifikator-Zelle in ``(doi, arxiv_id, url)``.

    Erkannt werden Markdown-Links auf ``doi.org``/``arxiv.org``, sonstige ``http(s)``-Links und
    ein roh notierter DOI. Platzhalter wie ``(zu ergänzen)`` liefern drei leere Werte. Ein
    arXiv-DataCite-DOI (:data:`ARXIV_DOI_PREFIX`) füllt **beide** Identifikator-Felder.
    """
    targets = [match.strip() for match in _LINK_TARGET.findall(cell)]
    if not targets:
        bare = cell.strip()
        targets = [bare] if _BARE_DOI.match(bare) else []

    doi = ""
    arxiv_id = ""
    url = ""
    for target in targets:
        doi_match = _DOI_URL.match(target)
        arxiv_match = _ARXIV_URL.match(target)
        if doi_match:
            doi = doi or doi_match.group(1).strip()
        elif arxiv_match:
            arxiv_id = arxiv_id or _ARXIV_VERSION.sub("", arxiv_match.group(1).strip())
        elif _BARE_DOI.match(target):
            doi = doi or target
        elif target.lower().startswith(("http://", "https://")):
            url = url or target

    if doi and not arxiv_id and doi.lower().startswith(ARXIV_DOI_PREFIX):
        arxiv_id = _ARXIV_VERSION.sub("", doi[len(ARXIV_DOI_PREFIX) :])
    return doi, arxiv_id, url


def parse_curated(markdown: str) -> dict[str, CuratedEntry]:
    """Liest die kuratierten Zeilen der Übersicht (Dateiname → Eintrag).

    Args:
        markdown: Inhalt der Übersichtsdatei.

    Returns:
        Die kuratierten Einträge je Dateiname; Entwurfszeilen (``Z…``) und Zeilen ohne internen
        Link werden übersprungen. Ohne erkennbaren Tabellenkopf ist das Ergebnis leer.
    """
    internal = link_column(markdown)
    external = column_index(markdown, EXTERNAL_COLUMN_LABEL)
    name_column = column_index(markdown, NAME_COLUMN_LABEL)
    if internal is None:
        return {}

    entries: dict[str, CuratedEntry] = {}
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
        doi, arxiv_id, url = ("", "", "")
        if external is not None and external < len(cells):
            doi, arxiv_id, url = parse_identifier(cells[external])
        title = ""
        if name_column is not None and name_column < len(cells):
            title = " ".join(cells[name_column].split())
        entries[filename] = CuratedEntry(
            row_id=row_id,
            filename=filename,
            title=title,
            doi=doi,
            arxiv_id=arxiv_id,
            url=url,
        )
    return entries


def load_curated(path: str | Path) -> dict[str, CuratedEntry]:
    """Liest die kuratierten Einträge aus einer Übersichtsdatei (fehlende Datei ⇒ leer)."""
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    return parse_curated(file_path.read_text(encoding="utf-8"))


def records_from_curated(
    entries: dict[str, CuratedEntry], paper_ids_by_filename: dict[str, str]
) -> tuple[MetadataRecord, ...]:
    """Bildet die kuratierten Einträge auf Metadaten-Datensätze ab.

    Args:
        entries: Ergebnis von :func:`parse_curated`.
        paper_ids_by_filename: Zuordnung Dateiname → ``paper_id`` (aus dem Index).

    Returns:
        Datensätze der Herkunft ``curated`` für alle Einträge, die einem Korpus-Paper zugeordnet
        werden können **und** einen Titel oder Identifikator tragen.
    """
    records: list[MetadataRecord] = []
    for filename, entry in sorted(entries.items()):
        paper_id = paper_ids_by_filename.get(filename)
        if paper_id is None or not (entry.has_identifier() or entry.title):
            continue
        records.append(
            MetadataRecord(
                paper_id=paper_id,
                origin=ORIGIN_CURATED,
                title=entry.title,
                doi=entry.doi,
                arxiv_id=entry.arxiv_id,
                url=entry.url,
                confidence=CONFIDENCE_STRONG,
                evidence=f"Übersicht.md Zeile {entry.row_id}",
            )
        )
    return tuple(records)
