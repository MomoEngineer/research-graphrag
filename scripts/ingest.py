"""CLI: Drop-in-Ingestion (papers/ → Canonical JSON → Index, Option B).

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.ingest
"""

from __future__ import annotations

import argparse
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.pipeline import ingest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    """Führt die Ingestion aus und gibt einen Kurzreport auf stdout aus."""
    parser = argparse.ArgumentParser(description="Drop-in-Ingestion (Option B).")
    parser.add_argument("--papers", default=str(_REPO_ROOT / "papers"), help="Ordner mit *.pdf")
    parser.add_argument("--data", default=str(_REPO_ROOT / "data"), help="Zielordner für Artefakte")
    args = parser.parse_args()

    try:
        report = ingest(args.papers, args.data)
    except DomainError as exc:
        print(f"[ingest] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    print(
        f"[ingest] extrahiert={report.extracted} übersprungen={report.skipped} "
        f"Paper={report.n_papers} Chunks={report.indexed_chunks} "
        f"geflaggt={report.flagged_papers} Flags={report.total_flags}"
    )
    print(
        f"[ingest] Graph: Knoten={report.n_nodes} Kanten={report.n_edges} "
        f"Communities={report.n_communities}"
    )
    print(
        f"[ingest] Zitationen: Kanten={report.n_citation_edges} "
        f"Paper mit Referenzabschnitt={report.n_papers_with_refs}"
    )
    print(f"[ingest] Qualitätsreport: {Path(args.data) / 'quality_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
