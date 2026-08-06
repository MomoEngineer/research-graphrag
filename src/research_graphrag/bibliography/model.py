"""Datentypen der bibliografischen Metadaten (Phase 12 / K1).

Zwei Typen mit klarer Aufgabenteilung (docs/adr/0025-citable-paper-metadata.md):

* :class:`MetadataRecord` ist die Aussage **einer** Quelle über ein Paper. Er trägt seine
  Herkunft (:data:`ORIGIN_PRECEDENCE`), eine Konfidenzstufe und einen nachvollziehbaren Beleg.
* :class:`PaperMetadata` ist der daraus **feldweise aufgelöste** Datensatz, mit dem zitiert wird.
  Er weist in ``origins`` je Feld aus, welche Quelle gewonnen hat – ohne diese Angabe wäre nicht
  prüfbar, ob eine DOI aus kuratierter Hand oder aus einer Regex stammt.

Das Modul ist bewusst frei von Datei-, Netz- und Index-Zugriffen.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

ORIGIN_MANUAL = "manual"
"""Von Hand in ``metadata/paper_metadata.json`` gepflegt (höchster Vorrang)."""

ORIGIN_CURATED = "curated"
"""Aus einer kuratierten Zeile der Übersicht übernommen."""

ORIGIN_RESOLVED = "resolved"
"""Über eine externe Metadatenquelle aufgelöst (docs/adr/0026-online-metadata-resolution.md)."""

ORIGIN_EXTRACTED = "extracted"
"""Per Regex aus dem PDF gelesen (niedrigster Vorrang)."""

ORIGIN_PRECEDENCE: tuple[str, ...] = (
    ORIGIN_MANUAL,
    ORIGIN_CURATED,
    ORIGIN_RESOLVED,
    ORIGIN_EXTRACTED,
)
"""Vorrang der Herkünfte, absteigend – die Reihenfolge der feldweisen Auflösung."""

CONFIDENCE_STRONG = "strong"
"""Der Datensatz ist eindeutig belegt (kuratiert, exakter Identifikator-Treffer)."""

CONFIDENCE_WEAK = "weak"
"""Der Datensatz ist plausibel, aber nicht eindeutig belegt (z. B. Titel-Ähnlichkeit)."""

CONFIDENCE_NONE = "none"
"""Kein Beleg – der Wert ist eine bloße Beobachtung."""

CONFIDENCES: tuple[str, ...] = (CONFIDENCE_NONE, CONFIDENCE_WEAK, CONFIDENCE_STRONG)
"""Konfidenzstufen **aufsteigend**; bewusst keine Zahl (keine Pseudo-Wahrscheinlichkeit)."""

METADATA_FIELDS: tuple[str, ...] = (
    "title",
    "authors",
    "year",
    "venue",
    "doi",
    "arxiv_id",
    "url",
)
"""Die feldweise aufgelösten Datenfelder (Reihenfolge = Ausgabereihenfolge)."""

CITABLE_FIELDS: tuple[str, ...] = ("title", "authors", "year")
"""Pflichtfelder einer vollständigen Literaturangabe (siehe :meth:`PaperMetadata.is_citable`)."""

_KEY_SEPARATORS = re.compile(r"[^A-Za-z0-9]+")
_STOPWORDS_IN_KEY = frozenset({"a", "an", "the", "on", "of", "for", "and", "in", "to"})
_TRANSLITERATION = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
)


def _ascii_fold(text: str) -> str:
    """Bildet Umlaute/Akzente auf ASCII ab (für stabile, dateinamensichere Zitierschlüssel).

    Deutsche Umlaute werden **transliteriert** (``ü`` → ``ue``), nicht nur entkleidet – das ist
    die im deutschsprachigen Raum übliche Schreibweise eines Nachnamens ohne Sonderzeichen.
    Alle übrigen diakritischen Zeichen werden nach NFKD verworfen.
    """
    transliterated = text.translate(_TRANSLITERATION)
    decomposed = unicodedata.normalize("NFKD", transliterated)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def surname_of(author: str) -> str:
    """Ermittelt den Nachnamen aus einer Autorenangabe.

    Unterstützt beide gängigen Schreibweisen: ``"Nachname, Vorname"`` und ``"Vorname Nachname"``.
    Bei mehrteiligen Namen gilt das **letzte** Token als Nachname; Namenspräfixe (``van``,
    ``de`` …) werden bewusst nicht gesondert behandelt (dokumentierte Grenze, siehe
    docs/adr/0025-citable-paper-metadata.md).
    """
    cleaned = " ".join(author.split())
    if not cleaned:
        return ""
    if "," in cleaned:
        return cleaned.split(",", 1)[0].strip()
    return cleaned.rsplit(" ", 1)[-1]


@dataclass(frozen=True)
class MetadataRecord:
    """Die Aussage **einer** Quelle über ein Paper.

    Attributes:
        paper_id: Stabile Paper-ID des Korpus.
        origin: Herkunft aus :data:`ORIGIN_PRECEDENCE`.
        title: Titel des Papers.
        authors: Autoren in Nennreihenfolge (Schreibweise der Quelle).
        year: Erscheinungsjahr; ``0`` wenn unbekannt.
        venue: Journal, Konferenz oder Verlag.
        doi: DOI ohne URL-Präfix.
        arxiv_id: arXiv-Identifikator ohne Version.
        url: Landing- oder Volltext-Link.
        confidence: Konfidenzstufe aus :data:`CONFIDENCES`.
        evidence: Nachvollziehbarer Beleg (z. B. ``"Übersicht.md Zeile A3"``).
    """

    paper_id: str
    origin: str
    title: str = ""
    authors: tuple[str, ...] = ()
    year: int = 0
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    confidence: str = CONFIDENCE_NONE
    evidence: str = ""

    def value_of(self, name: str) -> Any:
        """Liefert den Wert eines Feldes aus :data:`METADATA_FIELDS`."""
        return getattr(self, name)

    def has(self, name: str) -> bool:
        """``True``, wenn das Feld einen belastbaren (nicht-leeren) Wert trägt."""
        value = self.value_of(name)
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, tuple):
            return bool(value)
        return bool(value)

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Datensatz (Speicherform in ``metadata/paper_metadata.json``)."""
        return {
            "origin": self.origin,
            "title": self.title,
            "authors": list(self.authors),
            "year": self.year,
            "venue": self.venue,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, paper_id: str, payload: Mapping[str, Any]) -> MetadataRecord:
        """Liest einen Datensatz aus seiner Speicherform (fehlende Felder bleiben leer)."""
        authors = payload.get("authors") or ()
        if isinstance(authors, str):
            authors = (authors,)
        return cls(
            paper_id=paper_id,
            origin=str(payload.get("origin", ORIGIN_MANUAL)),
            title=str(payload.get("title", "")),
            authors=tuple(str(name) for name in authors),
            year=int(payload.get("year", 0) or 0),
            venue=str(payload.get("venue", "")),
            doi=str(payload.get("doi", "")),
            arxiv_id=str(payload.get("arxiv_id", "")),
            url=str(payload.get("url", "")),
            confidence=str(payload.get("confidence", CONFIDENCE_NONE)),
            evidence=str(payload.get("evidence", "")),
        )


