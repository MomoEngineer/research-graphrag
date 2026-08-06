"""Bibliografische Metadaten im Index (Phase 12 / K1).

Führt die vier Herkünfte aus docs/adr/0025-citable-paper-metadata.md zu **einem** zitierfähigen
Datensatz je Paper zusammen und legt ihn **additiv** als Tabelle ``paper_metadata`` in der
Index-Datei ab:

1. ``extracted`` – DOI/arXiv aus der Extraktion, Titel aus dem Dateinamen.
2. ``curated`` – Identifikator und Name aus den kuratierten Zeilen der Übersicht.
3. ``resolved`` / ``manual`` – aus der versionierten Datei ``metadata/paper_metadata.json``.

Der Bau läuft im **selben atomaren Fenster** wie Index, Ähnlichkeits- und Zitationsgraph
(docs/adr/0010-drop-in-workflow-and-qa-phase6.md); das Kern-Schema aus
:mod:`research_graphrag.indexing.tfidf_index` bleibt unverändert und die Tabelle trägt eine
eigene Teilschema-Version (Muster von ``graph_schema_version``/``citation_schema_version``).

Damit ist der Index die **einzige** Lesequelle des Retrievals: Kein Werkzeug liest zur
Abfragezeit Markdown oder JSON.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.bibliography.curated import load_curated, records_from_curated
from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_CURATED,
    ORIGIN_EXTRACTED,
    ORIGIN_MANUAL,
    ORIGIN_RESOLVED,
    MetadataRecord,
    PaperMetadata,
    empty_metadata,
)
from research_graphrag.bibliography.resolve import resolve_all
from research_graphrag.bibliography.store import load_records
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper
from research_graphrag.indexing.citation_graph import front_matter_text, title_from_uri, title_of

METADATA_SCHEMA_VERSION = "0.1.0"
"""Version des Teilschemas ``paper_metadata`` (additiv, unabhängig vom Kern-Schema)."""

_ARXIV_ID = re.compile(r"^(\d{2})(\d{2})\.\d{4,5}$")
_ARXIV_EPOCH = 2000

_METADATA_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
DROP TABLE IF EXISTS paper_metadata;
CREATE TABLE paper_metadata (
    paper_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT '',
    authors      TEXT NOT NULL DEFAULT '[]',
    year         INTEGER NOT NULL DEFAULT 0,
    venue        TEXT NOT NULL DEFAULT '',
    doi          TEXT NOT NULL DEFAULT '',
    arxiv_id     TEXT NOT NULL DEFAULT '',
    url          TEXT NOT NULL DEFAULT '',
    origins      TEXT NOT NULL DEFAULT '{}',
    confidence   TEXT NOT NULL DEFAULT 'none',
    citation_key TEXT NOT NULL DEFAULT ''
);
"""


@dataclass(frozen=True)
class MetadataBuildReport:
    """Zählwerte eines Metadaten-Baus."""

    n_papers: int
    n_with_identifier: int
    n_citable: int
    n_curated: int
    n_resolved: int
    n_manual: int
    n_weak: int


def year_from_arxiv(arxiv_id: str) -> int:
    """Leitet das Jahr des Preprints aus einer arXiv-ID ab (``2503.06689`` → ``2025``).

    Gilt nur für das seit 2007 verwendete Format ``JJMM.NNNNN``; alles andere liefert ``0``.
    Das ist eine **deterministische lokale** Näherung – der Publikationsjahrgang der
    begutachteten Fassung kann abweichen und wird von der Online-Auflösung überschrieben.
    """
    match = _ARXIV_ID.match(arxiv_id.strip())
    if not match:
        return 0
    year = _ARXIV_EPOCH + int(match.group(1))
    month = int(match.group(2))
    if not 1 <= month <= 12:
        return 0
    return year


