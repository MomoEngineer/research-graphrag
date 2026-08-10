"""Drop-in-Ingestion: papers/ → Canonical JSON → Offline-Hybrid-Index (Option B).

Bindet Extraktion (``pypdf`` für PDFs, nativer Adapter für Referenz-Einträge ``*.refjson``),
Dedup (``manifest.json`` über den Datei-Hash), Index-Bau
(TF-IDF/SQLite), den Paper-Ähnlichkeitsgraphen samt Louvain-Communities und den
Intra-Korpus-Zitationsgraphen zu einem Schritt zusammen. Nur neue/geänderte Dateien werden
extrahiert; Index, Graph und Zitationskanten werden als **voller Re-Index** aus allen
Canonical-JSONs gebaut (Standard, siehe Roadmap.md). Grundsätze:
docs/adr/0005-graphrag-index-backend-open.md, docs/adr/0007-graphrag-index-phase3-option-b.md,
docs/adr/0011-intra-corpus-citation-graph-phase7.md,
docs/adr/0030-reference-entries-in-corpus-phase13.md.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from research_graphrag.bibliography.store import metadata_path
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SCHEMA_VERSION, read_schema_version
from research_graphrag.extraction.pdf import CanonicalPaper, extract_pdf
from research_graphrag.extraction.refstub import STUB_SUFFIX, extract_stub
from research_graphrag.indexing.citation_graph import CitationBuildReport, build_citation_graph
from research_graphrag.indexing.graph_index import GraphBuildReport, build_graph
from research_graphrag.indexing.metadata_index import MetadataBuildReport, build_metadata_index
from research_graphrag.indexing.tfidf_index import build_index

OVERVIEW_FILENAME = "\u00dcbersicht.md"
"""Kuratierte Literaturübersicht (Quelle der Herkunft ``curated``)."""


@dataclass(frozen=True)
class IngestReport:
    """Zählwerte eines Ingestion-Laufs."""

    extracted: int
    skipped: int
    n_papers: int
    indexed_chunks: int
    flagged_papers: int
    total_flags: int
    n_nodes: int
    n_edges: int
    n_communities: int
    n_citation_edges: int
    n_papers_with_refs: int
    n_with_identifier: int = 0
    n_citable: int = 0
    n_weak_metadata: int = 0


def _load_manifest(path: Path) -> dict[str, dict[str, str]]:
    """Lädt das Dedup-Manifest (Dateiname → {sha256, paper_id}); leer, wenn nicht vorhanden."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(name): {"sha256": str(entry["sha256"]), "paper_id": str(entry["paper_id"])}
        for name, entry in raw.items()
    }


