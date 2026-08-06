"""Intra-Korpus-Zitationsgraph (CITES) – deterministisch & offline (Phase 7 / A2).

Baut aus den Canonical-Papers **gerichtete** ``CITES``-Kanten **innerhalb des eigenen Korpus**:
Für jedes Paper wird der Text seiner **Referenz-Sektion** (Sektionen mit ``kind = references``,
Heuristik aus Phase 2) gegen die korpuseigenen **Identifikatoren** (DOI/arXiv, sofern auf der
eigenen Titelseite belegt) und **Titel** (Dateiname-Stamm aus ``source_uri``) abgeglichen.
Präzedenz **DOI > arXiv > Titel**; Selbstzitate werden ausgeschlossen. Persistiert wird
**additiv** in die bestehende SQLite-Index-Datei (Tabelle ``citation_edges`` + versioniertes
Teilschema). Grundsatz und Grenzen (kein tiefes Referenz-Parsing, Präzision vor Recall):
docs/adr/0011-intra-corpus-citation-graph-phase7.md.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SECTION_KIND_REFERENCES, CanonicalPaper

CITATION_SCHEMA_VERSION = "0.1.0"
"""Version des Zitations-Teilschemas in ``index.sqlite`` (für spätere Migrationen)."""

MIN_TITLE_WORDS = 5
"""Mindestwortzahl eines Titels für das (konservative) Titel-Matching."""

MIN_TITLE_CHARS = 30
"""Mindestlänge (Zeichen) eines normalisierten Titels für das Titel-Matching."""

TITLE_PAGE_PAGES = 2
"""Seiten, die als Frontmatter gelten (Beleg-Fenster für die eigenen Identifikatoren)."""

# Präzedenz der Match-Methoden (kleiner = präziser); bestimmt die gespeicherte ``method``.
_METHOD_RANK = {"doi": 0, "arxiv": 1, "title": 2}

_CITATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
DROP TABLE IF EXISTS citation_edges;
CREATE TABLE citation_edges (
    source_paper_id TEXT NOT NULL,
    target_paper_id TEXT NOT NULL,
    method          TEXT NOT NULL,
    PRIMARY KEY (source_paper_id, target_paper_id)
);
"""


@dataclass(frozen=True)
class CitationBuildReport:
    """Zählwerte eines Zitationsgraph-Baus."""

    n_edges: int
    n_papers_with_refs: int


@dataclass(frozen=True)
class CitationEdge:
    """Eine gerichtete ``CITES``-Kante (``source`` zitiert ``target``) samt Match-Methode."""

    source_paper_id: str
    target_paper_id: str
    method: str

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Kante."""
        return {
            "source_paper_id": self.source_paper_id,
            "target_paper_id": self.target_paper_id,
            "method": self.method,
        }


@dataclass(frozen=True)
class CitationView:
    """Read-only-Sicht auf die Zitationen eines Papers (ausgehend + eingehend)."""

    paper_id: str
    cites: tuple[CitationEdge, ...]
    cited_by: tuple[CitationEdge, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Sicht (``cites`` = zitiert; ``cited_by`` = wird zitiert von)."""
        return {
            "paper_id": self.paper_id,
            "cites": [edge.to_dict() for edge in self.cites],
            "cited_by": [edge.to_dict() for edge in self.cited_by],
        }


