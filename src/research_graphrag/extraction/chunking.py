"""Abschnitts-/größenbasiertes Chunking (Phase 2, verfeinert in Phase 7 / A3).

Wandelt die absatzweisen :class:`~research_graphrag.extraction.structure.ContentBlock` in
retrievbare :class:`~research_graphrag.extraction.model.Chunk` um. Leitlinien:

- **Zielfenster** ``[MIN_CHARS, MAX_CHARS]``: Absätze werden bis ``MAX_CHARS`` zusammengefasst.
- **Section-Grenze**: Chunks überschreiten keine Abschnittswechsel.
- **Seite ist keine Grenze, sondern Provenienz**: Ein Chunk darf über einen Seitenumbruch laufen
  und trägt dann die Range ``page_number`` (Startseite) … ``page_end`` (Endseite). Die harte
  Seitengrenze aus Phase 2 zerschnitt rund vier von fünf Seitenumbrüchen mitten im Satz
  (docs/adr/0013-chunking-refinement-phase7.md).
- **Satz-Split**: übergroße Absätze werden an Satzgrenzen getrennt; ein einzelner übergroßer Satz
  bleibt erhalten und wird später als ``long_chunk`` markiert (siehe
  :mod:`research_graphrag.extraction.quality`). Reste unterhalb von ``MIN_CHARS`` gehen in die
  aggregierte Kennzahl ``short_chunks`` ein.

Das Verfahren ist deterministisch.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from research_graphrag.extraction.model import Chunk
from research_graphrag.extraction.structure import ContentBlock

MIN_CHARS = 200
"""Untergrenze des Chunk-Zielfensters (kürzere Chunks zählen in ``short_chunks``)."""

MAX_CHARS = 1500
"""Obergrenze des Chunk-Zielfensters (längere Chunks werden als ``long_chunk`` markiert)."""

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class _Record:
    """Interner Chunk-Zwischenstand (vor der ID-Vergabe)."""

    page_start: int
    page_end: int
    section_id: str
    text: str


def _split_to_max(paragraph: str, max_chars: int) -> list[str]:
    """Zerlegt einen übergroßen Absatz an Satzgrenzen (übergroße Einzelsätze bleiben erhalten)."""
    if len(paragraph) <= max_chars:
        return [paragraph]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT.split(paragraph):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence)
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = sentence if not current else f"{current} {sentence}"
    if current:
        pieces.append(current)
    return pieces


def build_chunks(
    paper_id: str,
    blocks: Sequence[ContentBlock],
    title_by_id: Mapping[str, str],
    *,
    max_chars: int = MAX_CHARS,
) -> tuple[Chunk, ...]:
    """Baut größenbegrenzte, sectiontreue Chunks mit Seiten-Range aus Fließtext-Blöcken.

    Der Puffer wird ausschließlich bei **Abschnittswechsel** oder **Größenüberschreitung**
    geleert; ein Seitenumbruch erweitert lediglich die Provenienz-Range.

    Args:
        paper_id: Paper-ID (Grundlage der ``chunk_id``-Vergabe).
        blocks: Absatzweise Blöcke in Lese-Reihenfolge (siehe
            :func:`research_graphrag.extraction.structure.analyze`).
        title_by_id: Abbildung ``section_id`` → Abschnittstitel (für die Chunk-Provenienz).
        max_chars: Obergrenze des Zielfensters.

    Returns:
        Die Chunks in stabiler Lese-Reihenfolge mit fortlaufender ``chunk_id``.
    """
    records: list[_Record] = []
    buf_parts: list[str] = []
    buf_start: int | None = None
    buf_end: int | None = None
    buf_section: str | None = None

    def flush() -> None:
        nonlocal buf_parts, buf_start, buf_end, buf_section
        if buf_parts and buf_start is not None and buf_end is not None and buf_section is not None:
            text = "\n\n".join(buf_parts).strip()
            if text:
                records.append(_Record(buf_start, buf_end, buf_section, text))
        buf_parts, buf_start, buf_end, buf_section = [], None, None, None

    for block in blocks:
        paragraph = block.text.strip()
        if not paragraph:
            continue
        if buf_parts and block.section_id != buf_section:
            flush()
        for piece in _split_to_max(paragraph, max_chars):
            projected = len("\n\n".join([*buf_parts, piece]))
            if buf_parts and projected > max_chars:
                flush()
            if not buf_parts:
                buf_start, buf_section = block.page_number, block.section_id
            buf_end = block.page_number
            buf_parts.append(piece)
    flush()

    return tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index:04d}",
            paper_id=paper_id,
            page_number=record.page_start,
            page_end=record.page_end,
            text=record.text,
            char_count=len(record.text),
            section_id=record.section_id,
            section_title=title_by_id.get(record.section_id, ""),
        )
        for index, record in enumerate(records)
    )
