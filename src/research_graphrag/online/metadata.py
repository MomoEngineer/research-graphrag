"""Online-Auflösung der Zitationsdaten (Phase 12 / K2).

Ergänzt die lokal **nicht** gewinnbaren Felder – Autoren, Venue und den Publikationsjahrgang –
über externe Metadatenquellen. Der Netzzugang läuft ausschließlich über den injizierbaren Port
:class:`research_graphrag.online.transport.HttpClient`, sodass die gesamte Auswahl-, Zuordnungs-
und Bewertungslogik **offline testbar** bleibt
(docs/adr/0026-online-metadata-resolution.md).

Reihenfolge der Wege, absteigend nach Beweiskraft:

1. **DOI** bei OpenAlex – eindeutig.
2. **arXiv-ID** bei OpenAlex (über den DataCite-DOI) – eindeutig.
3. **Titel-Suche** bei OpenAlex – nur ab :data:`research_graphrag.intake.TITLE_SIMILARITY`.
4. **arXiv-Feed** als Rückfall, wenn eine arXiv-ID vorliegt und OpenAlex nichts liefert.

Übernommen wird jeder belegte Treffer; wie stark der Beleg ist, weist die Konfidenz aus. Fremde
Zeichenketten gelten als nicht vertrauenswürdige Eingabe und werden vor der Übernahme bereinigt.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..bibliography.model import (
    CITABLE_FIELDS,
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_MANUAL,
    ORIGIN_RESOLVED,
    AuthorIdentity,
    MetadataRecord,
    normalize_openalex_author_id,
    normalize_orcid,
)
from ..errors import DomainError, ErrorCode
from ..indexing.citation_graph import normalize_title
from ..indexing.metadata_index import load_paper_metadata
from ..intake import TITLE_SIMILARITY, best_title_match
from .candidates import Candidate
from .sources import (
    OPENALEX_ENDPOINT,
    SearchQuery,
    SourceResult,
    authors_from_feed,
    fetch_arxiv_by_id,
    parse_openalex,
)
from .transport import HttpClient

METADATA_FIELDS = (
    "id,doi,title,publication_year,authorships,primary_location,open_access,best_oa_location"
)
"""Angeforderte OpenAlex-Felder – gegenüber der Kandidatensuche um Autoren und Venue erweitert."""

MAX_AUTHORS = 25
"""Obergrenze der übernommenen Autoren (Kollaborationslisten sprengen sonst jede Angabe)."""

MAX_FIELD_CHARS = 400
"""Längengrenze für Titel und Venue aus fremder Quelle."""

TITLE_SEARCH_LIMIT = 5
"""Treffer der Titel-Suche, aus denen der ähnlichste gewählt wird."""

ARXIV_DOI_PREFIX = "10.48550/arXiv."
"""DataCite-DOI-Präfix von arXiv – erlaubt die ID-Abfrage ohne eigene arXiv-Suche."""

MATCH_DOI = "doi"
"""Belegart: Abfrage über die DOI des Papers."""

MATCH_ARXIV = "arxiv"
"""Belegart: Abfrage über die arXiv-ID des Papers."""

MATCH_TITLE = "title"
"""Belegart: Titel-Suche mit Ähnlichkeitsprüfung."""


@dataclass(frozen=True)
class ResolutionTarget:
    """Ein aufzulösendes Paper mit allem, was lokal über es bekannt ist.

    Attributes:
        paper_id: Stabile Paper-ID des Korpus.
        title: Bester lokal bekannter Titel (kuratiert oder Dateiname-Stamm).
        doi: DOI, sofern bekannt.
        arxiv_id: arXiv-ID, sofern bekannt.
        identifier_backed: ``True``, wenn der Identifikator auf der eigenen Titelseite belegt
            und im Korpus eindeutig ist (Guard aus
            docs/adr/0011-intra-corpus-citation-graph-phase7.md).
        missing: Die fehlenden Pflichtfelder (nur zur Anzeige im Bericht).
    """

    paper_id: str
    title: str = ""
    doi: str = ""
    arxiv_id: str = ""
    identifier_backed: bool = True
    missing: tuple[str, ...] = ()

    def has_identifier(self) -> bool:
        """``True``, wenn eine Identifikator-Abfrage möglich ist."""
        return bool(self.doi or self.arxiv_id)


@dataclass(frozen=True)
class Resolution:
    """Das Ergebnis für **ein** Paper.

    Attributes:
        target: Das angefragte Paper.
        record: Der übernommene Datensatz; ``None``, wenn kein Beleg gefunden wurde.
        match: Belegart (:data:`MATCH_DOI`, :data:`MATCH_ARXIV`, :data:`MATCH_TITLE`) oder leer.
        note: Klartext-Begründung – auch (und gerade) im Misserfolgsfall.
        raw: Rohantworten des Laufs für die Ablage.
    """

    target: ResolutionTarget
    record: MetadataRecord | None
    match: str = ""
    note: str = ""
    raw: tuple[SourceResult, ...] = ()

    @property
    def resolved(self) -> bool:
        """``True``, wenn ein Datensatz übernommen wurde."""
        return self.record is not None


def _clean(text: str, *, limit: int = MAX_FIELD_CHARS) -> str:
    """Bereinigt eine fremde Zeichenkette (einzeilig, druckbar, längenbegrenzt)."""
    printable = "".join(char if char.isprintable() else " " for char in text)
    collapsed = " ".join(printable.split())
    return collapsed[:limit].strip()


def openalex_id_url(identifier: str, *, fields: str = METADATA_FIELDS) -> str:
    """Baut die OpenAlex-Abfrage über einen DOI (der Dienst löst DOIs direkt auf).

    Args:
        identifier: DOI des gesuchten Werks (für arXiv der DataCite-DOI).
        fields: Angeforderter Feldsatz; die Referenz-Auflösung fordert zusätzlich den
            invertierten Abstract-Index an (docs/adr/0029-reference-stub-resolution-phase13.md).
    """
    return f"{OPENALEX_ENDPOINT}/doi:{quote(identifier, safe='')}?select={quote(fields)}"


def openalex_title_url(title: str, *, limit: int = TITLE_SEARCH_LIMIT) -> str:
    """Baut die OpenAlex-Titelsuche (Freitext über den Titel)."""
    cleaned = _clean(title, limit=200)
    if not cleaned:
        raise DomainError(ErrorCode.INVALID_INPUT, "Titel-Suche ohne Titel.")
    return (
        f"{OPENALEX_ENDPOINT}?search={quote(cleaned)}"
        f"&per-page={limit}&select={quote(METADATA_FIELDS, safe=',')}"
    )


def parse_openalex_work(payload: bytes) -> Candidate | None:
    """Liest ein **einzelnes** OpenAlex-Werk (Antwort der DOI-Abfrage).

    Raises:
        DomainError: ``parse_error`` wenn die Antwort kein JSON-Objekt ist.
    """
    try:
        data = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise DomainError(ErrorCode.PARSE_ERROR, f"OpenAlex-Antwort nicht lesbar: {exc}") from exc
    if not isinstance(data, dict) or "id" not in data:
        return None
    wrapped = json.dumps({"results": [data]}, ensure_ascii=False).encode("utf-8")
    candidates = parse_openalex(wrapped, SearchQuery(query_id="", terms=(), reason=""))
    return candidates[0] if candidates else None


def authorships_of_work(work: Mapping[str, Any]) -> tuple[AuthorIdentity, ...]:
    """Liest die Autorennennungen **eines** OpenAlex-Werks samt Personenkennung.

    Übernommen werden der ``display_name`` in der Schreibweise der Quelle, ``author.id`` und
    ``author.orcid``. Beide Kennungen werden geprüft; eine ungültige ergibt einen leeren Wert
    (docs/adr/0041-author-identity-and-schema.md). Nennungen ohne Namen entfallen. Die Liste
    endet bei :data:`MAX_AUTHORS`.

    Öffentlich, weil der Nachtrag aus den abgelegten Rohantworten dieselbe Lesart braucht
    (Roadmap Phase 17 / A2, Punkt 3) – zwei Lesarten wären zwei Wahrheiten.
    """
    identities: list[AuthorIdentity] = []
    for entry in work.get("authorships") or []:
        if not isinstance(entry, dict):
            continue
        raw_author = entry.get("author")
        author: Mapping[str, Any] = raw_author if isinstance(raw_author, dict) else {}
        name = _clean(str(author.get("display_name") or ""), limit=200)
        if not name:
            continue
        identities.append(
            AuthorIdentity(
                name=name,
                openalex_id=normalize_openalex_author_id(author.get("id")),
                orcid=normalize_orcid(author.get("orcid")),
            )
        )
    return tuple(identities[:MAX_AUTHORS])


def authorships_of(payload: bytes) -> tuple[AuthorIdentity, ...]:
    """Liest die Autorennennungen aus einer OpenAlex-Antwort (Einzelwerk **oder** Trefferliste).

    Bei einer Trefferliste zählt das erste Werk mit mindestens einer Nennung – dieselbe Regel wie
    vor Phase 17 für die Namen allein.
    """
    try:
        data = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return ()
    if not isinstance(data, dict):
        return ()
    works = data.get("results") if isinstance(data.get("results"), list) else [data]
    for work in works or []:
        if not isinstance(work, dict):
            continue
        identities = authorships_of_work(work)
        if identities:
            return identities
    return ()


def authors_of(payload: bytes) -> tuple[str, ...]:
    """Liest die Autorennamen aus einer OpenAlex-Antwort (Einzelwerk **oder** Trefferliste)."""
    return tuple(identity.name for identity in authorships_of(payload))


def author_identifier_lists(
    identities: Sequence[AuthorIdentity],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Zerlegt Nennungen in positionsgleiche Listen aus OpenAlex-IDs und ORCIDs.

    Eine Liste ohne einen einzigen Wert wird leer geliefert – so bleibt die Speicherform eines
    Datensatzes ohne Kennung unverändert (docs/adr/0041-author-identity-and-schema.md).
    """
    ids = tuple(identity.openalex_id for identity in identities)
    orcids = tuple(identity.orcid for identity in identities)
    return (ids if any(ids) else (), orcids if any(orcids) else ())


