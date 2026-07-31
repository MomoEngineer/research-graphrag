"""Drop-in-Ingestion: papers/ → Canonical JSON → Offline-Hybrid-Index (Option B).

Bindet Extraktion (``pypdf``), Dedup (``manifest.json`` über den Datei-Hash) und Index-Bau
(TF-IDF/SQLite) zu einem Schritt zusammen. Nur neue/geänderte PDFs werden extrahiert; der
Index wird als **voller Re-Index** aus allen Canonical-JSONs gebaut (Standard, siehe
Roadmap.md). Grundsatz: docs/adr/0005-graphrag-index-backend-open.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, extract_pdf
from research_graphrag.indexing.tfidf_index import build_index


@dataclass(frozen=True)
class IngestReport:
    """Zählwerte eines Ingestion-Laufs."""

    extracted: int
    skipped: int
    n_papers: int
    indexed_chunks: int


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
        if (
            entry is not None
            and entry["sha256"] == sha256
            and (canonical_dir / f"{entry['paper_id']}.json").is_file()
        ):
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
    return IngestReport(
        extracted=extracted,
        skipped=skipped,
        n_papers=len(papers),
        indexed_chunks=indexed_chunks,
    )