def normalize_title(text: str) -> str:
    """Normalisiert Text für das Titel-Matching (Kleinschreibung, nur alphanumerische Token).

    Öffentlich, weil der Korpus-Intake (docs/adr/0019-corpus-intake-new-papers-phase8.md)
    exakt dieselbe Normalisierung für seine Titel-Verdachtsstufe verwendet.
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def title_from_uri(source_uri: str) -> str:
    """Leitet den Paper-Titel aus einer ``source_uri`` ab (Dateiname-Stamm, URL-dekodiert).

    Öffentlich, weil auch der Online-Modus einen Titel benötigt, dort aber nur die ``source_uri``
    aus dem Index vorliegt (docs/adr/0020-online-candidate-search-phase9.md).

    Args:
        source_uri: Quellverweis eines Papers.

    Returns:
        Den Dateinamen ohne Pfad und ohne ``.pdf``-Endung.
    """
    name = unquote(source_uri.rsplit("/", 1)[-1])
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return name


def title_of(paper: CanonicalPaper) -> str:
    """Leitet den Paper-Titel aus der ``source_uri`` ab (Dateiname-Stamm, URL-dekodiert)."""
    return title_from_uri(paper.source_uri)


def _reference_section_ids(paper: CanonicalPaper) -> set[str]:
    """Liefert die IDs der heuristisch erkannten Referenz-Sektionen eines Papers."""
    return {
        section.section_id for section in paper.sections if section.kind == SECTION_KIND_REFERENCES
    }


def _reference_text(paper: CanonicalPaper) -> str:
    """Sammelt den Text der Referenz-Sektion(en) eines Papers (leer, wenn keine erkannt)."""
    ref_ids = _reference_section_ids(paper)
    if not ref_ids:
        return ""
    return "\n".join(chunk.text for chunk in paper.chunks if chunk.section_id in ref_ids)


def front_matter_text(paper: CanonicalPaper) -> str:
    """Liefert den Text der Titelseite(n) **ohne** Referenzabschnitt (klein geschrieben).

    Beleg-Fenster für die eigenen Identifikatoren: Die Extraktion liest DOI/arXiv bevorzugt von
    der Titelseite, fällt aber auf den Volltext zurück; dabei kann eine **zitierte** fremde ID
    als eigene erfasst werden. Solche Werte würden hier massenhaft falsche Kanten erzeugen (der
    falsche Wert steht in vielen Referenzlisten), deshalb wird die Bibliografie ausgeschlossen
    (Präzision vor Recall, docs/adr/0011-intra-corpus-citation-graph-phase7.md).

    Seit der Seiten-Range (docs/adr/0013-chunking-refinement-phase7.md) zählt bewusst
    ``page_end``: Ein Chunk, der von der Titelseite auf eine Folgeseite überläuft, gilt **nicht**
    mehr als Frontmatter – das Fenster bleibt damit mindestens so streng wie zuvor.

    Öffentlich, weil die Herkunftsbewertung der bibliografischen Daten denselben Guard nutzt
    (docs/adr/0025-citable-paper-metadata.md).
    """
    ref_ids = _reference_section_ids(paper)
    return " ".join(
        chunk.text
        for chunk in paper.chunks
        if chunk.page_end <= TITLE_PAGE_PAGES and chunk.section_id not in ref_ids
    ).lower()


def _unique(papers: Sequence[CanonicalPaper]) -> list[CanonicalPaper]:
    """Filtert auf eindeutige Paper (per ``paper_id``), stabil nach ``paper_id`` sortiert."""
    seen: set[str] = set()
    unique: list[CanonicalPaper] = []
    for paper in sorted(papers, key=lambda item: item.paper_id):
        if paper.paper_id in seen:
            continue
        seen.add(paper.paper_id)
        unique.append(paper)
    return unique


def _consider(matches: dict[str, str], target: str, method: str) -> None:
    """Vermerkt einen Treffer und behält je Ziel die **präziseste** Methode."""
    if target not in matches or _METHOD_RANK[method] < _METHOD_RANK[matches[target]]:
        matches[target] = method


def _build_target_maps(
    papers: Sequence[CanonicalPaper],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Baut die Ziel-Maps (DOI/arXiv/Titel → ``paper_id``) aus dem Korpus.

    DOI/arXiv werden nur übernommen, wenn sie im Frontmatter des jeweiligen Papers belegt sind
    (siehe :func:`_front_matter_text`); Titel gelten erst ab einer Mindestlänge.
    """
    doi_to_pid: dict[str, str] = {}
    arxiv_to_pid: dict[str, str] = {}
    title_to_pid: dict[str, str] = {}
    for paper in papers:
        front = front_matter_text(paper)
        doi = paper.identifiers.get("doi")
        if doi and doi.lower() in front:
            doi_to_pid.setdefault(doi.lower(), paper.paper_id)
        arxiv = paper.identifiers.get("arxiv")
        if arxiv and arxiv.lower() in front:
            arxiv_to_pid.setdefault(arxiv.lower(), paper.paper_id)
        title_norm = normalize_title(title_of(paper))
        if len(title_norm) >= MIN_TITLE_CHARS and len(title_norm.split()) >= MIN_TITLE_WORDS:
            title_to_pid.setdefault(title_norm, paper.paper_id)
    return doi_to_pid, arxiv_to_pid, title_to_pid