def venue_of(payload: bytes) -> str:
    """Liest die Publikationsquelle (Journal/Konferenz) aus einer OpenAlex-Antwort."""
    try:
        data = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    works = data.get("results") if isinstance(data.get("results"), list) else [data]
    for work in works or []:
        if not isinstance(work, dict):
            continue
        location = work.get("primary_location") or {}
        source = location.get("source") if isinstance(location, dict) else None
        if isinstance(source, dict):
            name = _clean(str(source.get("display_name") or ""))
            if name:
                return name
    return ""


def _record_from(
    target: ResolutionTarget,
    candidate: Candidate,
    payload: bytes,
    *,
    confidence: str,
    evidence: str,
) -> MetadataRecord:
    """Baut den Datensatz der Herkunft ``resolved`` aus einem Treffer (samt Personenkennung)."""
    identities = authorships_of(payload)
    author_ids, author_orcids = author_identifier_lists(identities)
    return MetadataRecord(
        paper_id=target.paper_id,
        origin=ORIGIN_RESOLVED,
        title=_clean(candidate.title),
        authors=tuple(identity.name for identity in identities),
        author_ids=author_ids,
        author_orcids=author_orcids,
        year=candidate.year,
        venue=venue_of(payload),
        doi=_clean(candidate.doi, limit=200),
        arxiv_id=_clean(candidate.arxiv_id, limit=100),
        url=_clean(candidate.url, limit=200) if candidate.url.startswith("https://") else "",
        confidence=confidence,
        evidence=evidence,
    )


