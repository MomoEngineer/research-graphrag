"""Orchestrierung des Online-Modus: Anfragen aus dem Bestand und Ablauf eines Laufs.

Zwei Aufgaben:

1. **Anfragen entstehen aus dem eigenen Korpus** – aus den Keywords einer Community
   (:func:`query_from_community`) oder aus dem Titel eines Seed-Papers
   (:func:`query_from_seed`). Eine freie Volltextsuche ist bewusst nicht vorgesehen; der Wert
   des Modus liegt im Bezug zum eigenen Bestand
   (docs/adr/0020-online-candidate-search-phase9.md).
2. **Ein Lauf** (:func:`discover`) fragt beide Quellen ab, führt Dubletten zusammen, prüft gegen
   den Korpus, wendet den Aktualitätsfilter an und liefert das Ergebnis als
   :class:`~.report.DiscoveryReport`. Geschrieben wird hier nichts – das entscheidet der Aufrufer.

Die Funktion ist die **Single Source of Truth** für die CLI; der Netzzugang kommt ausschließlich
über den injizierten :class:`~.transport.HttpClient`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from ..errors import DomainError, ErrorCode
from ..indexing.citation_graph import title_from_uri
from ..indexing.graph_index import load_communities
from ..intake import load_corpus
from ..keywords import is_noise_term
from ..retrieval.paper import get_paper
from .candidates import Candidate, filter_recent, merge_candidates, partition
from .report import DiscoveryReport, store_raw
from .sources import DEFAULT_LIMIT, SearchQuery, SourceResult, fetch_arxiv, fetch_openalex
from .transport import HttpClient

DEFAULT_TERM_COUNT = 3
"""Zahl der Suchbegriffe je Anfrage (mehr UND-Terme lassen arXiv leer laufen)."""

DEFAULT_RECENT_YEARS = 5
"""Standard-Zeitfenster des Aktualitätsfilters in Jahren (in S0 als wirksamster Filter gemessen)."""

MIN_TERM_CHARS = 3
"""Kürzere Titelwörter tragen keine Bedeutung für eine Suchanfrage."""

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+-]*")


def default_min_year(*, years: int = DEFAULT_RECENT_YEARS, today: datetime | None = None) -> int:
    """Bestimmt die Jahresgrenze des Aktualitätsfilters.

    Args:
        years: Zeitfenster in Jahren.
        today: Bezugszeitpunkt; ``None`` nutzt die aktuelle UTC-Zeit.

    Returns:
        Das früheste zulässige Erscheinungsjahr.
    """
    reference = today or datetime.now(UTC)
    return reference.year - years


def query_from_community(
    db_path: Path, community_id: int, *, terms: int = DEFAULT_TERM_COUNT
) -> SearchQuery:
    """Bildet eine Anfrage aus den Keywords einer Community.

    Args:
        db_path: Pfad zum Index.
        community_id: Kennung der Community aus ``list_topics``/``scripts.graph_info``.
        terms: Zahl der übernommenen Keywords.

    Returns:
        Die Anfrage samt Herkunftsbegründung.

    Raises:
        DomainError: ``not_found`` wenn es die Community nicht gibt, ``constraint_violation``
            wenn sie keine Keywords trägt.
    """
    views = {view.community_id: view for view in load_communities(db_path)}
    view = views.get(community_id)
    if view is None:
        raise DomainError(
            ErrorCode.NOT_FOUND,
            f"Community {community_id} ist im Index nicht vorhanden.",
        )
    selected = tuple(view.keywords[:terms])
    if not selected:
        raise DomainError(
            ErrorCode.CONSTRAINT_VIOLATION,
            f"Community {community_id} trägt keine Keywords.",
        )
    reason = f"Community {community_id} ({view.size} Paper) im eigenen Ähnlichkeitsgraphen"
    return SearchQuery(query_id=f"C{community_id}", terms=selected, reason=reason)


def query_from_seed(
    db_path: Path, paper_id: str, *, terms: int = DEFAULT_TERM_COUNT
) -> SearchQuery:
    """Bildet eine Anfrage aus dem Titel eines Korpus-Papers („mehr wie dieses").

    Die Suchbegriffe sind die ersten inhaltstragenden Titelwörter – Stopwords und die kuratierten
    Rausch-Terme aus :mod:`research_graphrag.keywords` entfallen. Die Auswahl über die
    Titelreihenfolge ist bewusst simpel und deterministisch.

    Args:
        db_path: Pfad zum Index.
        paper_id: Kennung des Seed-Papers.
        terms: Zahl der übernommenen Titelwörter.

    Returns:
        Die Anfrage samt Herkunftsbegründung.

    Raises:
        DomainError: ``not_found`` wenn es das Paper nicht gibt, ``constraint_violation`` wenn
            der Titel keine brauchbaren Begriffe enthält.
    """
    detail = get_paper(db_path, paper_id)
    title = title_from_uri(detail.source_uri)
    selected = tuple(title_terms(title)[:terms])
    if not selected:
        raise DomainError(
            ErrorCode.CONSTRAINT_VIOLATION,
            f"Aus dem Titel von {paper_id} lässt sich keine Anfrage bilden: {title!r}",
        )
    return SearchQuery(
        query_id=f"S{paper_id[:8]}",
        terms=selected,
        reason=f"Seed-Paper „{title}“ ({paper_id})",
    )


def title_terms(title: str) -> list[str]:
    """Zerlegt einen Titel in inhaltstragende Suchbegriffe (Reihenfolge bleibt erhalten)."""
    words: list[str] = []
    for match in _WORD.finditer(title):
        word = match.group(0).lower()
        if len(word) < MIN_TERM_CHARS or word in ENGLISH_STOP_WORDS or is_noise_term(word):
            continue
        if word not in words:
            words.append(word)
    return words


def discover(
    db_path: Path,
    data_path: Path,
    queries: Sequence[SearchQuery],
    client: HttpClient,
    *,
    limit: int = DEFAULT_LIMIT,
    min_year: int | None = None,
    keep_raw: bool = True,
) -> DiscoveryReport:
    """Führt einen Suchlauf aus und liefert das Ergebnis – ohne den Bericht zu schreiben.

    Ablauf: je Anfrage beide Quellen abfragen, Dubletten **quellenübergreifend** zusammenführen,
    gegen den Korpus prüfen und erst danach den Aktualitätsfilter anwenden. Diese Reihenfolge
    hält bereits vorhandene Paper auch dann im Bericht, wenn sie älter als die Jahresgrenze sind –
    die Dedup-Entscheidung bleibt dadurch nachvollziehbar.

    Args:
        db_path: Pfad zum Index (Quelle der Anfragen).
        data_path: Datenverzeichnis (Prüfgrundlage und Ablage der Rohantworten).
        queries: Die zu stellenden Anfragen.
        client: Injizierter Netzzugang.
        limit: Treffer je Quelle und Anfrage.
        min_year: Jahresgrenze; ``None`` nutzt :func:`default_min_year`.
        keep_raw: Legt die Rohantworten datiert ab (Reproduzierbarkeit).

    Returns:
        Das Laufergebnis.

    Raises:
        DomainError: ``invalid_input`` wenn keine Anfrage übergeben wurde; Netz- und
            Parse-Fehler werden aus Transport und Quellen durchgereicht.
    """
    if not queries:
        raise DomainError(ErrorCode.INVALID_INPUT, "Es wurde keine Anfrage übergeben.")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    threshold = default_min_year() if min_year is None else min_year

    results: list[SourceResult] = []
    harvested: list[Candidate] = []
    for query in queries:
        for fetch in (fetch_arxiv, fetch_openalex):
            result = fetch(client, query, limit=limit)
            results.append(result)
            harvested.extend(result.candidates)

    merged = merge_candidates(harvested)
    fresh, known = partition(merged, load_corpus(data_path))
    recent = filter_recent(fresh, threshold)
    notes = tuple(_rate_limit_notes(results))

    raw_dir = store_raw(data_path, timestamp, tuple(results)) if keep_raw else None
    return DiscoveryReport(
        timestamp=timestamp,
        queries=tuple(queries),
        sources=tuple(results),
        fresh=tuple(recent),
        known=tuple(known),
        found=len(merged),
        dropped_old=len(fresh) - len(recent),
        min_year=threshold,
        raw_dir=raw_dir,
        notes=notes,
    )


def _rate_limit_notes(results: Sequence[SourceResult]) -> list[str]:
    """Erzeugt einen Hinweis, wenn eine Quelle ihr Restkontingent knapp meldet."""
    notes: list[str] = []
    for result in results:
        remaining = result.rate_limit.get("x-ratelimit-remaining")
        limit = result.rate_limit.get("x-ratelimit-limit")
        if remaining and limit:
            notes.append(f"{result.source}: Kontingent {remaining} von {limit} verbleibend")
    return notes[-1:]