def build_citation_graph(
    papers: Sequence[CanonicalPaper], db_path: str | Path
) -> CitationBuildReport:
    """Baut den Intra-Korpus-Zitationsgraphen und persistiert ihn **additiv**.

    Die Tabelle ``citation_edges`` wird voll neu gebaut (zuvor verworfen); der übrige Index
    (``papers``/``chunks``/``graph_*``) bleibt unangetastet.

    Args:
        papers: Extrahierte Canonical-Papers (Quelle für Referenztext und Identifikatoren).
        db_path: Pfad zur SQLite-Index-Datei; Elternordner wird angelegt.

    Returns:
        Ein :class:`CitationBuildReport` mit Kanten- und Referenz-Paper-Zahl.
    """
    unique = _unique(papers)
    doi_to_pid, arxiv_to_pid, title_to_pid = _build_target_maps(unique)

    edges: dict[tuple[str, str], str] = {}
    n_with_refs = 0
    for source in unique:
        reference_text = _reference_text(source)
        if not reference_text:
            continue
        n_with_refs += 1
        ref_lower = reference_text.lower()
        ref_norm = normalize_title(reference_text)

        matches: dict[str, str] = {}
        for doi, target in doi_to_pid.items():
            if target != source.paper_id and doi in ref_lower:
                _consider(matches, target, "doi")
        for arxiv, target in arxiv_to_pid.items():
            if target != source.paper_id and arxiv in ref_lower:
                _consider(matches, target, "arxiv")
        for title_norm, target in title_to_pid.items():
            if target != source.paper_id and title_norm in ref_norm:
                _consider(matches, target, "title")

        for target, method in matches.items():
            edges[(source.paper_id, target)] = method

    edge_list = sorted((src, tgt, method) for (src, tgt), method in edges.items())
    _persist_citations(db_path, edge_list)
    return CitationBuildReport(n_edges=len(edge_list), n_papers_with_refs=n_with_refs)


def _persist_citations(db_path: str | Path, edges: list[tuple[str, str, str]]) -> None:
    """Schreibt die Zitationskanten deterministisch (additiv) in die Index-Datei."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(_CITATION_SCHEMA)
        connection.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('citation_schema_version', ?)",
            (CITATION_SCHEMA_VERSION,),
        )
        for source, target, method in edges:
            connection.execute(
                "INSERT INTO citation_edges (source_paper_id, target_paper_id, method) "
                "VALUES (?, ?, ?)",
                (source, target, method),
            )
        connection.commit()
    finally:
        connection.close()


def load_citations(db_path: str | Path, paper_id: str) -> CitationView:
    """Lädt die Zitationen eines Papers (read-only): wen es zitiert und wer es zitiert.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        paper_id: Ziel-Paper (nicht leer).

    Returns:
        Eine :class:`CitationView`; ``cites``/``cited_by`` können leer sein.

    Raises:
        DomainError: ``invalid_input`` bei leerer ``paper_id`` (vor dem Index geprüft);
            ``not_found`` wenn die Index-Datei fehlt oder das Paper unbekannt ist;
            ``constraint_violation`` wenn kein Zitationsgraph gebaut wurde
            (siehe docs/error-model.md).
    """
    if not paper_id.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leere paper_id.")
    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")

    connection = sqlite3.connect(str(path))
    try:
        has_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'citation_edges'"
        ).fetchone()
        if has_table is None:
            raise DomainError(
                ErrorCode.CONSTRAINT_VIOLATION,
                "Kein Zitationsgraph im Index (Phase 7/A2 nicht gebaut?).",
            )
        exists = connection.execute(
            "SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        if exists is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"Paper nicht im Index: {paper_id}")
        cites_rows = connection.execute(
            "SELECT source_paper_id, target_paper_id, method FROM citation_edges "
            "WHERE source_paper_id = ? ORDER BY target_paper_id",
            (paper_id,),
        ).fetchall()
        cited_rows = connection.execute(
            "SELECT source_paper_id, target_paper_id, method FROM citation_edges "
            "WHERE target_paper_id = ? ORDER BY source_paper_id",
            (paper_id,),
        ).fetchall()
    finally:
        connection.close()

    cites = tuple(CitationEdge(str(s), str(t), str(m)) for s, t, m in cites_rows)
    cited_by = tuple(CitationEdge(str(s), str(t), str(m)) for s, t, m in cited_rows)
    return CitationView(paper_id=paper_id, cites=cites, cited_by=cited_by)
