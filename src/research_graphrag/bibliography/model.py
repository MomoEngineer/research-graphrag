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
from collections.abc import Callable, Mapping, Sequence
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

IDENTITY_OPENALEX = "openalex"
"""Identitätsstatus: Die Person trägt eine OpenAlex-Autor-ID (ADR 0041)."""

IDENTITY_ORCID = "orcid"
"""Identitätsstatus: Die Person trägt nur eine ORCID, keine OpenAlex-Autor-ID."""

IDENTITY_NAME = "name"
"""Identitätsstatus: nur ein Name – ausdrücklich **keine** bestätigte Identität."""

NAME_KEY_PREFIX = "name:"
"""Präfix des Personenschlüssels einer reinen Namensidentität (``name:akari asai``)."""

ORCID_KEY_PREFIX = "orcid:"
"""Präfix des Personenschlüssels einer Identität, die nur über ihre ORCID belegt ist."""

_OPENALEX_AUTHOR_ID = re.compile(r"^A\d{4,12}$")
_ORCID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
_OPENALEX_PREFIXES = ("https://openalex.org/", "http://openalex.org/", "openalex.org/")
_ORCID_PREFIXES = ("https://orcid.org/", "http://orcid.org/", "orcid.org/")
_NAME_SEPARATORS = re.compile(r"[^a-z0-9]+")

_KEY_SEPARATORS = re.compile(r"[^A-Za-z0-9]+")
_STOPWORDS_IN_KEY = frozenset({"a", "an", "the", "on", "of", "for", "and", "in", "to"})
_TRANSLITERATION = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
)


