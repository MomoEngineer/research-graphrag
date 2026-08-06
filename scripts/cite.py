"""CLI: fertige Literaturangabe zu einem Paper ausgeben (read-only).

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.cite <paper_id>
    python -m scripts.cite <paper_id> --stil apa

Ohne ``--stil`` werden **beide** unterstützten Formen ausgegeben (Harvard nach *Cite Them
Right* und APA 7) samt Kurzbeleg für den Fließtext. Die Angaben stammen ausschließlich aus dem
Index; unvollständige Datensätze werden als solche ausgewiesen statt ergänzt
(docs/adr/0025-citable-paper-metadata.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_graphrag.bibliography.styles import STYLES, format_in_text, format_reference
from research_graphrag.errors import DomainError
from research_graphrag.retrieval.reference import get_reference

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"


def main() -> int:
    """Gibt die Literaturangabe eines Papers aus und meldet fehlende Pflichtfelder."""
    # Robuste Unicode-Ausgabe (Titel/Autoren enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Literaturangabe eines Papers (Harvard/APA).")
    parser.add_argument("paper_id", help="Stabile Paper-ID (siehe scripts.ask/scripts.status)")
    parser.add_argument(
        "--stil",
        choices=STYLES,
        default=None,
        help="Nur einen Stil ausgeben (Default: beide).",
    )
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    args = parser.parse_args()

    try:
        result = get_reference(args.index, args.paper_id)
    except DomainError as exc:
        print(f"[cite] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    metadata = result.metadata
    origins = ", ".join(f"{field}={origin}" for field, origin in sorted(metadata.origins.items()))
    print(f"[cite] Paper {result.paper_id} · Schlüssel {metadata.citation_key()}")
    print(f"[cite] Herkunft: {origins or '(keine)'} · Konfidenz {metadata.confidence}")

    for style in STYLES if args.stil is None else (args.stil,):
        print(f"\n{style.upper()}")
        print(f"  {format_reference(metadata, style)}")
        print(f"  Kurzbeleg: {format_in_text(metadata, style)}")

    if result.missing:
        print(f"\n[cite] {result.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
