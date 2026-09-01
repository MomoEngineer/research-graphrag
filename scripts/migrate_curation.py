"""CLI: Kuratiertes Relevanzurteil aus Übersicht.md nach ``metadata/curation.json`` überführen.

Einmaliger (aber wiederholbar ausführbarer) Migrationsschritt aus Phase 15 / G4: Die 131
kuratierten Zeilen tragen das einzige menschliche Relevanzurteil im Repo (``Themenfokus``,
``Relevanz fuer Expose``, ``SRQ-Zuordnung``) und sind aus keiner anderen Quelle rekonstruierbar
(docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md). Dieses Werkzeug
überführt sie **verlustfrei** und macht den Abgleich Zeile für Zeile nachprüfbar.

Aufruf vom Repository-Wurzelverzeichnis::

    python -m scripts.migrate_curation --dry-run   # zeigt, was geschrieben würde
    python -m scripts.migrate_curation             # schreibt metadata/curation.json
    python -m scripts.migrate_curation --check      # vergleicht die Datei gegen Übersicht.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research_graphrag.extraction.pdf import CanonicalPaper
from research_graphrag.indexing.citation_graph import title_from_uri
from research_graphrag.overview.curation import (
    CurationEntry,
    curation_path,
    load_curation,
    load_curation_rows,
    migrate_from_overview,
    save_curation,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_UEBERSICHT = _REPO_ROOT / "Übersicht.md"
_DEFAULT_CANONICAL = _REPO_ROOT / "data" / "canonical"


def _paper_ids_by_filename(canonical_dir: Path) -> dict[str, str]:
    """Baut die Zuordnung ``Interner Link``-Dateiname → ``paper_id`` aus den Canonical-Papern."""
    mapping: dict[str, str] = {}
    for path in sorted(canonical_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        paper = CanonicalPaper.from_dict(data)
        mapping[f"{title_from_uri(paper.source_uri)}.pdf"] = paper.paper_id
    return mapping


def _diff(from_overview: dict[str, CurationEntry], existing: dict[str, CurationEntry]) -> list[str]:
    """Vergleicht zwei paper_id-geschlüsselte Kurations-Abbildungen Feld für Feld."""
    findings: list[str] = []
    all_ids = sorted(set(from_overview) | set(existing))
    for paper_id in all_ids:
        want = from_overview.get(paper_id)
        have = existing.get(paper_id)
        if want is None:
            findings.append(f"nur in der Datei, nicht mehr in Übersicht.md: {paper_id}")
            continue
        if have is None:
            findings.append(f"fehlt in der Datei: {paper_id} ({want.row_id})")
            continue
        want_values = (want.themenfokus, want.relevanz, want.srq)
        have_values = (have.themenfokus, have.relevanz, have.srq)
        if want_values != have_values:
            findings.append(f"weicht ab: {paper_id} ({want.row_id})")
    return findings


def main() -> int:
    """Migriert bzw. prüft die kuratierten Relevanzurteile."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(
        description="Kuratiertes Relevanzurteil aus Übersicht.md nach metadata/curation.json."
    )
    parser.add_argument("--uebersicht", default=str(_DEFAULT_UEBERSICHT))
    parser.add_argument("--canonical", default=str(_DEFAULT_CANONICAL))
    parser.add_argument("--out", default=str(curation_path(_REPO_ROOT)))
    parser.add_argument("--dry-run", action="store_true", help="Nichts schreiben, nur zählen.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Bestehende Datei gegen Übersicht.md vergleichen (Exit 1 bei Abweichung).",
    )
    args = parser.parse_args()

    rows = load_curation_rows(args.uebersicht)
    paper_ids_by_filename = _paper_ids_by_filename(Path(args.canonical))
    migrated = migrate_from_overview(rows, paper_ids_by_filename)
    unmapped = sorted(set(rows) - {entry.filename for entry in migrated.values()})

    if args.check:
        existing = load_curation(args.out)
        findings = _diff(migrated, existing)
        for finding in findings:
            print(f"  ! {finding}")
        print(
            f"[curation] Übersicht.md: {len(rows)} kuratierte Zeilen · "
            f"{len(migrated)} zuordenbar · {len(findings)} Abweichung(en)"
        )
        return 1 if findings else 0

    print(
        f"[curation] Übersicht.md: {len(rows)} kuratierte Zeilen, "
        f"{len(migrated)} einem Korpus-Paper zugeordnet"
    )
    if unmapped:
        print(f"  ! ohne zuordenbares Korpus-Paper: {', '.join(unmapped)}")
    if args.dry_run:
        print(f"[curation] --dry-run: nichts geschrieben (Ziel wäre {args.out})")
        return 0

    written = save_curation(migrated, args.out)
    print(f"[curation] geschrieben: {written} Datensätze → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