def _save_manifest(path: Path, manifest: dict[str, dict[str, str]]) -> None:
    """Schreibt das Manifest deterministisch (sortierte Schlüssel)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _remove_stale_canonical(
    canonical_dir: Path,
    manifest: dict[str, dict[str, str]],
    name: str,
    previous: dict[str, str] | None,
    new_paper_id: str,
) -> None:
    """Entfernt das Canonical JSON einer geänderten Datei, sofern keine andere es teilt."""
    if previous is None or previous["paper_id"] == new_paper_id:
        return
    old_paper_id = previous["paper_id"]
    still_referenced = any(
        other != name and value["paper_id"] == old_paper_id for other, value in manifest.items()
    )
    if not still_referenced:
        (canonical_dir / f"{old_paper_id}.json").unlink(missing_ok=True)


def _can_skip(entry: dict[str, str] | None, sha256: str, canonical_dir: Path) -> bool:
    """Prüft, ob eine PDF unverändert **und** mit aktuellem Schema bereits extrahiert ist."""
    if entry is None or entry["sha256"] != sha256:
        return False
    canonical_file = canonical_dir / f"{entry['paper_id']}.json"
    if not canonical_file.is_file():
        return False
    try:
        return read_schema_version(canonical_file) == SCHEMA_VERSION
    except (json.JSONDecodeError, OSError, KeyError):
        return False


def _write_quality_report(papers: list[CanonicalPaper], data_dir: Path) -> Path:
    """Schreibt den aggregierten Qualitätsreport (JSON + Markdown) und liefert den JSON-Pfad."""
    ordered = sorted(papers, key=lambda paper: paper.paper_id)
    flagged = [paper for paper in ordered if paper.quality_flags]
    total_flags = sum(len(paper.quality_flags) for paper in ordered)
    report = {
        "schema_version": SCHEMA_VERSION,
        "n_papers": len(ordered),
        "flagged_papers": len(flagged),
        "total_flags": total_flags,
        "papers": [
            {
                "paper_id": paper.paper_id,
                "source_uri": paper.source_uri,
                "n_pages": paper.n_pages,
                "n_chunks": len(paper.chunks),
                "flags": list(paper.quality_flags),
            }
            for paper in ordered
        ],
    }
    json_path = data_dir / "quality_report.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    lines = [
        "# Qualitätsreport (Ingestion)",
        "",
        f"- Paper gesamt: {len(ordered)}",
        f"- Paper mit Flags: {len(flagged)}",
        f"- Flags gesamt: {total_flags}",
        "",
    ]
    if flagged:
        lines.append("| Paper-ID | Seiten | Chunks | Flags |")
        lines.append("| --- | --- | --- | --- |")
        for paper in flagged:
            flags = ", ".join(paper.quality_flags)
            lines.append(f"| {paper.paper_id} | {paper.n_pages} | {len(paper.chunks)} | {flags} |")
    else:
        lines.append("Keine Qualitäts-Flags.")
    (data_dir / "quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path


def _build_index_atomically(
    papers: list[CanonicalPaper],
    index_path: Path,
    *,
    overview_path: Path | None = None,
    metadata_file: Path | None = None,
) -> tuple[int, GraphBuildReport, CitationBuildReport, MetadataBuildReport]:
    """Baut Index, Graph, Zitationskanten **und** Metadaten in eine Temporärdatei; ersetzt atomar.

    Der MCP-Server liest den Index pro Anfrage frisch (On-Read, siehe
    docs/adr/0010-drop-in-workflow-and-qa-phase6.md); ein *In-place*-Neuaufbau könnte daher
    kurzzeitig einen halbfertigen Zustand liefern. Deshalb wird zunächst vollständig nach
    ``index.sqlite.tmp`` gebaut (TF-IDF/SQLite, Paper-Graph, Zitationsgraph und die
    bibliografischen Datensätze aus docs/adr/0025-citable-paper-metadata.md) und erst nach
    Erfolg per :func:`os.replace` **atomar** an die Zielstelle verschoben. Schlägt der Bau fehl,
    bleibt der bestehende Index unangetastet (Crash-Sicherheit); die Temporärdatei wird stets
    entfernt.

    Args:
        papers: Extrahierte Canonical-Papers (Quelle für Index, Graph und Zitationen).
        index_path: Zielpfad der SQLite-Index-Datei.
        overview_path: Kuratierte Übersicht (Herkunft ``curated``); ``None`` überspringt sie.
        metadata_file: Versionierte Metadatendatei (``resolved``/``manual``); ``None``
            überspringt sie.

    Returns:
        Tupel aus indexierten Chunks, :class:`GraphBuildReport`, :class:`CitationBuildReport`
        und :class:`MetadataBuildReport`.
    """
    tmp_path = index_path.with_name(index_path.name + ".tmp")
    try:
        indexed_chunks = build_index(papers, tmp_path)
        graph_report = build_graph(papers, tmp_path)
        citation_report = build_citation_graph(papers, tmp_path)
        metadata_report = build_metadata_index(
            papers, tmp_path, overview_path=overview_path, metadata_file=metadata_file
        )
        os.replace(tmp_path, index_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return indexed_chunks, graph_report, citation_report, metadata_report


def forget_source(data_dir: str | Path, filename: str) -> bool:
    """Vergisst eine Korpus-Datei: Manifest-Eintrag und – falls verwaist – ihr Canonical.

    Nötig für den Upgrade-Pfad des Intake: Wird ein Referenz-Eintrag durch den Volltext abgelöst,
    bliebe sein Canonical sonst als **Waise** im Datenbestand und das Paper erschiene nach dem
    nächsten Re-Index doppelt – einmal als Stub, einmal als Volltext
    (docs/adr/0030-reference-entries-in-corpus-phase13.md).

    Args:
        data_dir: Datenordner mit ``manifest.json`` und ``canonical/``.
        filename: Name der nicht mehr vorhandenen Datei in ``papers/``.

    Returns:
        ``True``, wenn ein Eintrag entfernt wurde.
    """
    data_path = Path(data_dir)
    manifest_path = data_path / "manifest.json"
    if not manifest_path.is_file():
        return False
    manifest = _load_manifest(manifest_path)
    entry = manifest.pop(filename, None)
    if entry is None:
        return False
    paper_id = entry["paper_id"]
    still_referenced = any(value["paper_id"] == paper_id for value in manifest.values())
    if not still_referenced:
        (data_path / "canonical" / f"{paper_id}.json").unlink(missing_ok=True)
    _save_manifest(manifest_path, manifest)
    return True


def ingest(
    papers_dir: str | Path,
    data_dir: str | Path,
    *,
    overview_path: str | Path | None = None,
    metadata_file: str | Path | None = None,
) -> IngestReport:
    """Führt deduplizierte Extraktion und Index-Bau für einen ``papers/``-Ordner aus.

    Args:
        papers_dir: Ordner mit ``*.pdf`` und ``*.refjson`` (Referenz-Einträge ohne Volltext,
            docs/adr/0030-reference-entries-in-corpus-phase13.md).
        data_dir: Zielordner für ``canonical/``, ``manifest.json`` und ``index/index.sqlite``.
        overview_path: Kuratierte Übersicht als Metadatenquelle; ohne Angabe wird
            ``<data_dir>/../Übersicht.md`` verwendet.
        metadata_file: Versionierte Metadatendatei; ohne Angabe wird
            ``<data_dir>/../metadata/paper_metadata.json`` verwendet. Fehlende Dateien sind
            unkritisch (die jeweilige Herkunft entfällt dann).

    Returns:
        Ein :class:`IngestReport` mit Zählwerten.

    Raises:
        DomainError: ``not_found`` wenn ``papers_dir`` fehlt; ``invalid_input`` wenn keine
            indexierbaren Paper vorhanden sind (siehe docs/error-model.md).
    """
    papers_path = Path(papers_dir)
    data_path = Path(data_dir)
    if not papers_path.is_dir():
        raise DomainError(ErrorCode.NOT_FOUND, f"papers-Ordner fehlt: {papers_path}")

    root = data_path.parent
    overview = Path(overview_path) if overview_path is not None else root / OVERVIEW_FILENAME
    metadata = Path(metadata_file) if metadata_file is not None else metadata_path(root)

    canonical_dir = data_path / "canonical"
    index_path = data_path / "index" / "index.sqlite"
    manifest_path = data_path / "manifest.json"
    manifest = _load_manifest(manifest_path)

    extracted = 0
    skipped = 0
    sources = sorted(
        [*papers_path.glob("*.pdf"), *papers_path.glob(f"*{STUB_SUFFIX}")],
        key=lambda item: item.name,
    )
    for source in sources:
        sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        entry = manifest.get(source.name)
        if _can_skip(entry, sha256, canonical_dir):
            skipped += 1
            continue
        # Der Dokumenttyp entscheidet allein die Endung – ein Referenz-Eintrag wird nativ
        # gelesen, nicht per Heuristik aus einer synthetischen PDF zurückgewonnen.
        paper = (
            extract_stub(source) if source.suffix.lower() == STUB_SUFFIX else extract_pdf(source)
        )
        _remove_stale_canonical(canonical_dir, manifest, source.name, entry, paper.paper_id)
        paper.save_json(canonical_dir / f"{paper.paper_id}.json")
        manifest[source.name] = {"sha256": sha256, "paper_id": paper.paper_id}
        extracted += 1

    _save_manifest(manifest_path, manifest)

    papers = [CanonicalPaper.load_json(path) for path in sorted(canonical_dir.glob("*.json"))]
    if not papers:
        raise DomainError(
            ErrorCode.INVALID_INPUT, "Keine Canonical-Paper vorhanden (papers/ leer?)."
        )

    indexed_chunks, graph_report, citation_report, metadata_report = _build_index_atomically(
        papers, index_path, overview_path=overview, metadata_file=metadata
    )
    _write_quality_report(papers, data_path)
    return IngestReport(
        extracted=extracted,
        skipped=skipped,
        n_papers=len(papers),
        indexed_chunks=indexed_chunks,
        flagged_papers=sum(1 for paper in papers if paper.quality_flags),
        total_flags=sum(len(paper.quality_flags) for paper in papers),
        n_nodes=graph_report.n_nodes,
        n_edges=graph_report.n_edges,
        n_communities=graph_report.n_communities,
        n_citation_edges=citation_report.n_edges,
        n_papers_with_refs=citation_report.n_papers_with_refs,
        n_with_identifier=metadata_report.n_with_identifier,
        n_citable=metadata_report.n_citable,
        n_weak_metadata=metadata_report.n_weak,
    )
