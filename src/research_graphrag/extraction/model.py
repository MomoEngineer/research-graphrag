"""Datenmodell des Canonical Paper JSON (Offline-Hybrid, Option B).

Enthält die serialisierbaren Kernstrukturen der Extraktion – :class:`Section`,
:class:`Chunk` und :class:`CanonicalPaper` – ohne Abhängigkeit zu ``pypdf``. So bleiben
die reinen Datenstrukturen unabhängig von der Extraktions-Mechanik testbar; die
Orchestrierung liegt in :mod:`research_graphrag.extraction.pdf`.

Schema-Version **0.5.0**: Ein Paper trägt jetzt seine **Dokumentart** (:data:`DOCUMENT_KIND_FULL`
für ein extrahiertes PDF, :data:`DOCUMENT_KIND_REFERENCE` für einen Referenz-Eintrag ohne
Volltext, siehe docs/adr/0030-reference-entries-in-corpus-phase13.md). Seit Phase 17 / A2 trägt
ein Referenz-Eintrag zusätzlich seine :class:`SourceBibliography` – **additiv** und bewusst
**ohne** Versionssprung, weil ein Sprung jedes PDF neu extrahieren ließe
(docs/adr/0041-author-identity-and-schema.md). ``0.3.0 -> 0.4.0``: Die
Struktur blieb unverändert, der **Inhalts-Contract** wurde geschärft –
der Seitentext wird vor der Analyse normalisiert (Ligaturen repariert, Glyph-Artefakte entfernt)
und die Überschriften-Erkennung verwirft Bibliografie-Zeilen (siehe
docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md); die Anhebung ist zugleich der
Trigger für die Re-Extraktion. ``0.2.0 -> 0.3.0`` gab dem Chunk ``page_end`` – die Seite ist
**kein Segmentierungskriterium** mehr, sondern eine **Provenienz-Range** (``page_number`` =
Startseite, ``page_end`` = Endseite; siehe docs/adr/0013-chunking-refinement-phase7.md).
``0.1.0 -> 0.2.0`` ergänzte die **Section-Hierarchie** (heuristisch), **Identifikatoren**
(DOI/arXiv) sowie **Section-Provenienz je Chunk** und stellte die Chunk-Granularität von „eine
Seite = ein Chunk" auf **abschnitts-/größenbasiert** um. Grundsatz:
docs/adr/0006-canonical-model-phase2-scope.md.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.5.0"
"""Version des Canonical-JSON-Schemas (für spätere Migrationen)."""

SECTION_KIND_FRONT = "front"
SECTION_KIND_ABSTRACT = "abstract"
SECTION_KIND_BODY = "body"
SECTION_KIND_REFERENCES = "references"

DOCUMENT_KIND_FULL = "full"
"""Dokumentart: aus einem PDF extrahierter Volltext."""

DOCUMENT_KIND_REFERENCE = "reference"
"""Dokumentart: Referenz-Eintrag ohne Volltext – nur Titel und Abstract.

