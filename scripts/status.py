"""CLI: Read-only-Status von Index, Korpus und Artefakt-Konsistenz (Phase 6).

Zeigt auf einen Blick, ob die Drop-in-Artefakte konsistent sind: Index-Schema und
-Kennzahlen (Paper/Chunks/Communities/Zitationskanten), Qualitäts-Flags, Manifest-/
Identifier-Abdeckung sowie einen Konsistenz-Check zwischen ``papers/``, ``manifest.json``
und ``canonical/``. Rein **lesend** – es wird kein TF-IDF-Raum rekonstruiert und nichts
geschrieben. Dient der pragmatischen Qualitätssicherung (siehe
docs/adr/0010-drop-in-workflow-and-qa-phase6.md).

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.status
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from research_graphrag.extraction.refstub import STUB_SUFFIX

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA = _REPO_ROOT / "data"
_DEFAULT_PAPERS = _REPO_ROOT / "papers"

_PREVIEW = 5
"""Maximale Zahl beispielhaft gezeigter Einträge je Inkonsistenz-Gruppe."""


@dataclass(frozen=True)
class StatusReport:
    """Zusammengetragene, read-only Status-Kennzahlen der Drop-in-Artefakte."""

    index_present: bool
    schema_version: str | None
    graph_schema_version: str | None
    citation_schema_version: str | None
    metadata_schema_version: str | None
    n_papers: int
    n_chunks: int
    n_communities: int
    n_citation_edges: int
    n_identified: int
    n_reference_entries: int
    n_citable: int
    n_weak_metadata: int
    flagged_papers: int | None
    total_flags: int | None
    pdf_count: int
    manifest_entries: int
    canonical_count: int
    untracked_pdfs: tuple[str, ...]
    missing_pdfs: tuple[str, ...]
    missing_canonical: tuple[str, ...]
    orphan_canonical: tuple[str, ...]
    chunk_search: str | None = None

    @property
    def consistent(self) -> bool:
        """True, wenn papers/, Manifest und canonical/ widerspruchsfrei zusammenpassen."""
        return not (
            self.untracked_pdfs
            or self.missing_pdfs
            or self.missing_canonical
            or self.orphan_canonical
        )


def _scalar(connection: sqlite3.Connection, query: str) -> int:
    """Liest einen einzelnen ganzzahligen Skalarwert (z. B. ``COUNT(*)``)."""
    row = connection.execute(query).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _meta_value(connection: sqlite3.Connection, key: str) -> str | None:
    """Liest einen Wert aus der ``meta``-Tabelle; ``None``, wenn nicht vorhanden."""
    row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row is not None else None


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    """Prüft, ob eine Tabelle im Index existiert (robust gegen Teilschemata)."""
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    """Prüft, ob eine Spalte existiert (ein vor Phase 13 gebauter Index kennt sie nicht)."""
    return any(row[1] == column for row in connection.execute(f"PRAGMA table_info({table})"))


def _load_manifest(path: Path) -> dict[str, dict[str, str]]:
    """Lädt das Dedup-Manifest (Dateiname → {sha256, paper_id}); leer, wenn nicht vorhanden."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(name): {"paper_id": str(entry["paper_id"]), "sha256": str(entry["sha256"])}
        for name, entry in raw.items()
    }


def collect_status(data_dir: str | Path, papers_dir: str | Path) -> StatusReport:
    """Trägt den read-only Status aus Index, Qualitätsreport, Manifest und Ordnern zusammen.

    Args:
        data_dir: ``data/``-Ordner (Index, Manifest, Canonical, Qualitätsreport).
        papers_dir: Ordner mit den Quell-PDFs (``papers/``).

    Returns:
        Ein :class:`StatusReport`; fehlende Artefakte werden als ``None``/leer abgebildet.
    """
    data = Path(data_dir)
    papers = Path(papers_dir)
    index_path = data / "index" / "index.sqlite"

    index_present = index_path.is_file()
    schema_version: str | None = None
    graph_schema_version: str | None = None
    citation_schema_version: str | None = None
    metadata_schema_version: str | None = None
    chunk_search: str | None = None
    n_papers = n_chunks = n_communities = n_citation_edges = n_identified = 0
    n_citable = n_weak_metadata = n_reference_entries = 0
    if index_present:
        connection = sqlite3.connect(str(index_path))
        try:
            schema_version = _meta_value(connection, "schema_version")
            graph_schema_version = _meta_value(connection, "graph_schema_version")
            citation_schema_version = _meta_value(connection, "citation_schema_version")
            chunk_search = _meta_value(connection, "chunk_search")
            n_papers = _scalar(connection, "SELECT COUNT(*) FROM papers")
            n_chunks = _scalar(connection, "SELECT COUNT(*) FROM chunks")
            n_identified = _scalar(
                connection,
                "SELECT COUNT(*) FROM papers WHERE identifiers IS NOT NULL AND identifiers != '{}'",
            )
            if _column_exists(connection, "papers", "document_kind"):
                n_reference_entries = _scalar(
                    connection,
                    "SELECT COUNT(*) FROM papers WHERE document_kind = 'reference'",
                )
            if _table_exists(connection, "communities"):
                n_communities = _scalar(connection, "SELECT COUNT(*) FROM communities")
            if _table_exists(connection, "citation_edges"):
                n_citation_edges = _scalar(connection, "SELECT COUNT(*) FROM citation_edges")
            if _table_exists(connection, "paper_metadata"):
                metadata_schema_version = _meta_value(connection, "metadata_schema_version")
                n_citable = _scalar(
                    connection,
                    "SELECT COUNT(*) FROM paper_metadata WHERE title != '' AND year > 0 "
                    "AND authors != '[]'",
                )
                n_weak_metadata = _scalar(
                    connection, "SELECT COUNT(*) FROM paper_metadata WHERE confidence = 'weak'"
                )
        finally:
            connection.close()

    flagged_papers: int | None = None
    total_flags: int | None = None
    report_path = data / "quality_report.json"
    if report_path.is_file():
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        flagged_papers = int(payload.get("flagged_papers", 0))
        total_flags = int(payload.get("total_flags", 0))

    manifest = _load_manifest(data / "manifest.json")
    manifest_names = set(manifest.keys())
    manifest_paper_ids = {entry["paper_id"] for entry in manifest.values()}

    pdf_names = (
        {path.name for path in papers.glob("*.pdf")}
        | {path.name for path in papers.glob(f"*{STUB_SUFFIX}")}
        if papers.is_dir()
        else set()
    )
    canonical_dir = data / "canonical"
    canonical_ids = (
        {path.stem for path in canonical_dir.glob("*.json")} if canonical_dir.is_dir() else set()
    )

    return StatusReport(
        index_present=index_present,
        schema_version=schema_version,
        graph_schema_version=graph_schema_version,
        citation_schema_version=citation_schema_version,
        metadata_schema_version=metadata_schema_version,
        chunk_search=chunk_search,
        n_papers=n_papers,
        n_chunks=n_chunks,
        n_communities=n_communities,
        n_citation_edges=n_citation_edges,
        n_identified=n_identified,
        n_reference_entries=n_reference_entries,
        n_citable=n_citable,
        n_weak_metadata=n_weak_metadata,
        flagged_papers=flagged_papers,
        total_flags=total_flags,
        pdf_count=len(pdf_names),
        manifest_entries=len(manifest_names),
        canonical_count=len(canonical_ids),
        untracked_pdfs=tuple(sorted(pdf_names - manifest_names)),
        missing_pdfs=tuple(sorted(manifest_names - pdf_names)),
        missing_canonical=tuple(sorted(manifest_paper_ids - canonical_ids)),
        orphan_canonical=tuple(sorted(canonical_ids - manifest_paper_ids)),
    )