def extracted_records(papers: Sequence[CanonicalPaper]) -> tuple[MetadataRecord, ...]:
    """Bildet die Extraktion auf Metadaten-Datensätze ab (Herkunft ``extracted``).

    Die Konfidenz folgt demselben Guard wie der Zitationsgraph: Ein Identifikator zählt nur als
    belegt, wenn er auf der eigenen Titelseite steht **und** im Korpus eindeutig ist. Andernfalls
    bleibt der Datensatz erhalten, wird aber als ``weak`` ausgewiesen – gemessen betrifft das
    rund 45 der 341 Paper (docs/adr/0025-citable-paper-metadata.md, Befund 2).
    """
    carriers: Counter[str] = Counter()
    for paper in papers:
        for value in paper.identifiers.values():
            carriers[value.lower()] += 1

    records: list[MetadataRecord] = []
    for paper in sorted(papers, key=lambda item: item.paper_id):
        identifiers = dict(paper.identifiers)
        doi = identifiers.get("doi", "")
        arxiv_id = identifiers.get("arxiv", "")
        front = front_matter_text(paper) if identifiers else ""
        unbacked = [value for value in identifiers.values() if value.lower() not in front]
        ambiguous = [value for value in identifiers.values() if carriers[value.lower()] > 1]

        if not identifiers:
            confidence, evidence = CONFIDENCE_STRONG, "kein Identifikator im PDF gefunden"
        elif unbacked:
            confidence = CONFIDENCE_WEAK
            evidence = f"nicht auf der Titelseite belegt: {', '.join(sorted(unbacked))}"
        elif ambiguous:
            confidence = CONFIDENCE_WEAK
            evidence = f"im Korpus mehrfach vergeben: {', '.join(sorted(ambiguous))}"
        else:
            confidence, evidence = CONFIDENCE_STRONG, "auf der Titelseite belegt"

        records.append(
            MetadataRecord(
                paper_id=paper.paper_id,
                origin=ORIGIN_EXTRACTED,
                title=title_of(paper),
                year=year_from_arxiv(arxiv_id),
                doi=doi,
                arxiv_id=arxiv_id,
                confidence=confidence,
                evidence=evidence,
            )
        )
    return tuple(records)


def collect_records(
    papers: Sequence[CanonicalPaper],
    *,
    overview_path: str | Path | None = None,
    metadata_file: str | Path | None = None,
) -> tuple[MetadataRecord, ...]:
    """Sammelt die Datensätze aller Herkünfte für den Metadaten-Bau.

    Args:
        papers: Extrahierte Canonical-Papers.
        overview_path: Pfad der kuratierten Übersicht; ``None`` überspringt die Herkunft
            ``curated``.
        metadata_file: Pfad der versionierten Metadatendatei; ``None`` überspringt ``resolved``
            und ``manual``.

    Returns:
        Alle Datensätze in beliebiger Reihenfolge (die Auflösung sortiert selbst).
    """
    records: list[MetadataRecord] = list(extracted_records(papers))
    known_ids = {paper.paper_id for paper in papers}

    if overview_path is not None:
        by_filename = {
            f"{title_from_uri(paper.source_uri)}.pdf": paper.paper_id for paper in papers
        }
        records.extend(records_from_curated(load_curated(overview_path), by_filename))

    if metadata_file is not None:
        records.extend(
            record for record in load_records(metadata_file) if record.paper_id in known_ids
        )
    return tuple(records)


