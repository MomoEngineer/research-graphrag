"""Heuristische Struktur-Erkennung und Identifikator-Extraktion (Phase 2, Option B).

Arbeitet auf **reinem Seitentext** (unabhängig von ``pypdf``) und ist damit ohne PDF-Fixtures
deterministisch testbar. Erkennt Überschriften (numerierte Überschriften, bekannte
Sektions-Schlüsselwörter, kurze Versal-Zeilen), gruppiert den Fließtext in :class:`ContentBlock`
je Absatz und extrahiert **DOI/arXiv** per Regex. Grundsatz und Grenzen (keine Bounding-Boxes,
kein tiefes Referenz-Parsing): docs/adr/0006-canonical-model-phase2-scope.md.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from research_graphrag.extraction.model import (
    SECTION_KIND_ABSTRACT,
    SECTION_KIND_BODY,
    SECTION_KIND_FRONT,
    SECTION_KIND_REFERENCES,
    Section,
)

_MAX_HEADING_LEN = 90

# Bekannte Sektions-Titel (normalisiert) → Klassifikation.
_KNOWN_SECTIONS: dict[str, str] = {
    "abstract": SECTION_KIND_ABSTRACT,
    "introduction": SECTION_KIND_BODY,
    "background": SECTION_KIND_BODY,
    "related work": SECTION_KIND_BODY,
    "related works": SECTION_KIND_BODY,
    "motivation": SECTION_KIND_BODY,
    "preliminaries": SECTION_KIND_BODY,
    "problem formulation": SECTION_KIND_BODY,
    "methodology": SECTION_KIND_BODY,
    "methods": SECTION_KIND_BODY,
    "method": SECTION_KIND_BODY,
    "materials and methods": SECTION_KIND_BODY,
    "approach": SECTION_KIND_BODY,
    "proposed approach": SECTION_KIND_BODY,
    "proposed method": SECTION_KIND_BODY,
    "model": SECTION_KIND_BODY,
    "models": SECTION_KIND_BODY,
    "system model": SECTION_KIND_BODY,
    "experiments": SECTION_KIND_BODY,
    "experimental setup": SECTION_KIND_BODY,
    "experimental results": SECTION_KIND_BODY,
    "experiments and results": SECTION_KIND_BODY,
    "evaluation": SECTION_KIND_BODY,
    "results": SECTION_KIND_BODY,
    "results and discussion": SECTION_KIND_BODY,
    "discussion": SECTION_KIND_BODY,
    "analysis": SECTION_KIND_BODY,
    "ablation study": SECTION_KIND_BODY,
    "limitations": SECTION_KIND_BODY,
    "threats to validity": SECTION_KIND_BODY,
    "conclusion": SECTION_KIND_BODY,
    "conclusions": SECTION_KIND_BODY,
    "conclusion and future work": SECTION_KIND_BODY,
    "conclusions and future work": SECTION_KIND_BODY,
    "future work": SECTION_KIND_BODY,
    "acknowledgements": SECTION_KIND_BODY,
    "acknowledgments": SECTION_KIND_BODY,
    "acknowledgement": SECTION_KIND_BODY,
    "acknowledgment": SECTION_KIND_BODY,
    "appendix": SECTION_KIND_BODY,
    "references": SECTION_KIND_REFERENCES,
    "bibliography": SECTION_KIND_REFERENCES,
}

_NUM_PREFIX = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+")
_ROMAN_PREFIX = re.compile(r"^\s*([IVXLC]+)[.)]\s+")
_SENTENCE_TAIL = (".", "!", "?", ",", ";")

_DOI = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
_ARXIV = re.compile(r"arxiv[:\s]\s*(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)


@dataclass(frozen=True)
class _Heading:
    """Ergebnis der Überschriften-Erkennung einer einzelnen Zeile."""

    title: str
    kind: str
    level: int


@dataclass(frozen=True)
class ContentBlock:
    """Ein Fließtext-Absatz mit Seiten- und Section-Zuordnung (Chunker-Eingabe)."""

    page_number: int
    section_id: str
    text: str


@dataclass(frozen=True)
class Sectioning:
    """Ergebnis der Struktur-Analyse: Abschnitte plus zugeordnete Fließtext-Blöcke."""

    sections: tuple[Section, ...]
    blocks: tuple[ContentBlock, ...]

    def title_by_id(self) -> dict[str, str]:
        """Bildet ``section_id`` auf den Abschnittstitel ab (für die Chunk-Provenienz)."""
        return {section.section_id: section.title for section in self.sections}


def detect_heading(line: str) -> _Heading | None:
    """Prüft, ob eine (bereits getrimmte) Zeile eine Überschrift ist.

    Returns:
        Ein :class:`_Heading` mit Titel/Klassifikation/Ebene oder ``None``.
    """
    text = line.strip()
    if not text or len(text) > _MAX_HEADING_LEN:
        return None

    level = 1
    core = text
    numbered = False
    num_match = _NUM_PREFIX.match(text)
    if num_match:
        numbered = True
        level = num_match.group(1).count(".") + 1
        core = text[num_match.end() :].strip()
    else:
        roman_match = _ROMAN_PREFIX.match(text)
        if roman_match:
            numbered = True
            core = text[roman_match.end() :].strip()

    core_norm = re.sub(r"\s+", " ", core.rstrip(" .:—-")).lower()

    if core_norm in _KNOWN_SECTIONS:
        return _Heading(title=core or text, kind=_KNOWN_SECTIONS[core_norm], level=level)
    if core_norm.startswith("abstract") and len(core_norm) <= 12:
        return _Heading(title="Abstract", kind=SECTION_KIND_ABSTRACT, level=level)

    words = core.split()
    if numbered and core and len(words) <= 8 and not core.rstrip().endswith(_SENTENCE_TAIL):
        return _Heading(title=core, kind=SECTION_KIND_BODY, level=level)

    letters = [char for char in text if char.isalpha()]
    if letters and text.upper() == text and len(words) <= 6 and len(letters) >= 3:
        kind = SECTION_KIND_REFERENCES if core_norm in _KNOWN_SECTIONS else SECTION_KIND_BODY
        return _Heading(title=text.title(), kind=kind, level=1)
    return None


def extract_identifiers(text: str) -> dict[str, str]:
    """Extrahiert DOI/arXiv-Identifikatoren aus dem Volltext (jeweils erster Treffer)."""
    identifiers: dict[str, str] = {}
    doi_match = _DOI.search(text)
    if doi_match:
        identifiers["doi"] = doi_match.group(0).rstrip(".,;)")
    arxiv_match = _ARXIV.search(text)
    if arxiv_match:
        identifiers["arxiv"] = arxiv_match.group(1)
    return identifiers


def analyze(paper_id: str, pages: Sequence[tuple[int, str]]) -> Sectioning:
    """Erkennt Abschnitte und gruppiert den Fließtext absatzweise.

    Args:
        paper_id: Paper-ID (Grundlage der ``section_id``-Vergabe).
        pages: Reihenfolge aus ``(Seitennummer, Seitentext)``.

    Returns:
        Ein :class:`Sectioning`; Text vor der ersten Überschrift bildet einen ``front``-Abschnitt.
        Werden keine Überschriften erkannt, ist der gesamte Text ein ``front``-Abschnitt.
    """
    front_id = f"{paper_id}-s000"
    sections: list[Section] = []
    blocks: list[ContentBlock] = []
    current_id = front_id
    heading_count = 0

    for page_number, text in pages:
        paragraph: list[str] = []
        for raw_line in text.split("\n"):
            stripped = raw_line.strip()
            if not stripped:
                if paragraph:
                    blocks.append(ContentBlock(page_number, current_id, " ".join(paragraph)))
                    paragraph = []
                continue
            heading = detect_heading(stripped)
            if heading is None:
                paragraph.append(stripped)
                continue
            if paragraph:
                blocks.append(ContentBlock(page_number, current_id, " ".join(paragraph)))
                paragraph = []
            heading_count += 1
            section = Section(
                section_id=f"{paper_id}-s{heading_count:03d}",
                title=heading.title,
                kind=heading.kind,
                level=heading.level,
                page_number=page_number,
                order=heading_count,
            )
            sections.append(section)
            current_id = section.section_id
        if paragraph:
            blocks.append(ContentBlock(page_number, current_id, " ".join(paragraph)))

    front_blocks = [block for block in blocks if block.section_id == front_id]
    if front_blocks or not sections:
        front_page = front_blocks[0].page_number if front_blocks else (pages[0][0] if pages else 1)
        front = Section(
            section_id=front_id,
            title="",
            kind=SECTION_KIND_FRONT,
            level=0,
            page_number=front_page,
            order=0,
        )
        sections.insert(0, front)

    return Sectioning(sections=tuple(sections), blocks=tuple(blocks))