def fetch_openalex_url(client: HttpClient, url: str) -> SourceResult:
    """Führt eine OpenAlex-Abfrage aus und verpackt sie wie die übrigen Quellen.

    Öffentlich, weil die Referenz-Auflösung denselben Weg nimmt und keine zweite
    Abruf-Mechanik entstehen soll (docs/adr/0029-reference-stub-resolution-phase13.md).

    Args:
        client: Injizierter Transport-Port (die einzige Stelle mit Netzzugriff).
        url: Vollständige Abfrage-URL.

    Returns:
        Das Quellenergebnis samt Rohantwort und Kontingent-Angaben.
    """
    response = client.get(url, accept="application/json")
    note = "" if response.status == 200 else f"OpenAlex antwortete mit HTTP {response.status}"
    return SourceResult(
        source="OpenAlex",
        url=url,
        status=response.status,
        raw=response.body,
        note=note,
        rate_limit={
            key: value for key, value in response.headers.items() if key.startswith("x-ratelimit")
        },
    )


def _by_identifier(client: HttpClient, target: ResolutionTarget) -> Resolution | None:
    """Versucht die eindeutige Abfrage über DOI bzw. arXiv-ID."""
    attempts = []
    if target.doi:
        attempts.append((MATCH_DOI, target.doi))
    if target.arxiv_id:
        attempts.append((MATCH_ARXIV, f"{ARXIV_DOI_PREFIX}{target.arxiv_id}"))

    collected: list[SourceResult] = []
    for match, identifier in attempts:
        source = fetch_openalex_url(client, openalex_id_url(identifier))
        collected.append(source)
        if source.status != 200:
            continue
        candidate = parse_openalex_work(source.raw)
        if candidate is None:
            continue
        confidence = CONFIDENCE_STRONG if target.identifier_backed else CONFIDENCE_WEAK
        evidence = f"OpenAlex über {match}:{identifier}"
        if not target.identifier_backed:
            evidence += " (Identifikator lokal nicht belegt)"
        return Resolution(
            target=target,
            record=_record_from(
                target, candidate, source.raw, confidence=confidence, evidence=evidence
            ),
            match=match,
            note=evidence,
            raw=tuple(collected),
        )
    return Resolution(target=target, record=None, raw=tuple(collected)) if collected else None


