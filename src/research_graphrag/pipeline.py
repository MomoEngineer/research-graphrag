"""Drop-in-Ingestion: papers/ → Canonical JSON → Offline-Hybrid-Index (Option B).

Bindet Extraktion (``pypdf``), Dedup (``manifest.json`` über den Datei-Hash), Index-Bau
(TF-IDF/SQLite) und den Paper-Ähnlichkeitsgraphen samt Louvain-Communities zu einem Schritt
zusammen. Nur neue/geänderte PDFs werden extrahiert; Index und Graph werden als **voller
Re-Index** aus allen Canonical-JSONs gebaut (Standard, siehe Roadmap.md). Grundsätze:
docs/adr/0005-graphrag-index-backend-open.md, docs/adr/0007-graphrag-index-phase3-option-b.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SCHEMA_VERSION, read_schema_version
from research_graphrag.extraction.pdf import CanonicalPaper, extract_pdf
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index


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


def ingest(papers_dir: str | Path, data_dir: str | Path) -> IngestReport:
    """Führt deduplizierte Extraktion und Index-Bau für einen ``papers/``-Ordner aus.

    Args:
        papers_dir: Ordner mit ``*.pdf``.
        data_dir: Zielordner für ``canonical/``, ``manifest.json`` und ``index/index.sqlite``.

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

    canonical_dir = data_path / "canonical"
    index_path = data_path / "index" / "index.sqlite"
    manifest_path = data_path / "manifest.json"
    manifest = _load_manifest(manifest_path)

    extracted = 0
    skipped = 0
    for pdf in sorted(papers_path.glob("*.pdf")):
        sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()
        entry = manifest.get(pdf.name)
        if _can_skip(entry, sha256, canonical_dir):
            skipped += 1
            continue
        paper = extract_pdf(pdf)
        _remove_stale_canonical(canonical_dir, manifest, pdf.name, entry, paper.paper_id)
        paper.save_json(canonical_dir / f"{paper.paper_id}.json")
        manifest[pdf.name] = {"sha256": sha256, "paper_id": paper.paper_id}
        extracted += 1

    _save_manifest(manifest_path, manifest)

    papers = [CanonicalPaper.load_json(path) for path in sorted(canonical_dir.glob("*.json"))]
    if not papers:
        raise DomainError(
            ErrorCode.INVALID_INPUT, "Keine Canonical-Paper vorhanden (papers/ leer?)."
        )

    indexed_chunks = build_index(papers, index_path)
    graph_report = build_graph(papers, index_path)
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
    )
