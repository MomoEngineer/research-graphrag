"""Heuristische Struktur-Erkennung und Identifikator-Extraktion (Phase 2, Option B).

Arbeitet auf **reinem Seitentext** (unabhängig von ``pypdf``) und ist damit ohne PDF-Fixtures
deterministisch testbar. Erkennt Überschriften (numerierte Überschriften, bekannte
Sektions-Schlüsselwörter, kurze Versal-Zeilen), gruppiert den Fließtext in :class:`ContentBlock`
je Absatz und extrahiert **DOI/arXiv** per Regex. Grundsatz und Grenzen (keine Bounding-Boxes,
kein tiefes Referenz-Parsing): docs/adr/0006-canonical-model-phase2-scope.md.

Gegen die **Übersegmentierung** der Heuristik (Pseudocode-Zeilen, Tabellenzellen, Running Header
wurden als Überschriften gelesen) wirken zwei Stufen aus
docs/adr/0013-chunking-refinement-phase7.md:

- **Reject-Regeln** in :func:`detect_heading` für eindeutige Nicht-Überschriften (Mathematik-/
  Pseudocode-Symbole, tabellarische Zeilen, Silbentrennungsreste, ziffernlastige Zellen). Sie
  greifen bewusst **erst nach** dem Schlüsselwort-Zweig, damit bekannte Abschnitte
  (``Abstract``/``References`` …) niemals verworfen werden.
- **Section-Absorption** in :func:`analyze`: Abschnitte mit zu wenig eigenem Inhalt werden in
  ihren Vorgänger zurückgeführt (evidenzbasiert über die gemessene Textmasse).

Gegen **Bibliografie-Rauschen** in den Abschnittstiteln wirken drei weitere Stufen aus
docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md: eine Regel **vor** dem
Schlüsselwort-Zweig (kleingeschriebene Fließtextreste wie ``methods.`` sind keine Abschnitte),
vier weitere Zeilenregeln danach (Satzpunkt-Ende, URL-/DOI-Marker, ``et al``, JSON-/Code-Zeichen)
und der **Referenzkontext** – innerhalb der Bibliografie ist der Numerierungs-Zweig abgeschaltet,
weil dort die laufende Nummer eines Literatureintrags sonst als Abschnittsnummer gelesen wird.
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

MIN_SECTION_CHARS = 200
"""Mindest-Textmasse eines eigenständigen Abschnitts (spiegelt die Chunk-Untergrenze
``chunking.MIN_CHARS``; hier eigenständig definiert, damit kein Import-Zyklus entsteht)."""

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

# Reject-Regeln gegen Übersegmentierung (docs/adr/0013-chunking-refinement-phase7.md).
_COLUMN_SPLIT = re.compile(r" {2,}")
_MIN_COLUMNS = 3
_MATH_SYMBOLS = re.compile(r"[\u2190-\u21ff\u2200-\u22ff\U0001d400-\U0001d7ff]")
"""Pfeile, mathematische Operatoren und mathematische Alphanumerics – ein starkes Signal für
Pseudocode-/Formelzeilen (``4 𝑥 ←𝑞.𝑝𝑜𝑝();``), die keine Überschriften sind."""
_REJECT_TAIL = ("-", ";", ",", ".")
_MAX_DIGIT_RATIO = 0.3

# Bibliografie-Rejects (docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md).
_BIB_MARKERS = ("http://", "https://", "www.", "doi:", "doi.org/", "arxiv:")
"""Marker eines Literatureintrags bzw. einer Linkzeile – keine Überschrift."""
_CITATION = re.compile(r"\bet\s+al\b", re.IGNORECASE)
_CODE_CHARS = frozenset('"{}[]=<>|')
"""Zeichen aus JSON-/Code-Fragmenten und Formeln, die in Überschriften nicht vorkommen."""

_DOI = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
_ARXIV = re.compile(r"arxiv[:\s]\s*(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)


def looks_tabular(line: str) -> bool:
    """Erkennt eine tabellarisch anmutende Zeile (≥ 3 Felder über Tab/Mehrfach-Leerzeichen)."""
    if "\t" in line:
        return True
    return len([field for field in _COLUMN_SPLIT.split(line.strip()) if field]) >= _MIN_COLUMNS


def _is_rejected(text: str, core: str) -> bool:
    """Prüft, ob eine Zeile eindeutig **keine** Überschrift ist (siehe Modul-Docstring)."""
    if _MATH_SYMBOLS.search(text) or looks_tabular(text):
        return True
    if text.rstrip().endswith(_REJECT_TAIL):
        return True
    lowered = text.lower()
    if any(marker in lowered for marker in _BIB_MARKERS):
        return True
    if _CITATION.search(text):
        return True
    if any(char in _CODE_CHARS for char in text):
        return True
    compact = [char for char in core if not char.isspace()]
    if not compact:
        return True
    digits = sum(1 for char in compact if char.isdigit() or char == "%")
    return digits / len(compact) > _MAX_DIGIT_RATIO


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


def detect_heading(line: str, *, in_references: bool = False) -> _Heading | None:
    """Prüft, ob eine (bereits getrimmte) Zeile eine Überschrift ist.

    Reihenfolge der Prüfungen: Zuerst wird ein **kleingeschriebener Fließtextrest** mit
    Satzzeichen abgewiesen (``methods.`` ist kein Abschnitt, auch wenn ``methods`` ein bekanntes
    Schlüsselwort ist). Danach greifen die bekannten Sektions-Schlüsselwörter (``Abstract``,
    ``References`` …), die in üblicher Schreibweise nie verworfen werden. Erst zuletzt greifen die
    Reject-Regeln (:func:`_is_rejected`), die die beiden unscharfen Zweige (Numerierung,
    Versalzeile) gegen Pseudocode, Tabellenzellen, Silbentrennungsreste und Bibliografie-Zeilen
    absichern.

    Args:
        line: Getrimmte Zeile des Seitentexts.
        in_references: Ob die Zeile innerhalb eines Referenzabschnitts steht. Dort ist der
            Numerierungs-Zweig abgeschaltet, weil eine numerierte Zeile ein Literatureintrag ist
            (docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md).

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

    if not numbered and core[:1].islower() and text.rstrip().endswith(_SENTENCE_TAIL):
        # Fließtextrest wie „methods." – muss VOR dem Schlüsselwort-Zweig greifen, weil er sonst
        # als bekannter Abschnitt gilt und den Folgetext an sich zieht (ADR 0015). Echte
        # Überschriften beginnen nicht mit einem Kleinbuchstaben.
        return None

    core_norm = re.sub(r"\s+", " ", core.rstrip(" .:—-")).lower()

    if core_norm in _KNOWN_SECTIONS:
        return _Heading(title=core or text, kind=_KNOWN_SECTIONS[core_norm], level=level)
    if core_norm.startswith("abstract") and len(core_norm) <= 12:
        return _Heading(title="Abstract", kind=SECTION_KIND_ABSTRACT, level=level)

    if _is_rejected(text, core):
        return None

    words = core.split()
    if (
        numbered
        and not in_references
        and core
        and len(words) <= 8
        and not core.rstrip().endswith(_SENTENCE_TAIL)
    ):
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