def _by_title(client: HttpClient, target: ResolutionTarget) -> Resolution | None:
    """Versucht die Titel-Suche mit Ähnlichkeitsprüfung."""
    if not target.title.strip():
        return None
    source = fetch_openalex_url(client, openalex_title_url(target.title))
    if source.status != 200:
        return Resolution(target=target, record=None, note=source.note, raw=(source,))

    candidates = parse_openalex(source.raw, SearchQuery(query_id="", terms=(), reason=""))
    titles = {normalize_title(candidate.title): candidate for candidate in candidates}
    ratio, matched_title = best_title_match(
        [normalize_title(target.title)], {key: key for key in titles}
    )
    if not matched_title or ratio < TITLE_SIMILARITY:
        return Resolution(
            target=target,
            record=None,
            note=f"Titel-Suche ohne belastbaren Treffer (beste Ähnlichkeit {ratio:.2f})",
            raw=(source,),
        )

    candidate = titles[matched_title]
    evidence = f"OpenAlex über Titel-Ähnlichkeit {ratio:.2f}"
    return Resolution(
        target=target,
        record=_record_from(
            target, candidate, source.raw, confidence=CONFIDENCE_WEAK, evidence=evidence
        ),
        match=MATCH_TITLE,
        note=evidence,
        raw=(source,),
    )


def _by_arxiv_feed(client: HttpClient, target: ResolutionTarget) -> Resolution | None:
    """Rückfall auf den arXiv-Feed – abgefragt über die **Kennung**, nicht über eine Volltextsuche.

    Die Abfrage nutzt ``id_list``: Die früher verwendete Suche ``search_query=all:"<id>"``
    durchsucht den **Volltext** und liefert dadurch fremde Werke (gemessen in Phase 13 / R1:
    ``1706.03762`` ergab ``2002.05202``). Die ID-Prüfung unten hätte den Fehlgriff zwar verworfen –
    damit war der Rückfall aber wirkungslos statt falsch
    (docs/adr/0026-online-metadata-resolution.md, Nachtrag).

    Der Feed liefert Titel, **Autoren** und das Preprint-Jahr. Ohne die Autoren bliebe der
    Datensatz unvollständig, und genau dafür existiert dieser Rückfall
    (docs/adr/0025-citable-paper-metadata.md).
    """
    if not target.arxiv_id:
        return None
    query = SearchQuery(query_id=target.paper_id, terms=(target.arxiv_id,), reason="Metadaten")
    source = fetch_arxiv_by_id(client, target.arxiv_id, query)
    if source.status != 200 or not source.candidates:
        return Resolution(target=target, record=None, note=source.note, raw=(source,))

    candidate = source.candidates[0]
    if candidate.arxiv_id and candidate.arxiv_id != target.arxiv_id:
        return Resolution(
            target=target,
            record=None,
            note=f"arXiv lieferte eine andere ID ({candidate.arxiv_id})",
            raw=(source,),
        )
    evidence = f"arXiv-Feed über arxiv:{target.arxiv_id}"
    confidence = CONFIDENCE_STRONG if target.identifier_backed else CONFIDENCE_WEAK
    record = MetadataRecord(
        paper_id=target.paper_id,
        origin=ORIGIN_RESOLVED,
        title=_clean(candidate.title),
        authors=authors_from_feed(source.raw)[:MAX_AUTHORS],
        year=candidate.year,
        doi=_clean(candidate.doi, limit=200),
        arxiv_id=target.arxiv_id,
        confidence=confidence,
        evidence=evidence,
    )
    return Resolution(target=target, record=record, match=MATCH_ARXIV, note=evidence, raw=(source,))


