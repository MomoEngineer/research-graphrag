"""CLI: Korpus-Zufluss über den Eingangsordner ``new_papers/`` (Phase 8).

Prüft neue PDFs auf Doppelbestand (sha256 → DOI/arXiv → Titel-Verdacht), übernimmt die neuen
nach ``papers/``, stößt **einen** Ingest-Lauf an und ergänzt die kuratierte ``Übersicht.md`` um
Entwurfszeilen. Grundsätze und Konsequenzen je Stufe:
docs/adr/0019-corpus-intake-new-papers-phase8.md.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.intake --dry-run   # zeigt jede geplante Aktion, verändert nichts
    python -m scripts.intake
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.intake import (
    ACTION_ACCEPTED,
    ACTION_DELETED,
    ACTION_KEPT,
    ACTION_QUARANTINED,
    IntakeReport,
    run_intake,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent

_ACTION_LABELS = {
    ACTION_ACCEPTED: "übernommen",
    ACTION_DELETED: "gelöscht",
    ACTION_QUARANTINED: "quarantäne",
    ACTION_KEPT: "liegen geblieben",
}


def render(report: IntakeReport) -> str:
    """Formatiert den Abschlussbericht eines Intake-Laufs."""
    lines: list[str] = []
    if report.dry_run:
        lines.append("[intake] TROCKENLAUF – es wurde nichts verändert.")
    if not report.decisions:
        lines.append("[intake] Eingangsordner ist leer – nichts zu tun.")
        return "\n".join(lines)

    for action, label in _ACTION_LABELS.items():
        for item in report.by_action(action):
            prefix = "[würde]" if report.dry_run else "      "
            lines.append(f"{prefix} {label:>16}: {item.filename}")
            lines.append(f"{'':>25}{item.reason} – {item.detail}")
            if action == ACTION_DELETED:
                lines.append(f"{'':>25}sha256 {item.sha256}")
            if item.flags:
                lines.append(f"{'':>25}Qualitäts-Flags: {', '.join(item.flags)}")

    counts = ", ".join(
        f"{label}={len(report.by_action(action))}" for action, label in _ACTION_LABELS.items()
    )
    lines.append(f"[intake] {counts}")

    if report.ingest is not None:
        ingest = report.ingest
        lines.append(
            f"[intake] Index: Paper={ingest.n_papers} Chunks={ingest.indexed_chunks} "
            f"Communities={ingest.n_communities} Zitationskanten={ingest.n_citation_edges}"
        )
    if report.overview is not None:
        overview = report.overview
        ids = ", ".join(overview.row_ids) if overview.row_ids else "–"
        lines.append(f"[intake] Übersicht: neue Zeilen={overview.written} (IDs: {ids})")
    return "\n".join(lines)


def main() -> int:
    """Führt den Intake aus und gibt den Abschlussbericht auf stdout aus."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description="Korpus-Zufluss über new_papers/ (Phase 8).")
    parser.add_argument(
        "--new", default=str(_REPO_ROOT / "new_papers"), help="Eingangsordner mit *.pdf"
    )
    parser.add_argument("--papers", default=str(_REPO_ROOT / "papers"), help="Korpus-Ordner")
    parser.add_argument("--data", default=str(_REPO_ROOT / "data"), help="Datenordner")
    parser.add_argument(
        "--uebersicht",
        default=str(_REPO_ROOT / "Übersicht.md"),
        help="Kuratierte Übersicht (wird append-only ergänzt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Zeigt jede geplante Aktion, verändert nichts (empfohlen vor dem ersten Lauf)",
    )
    parser.add_argument(
        "--delete-identifier-duplicates",
        action="store_true",
        help="Löscht DOI-/arXiv-Duplikate hart, statt sie in die Quarantäne zu verschieben",
    )
    args = parser.parse_args()

    try:
        report = run_intake(
            inbox_dir=args.new,
            papers_dir=args.papers,
            data_dir=args.data,
            uebersicht_path=args.uebersicht,
            dry_run=args.dry_run,
            delete_identifier_duplicates=args.delete_identifier_duplicates,
        )
    except DomainError as exc:
        print(f"[intake] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