def ascii_fold(text: str) -> str:
    """Bildet Umlaute/Akzente auf ASCII ab (für stabile, dateinamensichere Zitierschlüssel).

    Deutsche Umlaute werden **transliteriert** (``ü`` → ``ue``), nicht nur entkleidet – das ist
    die im deutschsprachigen Raum übliche Schreibweise eines Nachnamens ohne Sonderzeichen.
    Alle übrigen diakritischen Zeichen werden nach NFKD verworfen.

    Öffentlich, weil auch die Referenz-Auflösung dateinamensichere Slugs bildet
    (docs/adr/0029-reference-stub-resolution-phase13.md) – zwei Faltungen wären zwei Wahrheiten.
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


def _strip_prefix(value: str, prefixes: Sequence[str]) -> str:
    """Entfernt ein bekanntes URL-Präfix (Groß-/Kleinschreibung egal)."""
    lowered = value.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return value[len(prefix) :]
    return value


def normalize_openalex_author_id(value: object) -> str:
    """Bildet eine OpenAlex-Autor-Kennung auf ihre Kurzform ab (``A5023888391``).

    Die Kennung stammt aus einer fremden Antwort oder einer von Hand bearbeiteten Datei. Deshalb
    wird sie **geprüft**, nicht nur gekürzt: Alles, was nicht dem Muster ``A`` + Ziffern
    entspricht, ergibt einen leeren String. Eine falsche Kennung wäre schlimmer als keine, weil
    sie zwei Personen still verbinden könnte (docs/adr/0041-author-identity-and-schema.md).

    Args:
        value: Rohwert, z. B. ``"https://openalex.org/A5023888391"``.

    Returns:
        Die Kurzform oder ``""``.
    """
    if not isinstance(value, str):
        return ""
    candidate = _strip_prefix(value.strip(), _OPENALEX_PREFIXES).strip()
    candidate = candidate[:1].upper() + candidate[1:]
    return candidate if _OPENALEX_AUTHOR_ID.match(candidate) else ""


def normalize_orcid(value: object) -> str:
    """Bildet eine ORCID auf ihre Kurzform ab (``0000-0002-1825-0097``); ungültig ⇒ ``""``.

    Geprüft wird das Format einschließlich der Prüfziffer nach ISO 7064 (Mod 11-2). Die
    ORCID-Spezifikation gibt diese Prüfung vor, und sie verhindert, dass ein Tippfehler zu einer
    fremden, gültig aussehenden Kennung wird.

    Args:
        value: Rohwert, z. B. ``"https://orcid.org/0000-0002-1825-0097"``.

    Returns:
        Die Kurzform (Prüfziffer ``X`` groß) oder ``""``.
    """
    if not isinstance(value, str):
        return ""
    candidate = _strip_prefix(value.strip(), _ORCID_PREFIXES).strip().upper()
    if not _ORCID.match(candidate):
        return ""
    digits = candidate.replace("-", "")
    total = 0
    for char in digits[:-1]:
        total = (total + int(char)) * 2
    check = (12 - total % 11) % 11
    expected = "X" if check == 10 else str(check)
    return candidate if digits[-1] == expected else ""


def person_name_key(name: str) -> str:
    """Normalisiert einen Personennamen zu einem Vergleichsschlüssel (``"akari asai"``).

    ``"Nachname, Vorname"`` wird zu ``"Vorname Nachname"`` gedreht. Danach wird über
    :func:`ascii_fold` gefaltet – es gibt bewusst **keine** zweite Faltung – und alles außer
    Buchstaben und Ziffern wird zu einem Leerzeichen. Damit fallen ``"Asai, Akari"`` und
    ``"Akari Asai"`` zusammen, ``"Y. Wang"`` wird zu ``"y wang"``.

    Der Schlüssel ist eine **Namens**-Gleichheit, keine Identität: Er trennt Gleichnamige nicht
    (gemessen: 15 verschiedene „Y. … Wang", Roadmap Phase 17, Befund 4).

    Args:
        name: Name in der Schreibweise der Quelle.

    Returns:
        Den normalisierten Schlüssel; leer, wenn der Name nichts Verwertbares enthält.
    """
    cleaned = " ".join(name.split())
    if cleaned.count(",") == 1:
        family, given = (part.strip() for part in cleaned.split(",", 1))
        if family and given:
            cleaned = f"{given} {family}"
    folded = ascii_fold(cleaned).lower()
    return " ".join(_NAME_SEPARATORS.sub(" ", folded).split())


def person_key(name: str, openalex_id: str = "", orcid: str = "") -> str:
    """Bildet den Personenschlüssel: Kennung vor Name (Roadmap Phase 17 / A3).

    Reihenfolge: OpenAlex-Autor-ID (``A5023888391``), sonst ``orcid:<ORCID>``, sonst ausdrücklich
    ``name:<normalisiert>`` als **unbestätigte** Identität. Das Präfix ``name:`` macht den
    Unterschied in jeder Ausgabe sichtbar, statt eine Namensgleichheit als Identität auszugeben.
    """
    if openalex_id:
        return openalex_id
    if orcid:
        return f"{ORCID_KEY_PREFIX}{orcid}"
    return f"{NAME_KEY_PREFIX}{person_name_key(name)}"


@dataclass(frozen=True)
class AuthorIdentity:
    """Eine Autorennennung mit ihrer Personenkennung.

    Attributes:
        name: Name in der Schreibweise der Quelle (Provenienz – nicht normalisiert).
        openalex_id: OpenAlex-Autor-ID in Kurzform; leer, wenn unbekannt.
        orcid: ORCID in Kurzform; leer, wenn unbekannt.
    """

    name: str
    openalex_id: str = ""
    orcid: str = ""

    @property
    def identity(self) -> str:
        """Identitätsstatus: :data:`IDENTITY_OPENALEX`, :data:`IDENTITY_ORCID` oder
        :data:`IDENTITY_NAME`."""
        if self.openalex_id:
            return IDENTITY_OPENALEX
        if self.orcid:
            return IDENTITY_ORCID
        return IDENTITY_NAME

    @property
    def person_key(self) -> str:
        """Der Personenschlüssel (siehe :func:`person_key`)."""
        return person_key(self.name, self.openalex_id, self.orcid)

    def to_dict(self) -> dict[str, str]:
        """Serialisiert die Nennung (Ausgabeform der Werkzeuge, additiv)."""
        return {
            "name": self.name,
            "openalex_id": self.openalex_id,
            "orcid": self.orcid,
            "person_key": self.person_key,
            "identity": self.identity,
        }


def aligned_identifiers(authors: Sequence[str], values: Sequence[str]) -> tuple[str, ...]:
    """Prüft, ob eine Kennungsliste parallel zur Autorenliste steht.

    Kennungen werden **positionsgleich** zu ``authors`` gespeichert (leerer String = unbekannt).
    Passt die Länge nicht, ist die Zuordnung nicht mehr belegbar – etwa nach einer
    Handbearbeitung der Namen. Dann wird die ganze Liste verworfen: Eine Kennung am falschen
    Namen würde zwei Personen still vertauschen (Präzision vor Recall).

    Returns:
        Die Kennungen als Tupel; leer, wenn keine vorliegt oder die Länge nicht passt.
    """
    if not values or len(values) != len(authors) or not any(values):
        return ()
    return tuple(values)


def read_identifier_list(
    authors: Sequence[str], raw: object, normalize: Callable[[object], str]
) -> tuple[str, ...]:
    """Liest eine positionsgleiche Kennungsliste aus fremder oder handbearbeiteter Speicherform.

    Jeder Eintrag wird mit ``normalize`` geprüft (ungültig ⇒ ``""``), danach gilt
    :func:`aligned_identifiers`.

    Args:
        authors: Die Autorennamen, zu denen die Liste positionsgleich stehen muss.
        raw: Der gespeicherte Wert (erwartet: Liste von Strings; alles andere ⇒ leer).
        normalize: :func:`normalize_openalex_author_id` oder :func:`normalize_orcid`.

    Returns:
        Die geprüften Kennungen oder ein leeres Tupel.
    """
    if not isinstance(raw, list):
        return ()
    return aligned_identifiers(authors, [normalize(value) for value in raw])


def identities_of(
    authors: Sequence[str], author_ids: Sequence[str], author_orcids: Sequence[str]
) -> tuple[AuthorIdentity, ...]:
    """Verbindet Namen und positionsgleiche Kennungen zu :class:`AuthorIdentity`-Einträgen."""
    ids = aligned_identifiers(authors, author_ids)
    orcids = aligned_identifiers(authors, author_orcids)
    return tuple(
        AuthorIdentity(
            name=name,
            openalex_id=ids[position] if ids else "",
            orcid=orcids[position] if orcids else "",
        )
        for position, name in enumerate(authors)
    )


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
        cleared_fields: Felder, die diese Quelle **ausdrücklich** als leer bestätigt (nicht bloß
            nie befüllt) – unterscheidet "geprüft: leer" von "nie geprüft", damit eine
            niedrigerrangige Herkunft nicht durchscheint (docs/adr/0040-explicit-field-clearing.md).
            Additiv: Ein Datensatz ohne diesen Schlüssel in der Speicherform liefert ein leeres
            Frozenset – das bisherige Verhalten, unverändert.
        author_ids: OpenAlex-Autor-IDs **positionsgleich** zu ``authors`` (``""`` = unbekannt);
            leer, wenn die Quelle keine liefert. Additiv wie ``cleared_fields``
            (docs/adr/0041-author-identity-and-schema.md).
        author_orcids: ORCIDs positionsgleich zu ``authors``; Regeln wie bei ``author_ids``.
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
    cleared_fields: frozenset[str] = frozenset()
    author_ids: tuple[str, ...] = ()
    author_orcids: tuple[str, ...] = ()

    @property
    def author_identities(self) -> tuple[AuthorIdentity, ...]:
        """Die Autorennennungen samt Kennung, positionsgleich zu ``authors``."""
        return identities_of(self.authors, self.author_ids, self.author_orcids)

    def value_of(self, name: str) -> Any:
        """Liefert den Wert eines Feldes aus :data:`METADATA_FIELDS`."""
        return getattr(self, name)

    def has(self, name: str) -> bool:
        """``True``, wenn das Feld einen belastbaren Wert trägt oder explizit geleert wurde.

        Ein in :attr:`cleared_fields` genanntes Feld gilt auch dann als "diese Quelle hat eine
        Aussage", wenn sein Wert leer ist – das unterscheidet "geprüft: leer" von "nie geprüft"
        und lässt eine niedrigerrangige Herkunft nicht mehr durchscheinen
        (docs/adr/0040-explicit-field-clearing.md). Diese Methode ist die **einzige** Stelle, an
        der beide Aufrufer (:mod:`research_graphrag.bibliography.resolve` für die
        Präzedenzauflösung, :func:`research_graphrag.online.metadata.filter_pending` für die
        "noch offen?"-Prüfung vor einer Online-Auflösung) dieselbe Semantik erhalten.
        """
        if name in self.cleared_fields:
            return True
        value = self.value_of(name)
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, tuple):
            return bool(value)
        return bool(value)

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Datensatz (Speicherform in ``metadata/paper_metadata.json``).

        ``author_ids``/``author_orcids`` erscheinen nur, wenn die Quelle mindestens eine Kennung
        lieferte. Ein Datensatz ohne Kennung wird damit byte-identisch zur Form vor
        docs/adr/0041-author-identity-and-schema.md geschrieben.
        """
        payload: dict[str, Any] = {
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
            "cleared_fields": sorted(self.cleared_fields),
        }
        if self.author_ids:
            payload["author_ids"] = list(self.author_ids)
        if self.author_orcids:
            payload["author_orcids"] = list(self.author_orcids)
        return payload

    @classmethod
    def from_dict(cls, paper_id: str, payload: Mapping[str, Any]) -> MetadataRecord:
        """Liest einen Datensatz aus seiner Speicherform (fehlende Felder bleiben leer).

        ``cleared_fields`` fehlt in jeder vor ADR 0040 geschriebenen Datei; das ist bewusst
        gleichwertig zu einem leeren Frozenset (kein Feld ist explizit geleert) – keine
        Migration nötig. Dasselbe gilt für ``author_ids``/``author_orcids`` (ADR 0041). Die
        Datei kann von Hand bearbeitet sein, deshalb wird jede Kennung erneut geprüft, und eine
        Liste, die nicht mehr positionsgleich zu ``authors`` steht, entfällt ganz.
        """
        authors = payload.get("authors") or ()
        if isinstance(authors, str):
            authors = (authors,)
        names = tuple(str(name) for name in authors)
        cleared_fields = payload.get("cleared_fields") or ()
        return cls(
            paper_id=paper_id,
            origin=str(payload.get("origin", ORIGIN_MANUAL)),
            title=str(payload.get("title", "")),
            authors=names,
            year=int(payload.get("year", 0) or 0),
            venue=str(payload.get("venue", "")),
            doi=str(payload.get("doi", "")),
            arxiv_id=str(payload.get("arxiv_id", "")),
            url=str(payload.get("url", "")),
            confidence=str(payload.get("confidence", CONFIDENCE_NONE)),
            evidence=str(payload.get("evidence", "")),
            cleared_fields=frozenset(str(name) for name in cleared_fields),
            author_ids=read_identifier_list(
                names, payload.get("author_ids"), normalize_openalex_author_id
            ),
            author_orcids=read_identifier_list(
                names, payload.get("author_orcids"), normalize_orcid
            ),
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
    author_ids: tuple[str, ...] = ()
    author_orcids: tuple[str, ...] = ()

    @property
    def author_identities(self) -> tuple[AuthorIdentity, ...]:
        """Die Autoren samt Personenkennung, positionsgleich zu ``authors``.

        Die Kennungen stammen stets aus **demselben** Datensatz wie die Namen (siehe
        :func:`research_graphrag.bibliography.resolve.resolve_metadata`); eine Kennung kann einem
        Namen aus einer anderen Quelle nie zugeordnet werden.
        """
        return identities_of(self.authors, self.author_ids, self.author_orcids)

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
            base = _KEY_SEPARATORS.sub("", ascii_fold(surname_of(self.authors[0])))
        if not base and self.title:
            for word in _KEY_SEPARATORS.split(ascii_fold(self.title)):
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
        frei von Formatierungswissen. ``author_identities`` ist additiv (ADR 0041): je Autor
        Name, Kennungen, Personenschlüssel und Identitätsstatus – ohne Kennung ausdrücklich
        ``identity = "name"``.
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
            "author_identities": [entry.to_dict() for entry in self.author_identities],
        }


def empty_metadata(paper_id: str) -> PaperMetadata:
    """Liefert einen leeren Datensatz – die ehrliche Antwort auf „nichts bekannt"."""
    return PaperMetadata(paper_id=paper_id)


def lowest_confidence(values: Sequence[str]) -> str:
    """Bestimmt die **niedrigste** Konfidenzstufe einer Menge (leer ⇒ :data:`CONFIDENCE_NONE`)."""
    if not values:
        return CONFIDENCE_NONE
    return min(values, key=lambda value: CONFIDENCES.index(value) if value in CONFIDENCES else 0)