def _render_inconsistencies(status: StatusReport) -> list[str]:
    """Formatiert die Konsistenz-Befunde (nur nicht-leere Gruppen, gekürzte Vorschau)."""
    groups = (
        ("PDF ohne Manifest-Eintrag (noch nicht ingestet)", status.untracked_pdfs),
        ("Manifest-Eintrag ohne PDF (gelöscht?)", status.missing_pdfs),
        ("Manifest-Paper ohne Canonical", status.missing_canonical),
        ("Canonical ohne Manifest-Referenz (verwaist)", status.orphan_canonical),
    )
    lines: list[str] = []
    for label, items in groups:
        if not items:
            continue
        preview = ", ".join(items[:_PREVIEW])
        suffix = " …" if len(items) > _PREVIEW else ""
        lines.append(f"  ! {label}: {len(items)} ({preview}{suffix})")
    return lines


def render(status: StatusReport) -> list[str]:
    """Baut die menschenlesbaren Statuszeilen (ohne Seiteneffekte)."""
    lines = ["[status] Index & Korpus:"]
    if status.index_present:
        lines.append(
            f"  Index-Schema: {status.schema_version} · Graph-Schema: {status.graph_schema_version}"
            f" · Zitations-Schema: {status.citation_schema_version}"
            f" · Metadaten-Schema: {status.metadata_schema_version}"
        )
        lines.append(
            f"  Phrasenindex (FTS5 über chunks, Phase 16 / F2): "
            f"{status.chunk_search or 'fehlt – mit `python -m scripts.ingest` neu bauen'}"
        )
        lines.append(
            f"  Paper: {status.n_papers} · Chunks: {status.n_chunks} · "
            f"Communities: {status.n_communities} · Zitationskanten: {status.n_citation_edges}"
        )
        lines.append(f"  Mit Identifikatoren (DOI/arXiv): {status.n_identified}/{status.n_papers}")
        if status.n_reference_entries:
            lines.append(f"  Davon Referenz-Einträge ohne Volltext: {status.n_reference_entries}")
        lines.append(
            f"  Zitierfähig (Titel/Autoren/Jahr): {status.n_citable}/{status.n_papers} · "
            f"schwach belegt: {status.n_weak_metadata}"
        )
    else:
        lines.append("  (kein Index gefunden – zunächst `python -m scripts.ingest` ausführen)")

    if status.flagged_papers is not None:
        lines.append(
            f"  Qualität: {status.flagged_papers} Paper mit Flags · "
            f"{status.total_flags} Flags gesamt"
        )

    lines.append("[status] Artefakt-Konsistenz:")
    lines.append(
        f"  PDFs: {status.pdf_count} · Manifest-Einträge: {status.manifest_entries} · "
        f"Canonical: {status.canonical_count}"
    )
    if status.consistent:
        lines.append("  OK konsistent (papers/ ↔ manifest ↔ canonical)")
    else:
        lines.extend(_render_inconsistencies(status))
    return lines


def main() -> int:
    """Gibt den read-only Status auf stdout aus (Exit-Code 0)."""
    # Robuste Unicode-Ausgabe (Dateinamen/Snippets enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Read-only-Status der Drop-in-Artefakte (Phase 6)."
    )
    parser.add_argument("--data", default=str(_DEFAULT_DATA), help="Datenordner (data/)")
    parser.add_argument("--papers", default=str(_DEFAULT_PAPERS), help="Ordner mit *.pdf")
    args = parser.parse_args()

    status = collect_status(args.data, args.papers)
    for line in render(status):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