def _absorb_short_sections(
    sections: Sequence[Section], blocks: Sequence[ContentBlock]
) -> tuple[tuple[Section, ...], tuple[ContentBlock, ...]]:
    """Führt inhaltsarme Abschnitte in ihren Vorgänger zurück (Anti-Übersegmentierung).

    Ein Abschnitt wird absorbiert, wenn seine **eigene** Textmasse unter
    :data:`MIN_SECTION_CHARS` liegt. Geschützt sind ``front``, ``abstract`` und ``references``
    (sie tragen Qualitäts-Flags und den Zitationsgraphen); außerdem wird nie **in** einen
    ``references``-Abschnitt hinein absorbiert, damit Anhänge nicht als Bibliografie gelten.
    Die überlebenden Abschnitte behalten ihre ``section_id``/``order`` (die Numerierung bleibt
    damit auf die erkannten Überschriften rückführbar und weist Lücken auf).

    Args:
        sections: Erkannte Abschnitte in Lese-Reihenfolge.
        blocks: Zugeordnete Fließtext-Blöcke.

    Returns:
        Die verbleibenden Abschnitte und die auf sie umgehängten Blöcke.
    """
    own_chars: dict[str, int] = {}
    for block in blocks:
        own_chars[block.section_id] = own_chars.get(block.section_id, 0) + len(block.text.strip())

    remap: dict[str, str] = {}
    survivors: list[Section] = []
    for section in sections:
        previous = survivors[-1] if survivors else None
        absorbable = (
            section.kind == SECTION_KIND_BODY
            and own_chars.get(section.section_id, 0) < MIN_SECTION_CHARS
            and previous is not None
            and previous.kind != SECTION_KIND_REFERENCES
        )
        if absorbable and previous is not None:
            remap[section.section_id] = previous.section_id
            continue
        remap[section.section_id] = section.section_id
        survivors.append(section)

    merged = tuple(
        ContentBlock(block.page_number, remap[block.section_id], block.text) for block in blocks
    )
    return tuple(survivors), merged


def analyze(paper_id: str, pages: Sequence[tuple[int, str]]) -> Sectioning:
    """Erkennt Abschnitte und gruppiert den Fließtext absatzweise.

    Inhaltsarme Abschnitte werden anschließend in ihren Vorgänger zurückgeführt
    (:func:`_absorb_short_sections`, docs/adr/0013-chunking-refinement-phase7.md).

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
    in_references = False

    for page_number, text in pages:
        paragraph: list[str] = []
        for raw_line in text.split("\n"):
            stripped = raw_line.strip()
            if not stripped:
                if paragraph:
                    blocks.append(ContentBlock(page_number, current_id, " ".join(paragraph)))
                    paragraph = []
                continue
            heading = detect_heading(stripped, in_references=in_references)
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
            in_references = heading.kind == SECTION_KIND_REFERENCES
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

    kept, merged = _absorb_short_sections(sections, blocks)
    return Sectioning(sections=kept, blocks=merged)