@dataclass(frozen=True)
class PaperMetadata:
    """Der feldweise aufgelöste, zitierfähige Datensatz eines Papers.

    ``origins`` nennt je gefülltem Feld die Herkunft, die es beigesteuert hat; ``confidence``
    ist die **niedrigste** Konfidenz der beteiligten Quellen – eine Angabe ist nur so verlässlich
    wie ihr schwächster verwendeter Bestandteil.
    """

    paper_id: str
    title: str = ""
    authors: tuple[str, ...] = ()
    year: int = 0
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    origins: Mapping[str, str] = field(default_factory=dict)
    confidence: str = CONFIDENCE_NONE

    @property
    def identifiers(self) -> dict[str, str]:
        """Die extern auflösbaren Identifikatoren (leer, wenn keiner bekannt ist).

        Reihenfolge der Schlüssel entspricht der Zitier-Präzedenz **DOI vor arXiv vor URL**
        (docs/adr/0025-citable-paper-metadata.md, Punkt 3).
        """
        values = {"doi": self.doi, "arxiv": self.arxiv_id, "url": self.url}
        return {key: value for key, value in values.items() if value}

    @property
    def preferred_url(self) -> str:
        """Der bevorzugte Link zum Paper (DOI vor arXiv vor bereits bekannter URL)."""
        if self.doi:
            return f"https://doi.org/{self.doi}"
        if self.arxiv_id:
            return f"https://arxiv.org/abs/{self.arxiv_id}"
        return self.url

    def citation_key(self) -> str:
        """Erzeugt einen stabilen, ASCII-sicheren Zitierschlüssel (z. B. ``Mueller2023``).

        Ohne Autor tritt das erste bedeutungstragende Titelwort an dessen Stelle; fehlt auch der
        Titel, bleibt die ``paper_id``. Der Schlüssel ist eine **Anzeigehilfe**, kein
        Identifikator – Eindeutigkeit wird nicht garantiert.
        """
        base = ""
        if self.authors:
            base = _KEY_SEPARATORS.sub("", _ascii_fold(surname_of(self.authors[0])))
        if not base and self.title:
            for word in _KEY_SEPARATORS.split(_ascii_fold(self.title)):
                if word and word.lower() not in _STOPWORDS_IN_KEY:
                    base = word
                    break
        if not base:
            return self.paper_id[:8]
        return f"{base}{self.year}" if self.year else base

    def is_citable(self) -> bool:
        """``True``, wenn Titel, Autoren **und** Jahr vorliegen (vollständige Literaturangabe)."""
        return bool(self.title.strip()) and bool(self.authors) and self.year > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den aufgelösten Datensatz **ohne** die Stil-Formen.

        Die fertigen Literaturangaben ergänzt
        :func:`research_graphrag.bibliography.styles.reference_payload`; so bleibt dieses Modul
        frei von Formatierungswissen.
        """
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": list(self.authors),
            "year": self.year,
            "venue": self.venue,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
            "identifiers": self.identifiers,
            "citation_key": self.citation_key(),
            "origins": dict(self.origins),
            "confidence": self.confidence,
            "citable": self.is_citable(),
        }


def empty_metadata(paper_id: str) -> PaperMetadata:
    """Liefert einen leeren Datensatz – die ehrliche Antwort auf „nichts bekannt"."""
    return PaperMetadata(paper_id=paper_id)


def lowest_confidence(values: Sequence[str]) -> str:
    """Bestimmt die **niedrigste** Konfidenzstufe einer Menge (leer ⇒ :data:`CONFIDENCE_NONE`)."""
    if not values:
        return CONFIDENCE_NONE
    return min(values, key=lambda value: CONFIDENCES.index(value) if value in CONFIDENCES else 0)
