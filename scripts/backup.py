"""CLI: Sicherung des nicht reproduzierbaren Bestandes (Phase 11 / B1).

Sichert PDF-Korpus, kuratierte Übersicht, Zitationsdaten, Manifest und die append-only
Protokolle in ein Zielverzeichnis **außerhalb** der Arbeitskopie. Abgeleitete Artefakte
(``data/canonical/``, ``data/index/``, Qualitätsberichte) bleiben bewusst draußen – sie
entstehen beim nächsten ``python -m scripts.ingest`` deterministisch neu
(docs/adr/0027-corpus-backup-phase11.md).

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.backup --ziel D:\\Sicherung\\research-graphrag --dry-run
    python -m scripts.backup --ziel D:\\Sicherung\\research-graphrag
    python -m scripts.backup --ziel D:\\Sicherung\\research-graphrag --pruefen
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_graphrag.backup import (
    ACTION_COPIED,
    ACTION_MISSING,
    BackupReport,
    VerificationReport,
    create_backup,
    verify_backup,
)
from research_graphrag.errors import DomainError

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BAR_WIDTH = 30


def _show_progress(name: str, current: int, total: int) -> None:
    """Schreibt einen Fortschrittsbalken auf stderr (nur an interaktiven Terminals)."""
    if not sys.stderr.isatty():
        return
    filled = int(_BAR_WIDTH * current / total) if total > 0 else _BAR_WIDTH
    arrow = ">" if filled < _BAR_WIDTH else ""
    bar = "=" * filled + arrow + " " * max(0, _BAR_WIDTH - filled - 1)
    sys.stderr.write(f"\r[{bar}] {current:>4}/{total} {name[:44].ljust(44)}")
    sys.stderr.flush()
    if current == total:
        sys.stderr.write("\n")
        sys.stderr.flush()


def render(report: BackupReport) -> str:
    """Formatiert die Bilanz eines Sicherungslaufs."""
    lines: list[str] = []
    if report.dry_run:
        lines.append("[backup] VORSCHAU – es wurde nichts geschrieben.")
    lines.append(f"[backup] Ziel: {report.target}")
    lines.append(
        f"  Gesichert: {report.n_copied} neu · {report.n_unchanged} unverändert · "
        f"{report.total_bytes / 1_048_576:.1f} MiB gesamt"
    )
    missing = [item.relative_path for item in report.items if item.action == ACTION_MISSING]
    if missing:
        lines.append(f"  Nicht vorhanden (übersprungen): {', '.join(missing)}")
    copied = [item.relative_path for item in report.items if item.action == ACTION_COPIED]
    if copied:
        shown = copied[:10]
        lines.append("  Neu geschrieben:")
        lines.extend(f"    {name}" for name in shown)
        if len(copied) > len(shown):
            lines.append(f"    … und {len(copied) - len(shown)} weitere")
    lines.append(
        "  Hinweis: Index und Canonical sind bewusst nicht enthalten – nach dem "
        "Zurückkopieren 'python -m scripts.ingest' ausführen."
    )
    return "\n".join(lines)


def render_verification(result: VerificationReport) -> str:
    """Formatiert das Ergebnis der Nachrechnung."""
    lines = [f"[backup] Prüfung: {result.target}"]
    lines.append(f"  Geprüft: {result.n_checked} Dateien")
    if result.ok:
        lines.append("  OK Sicherungsstand vollständig und unverändert.")
        return "\n".join(lines)
    if result.missing:
        lines.append(f"  ! Fehlend ({len(result.missing)}):")
        lines.extend(f"    {name}" for name in result.missing[:10])
    if result.mismatched:
        lines.append(f"  ! Verändert ({len(result.mismatched)}):")
        lines.extend(f"    {name}" for name in result.mismatched[:10])
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    """Baut den Argument-Parser der CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.backup",
        description=(
            "Sichert den nicht reproduzierbaren Bestand (PDFs, Übersicht, Zitationsdaten, "
            "Manifest, Protokolle) in ein Verzeichnis außerhalb der Arbeitskopie."
        ),
    )
    parser.add_argument("--ziel", required=True, help="Zielverzeichnis der Sicherung")
    parser.add_argument("--root", default=str(_REPO_ROOT), help="Wurzel der Arbeitskopie")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Zeigt den Lauf, ohne zu schreiben",
    )
    parser.add_argument(
        "--pruefen",
        action="store_true",
        help="Rechnet einen vorhandenen Sicherungsstand gegen sein Manifest nach",
    )
    return parser


def main() -> int:
    """Einstiegspunkt der CLI."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    args = _build_parser().parse_args()

    try:
        if args.pruefen:
            result = verify_backup(args.ziel)
            print(render_verification(result))
            return 0 if result.ok else 1
        report = create_backup(
            args.root,
            args.ziel,
            dry_run=args.dry_run,
            progress=_show_progress,
        )
    except DomainError as exc:
        print(f"[backup] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