def build_metadata_index(
    papers: Sequence[CanonicalPaper],
    db_path: str | Path,
    *,
    overview_path: str | Path | None = None,
    metadata_file: str | Path | None = None,
) -> MetadataBuildReport:
    """Baut die Tabelle ``paper_metadata`` und persistiert sie **additiv**.

    Args:
        papers: Extrahierte Canonical-Papers (Reihenfolge unerheblich).
        db_path: Pfad der Index-Datei (muss existieren; die Kern-Tabellen sind bereits gebaut).
        overview_path: Pfad der kuratierten Übersicht (optional).
        metadata_file: Pfad der versionierten Metadatendatei (optional).

    Returns:
        Einen :class:`MetadataBuildReport` mit den Zählwerten des Laufs.

    Raises:
        DomainError: ``not_found``, wenn die Index-Datei fehlt (siehe docs/error-model.md);
            ``parse_error``/``constraint_violation`` aus dem Lesen der Metadatendatei.
    """
    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")

    records = collect_records(papers, overview_path=overview_path, metadata_file=metadata_file)
    paper_ids = sorted({paper.paper_id for paper in papers})
    resolved = resolve_all(records, paper_ids)
    _persist_metadata(path, resolved)

    origins = Counter(record.origin for record in records)
    return MetadataBuildReport(
        n_papers=len(paper_ids),
        n_with_identifier=sum(1 for item in resolved.values() if item.identifiers),
        n_citable=sum(1 for item in resolved.values() if item.is_citable()),
        n_curated=origins[ORIGIN_CURATED],
        n_resolved=origins[ORIGIN_RESOLVED],
        n_manual=origins[ORIGIN_MANUAL],
        n_weak=sum(1 for item in resolved.values() if item.confidence == CONFIDENCE_WEAK),
    )


def _persist_metadata(db_path: Path, resolved: Mapping[str, PaperMetadata]) -> None:
    """Schreibt die aufgelösten Datensätze (voller Neubau der Tabelle)."""
    connection = sqlite3.connect(str(db_path))
    try:
        connection.executescript(_METADATA_SCHEMA)
        connection.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('metadata_schema_version', ?)",
            (METADATA_SCHEMA_VERSION,),
        )
        for paper_id in sorted(resolved):
            item = resolved[paper_id]
            connection.execute(
                "INSERT INTO paper_metadata (paper_id, title, authors, year, venue, doi, "
                "arxiv_id, url, origins, confidence, citation_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.paper_id,
                    item.title,
                    json.dumps(list(item.authors), ensure_ascii=False),
                    item.year,
                    item.venue,
                    item.doi,
                    item.arxiv_id,
                    item.url,
                    json.dumps(dict(item.origins), ensure_ascii=False, sort_keys=True),
                    item.confidence,
                    item.citation_key(),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _row_to_metadata(row: Sequence[Any]) -> PaperMetadata:
    """Bildet eine Tabellenzeile auf einen :class:`PaperMetadata` ab."""
    return PaperMetadata(
        paper_id=str(row[0]),
        title=str(row[1]),
        authors=tuple(str(name) for name in json.loads(str(row[2]))),
        year=int(row[3]),
        venue=str(row[4]),
        doi=str(row[5]),
        arxiv_id=str(row[6]),
        url=str(row[7]),
        origins={str(key): str(value) for key, value in json.loads(str(row[8])).items()},
        confidence=str(row[9]),
    )


def load_paper_metadata(db_path: str | Path) -> dict[str, PaperMetadata]:
    """Lädt alle bibliografischen Datensätze aus dem Index (leer, wenn die Tabelle fehlt).

    Ein fehlendes Teilschema ist **kein** Fehler: Ein vor Phase 12 gebauter Index bleibt
    lesbar, die Werkzeuge liefern dann lediglich keine Zitationsdaten.
    """
    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")
    connection = sqlite3.connect(str(path))
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'paper_metadata'"
        ).fetchone()
        if exists is None:
            return {}
        rows = connection.execute(
            "SELECT paper_id, title, authors, year, venue, doi, arxiv_id, url, origins, "
            "confidence FROM paper_metadata"
        ).fetchall()
    finally:
        connection.close()
    return {str(row[0]): _row_to_metadata(row) for row in rows}


def metadata_for(db_path: str | Path, paper_id: str) -> PaperMetadata:
    """Lädt den Datensatz **eines** Papers (unbekannt ⇒ leerer Datensatz)."""
    return load_paper_metadata(db_path).get(paper_id, empty_metadata(paper_id))
