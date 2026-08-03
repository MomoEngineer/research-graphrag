"""Quellen-Adapter des Online-Modus: arXiv und OpenAlex.

Beide Adapter bauen ihre Anfrage aus derselben :class:`SearchQuery`, rufen sie über den
injizierten :class:`~.transport.HttpClient` ab und bilden das Ergebnis auf
:class:`~.candidates.Candidate` ab. Das Modul kennt keine Netzdetails und ist damit über
gespeicherte Antworten vollständig offline testbar.

Nur diese beiden Quellen sind umgesetzt; Crossref, Semantic Scholar und Unpaywall wurden in S0
gemessen und begründet ausgeschlossen (docs/adr/0020-online-candidate-search-phase9.md).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import quote

from ..errors import DomainError, ErrorCode
from .candidates import SOURCE_ARXIV, SOURCE_OPENALEX, Candidate
from .transport import HttpClient

ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
"""Basis-URL der arXiv-API (Atom)."""

OPENALEX_ENDPOINT = "https://api.openalex.org/works"
"""Basis-URL der OpenAlex-API (JSON)."""

OPENALEX_FIELDS = (
    "id,doi,title,publication_year,open_access,primary_location,abstract_inverted_index"
)
"""Angeforderte OpenAlex-Felder – bewusst schmal, um Antwortgröße und Kosten klein zu halten."""

DEFAULT_LIMIT = 10
"""Treffer je Quelle und Anfrage."""

MAX_ARXIV_TERMS = 3
"""Mehr als drei UND-verknüpfte Terme lassen die arXiv-Suche praktisch leer laufen."""

_ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_DOI_PREFIX = "https://doi.org/"
_ARXIV_DOI_PREFIX = "10.48550/arxiv."
_XML_FORBIDDEN = ("<!DOCTYPE", "<!ENTITY")


@dataclass(frozen=True)
class SearchQuery:
    """Eine Anfrage samt Herkunftsbegründung.

    Attributes:
        query_id: Kurze Kennung (``C3``, ``S1`` …) zur Zuordnung im Bericht.
        terms: Suchbegriffe in absteigender Wichtigkeit.
        reason: Klartext, warum diese Anfrage gestellt wurde (Community, Seed-Paper).
    """

    query_id: str
    terms: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class SourceResult:
    """Ergebnis einer Quelle für genau eine Anfrage.

    Attributes:
        source: Quellenkennung.
        url: Tatsächlich abgerufene URL (Reproduzierbarkeit).
        status: HTTP-Status der Antwort.
        raw: Unveränderte Rohantwort für die Ablage.
        candidates: Die extrahierten Kandidaten.
        note: Klartext-Hinweis bei auffälligem Status (Rate-Limit o. Ä.).
    """

    source: str
    url: str
    status: int
    raw: bytes
    candidates: tuple[Candidate, ...] = ()
    note: str = ""
    rate_limit: dict[str, str] = field(default_factory=dict)


def arxiv_url(query: SearchQuery, *, limit: int = DEFAULT_LIMIT) -> str:
    """Baut die arXiv-Anfrage (UND-Verknüpfung der wichtigsten Terme)."""
    terms = [term for term in query.terms if term.strip()][:MAX_ARXIV_TERMS]
    if not terms:
        raise DomainError(ErrorCode.INVALID_INPUT, "Anfrage ohne Suchbegriffe.")
    expression = " AND ".join(f'all:"{term}"' for term in terms)
    return f"{ARXIV_ENDPOINT}?search_query={quote(expression)}&max_results={limit}&sortBy=relevance"


def openalex_url(query: SearchQuery, *, limit: int = DEFAULT_LIMIT) -> str:
    """Baut die OpenAlex-Anfrage (Freitext über alle Terme)."""
    terms = " ".join(term for term in query.terms if term.strip())
    if not terms:
        raise DomainError(ErrorCode.INVALID_INPUT, "Anfrage ohne Suchbegriffe.")
    return (
        f"{OPENALEX_ENDPOINT}?search={quote(terms)}"
        f"&per-page={limit}&select={quote(OPENALEX_FIELDS, safe=',')}"
    )


def parse_arxiv(payload: bytes, query: SearchQuery) -> list[Candidate]:
    """Liest den Atom-Feed der arXiv-API.

    Args:
        payload: Rohantwort der API.
        query: Auslösende Anfrage (liefert Kennung und Begründung).

    Returns:
        Die Kandidaten in Trefferreihenfolge.

    Raises:
        DomainError: ``parse_error`` wenn der Feed nicht lesbar ist oder eine Dokumenttyp-
            bzw. Entity-Deklaration enthält (Schutz vor Entity-Expansion, da die Standard-
            bibliothek dagegen nicht härtet).
    """
    text = payload.decode("utf-8", errors="replace")
    head = text[:2048].upper()
    if any(marker in head for marker in _XML_FORBIDDEN):
        raise DomainError(ErrorCode.PARSE_ERROR, "XML mit Dokumenttyp-Deklaration abgelehnt.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise DomainError(ErrorCode.PARSE_ERROR, f"arXiv-Feed nicht lesbar: {exc}") from exc

    candidates: list[Candidate] = []
    for entry in root.findall("a:entry", _ATOM):
        raw_id = entry.findtext("a:id", default="", namespaces=_ATOM) or ""
        arxiv_id = raw_id.rsplit("/", 1)[-1].split("v")[0] if raw_id else ""
        links = [link.attrib for link in entry.findall("a:link", _ATOM)]
        pdf = next((str(link.get("href", "")) for link in links if link.get("title") == "pdf"), "")
        published = entry.findtext("a:published", default="", namespaces=_ATOM) or ""
        candidates.append(
            Candidate(
                title=_squeeze(entry.findtext("a:title", default="", namespaces=_ATOM)),
                year=_year_of(published[:4]),
                sources=(SOURCE_ARXIV,),
                arxiv_id=arxiv_id,
                doi=entry.findtext("arxiv:doi", default="", namespaces=_ATOM) or "",
                abstract=_squeeze(entry.findtext("a:summary", default="", namespaces=_ATOM)),
                url=pdf or raw_id,
                license="",
                query_id=query.query_id,
                reason=query.reason,
            )
        )
    return candidates


def parse_openalex(payload: bytes, query: SearchQuery) -> list[Candidate]:
    """Liest die JSON-Antwort der OpenAlex-API.

    Args:
        payload: Rohantwort der API.
        query: Auslösende Anfrage (liefert Kennung und Begründung).

    Returns:
        Die Kandidaten in Trefferreihenfolge.

    Raises:
        DomainError: ``parse_error`` wenn die Antwort kein erwartetes JSON ist.
    """
    try:
        data = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise DomainError(ErrorCode.PARSE_ERROR, f"OpenAlex-Antwort nicht lesbar: {exc}") from exc
    if not isinstance(data, dict):
        raise DomainError(ErrorCode.PARSE_ERROR, "OpenAlex-Antwort ist kein Objekt.")

    candidates: list[Candidate] = []
    for item in data.get("results", []):
        if not isinstance(item, dict):
            continue
        doi = str(item.get("doi") or "").removeprefix(_DOI_PREFIX)
        access = item.get("open_access") or {}
        location = item.get("primary_location") or {}
        arxiv_id = doi[len(_ARXIV_DOI_PREFIX) :] if doi.startswith(_ARXIV_DOI_PREFIX) else ""
        candidates.append(
            Candidate(
                title=_squeeze(str(item.get("title") or "")),
                year=_year_of(str(item.get("publication_year") or "")),
                sources=(SOURCE_OPENALEX,),
                arxiv_id=arxiv_id,
                doi=doi,
                abstract=_restore_abstract(item.get("abstract_inverted_index")),
                url=str(access.get("oa_url") or item.get("id") or ""),
                license=str(location.get("license") or ""),
                query_id=query.query_id,
                reason=query.reason,
            )
        )
    return candidates


def fetch_arxiv(
    client: HttpClient, query: SearchQuery, *, limit: int = DEFAULT_LIMIT
) -> SourceResult:
    """Ruft arXiv für eine Anfrage ab (genau eine Anfrage, kein Bulk)."""
    url = arxiv_url(query, limit=limit)
    response = client.get(url, accept="application/atom+xml")
    if response.status != 200:
        return SourceResult(
            source=SOURCE_ARXIV,
            url=url,
            status=response.status,
            raw=response.body,
            note=f"arXiv antwortete mit HTTP {response.status}",
        )
    return SourceResult(
        source=SOURCE_ARXIV,
        url=url,
        status=response.status,
        raw=response.body,
        candidates=tuple(parse_arxiv(response.body, query)),
    )


def fetch_openalex(
    client: HttpClient, query: SearchQuery, *, limit: int = DEFAULT_LIMIT
) -> SourceResult:
    """Ruft OpenAlex für eine Anfrage ab und reicht die Kontingent-Angaben durch."""
    url = openalex_url(query, limit=limit)
    response = client.get(url, accept="application/json")
    rate = {key: value for key, value in response.headers.items() if key.startswith("x-ratelimit")}
    if response.status != 200:
        return SourceResult(
            source=SOURCE_OPENALEX,
            url=url,
            status=response.status,
            raw=response.body,
            note=f"OpenAlex antwortete mit HTTP {response.status}",
            rate_limit=rate,
        )
    return SourceResult(
        source=SOURCE_OPENALEX,
        url=url,
        status=response.status,
        raw=response.body,
        candidates=tuple(parse_openalex(response.body, query)),
        rate_limit=rate,
    )


def _squeeze(text: str | None) -> str:
    """Verdichtet Whitespace – API-Felder enthalten Zeilenumbrüche aus dem Satzspiegel."""
    return " ".join((text or "").split())


def _year_of(value: str) -> int:
    """Liest ein Jahr; nicht deutbare Angaben werden zu ``0`` (kein Beleg für Veralterung)."""
    return int(value) if value.isdigit() and len(value) == 4 else 0


def _restore_abstract(inverted: object) -> str:
    """Baut den Abstract aus OpenAlex' invertiertem Index zurück."""
    if not isinstance(inverted, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, spots in inverted.items():
        if not isinstance(spots, list):
            continue
        positions.extend((int(spot), str(word)) for spot in spots if isinstance(spot, int))
    return " ".join(word for _, word in sorted(positions))