def targets_from_index(
    db_path: str | Path, *, only_incomplete: bool = True
) -> tuple[ResolutionTarget, ...]:
    """Bestimmt aus dem Index, welche Paper aufgelöst werden sollen.

    Standardmäßig sind das nur die Paper mit **unvollständiger** Angabe – jede weitere Anfrage
    wäre eine Belastung fremder Dienste ohne Gegenwert
    (docs/adr/0026-online-metadata-resolution.md, Punkt 4).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        only_incomplete: ``False`` nimmt auch bereits vollständige Paper auf.

    Returns:
        Die Ziele, stabil nach ``paper_id`` sortiert.

    Raises:
        DomainError: ``not_found`` wenn die Index-Datei fehlt (siehe docs/error-model.md).
    """
    metadata = load_paper_metadata(db_path)
    targets: list[ResolutionTarget] = []
    for paper_id in sorted(metadata):
        item = metadata[paper_id]
        missing = tuple(name for name in CITABLE_FIELDS if not getattr(item, name))
        if only_incomplete and not missing:
            continue
        targets.append(
            ResolutionTarget(
                paper_id=paper_id,
                title=item.title,
                doi=item.doi,
                arxiv_id=item.arxiv_id,
                # Die aufgelöste Konfidenz ist das Minimum der beteiligten Quellen; ``strong``
                # heißt daher: Der Identifikator ist auf der eigenen Titelseite belegt.
                identifier_backed=item.confidence == CONFIDENCE_STRONG,
                missing=missing,
            )
        )
    return tuple(targets)


def filter_pending(
    targets: Sequence[ResolutionTarget], records: Sequence[MetadataRecord]
) -> tuple[ResolutionTarget, ...]:
    """Blendet Ziele aus, für die bereits ein brauchbarer Datensatz gespeichert ist.

    Notwendig, weil die Auswahl aus dem **Index** stammt, ein Auflösungslauf aber zunächst nur
    die Datei schreibt: Ohne diesen Filter würde ein zweiter Lauf vor dem nächsten
    ``scripts.ingest`` dieselben Paper erneut abfragen
    (docs/adr/0026-online-metadata-resolution.md).

    Args:
        targets: Die aus dem Index bestimmten Ziele.
        records: Bereits gespeicherte Datensätze (alle Herkünfte).

    Returns:
        Die Ziele, deren fehlende Felder noch nicht abgedeckt sind.
    """
    covered: dict[str, set[str]] = {}
    for record in records:
        if record.origin not in (ORIGIN_RESOLVED, ORIGIN_MANUAL):
            continue
        filled = covered.setdefault(record.paper_id, set())
        filled.update(name for name in CITABLE_FIELDS if record.has(name))
    return tuple(
        target
        for target in targets
        if not target.missing or (set(target.missing) - covered.get(target.paper_id, set()))
    )


def resolve_target(client: HttpClient, target: ResolutionTarget) -> Resolution:
    """Löst die Metadaten **eines** Papers auf.

    Args:
        client: Injizierter Transport-Port (die einzige Stelle mit Netzzugriff).
        target: Das aufzulösende Paper samt lokal bekannter Angaben.

    Returns:
        Eine :class:`Resolution`; ohne Beleg ist ``record`` ``None`` und ``note`` nennt den Grund.
    """
    collected: list[SourceResult] = []
    notes: list[str] = []
    for attempt in (_by_identifier, _by_title, _by_arxiv_feed):
        result = attempt(client, target)
        if result is None:
            continue
        collected.extend(result.raw)
        if result.resolved:
            return Resolution(
                target=result.target,
                record=result.record,
                match=result.match,
                note=result.note,
                raw=tuple(collected),
            )
        if result.note:
            notes.append(result.note)
    if notes:
        note = "; ".join(notes)
    elif collected:
        note = "kein belastbarer Treffer"
    else:
        note = "keine Abfragemöglichkeit (kein Titel, kein Identifikator)"
    return Resolution(target=target, record=None, note=note, raw=tuple(collected))
