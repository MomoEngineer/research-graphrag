"""Referenz-Einträge ohne Volltext: Kennungsliste → Stub-Dateien (Phase 13 / R1).

Aus der kuratierten Liste ``new_papers/referenzen.txt`` entsteht je DOI bzw. arXiv-Kennung
**eine** native Stub-Datei ``*.refjson`` im Eingangsordner. Sie enthält Titel, Autoren, Jahr,
Venue, Identifikatoren und – der eigentliche Zweck – den **Abstract**. Der Weg in den Korpus
führt danach ausschließlich über ``python -m scripts.intake``; dieses Modul schreibt **nie** nach
``papers/`` (docs/adr/0029-reference-stub-resolution-phase13.md).

Der Netzzugang läuft ausschließlich über den injizierbaren Port
:class:`research_graphrag.online.transport.HttpClient`. Parsen, Planen, Benennen und Schreiben
sind netzfrei und damit offline testbar.

Drei Eigenschaften sind für den Betrieb wesentlich:

1. **Idempotenz vor der ersten Abfrage.** Geprüft wird gegen den Korpus, gegen die bereits
   erzeugten Stub-Dateien im Eingang und gegen die Quarantäne ``new_papers/_duplikate/`` – erst
   danach wird überhaupt eine Verbindung geöffnet.
2. **Die Datei ist die eingefrorene Antwort.** Das Netz wird genau einmal befragt; jede spätere
   Verarbeitung ist deterministisch.
3. **Ein Titel ist Pflicht, ein Abstract nicht.** Ohne Titel entsteht keine Datei (ein solcher
   Eintrag wäre weder zitierfähig noch als Zitationsziel brauchbar); ohne Abstract entsteht sie
   sehr wohl – er wird dann von Hand in **diese** Datei nachgetragen.

Titel, Autoren, Venue und Abstract stammen aus fremden Diensten und gelten als **nicht
vertrauenswürdige Eingabe**: Sie werden auf druckbare Zeichen reduziert, in Whitespace verdichtet
und längenbegrenzt, bevor sie in eine Datei gelangen.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from ..bibliography.model import ascii_fold, normalize_openalex_author_id, normalize_orcid
from ..errors import DomainError, ErrorCode

# Das Stub-Format hat **eine** Definitionsstelle: den lesenden Adapter. Der Schreiber übernimmt
# Endung, Formatversion und Dokumentart von dort, damit beide Seiten nie auseinanderlaufen
# (docs/adr/0041-author-identity-and-schema.md; vorher war die Version hier dupliziert).
from ..extraction.model import DOCUMENT_KIND_REFERENCE
from ..extraction.refstub import STUB_SCHEMA_VERSION, STUB_SUFFIX
from ..intake import QUARANTINE_DIR, CorpusView
from .candidates import SOURCE_ARXIV, SOURCE_OPENALEX
from .metadata import (
    ARXIV_DOI_PREFIX,
    MAX_AUTHORS,
    MAX_FIELD_CHARS,
    METADATA_FIELDS,
    author_identifier_lists,
    authorships_of,
    fetch_openalex_url,
    openalex_id_url,
    parse_openalex_work,
    venue_of,
)
from .sources import SearchQuery, SourceResult, authors_from_feed, fetch_arxiv_by_id
from .transport import HttpClient

_logger = logging.getLogger(__name__)

REFERENCE_LIST_NAME = "referenzen.txt"
"""Dateiname der kuratierten Kennungsliste unterhalb des Eingangsordners."""

REFERENCE_FIELDS = f"{METADATA_FIELDS},abstract_inverted_index"
"""OpenAlex-Feldsatz der Referenz-Auflösung – wie bei den Zitationsdaten, plus Abstract."""

MAX_ABSTRACT_CHARS = 5000
"""Längengrenze des übernommenen Abstracts."""

MAX_URL_CHARS = 500
"""Längengrenze für Verweise; längere werden verworfen."""

MAX_TITLE_SLUG_CHARS = 40
"""Längengrenze des sprechenden Namensteils."""

MAX_ID_SLUG_CHARS = 70
"""Längengrenze des Identifikator-Teils im Dateinamen (danach mit Kurz-Hash gekürzt)."""

TITLE_SLUG_WORDS = 3
"""Höchstzahl der Wörter im sprechenden Namensteil."""

COLON_PREFIX_WORDS = 4
"""Bis zu so vielen Wörtern vor einem Doppelpunkt gilt der Vorspann als System-/Modellname."""

DEFAULT_LIMIT = 25
"""Obergrenze der Abfragen je Lauf – schont das Kontingent der abgefragten Dienste."""

KIND_DOI = "doi"
"""Kennungsart: DOI."""

KIND_ARXIV = "arxiv"
"""Kennungsart: arXiv-Identifikator (ohne Version)."""

ACTION_WRITTEN = "written"
"""Ergebnis: Stub-Datei wurde geschrieben."""

ACTION_SKIPPED = "skipped"
"""Ergebnis: bereits vorhanden – es wurde **keine** Abfrage gestellt."""

ACTION_UNRESOLVED = "unresolved"
"""Ergebnis: abgefragt, aber ohne verwertbaren Treffer (kein Titel)."""

ACTION_INVALID = "invalid"
"""Ergebnis: Zeile der Liste ist keine deutbare Kennung."""

REASON_IN_CORPUS = "in_corpus"
"""Grund: Das Paper liegt bereits im Korpus."""

REASON_STUB_EXISTS = "stub_exists"
"""Grund: Im Eingang liegt bereits eine Stub-Datei zu dieser Kennung."""

REASON_QUARANTINED = "quarantined"
"""Grund: In der Quarantäne liegt bereits eine Stub-Datei zu dieser Kennung."""

REASON_DUPLICATE_LINE = "duplicate_line"
"""Grund: Dieselbe Kennung steht mehrfach in der Liste."""

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "or",
        "the",
        "to",
        "towards",
        "via",
        "with",
        "without",
    }
)

_DOI_CORE = r"10\.\d{4,9}/[^\s\"'<>]+"
_DOI_PATTERN = re.compile(rf"(?i)(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?({_DOI_CORE})")
_ARXIV_NEW = re.compile(r"(?i)(?:arxiv[:/]\s*)?(\d{4}\.\d{4,5})(?:v\d+)?\b")
_ARXIV_OLD = re.compile(r"(?i)(?:arxiv[:/]\s*)?([a-z][a-z.-]+/\d{7})(?:v\d+)?\b")
_ARXIV_URL = re.compile(r"(?i)arxiv\.org/(?:abs|pdf)/([^\s?#]+)")
_ARXIV_DOI = re.compile(rf"(?i)^{re.escape(ARXIV_DOI_PREFIX)}(.+)$")
_DOI_TRAILING = ".,;:)]}>"
_SLUG_ALLOWED = re.compile(r"[^a-z0-9]+")
_ID_SLUG_ALLOWED = re.compile(r"[^a-z0-9._-]+")


@dataclass(frozen=True)
class ReferenceRequest:
    """Eine Zeile der Kennungsliste, so weit gedeutet, wie es netzfrei möglich ist.

    Attributes:
        line_number: Zeilennummer in der Liste (1-basiert, für Befunde im Bericht).
        raw: Die Zeile, wie sie in der Datei steht (ohne Zeilenende).
        kind: :data:`KIND_DOI`, :data:`KIND_ARXIV` oder leer, wenn nicht deutbar.
        value: Die normalisierte Kennung (DOI ohne URL-Präfix, arXiv-ID ohne Version).
        comment: Der Kommentar hinter der Kennung, sofern vorhanden.
    """

    line_number: int
    raw: str
    kind: str = ""
    value: str = ""
    comment: str = ""

    @property
    def key(self) -> tuple[str, str]:
        """Der Vergleichsschlüssel ``(Art, Wert)`` – identisch zum Schlüssel des Intake."""
        return (self.kind, self.value.lower())

    @property
    def label(self) -> str:
        """Sprechende Kurzform der Kennung (``arxiv:2404.16130``)."""
        return f"{self.kind}:{self.value}" if self.kind else self.raw.strip()


@dataclass(frozen=True)
class ReferenceOutcome:
    """Das Ergebnis für **eine** Zeile der Liste.

    Attributes:
        request: Die auslösende Zeile.
        action: :data:`ACTION_WRITTEN`, :data:`ACTION_SKIPPED`, :data:`ACTION_UNRESOLVED` oder
            :data:`ACTION_INVALID`.
        reason: Maschinenlesbarer Grund bei :data:`ACTION_SKIPPED`, sonst leer.
        note: Klartext-Begründung – auch (und gerade) im Misserfolgsfall.
        path: Die geschriebene Datei, sofern eine entstanden ist.
        title: Der aufgelöste Titel, sofern einer gefunden wurde.
        has_abstract: ``True``, wenn ein Abstract übernommen wurde.
        raw: Rohantworten des Laufs für die Ablage.
    """

    request: ReferenceRequest
    action: str
    reason: str = ""
    note: str = ""
    path: Path | None = None
    title: str = ""
    has_abstract: bool = False
    raw: tuple[SourceResult, ...] = ()


def _clean(text: str, *, limit: int = MAX_FIELD_CHARS) -> str:
    """Bereinigt eine fremde Zeichenkette (einzeilig, druckbar, längenbegrenzt)."""
    printable = "".join(char if char.isprintable() else " " for char in text)
    return " ".join(printable.split())[:limit].strip()


def _safe_url(url: str) -> str:
    """Gibt einen Verweis nur zurück, wenn Schema und Länge unbedenklich sind.

    Bewusst enger und anders als :func:`research_graphrag.online.report.safe_url`: Ziel ist hier
    eine JSON-Datei, kein Markdown – eine Maskierung von Steuerzeichen würde den Wert verfälschen.
    """
    cleaned = "".join(char for char in url.strip() if char.isprintable() and not char.isspace())
    if not cleaned.startswith(("https://", "http://")) or len(cleaned) > MAX_URL_CHARS:
        return ""
    return cleaned


def normalize_identifier(text: str) -> tuple[str, str]:
    """Deutet eine Kennung in beliebiger gebräuchlicher Schreibweise.

    Erkannt werden DOIs (nackt, mit ``doi:``-Präfix oder als ``https://doi.org/…``) und
    arXiv-Kennungen (neu ``2404.16130``, alt ``cs/0501001``, mit ``arXiv:``-Präfix oder als
    ``arxiv.org/abs/…``). Der DataCite-DOI ``10.48550/arXiv.X`` wird zur arXiv-Kennung ``X``
    normalisiert – beide bezeichnen dasselbe Werk.

    Args:
        text: Die zu deutende Zeichenkette.

    Returns:
        ``(Art, Wert)`` mit der Art :data:`KIND_DOI` oder :data:`KIND_ARXIV`; nicht deutbare
        Eingaben ergeben ``("", "")``.
    """
    candidate = text.strip()
    if not candidate:
        return ("", "")

    url_match = _ARXIV_URL.search(candidate)
    if url_match:
        candidate = url_match.group(1)

    doi_match = _DOI_PATTERN.search(candidate)
    if doi_match:
        value = doi_match.group(1).rstrip(_DOI_TRAILING)
        arxiv_doi = _ARXIV_DOI.match(value)
        if arxiv_doi:
            return (KIND_ARXIV, arxiv_doi.group(1).rstrip(_DOI_TRAILING))
        return (KIND_DOI, value)

    old_match = _ARXIV_OLD.search(candidate)
    if old_match:
        return (KIND_ARXIV, old_match.group(1).lower())
    new_match = _ARXIV_NEW.search(candidate)
    if new_match:
        return (KIND_ARXIV, new_match.group(1))
    return ("", "")


def read_reference_list(path: Path) -> tuple[ReferenceRequest, ...]:
    """Liest die Kennungsliste; die Datei selbst bleibt unverändert.

    Leerzeilen und reine Kommentarzeilen (``#``) entfallen. Ein Kommentar **hinter** einer
    Kennung wird als Begründung mitgeführt. Eine nicht deutbare Zeile wird als Eintrag mit leerer
    Art zurückgegeben – der Aufrufer meldet sie als Befund, statt den Lauf abzubrechen.

    Args:
        path: Pfad der Liste (üblicherweise ``new_papers/referenzen.txt``).

    Returns:
        Die Einträge in Dateireihenfolge.

    Raises:
        DomainError: ``not_found`` wenn die Datei fehlt (siehe docs/error-model.md).
    """
    if not path.is_file():
        raise DomainError(
            ErrorCode.NOT_FOUND,
            f"Kennungsliste nicht gefunden: {path}. Datei anlegen und je Zeile eine DOI oder "
            "arXiv-ID eintragen (`#` leitet einen Kommentar ein).",
        )
    requests: list[ReferenceRequest] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        payload, _, comment = raw.partition("#")
        if not payload.strip():
            continue
        kind, value = normalize_identifier(payload)
        requests.append(
            ReferenceRequest(
                line_number=number,
                raw=raw.rstrip(),
                kind=kind,
                value=value,
                comment=_clean(comment, limit=200),
            )
        )
    return tuple(requests)


def stub_identifiers(inbox: Path) -> dict[tuple[str, str], Path]:
    """Sammelt die Kennungen **aller** Stub-Dateien im Eingang und in der Quarantäne.

    Bewusst inhaltsbasiert statt über den Dateinamen: Auch eine von Hand umbenannte Stub-Datei
    wird dadurch wiedererkannt. Eine unlesbare Datei wird protokolliert und übersprungen – sie
    darf einen ganzen Lauf nicht blockieren.

    Args:
        inbox: Eingangsordner (üblicherweise ``new_papers/``).

    Returns:
        ``(Art, Wert)`` → Pfad der Datei, in der die Kennung steht.
    """
    found: dict[tuple[str, str], Path] = {}
    for folder in (inbox, inbox / QUARANTINE_DIR):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob(f"*{STUB_SUFFIX}")):
            for key in _identifiers_of_stub(path):
                found.setdefault(key, path)
    return found


def _identifiers_of_stub(path: Path) -> tuple[tuple[str, str], ...]:
    """Liest die Kennungen einer Stub-Datei (defekte Dateien ergeben nichts)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Stub-Datei nicht lesbar, wird übersprungen: %s (%s)", path, exc)
        return ()
    if not isinstance(payload, dict):
        _logger.warning("Stub-Datei ohne Objekt-Struktur, wird übersprungen: %s", path)
        return ()
    keys: list[tuple[str, str]] = []
    for kind, name in ((KIND_DOI, "doi"), (KIND_ARXIV, "arxiv_id")):
        value = str(payload.get(name) or "").strip().lower()
        if value:
            keys.append((kind, value))
    requested = normalize_identifier(str(payload.get("requested") or ""))
    if requested[0]:
        keys.append((requested[0], requested[1].lower()))
    return tuple(dict.fromkeys(keys))


def plan(
    requests: Sequence[ReferenceRequest],
    corpus: CorpusView,
    stubs: dict[tuple[str, str], Path],
) -> tuple[list[ReferenceRequest], list[ReferenceOutcome]]:
    """Trennt die abzufragenden Einträge von denen, die bereits erledigt sind.

    Geprüft wird gegen drei Zustände – Korpus, Stub-Dateien im Eingang und Quarantäne –, und zwar
    **vor** jeder Abfrage: Ein Wiederholungslauf soll weder Kontingent verbrauchen noch eine
    zweite Datei erzeugen (docs/adr/0029-reference-stub-resolution-phase13.md).

    Args:
        requests: Die gelesenen Einträge der Liste.
        corpus: Prüfgrundlage aus :func:`research_graphrag.intake.load_corpus`.
        stubs: Bereits vorhandene Stub-Kennungen aus :func:`stub_identifiers`.

    Returns:
        Die abzufragenden Einträge und die bereits entschiedenen Ergebnisse (in Listenreihenfolge).
    """
    pending: list[ReferenceRequest] = []
    settled: list[ReferenceOutcome] = []
    seen: set[tuple[str, str]] = set()
    quarantine = QUARANTINE_DIR

    for request in requests:
        if not request.kind:
            settled.append(
                ReferenceOutcome(
                    request=request,
                    action=ACTION_INVALID,
                    note=f"Zeile {request.line_number} ist keine deutbare DOI/arXiv-Kennung",
                )
            )
            continue
        if request.key in seen:
            settled.append(
                ReferenceOutcome(
                    request=request,
                    action=ACTION_SKIPPED,
                    reason=REASON_DUPLICATE_LINE,
                    note="Kennung steht mehrfach in der Liste",
                )
            )
            continue
        seen.add(request.key)
        if request.key in corpus.identifier_to_paper:
            settled.append(
                ReferenceOutcome(
                    request=request,
                    action=ACTION_SKIPPED,
                    reason=REASON_IN_CORPUS,
                    note=f"liegt im Korpus als {corpus.identifier_to_paper[request.key]}",
                )
            )
            continue
        existing = stubs.get(request.key)
        if existing is not None:
            in_quarantine = existing.parent.name == quarantine
            settled.append(
                ReferenceOutcome(
                    request=request,
                    action=ACTION_SKIPPED,
                    reason=REASON_QUARANTINED if in_quarantine else REASON_STUB_EXISTS,
                    note=f"Stub-Datei liegt bereits vor: {existing.name}",
                    path=existing,
                )
            )
            continue
        pending.append(request)
    return pending, settled


def title_slug(title: str) -> str:
    """Bildet den sprechenden Teil des Dateinamens aus dem Titel.

    Steht vor dem ersten Doppelpunkt ein kurzer Vorspann (bis :data:`COLON_PREFIX_WORDS`
    Wörter), wird dieser genommen – die verbreitete Titelkonvention macht damit den System- oder
    Modellnamen sichtbar (``GraphRAG: From Local to Global`` → ``graphrag``). Sonst dienen die
    ersten bedeutungstragenden Wörter des Titels als Slug.

    Der Slug entsteht ausschließlich über eine **Whitelist** (``a``–``z``, ``0``–``9``); ein
    fremder Wert kann den Dateinamen dadurch weder verlassen noch verlängern.

    Args:
        title: Titel aus der Antwort der Quelle.

    Returns:
        Den Slug, oder eine leere Zeichenkette, wenn kein brauchbares Wort übrig bleibt.
    """
    head = title.split(":", 1)[0] if ":" in title else title
    if len(head.split()) > COLON_PREFIX_WORDS:
        head = title
    words = [word for word in _SLUG_ALLOWED.sub(" ", ascii_fold(head.lower())).split() if word]
    meaningful = [word for word in words if word not in _STOPWORDS] or words
    return "-".join(meaningful[:TITLE_SLUG_WORDS])[:MAX_TITLE_SLUG_CHARS].strip("-")


def stub_filename(kind: str, value: str, title: str = "") -> str:
    """Bildet den Dateinamen einer Stub-Datei: sprechendes Wort plus Kennung als Anker.

    Args:
        kind: Kennungsart (:data:`KIND_DOI` oder :data:`KIND_ARXIV`).
        value: Die Kennung.
        title: Titel aus der Antwort; fehlt er, entsteht ein Name allein aus der Kennung.

    Returns:
        Den Dateinamen inklusive :data:`STUB_SUFFIX`.
    """
    identifier = _ID_SLUG_ALLOWED.sub("_", f"{kind}-{value}".lower()).strip("_-")
    if len(identifier) > MAX_ID_SLUG_CHARS:
        digest = _short_digest(f"{kind}:{value}")
        identifier = f"{identifier[:MAX_ID_SLUG_CHARS]}-{digest}"
    slug = title_slug(title)
    parts = ["ref", slug, identifier] if slug else ["ref", identifier]
    return "-".join(parts) + STUB_SUFFIX


def _short_digest(text: str) -> str:
    """Kurzer, stabiler Hash für gekürzte Dateinamen."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def build_stub(
    request: ReferenceRequest,
    *,
    title: str,
    authors: Iterable[str] = (),
    author_ids: Sequence[str] = (),
    author_orcids: Sequence[str] = (),
    year: int = 0,
    venue: str = "",
    doi: str = "",
    arxiv_id: str = "",
    url: str = "",
    abstract: str = "",
    source: str = "",
    source_url: str = "",
    retrieved_at: str = "",
    note: str = "",
) -> dict[str, object]:
    """Baut den Inhalt einer Stub-Datei – bereinigt und in fester Feldreihenfolge.

    Die Feldnamen sind deckungsgleich mit
    :class:`research_graphrag.bibliography.model.MetadataRecord`, damit die Übernahme in R2 eine
    Zuweisung bleibt. ``abstract`` steht bewusst am Ende: Es ist das einzige Feld, das von Hand
    nachgetragen wird.

    ``author_ids``/``author_orcids`` stehen positionsgleich zu ``authors`` (Format 0.2.0,
    docs/adr/0041-author-identity-and-schema.md). Entfällt ein Name bei der Bereinigung, entfällt
    seine Kennung mit ihm, damit die Zuordnung erhalten bleibt. Passen die Listen nicht zur
    Namensliste, werden sie leer geschrieben.

    Returns:
        Den Datensatz als serialisierbares ``dict``.
    """
    raw_names = list(authors)
    ids = list(author_ids) if len(author_ids) == len(raw_names) else [""] * len(raw_names)
    orcids = list(author_orcids) if len(author_orcids) == len(raw_names) else [""] * len(raw_names)
    kept = [
        (name, ids[position], orcids[position])
        for position, name in enumerate(_clean(item, limit=200) for item in raw_names)
        if name
    ][:MAX_AUTHORS]
    kept_ids = [normalize_openalex_author_id(value) for _, value, _ in kept]
    kept_orcids = [normalize_orcid(value) for _, _, value in kept]
    return {
        "schema_version": STUB_SCHEMA_VERSION,
        "document_kind": DOCUMENT_KIND_REFERENCE,
        "requested": request.label,
        "title": _clean(title),
        "authors": [name for name, _, _ in kept],
        "author_ids": kept_ids if any(kept_ids) else [],
        "author_orcids": kept_orcids if any(kept_orcids) else [],
        "year": year if year > 0 else 0,
        "venue": _clean(venue),
        "doi": _clean(doi, limit=200),
        "arxiv_id": _clean(arxiv_id, limit=100),
        "url": _safe_url(url),
        "source": _clean(source, limit=100),
        "source_url": _safe_url(source_url),
        "retrieved_at": _clean(retrieved_at, limit=40),
        "note": _clean(note, limit=300),
        "abstract": _clean(abstract, limit=MAX_ABSTRACT_CHARS),
    }


def write_stub(inbox: Path, payload: dict[str, object], filename: str) -> Path:
    """Schreibt eine Stub-Datei atomar in den Eingangsordner.

    Args:
        inbox: Eingangsordner (üblicherweise ``new_papers/``).
        payload: Der Datensatz aus :func:`build_stub`.
        filename: Dateiname aus :func:`stub_filename`.

    Returns:
        Den Pfad der geschriebenen Datei.
    """
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / filename
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp_path = target.with_name(target.name + ".tmp")
    try:
        tmp_path.write_bytes(text.encode("utf-8"))
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)
    return target


@dataclass(frozen=True)
class ReferenceLookup:
    """Das Abfrageergebnis einer Kennung, netzfrei weiterverarbeitbar.

    Attributes:
        title: Titel des Werks; leer, wenn keine Quelle etwas geliefert hat.
        authors: Autoren in Nennreihenfolge.
        year: Erscheinungsjahr; ``0`` wenn unbekannt.
        venue: Journal, Konferenz oder Verlag.
        doi: DOI ohne URL-Präfix.
        arxiv_id: arXiv-Identifikator ohne Version.
        url: Landing- oder Volltext-Link.
        abstract: Abstract als Fließtext; leer, wenn keine Quelle einen liefert.
        source: Quelle, aus der die Felder stammen.
        source_url: Tatsächlich abgerufene URL (Reproduzierbarkeit).
        raw: Rohantworten des Laufs für die Ablage.
        note: Klartext-Begründung, wenn etwas fehlt.
        author_ids: OpenAlex-Autor-IDs positionsgleich zu ``authors`` (nur aus OpenAlex).
        author_orcids: ORCIDs positionsgleich zu ``authors`` (nur aus OpenAlex).
    """

    title: str = ""
    authors: tuple[str, ...] = ()
    year: int = 0
    venue: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    abstract: str = ""
    source: str = ""
    source_url: str = ""
    raw: tuple[SourceResult, ...] = ()
    note: str = ""
    author_ids: tuple[str, ...] = ()
    author_orcids: tuple[str, ...] = ()


def _openalex_lookup(client: HttpClient, identifier: str) -> ReferenceLookup:
    """Fragt OpenAlex über einen DOI ab (für arXiv über den DataCite-DOI)."""
    url = openalex_id_url(identifier, fields=REFERENCE_FIELDS)
    source = fetch_openalex_url(client, url)
    if source.status != 200:
        return ReferenceLookup(raw=(source,), note=source.note)
    candidate = parse_openalex_work(source.raw)
    if candidate is None:
        return ReferenceLookup(raw=(source,), note=f"OpenAlex kennt {identifier} nicht")
    identities = authorships_of(source.raw)
    author_ids, author_orcids = author_identifier_lists(identities)
    return ReferenceLookup(
        title=candidate.title,
        authors=tuple(identity.name for identity in identities),
        author_ids=author_ids,
        author_orcids=author_orcids,
        year=candidate.year,
        venue=venue_of(source.raw),
        doi=candidate.doi,
        arxiv_id=candidate.arxiv_id,
        url=candidate.url,
        abstract=candidate.abstract,
        source=SOURCE_OPENALEX,
        source_url=url,
        raw=(source,),
    )


def _arxiv_lookup(client: HttpClient, arxiv_id: str) -> ReferenceLookup:
    """Fragt den arXiv-Feed über die **Kennung** ab (liefert Titel, Abstract und Preprint-Jahr)."""
    query = SearchQuery(query_id=arxiv_id, terms=(arxiv_id,), reason="Referenz-Eintrag")
    source = fetch_arxiv_by_id(client, arxiv_id, query)
    if source.status != 200 or not source.candidates:
        return ReferenceLookup(raw=(source,), note=source.note or f"arXiv kennt {arxiv_id} nicht")
    candidate = source.candidates[0]
    # Alte Kennungen (``cs/0501001``) verlieren beim Auslesen des Feeds ihr Archiv-Präfix;
    # der Vergleich muss das zulassen, sonst ist der Rückfall für sie unbrauchbar.
    returned = candidate.arxiv_id
    if returned and returned not in (arxiv_id, arxiv_id.rsplit("/", 1)[-1]):
        return ReferenceLookup(
            raw=(source,), note=f"arXiv lieferte eine andere ID ({candidate.arxiv_id})"
        )
    return ReferenceLookup(
        title=candidate.title,
        authors=authors_from_feed(source.raw),
        year=candidate.year,
        doi=candidate.doi,
        arxiv_id=arxiv_id,
        url=candidate.url,
        abstract=candidate.abstract,
        source=SOURCE_ARXIV,
        source_url=source.url,
        raw=(source,),
    )


def resolve_reference(client: HttpClient, request: ReferenceRequest) -> ReferenceLookup:
    """Löst **eine** Kennung auf – OpenAlex zuerst, arXiv-Feed als Rückfall und Abstract-Quelle.

    Der arXiv-Feed wird immer dann noch befragt, wenn eine arXiv-Kennung bekannt ist (aus der
    Anfrage oder aus der OpenAlex-Antwort) und OpenAlex entweder gar nichts oder **keinen**
    Abstract geliefert hat. Genau diese Kombination hat die Vorabmessung R0 gemessen (Ausbeute
    93 %); ohne sie wäre der gemessene Wert nicht reproduzierbar.

    Args:
        client: Injizierter Transport-Port (die einzige Stelle mit Netzzugriff).
        request: Die aufzulösende Kennung.

    Returns:
        Das Abfrageergebnis samt Rohantworten; ohne Treffer ist ``title`` leer und ``note``
        nennt den Grund.
    """
    identifier = request.value if request.kind == KIND_DOI else f"{ARXIV_DOI_PREFIX}{request.value}"
    primary = _openalex_lookup(client, identifier)
    arxiv_id = request.value if request.kind == KIND_ARXIV else primary.arxiv_id
    if not arxiv_id or (primary.title and primary.abstract):
        return primary

    fallback = _arxiv_lookup(client, arxiv_id)
    collected = primary.raw + fallback.raw
    if primary.title:
        return replace(
            primary,
            abstract=primary.abstract or fallback.abstract,
            raw=collected,
            note="" if fallback.abstract else fallback.note,
        )
    if fallback.title:
        return replace(fallback, arxiv_id=fallback.arxiv_id or arxiv_id, raw=collected)
    return replace(
        primary,
        raw=collected,
        note="; ".join(part for part in (primary.note, fallback.note) if part),
    )


def process(client: HttpClient, request: ReferenceRequest, inbox: Path) -> ReferenceOutcome:
    """Löst eine Kennung auf und schreibt die Stub-Datei, sofern ein Titel vorliegt.

    Ohne Titel entsteht **keine** Datei: Ein Eintrag ohne Titel wäre weder zitierfähig noch als
    Ziel einer Titel-Kante brauchbar. Ohne Abstract entsteht sie sehr wohl – er wird dann von
    Hand nachgetragen (docs/adr/0029-reference-stub-resolution-phase13.md).

    Args:
        client: Injizierter Transport-Port.
        request: Die aufzulösende Kennung.
        inbox: Eingangsordner (üblicherweise ``new_papers/``).

    Returns:
        Das Ergebnis für diese Kennung.
    """
    found = resolve_reference(client, request)
    if not found.title.strip():
        return ReferenceOutcome(
            request=request,
            action=ACTION_UNRESOLVED,
            note=found.note or "keine Quelle liefert Titel-Angaben",
            raw=found.raw,
        )

    hint = "" if found.abstract.strip() else "Abstract von Hand nachtragen"
    payload = build_stub(
        request,
        title=found.title,
        authors=found.authors,
        author_ids=found.author_ids,
        author_orcids=found.author_orcids,
        year=found.year,
        venue=found.venue,
        doi=found.doi or (request.value if request.kind == KIND_DOI else ""),
        arxiv_id=found.arxiv_id or (request.value if request.kind == KIND_ARXIV else ""),
        url=found.url,
        abstract=found.abstract,
        source=found.source,
        source_url=found.source_url,
        retrieved_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        note=hint,
    )
    filename = stub_filename(request.kind, request.value, found.title)
    path = write_stub(inbox, payload, filename)
    note = f"{found.source}: {found.title[:80]}"
    return ReferenceOutcome(
        request=request,
        action=ACTION_WRITTEN,
        note=f"{note} ({hint})" if hint else note,
        path=path,
        title=str(payload["title"]),
        has_abstract=bool(payload["abstract"]),
        raw=found.raw,
    )
