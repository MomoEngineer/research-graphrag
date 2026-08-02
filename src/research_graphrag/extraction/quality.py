"""Heuristische Qualitäts-Gates der Extraktion (Phase 2, Option B).

Erzeugt aus Seitentext, erkannten Abschnitten und Chunks eine deterministische, sortierte
Liste von **Qualitäts-Flags**. Die Flags sind Signale für die spätere Stichproben-QS
(README, „Qualitätssicherung"); sie sind bewusst heuristisch (kein tiefes Referenz-/Tabellen-
Parsing – das bleibt Phase 7). Grundsatz: docs/adr/0006-canonical-model-phase2-scope.md.

Flag-Katalog:

- ``empty_document`` – kein Seitentext extrahierbar.
- ``empty_page:<n>`` – Seite ``n`` ohne Text.
- ``no_chunks`` – Seitentext vorhanden, aber **kein** Fließtext-Chunk erzeugt (z. B. reiner Scan
  ohne Textebene, Deckblatt, Fehlerseite). Schließt die in
  docs/adr/0013-chunking-refinement-phase7.md dokumentierte Lücke; entschieden in
  docs/adr/0019-corpus-intake-new-papers-phase8.md.
- ``missing_abstract`` / ``missing_references`` – kein Abstract-/Referenz-Abschnitt erkannt.
- ``no_sections_detected`` – keinerlei Überschrift erkannt (nur ``front``).
- ``ocr_noise`` – auffällig niedriger Alphanumerik-Anteil / viele Ein-Zeichen-Token.
- ``possible_headless_table:<n>`` – tabellarischer Block ohne „Table/Tabelle"-Caption.
- ``short_chunks:<n>`` – **aggregierte** Anzahl der Chunks unterhalb des Zielfensters (bewusst
  nicht pro Chunk: die Einzel-IDs waren nicht handlungsleitend und haben den Report dominiert,
  siehe docs/adr/0013-chunking-refinement-phase7.md).
- ``long_chunk:<id>`` – Chunk oberhalb des Zielfensters (bleibt pro Chunk: selten und einzeln
  handlungsleitend, weil ein unteilbarer Übersatz dahintersteht).
"""

from __future__ import annotations

from collections.abc import Sequence

from research_graphrag.extraction.chunking import MAX_CHARS, MIN_CHARS
from research_graphrag.extraction.model import (
    SECTION_KIND_ABSTRACT,
    SECTION_KIND_FRONT,
    SECTION_KIND_REFERENCES,
    Chunk,
    Section,
)
from research_graphrag.extraction.structure import looks_tabular

_MIN_OCR_LEN = 200
_OCR_ALNUM_RATIO = 0.55
_OCR_SINGLE_TOKEN_RATIO = 0.4
_CAPTION_PREFIXES = ("table", "tabelle")


def _looks_like_ocr_noise(text: str) -> bool:
    """Heuristik für OCR-Rauschen (niedriger Alphanumerik-Anteil / viele Ein-Zeichen-Token)."""
    stripped = text.strip()
    if len(stripped) < _MIN_OCR_LEN:
        return False
    non_space = [char for char in stripped if not char.isspace()]
    if not non_space:
        return False
    alnum_ratio = sum(char.isalnum() for char in non_space) / len(non_space)
    tokens = stripped.split()
    single_ratio = sum(1 for token in tokens if len(token) == 1) / len(tokens) if tokens else 0.0
    return alnum_ratio < _OCR_ALNUM_RATIO or single_ratio > _OCR_SINGLE_TOKEN_RATIO


def _has_caption_above(lines: Sequence[str], start: int) -> bool:
    """Prüft, ob in den zwei nicht-leeren Zeilen vor ``start`` eine Tabellen-Caption steht."""
    seen = 0
    index = start - 1
    while index >= 0 and seen < 2:
        previous = lines[index].strip()
        if previous:
            seen += 1
            if previous.lower().startswith(_CAPTION_PREFIXES):
                return True
        index -= 1
    return False


def _flag_headless_tables(pages: Sequence[tuple[int, str]]) -> list[str]:
    """Markiert Seiten mit tabellarischem Block ohne vorangehende „Table/Tabelle"-Caption."""
    flags: list[str] = []
    for page_number, text in pages:
        lines = text.split("\n")
        index = 0
        flagged = False
        while index < len(lines):
            if looks_tabular(lines[index]):
                end = index
                while end < len(lines) and looks_tabular(lines[end]):
                    end += 1
                if end - index >= 3 and not _has_caption_above(lines, index):
                    flagged = True
                index = end
            else:
                index += 1
        if flagged:
            flags.append(f"possible_headless_table:{page_number}")
    return flags


def assess(
    pages: Sequence[tuple[int, str]],
    sections: Sequence[Section],
    chunks: Sequence[Chunk],
    *,
    min_chars: int = MIN_CHARS,
    max_chars: int = MAX_CHARS,
) -> tuple[str, ...]:
    """Bewertet die Extraktion und liefert eine sortierte, deduplizierte Flag-Liste.

    Args:
        pages: ``(Seitennummer, Seitentext)`` in Reihenfolge.
        sections: Erkannte Abschnitte (siehe :mod:`research_graphrag.extraction.structure`).
        chunks: Erzeugte Chunks (siehe :func:`research_graphrag.extraction.chunking.build_chunks`).
        min_chars: Untergrenze des Chunk-Zielfensters.
        max_chars: Obergrenze des Chunk-Zielfensters.

    Returns:
        Deterministisch sortiertes Tupel der Qualitäts-Flags (ggf. leer).
    """
    flags: list[str] = []
    non_empty_pages = [(number, text) for number, text in pages if text.strip()]

    if not non_empty_pages:
        flags.append("empty_document")
    for number, text in pages:
        if not text.strip():
            flags.append(f"empty_page:{number}")

    if non_empty_pages:
        if not chunks:
            flags.append("no_chunks")
        kinds = {section.kind for section in sections}
        if SECTION_KIND_ABSTRACT not in kinds:
            flags.append("missing_abstract")
        if SECTION_KIND_REFERENCES not in kinds:
            flags.append("missing_references")
        if all(section.kind == SECTION_KIND_FRONT for section in sections):
            flags.append("no_sections_detected")

    if _looks_like_ocr_noise("\n".join(text for _, text in pages)):
        flags.append("ocr_noise")

    flags.extend(_flag_headless_tables(pages))

    short = sum(1 for chunk in chunks if chunk.char_count < min_chars)
    if short:
        flags.append(f"short_chunks:{short}")
    flags.extend(f"long_chunk:{chunk.chunk_id}" for chunk in chunks if chunk.char_count > max_chars)

    return tuple(sorted(set(flags)))
