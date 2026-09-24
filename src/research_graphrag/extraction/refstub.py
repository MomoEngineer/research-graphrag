"""Referenz-Einträge ohne Volltext: ``*.refjson`` → :class:`CanonicalPaper` (Phase 13 / R2).

Zweiter Extraktions-Adapter neben :mod:`research_graphrag.extraction.pdf`. Er liest die nativen
Stub-Dateien, die ``python -m scripts.resolve_references`` erzeugt
(docs/adr/0029-reference-stub-resolution-phase13.md), und überführt sie **ohne Heuristik** in das
kanonische Modell – der Weg über eine synthetische PDF wäre ein Verlustkanal ohne Gegenwert
(docs/adr/0030-reference-entries-in-corpus-phase13.md).

Dieses Modul ist die **einzige** Definitionsstelle des Stub-Formats: Konstanten und Leser leben
hier, der schreibende Online-Lauf importiert sie. Wer ein Format schreibt und wer es liest,
teilen sich damit eine Wahrheit.

Drei Eigenschaften eines Referenz-Eintrags sind bewusst gesetzt:

* **Genau ein Chunk** aus Titel *und* Abstract. Fehlt der Abstract, bleibt der Titel – nur so ist
  der Eintrag über seinen Titel auffindbar, und genau das ist die Voraussetzung für die
  Titel-Kanten des Zitationsgraphen.
* **Keine Seitenangabe.** ``page_number`` und ``page_end`` sind ``0``; „Seite 1" wäre eine falsche
  Aussage über die Herkunft. Die Anzeigeform liefert
  :func:`research_graphrag.retrieval.provenance.page_label`.
* **Keine Referenz-Sektion.** Ein Stub ist Ziel von ``CITES``-Kanten, nie deren Quelle.

Seit Phase 17 / A2 reicht der Adapter außerdem die **bibliografischen Angaben** der Datei als
:class:`~research_graphrag.extraction.model.SourceBibliography` an das Canonical weiter. Vorher
gingen Autoren, Jahr, Venue und URL hier verloren, und im Index kamen nur 5 von 366 Autorenlisten
an (Roadmap Phase 17, Befund 2). Mit Format **0.2.0** trägt die Datei je Autor zusätzlich die
OpenAlex-Autor-ID und die ORCID (docs/adr/0041-author-identity-and-schema.md).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.bibliography.model import (
    normalize_openalex_author_id,
    normalize_orcid,
    read_identifier_list,
)
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import (
    DOCUMENT_KIND_REFERENCE,
    SECTION_KIND_ABSTRACT,
    CanonicalPaper,
    Chunk,
    Section,
    SourceBibliography,
)
from research_graphrag.extraction.quality import assess_reference

STUB_SUFFIX = ".refjson"
"""Endung der Stub-Dateien – eigen, damit ``*.pdf``-Globs unberührt bleiben."""

STUB_SCHEMA_VERSION = "0.2.0"
"""Version des Stub-Formats (eigenständig, unabhängig vom Canonical-Schema).