Bewusst **kein** Qualitäts-Flag: Flags sind Befunde über *misslungene* Extraktion, dies hier ist
eine Eigenschaft des Dokuments (docs/adr/0030-reference-entries-in-corpus-phase13.md).
"""


@dataclass(frozen=True)
class Section:
    """Heuristisch erkannter Abschnitt eines Papers (Provenienz-Anker)."""

    section_id: str
    title: str
    kind: str
    level: int
    page_number: int
    order: int

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Abschnitt als Canonical-JSON-kompatibles Dict."""
        return {
            "section_id": self.section_id,
            "title": self.title,
            "kind": self.kind,
            "level": self.level,
            "page_number": self.page_number,
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Section:
        """Rekonstruiert einen :class:`Section` aus Canonical JSON."""
        return cls(
            section_id=str(data["section_id"]),
            title=str(data["title"]),
            kind=str(data["kind"]),
            level=int(data["level"]),
            page_number=int(data["page_number"]),
            order=int(data["order"]),
        )


@dataclass(frozen=True)
class Chunk:
    """Kleinste retrievbare Einheit mit Seiten- und Section-Provenienz.

    ``page_number`` ist die **Startseite**, ``page_end`` die **Endseite** des Chunks (identisch,
    solange der Chunk auf einer Seite liegt – siehe
    docs/adr/0013-chunking-refinement-phase7.md). ``section_id``/``section_title`` verweisen auf
    den zugehörigen :class:`Section` (leer, wenn keiner erkannt wurde).
    """

    chunk_id: str
    paper_id: str
    page_number: int
    text: str
    char_count: int
    section_id: str | None = None
    section_title: str = ""
    page_end: int = 0

    def __post_init__(self) -> None:
        """Normalisiert die Seiten-Range: ``page_end`` fällt auf die Startseite zurück."""
        if self.page_end < self.page_number:
            object.__setattr__(self, "page_end", self.page_number)

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Chunk als Canonical-JSON-kompatibles Dict."""
        return {
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "page_number": self.page_number,
            "page_end": self.page_end,
            "text": self.text,
            "char_count": self.char_count,
            "section_id": self.section_id,
            "section_title": self.section_title,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Chunk:
        """Rekonstruiert einen :class:`Chunk` aus Canonical JSON (0.1.0/0.2.0-tolerant)."""
        section_id = data.get("section_id")
        return cls(
            chunk_id=str(data["chunk_id"]),
            paper_id=str(data["paper_id"]),
            page_number=int(data["page_number"]),
            text=str(data["text"]),
            char_count=int(data["char_count"]),
            section_id=None if section_id is None else str(section_id),
            section_title=str(data.get("section_title", "")),
            page_end=int(data.get("page_end", 0)),
        )


@dataclass(frozen=True)
class SourceBibliography:
    """Bibliografische Angaben, die die **Quelldatei selbst** mitbringt.

    Heute trägt nur ein Referenz-Eintrag solche Angaben: Seine Stub-Datei wurde über die eigene
    DOI bzw. arXiv-ID aufgelöst (docs/adr/0029-reference-stub-resolution-phase13.md). Ein PDF
    liefert keine – Autoren werden aus dem PDF-Text bewusst **nicht** heuristisch gelesen
    (Roadmap Phase 17, „Bewusst ausgeschlossen").

    Additiv seit Phase 17 / A2 (docs/adr/0041-author-identity-and-schema.md), ohne Anhebung von
    :data:`SCHEMA_VERSION`.

    Attributes:
        title: Titel in der Schreibweise der Quelle.
        authors: Autoren in Nennreihenfolge (Schreibweise der Quelle).
        author_ids: OpenAlex-Autor-IDs positionsgleich zu ``authors`` (leer = keine Angabe).
        author_orcids: ORCIDs positionsgleich zu ``authors`` (leer = keine Angabe).
        year: Erscheinungsjahr; ``0`` wenn unbekannt.
        venue: Journal, Konferenz oder Verlag.
        url: Landing- oder Volltext-Link.
        source: Dienst, der die Angaben geliefert hat (z. B. ``"OpenAlex"``).
        requested: Die angefragte Kennung (z. B. ``"doi:10.1145/…"``) – der Beleg.
    """

    title: str = ""
    authors: tuple[str, ...] = ()
    author_ids: tuple[str, ...] = ()
    author_orcids: tuple[str, ...] = ()
    year: int = 0
    venue: str = ""
    url: str = ""
    source: str = ""
    requested: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Angaben (Teil des Canonical JSON)."""
        return {
            "title": self.title,
            "authors": list(self.authors),
            "author_ids": list(self.author_ids),
            "author_orcids": list(self.author_orcids),
            "year": self.year,
            "venue": self.venue,
            "url": self.url,
            "source": self.source,
            "requested": self.requested,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceBibliography:
        """Rekonstruiert die Angaben aus Canonical JSON (fehlende Felder bleiben leer)."""
        return cls(
            title=str(data.get("title", "")),
            authors=tuple(str(name) for name in data.get("authors", [])),
            author_ids=tuple(str(value) for value in data.get("author_ids", [])),
            author_orcids=tuple(str(value) for value in data.get("author_orcids", [])),
            year=int(data.get("year", 0) or 0),
            venue=str(data.get("venue", "")),
            url=str(data.get("url", "")),
            source=str(data.get("source", "")),
            requested=str(data.get("requested", "")),
        )


BIBLIOGRAPHY_KEY = "bibliography"
"""Schlüssel der :class:`SourceBibliography` im Canonical JSON (nur bei Referenz-Einträgen)."""


@dataclass(frozen=True)
class CanonicalPaper:
    """Kanonische, serialisierbare Repräsentation eines extrahierten Papers."""

    paper_id: str
    source_uri: str
    source_sha256: str
    n_pages: int
    chunks: tuple[Chunk, ...]
    quality_flags: tuple[str, ...]
    sections: tuple[Section, ...] = ()
    identifiers: Mapping[str, str] = field(default_factory=dict)
    document_kind: str = DOCUMENT_KIND_FULL
    bibliography: SourceBibliography | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Paper als Canonical-JSON-kompatibles Dict.

        ``bibliography`` erscheint nur, wenn die Quelldatei Angaben mitbringt. Ein PDF-Canonical
        bleibt dadurch byte-identisch zur Form vor Phase 17.
        """
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "paper_id": self.paper_id,
            "source_uri": self.source_uri,
            "source_sha256": self.source_sha256,
            "document_kind": self.document_kind,
            "n_pages": self.n_pages,
            "identifiers": {key: self.identifiers[key] for key in sorted(self.identifiers)},
            "quality_flags": list(self.quality_flags),
            "sections": [section.to_dict() for section in self.sections],
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }
        if self.bibliography is not None:
            payload[BIBLIOGRAPHY_KEY] = self.bibliography.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CanonicalPaper:
        """Rekonstruiert ein :class:`CanonicalPaper` aus Canonical JSON (0.1.0-tolerant)."""
        chunks = tuple(Chunk.from_dict(entry) for entry in data["chunks"])
        sections = tuple(Section.from_dict(entry) for entry in data.get("sections", []))
        identifiers = {str(key): str(value) for key, value in data.get("identifiers", {}).items()}
        bibliography = data.get(BIBLIOGRAPHY_KEY)
        return cls(
            paper_id=str(data["paper_id"]),
            source_uri=str(data["source_uri"]),
            source_sha256=str(data["source_sha256"]),
            n_pages=int(data["n_pages"]),
            chunks=chunks,
            quality_flags=tuple(str(flag) for flag in data.get("quality_flags", [])),
            sections=sections,
            identifiers=identifiers,
            # Vor Schema 0.5.0 gab es nur Volltext-Dokumente; ein fehlendes Feld ist deshalb
            # eindeutig deutbar und kein Grund, ein Alt-Artefakt abzulehnen.
            document_kind=str(data.get("document_kind", DOCUMENT_KIND_FULL)),
            bibliography=(
                SourceBibliography.from_dict(bibliography)
                if isinstance(bibliography, Mapping)
                else None
            ),
        )

    def save_json(self, path: str | Path) -> None:
        """Schreibt das Canonical JSON (UTF-8) und legt Elternordner an."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load_json(cls, path: str | Path) -> CanonicalPaper:
        """Lädt ein Canonical JSON und rekonstruiert das :class:`CanonicalPaper`."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


def read_schema_version(path: str | Path) -> str:
    """Liest nur die ``schema_version`` eines Canonical JSON (für Upgrade-Erkennung).

    Returns:
        Die gespeicherte Schema-Version; ``"0.1.0"`` wenn das Feld fehlt (Alt-Artefakt).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return str(data.get("schema_version", "0.1.0"))


def has_source_bibliography(path: str | Path) -> bool:
    """Prüft, ob ein Canonical JSON bereits den Schlüssel :data:`BIBLIOGRAPHY_KEY` trägt.

    Dient der gezielten Nachextraktion von Referenz-Einträgen, die vor Phase 17 gelesen wurden
    (docs/adr/0041-author-identity-and-schema.md). Diese Einträge sind billig neu zu lesen. Eine
    Anhebung von :data:`SCHEMA_VERSION` würde dagegen **jedes** PDF neu extrahieren.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return BIBLIOGRAPHY_KEY in data