``0.1.0 -> 0.2.0`` (Phase 17 / A2): additiv ``author_ids`` und ``author_orcids``, positionsgleich
zu ``authors``. Der Leser prüft die Version bewusst nicht: Eine 0.1.0-Datei ist eine gültige
0.2.0-Datei ohne Kennungen (docs/adr/0041-author-identity-and-schema.md)."""

ABSTRACT_SECTION_TITLE = "Abstract"
"""Titel der einzigen Section eines Referenz-Eintrags."""

MAX_TITLE_CHARS = 400
"""Längengrenze des Titels (fremde Eingabe, wie beim Schreiben der Datei)."""

MAX_ABSTRACT_CHARS = 5000
"""Längengrenze des Abstracts (fremde Eingabe, wie beim Schreiben der Datei)."""


@dataclass(frozen=True)
class ReferenceStub:
    """Der Inhalt einer Stub-Datei, bereinigt und ohne Interpretation.

    Attributes:
        title: Titel des Werks (Pflichtangabe – ohne ihn entsteht kein Eintrag).
        authors: Autoren in Nennreihenfolge.
        year: Erscheinungsjahr; ``0`` wenn unbekannt.
        venue: Journal, Konferenz oder Verlag.
        doi: DOI ohne URL-Präfix.
        arxiv_id: arXiv-Identifikator ohne Version.
        url: Landing- oder Volltext-Link.
        abstract: Abstract als Fließtext; leer, wenn keine Quelle einen lieferte.
        author_ids: OpenAlex-Autor-IDs positionsgleich zu ``authors`` (leer = keine Angabe).
        author_orcids: ORCIDs positionsgleich zu ``authors`` (leer = keine Angabe).
        source: Dienst, der die Angaben lieferte (``"OpenAlex"``/``"arXiv"``).
        requested: Die angefragte Kennung (``"doi:…"``/``"arxiv:…"``).
    """

    title: str
    authors: tuple[str, ...] = ()
    year: int = 0
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    abstract: str = ""
    author_ids: tuple[str, ...] = ()
    author_orcids: tuple[str, ...] = ()
    source: str = ""
    requested: str = ""

    @property
    def identifiers(self) -> dict[str, str]:
        """Die externen Identifikatoren in der Form des Canonical-Modells."""
        found = {"doi": self.doi, "arxiv": self.arxiv_id}
        return {key: value for key, value in found.items() if value}

    @property
    def text(self) -> str:
        """Der Text des einzigen Chunks: Titel und Abstract."""
        return f"{self.title}\n\n{self.abstract}".strip() if self.abstract else self.title

    @property
    def bibliography(self) -> SourceBibliography:
        """Die bibliografischen Angaben der Datei in der Form des Canonical-Modells."""
        return SourceBibliography(
            title=self.title,
            authors=self.authors,
            author_ids=self.author_ids,
            author_orcids=self.author_orcids,
            year=self.year,
            venue=self.venue,
            url=self.url,
            source=self.source,
            requested=self.requested,
        )


def _clean(value: Any, *, limit: int) -> str:
    """Bereinigt einen fremden Wert (einzeilig, druckbar, längenbegrenzt)."""
    text = value if isinstance(value, str) else ""
    printable = "".join(char if char.isprintable() else " " for char in text)
    return " ".join(printable.split())[:limit].strip()


def parse_stub(raw: bytes) -> ReferenceStub:
    """Liest eine Stub-Datei und prüft sie gegen das erwartete Format.

    Die Datei stammt zwar aus dem eigenen Werkzeug, kann aber von Hand bearbeitet worden sein
    (der Abstract wird genau so nachgetragen) – geprüft und bereinigt wird deshalb vollständig.

    Args:
        raw: Dateiinhalt der ``*.refjson``.

    Returns:
        Den bereinigten Inhalt.

    Raises:
        DomainError: ``parse_error`` wenn die Datei kein JSON-Objekt ist, eine fremde Dokumentart
            trägt oder keinen Titel enthält (siehe docs/error-model.md).
    """
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DomainError(ErrorCode.PARSE_ERROR, f"Referenz-Eintrag nicht lesbar: {exc}") from exc
    if not isinstance(data, dict):
        raise DomainError(ErrorCode.PARSE_ERROR, "Referenz-Eintrag ist kein JSON-Objekt.")
    kind = str(data.get("document_kind", ""))
    if kind != DOCUMENT_KIND_REFERENCE:
        raise DomainError(
            ErrorCode.PARSE_ERROR,
            f"Unerwartete Dokumentart '{kind}' – erwartet '{DOCUMENT_KIND_REFERENCE}'.",
        )
    title = _clean(data.get("title"), limit=MAX_TITLE_CHARS)
    if not title:
        raise DomainError(ErrorCode.PARSE_ERROR, "Referenz-Eintrag ohne Titel.")

    raw_authors = data.get("authors")
    names = raw_authors if isinstance(raw_authors, list) else []
    cleaned_names = [_clean(name, limit=200) for name in names]
    authors = tuple(name for name in cleaned_names if name)
    # Die Kennungen stehen positionsgleich zu den **rohen** Namen. Fällt ein leerer Name heraus,
    # wäre die Zuordnung verschoben – dann entfallen die Kennungen ganz (Präzision vor Recall).
    aligned = len(authors) == len(cleaned_names)
    year = data.get("year")
    return ReferenceStub(
        title=title,
        authors=authors,
        year=year if isinstance(year, int) and year > 0 else 0,
        venue=_clean(data.get("venue"), limit=MAX_TITLE_CHARS),
        doi=_clean(data.get("doi"), limit=200),
        arxiv_id=_clean(data.get("arxiv_id"), limit=100),
        url=_clean(data.get("url"), limit=500),
        abstract=_clean(data.get("abstract"), limit=MAX_ABSTRACT_CHARS),
        author_ids=(
            read_identifier_list(authors, data.get("author_ids"), normalize_openalex_author_id)
            if aligned
            else ()
        ),
        author_orcids=(
            read_identifier_list(authors, data.get("author_orcids"), normalize_orcid)
            if aligned
            else ()
        ),
        source=_clean(data.get("source"), limit=100),
        requested=_clean(data.get("requested"), limit=300),
    )


def extract_stub(path: str | Path, *, source_uri: str | None = None) -> CanonicalPaper:
    """Überführt eine Stub-Datei in ein :class:`CanonicalPaper`.

    Args:
        path: Dateisystempfad zur ``*.refjson``.
        source_uri: Optionale Quell-URI für die Provenienz; Standard ist die ``file://``-URI
            des aufgelösten Pfads.

    Returns:
        Ein :class:`CanonicalPaper` der Dokumentart
        :data:`~research_graphrag.extraction.model.DOCUMENT_KIND_REFERENCE` mit genau einer
        Section und genau einem Chunk.

    Raises:
        DomainError: ``invalid_input`` bei leerem Pfad; ``not_found`` wenn die Datei fehlt;
            ``parse_error`` bei unbrauchbarem Inhalt; ``internal_error`` bei OS-Lesefehlern
            (siehe docs/error-model.md).
    """
    if not str(path).strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leerer Pfad zum Referenz-Eintrag.")

    stub_path = Path(path)
    uri = source_uri or stub_path.resolve().as_uri()

    if not stub_path.is_file():
        raise DomainError(
            ErrorCode.NOT_FOUND, f"Referenz-Eintrag nicht gefunden: {stub_path}", {"uri": uri}
        )
    try:
        raw = stub_path.read_bytes()
    except OSError as exc:
        raise DomainError(
            ErrorCode.INTERNAL_ERROR, f"Referenz-Eintrag nicht lesbar: {exc}", {"uri": uri}
        ) from exc

    stub = parse_stub(raw)
    source_sha256 = hashlib.sha256(raw).hexdigest()
    paper_id = source_sha256[:16]
    return canonical_from_stub(stub, paper_id=paper_id, source_uri=uri, source_sha256=source_sha256)


def canonical_from_stub(
    stub: ReferenceStub, *, paper_id: str, source_uri: str, source_sha256: str
) -> CanonicalPaper:
    """Baut das :class:`CanonicalPaper` eines Referenz-Eintrags (deterministisch, ohne Heuristik).

    Args:
        stub: Der gelesene Stub-Inhalt.
        paper_id: Stabile Paper-ID (sha256-Präfix der Datei, wie bei PDFs).
        source_uri: Quellverweis für die Provenienz.
        source_sha256: Hash der Quelldatei.

    Returns:
        Ein Paper mit einer Abstract-Section, einem Chunk, den bibliografischen Angaben der
        Datei und – falls der Abstract fehlt – dem Befund ``reference_without_abstract``.
    """
    section = Section(
        section_id=f"{paper_id}-s0001",
        title=ABSTRACT_SECTION_TITLE,
        kind=SECTION_KIND_ABSTRACT,
        level=1,
        page_number=0,
        order=0,
    )
    text = stub.text
    chunk = Chunk(
        chunk_id=f"{paper_id}-c0001",
        paper_id=paper_id,
        page_number=0,
        text=text,
        char_count=len(text),
        section_id=section.section_id,
        section_title=section.title,
        page_end=0,
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=source_uri,
        source_sha256=source_sha256,
        n_pages=0,
        chunks=(chunk,),
        quality_flags=assess_reference(has_abstract=bool(stub.abstract)),
        sections=(section,),
        identifiers=stub.identifiers,
        document_kind=DOCUMENT_KIND_REFERENCE,
        bibliography=stub.bibliography,
    )
