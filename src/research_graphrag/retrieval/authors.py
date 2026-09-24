"""Personen-Werkzeuge: Autoren als Rechercheebene (Phase 17 / A4).

Vier read-only Abfragen über die Tabelle ``paper_authors`` aus
:mod:`research_graphrag.indexing.author_index`
(docs/adr/0043-author-index-and-person-tools.md):

* :func:`search_authors` – „Wer ist gemeint?“: Kandidaten je Personenschlüssel,
* :func:`get_author` – „Was hat X im Korpus?“: Paper, Jahresspanne, Communities, Mitautoren,
* :func:`search_author_papers` – „Was schreibt X über Y?“: Basic-Suche in den Papern der Person,
* :func:`get_author_citations` – „Wer zitiert X, wen zitiert X?“ innerhalb des Korpus.

Drei Regeln gelten für alle vier:

* **Abdeckung in jeder Antwort.** Die Personenebene kennt nur die Autoren belegter
  (``strong``) Zitierdaten. :class:`Coverage` weist aus, für wie viele Volltexte das gilt, damit
  keine Vollständigkeit suggeriert wird.
* **Keine stille Zusammenführung.** Je Personenschlüssel entsteht genau ein Kandidat; eine reine
  Namensidentität bleibt als ``identity = "name"`` erkennbar.
* **Obergrenze:** Jede Liste hält :data:`research_graphrag.limits.MAX_RESULT_COUNT` ein und nennt
  die Zahl vor der Kappung (ADR 0037).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.author_index import (
    AuthorRow,
    author_coverage,
    has_author_index,
    load_author_rows,
    search_name_keys,
)
from research_graphrag.indexing.citation_graph import load_citations
from research_graphrag.indexing.graph_index import load_communities
from research_graphrag.indexing.tfidf_index import TfidfIndex
from research_graphrag.limits import MAX_RESULT_COUNT, check_max_count
from research_graphrag.retrieval.provenance import Citation, ProvenanceAssembler

DEFAULT_CANDIDATE_LIMIT = 20
"""Standard-Deckel der Kandidatenliste von :func:`search_authors`."""

MAX_SAMPLE_TITLES = 3
"""Beispieltitel je Kandidat (die jüngsten Paper zuerst)."""

COMMUNITY_KEYWORDS = 5
"""Keywords je Community im Profil."""

SCOPE_CORPUS = "corpus"
"""Reichweite der Zitationsabfrage: nur Kanten zwischen Korpus-Papern."""

CORPUS_SCOPE_NOTE = (
    "Nur Zitationen innerhalb des Korpus: Werke außerhalb des Korpus und Verweise, die der "
    "Zitationsgraph nicht erkannt hat, fehlen. `methods` nennt, woran eine Kante erkannt wurde "
    "(doi, arxiv oder title)."
)
"""Klartext zur Grenze von :func:`get_author_citations`."""

REBUILD_HINT = (
    "Der Index enthält keine Personenebene (gebaut vor Phase 17 / A3); "
    "`python -m scripts.ingest` baut sie."
)
"""Hinweis für einen Index ohne Tabelle ``paper_authors``."""


@dataclass(frozen=True)
class Coverage:
    """Abdeckung der Personenebene: Volltexte mit belegten Autoren gegenüber allen Volltexten."""

    full_texts_with_authors: int
    full_texts: int

    @property
    def share(self) -> float:
        """Anteil der Volltexte mit Autoren (0, wenn der Index keine Volltexte enthält)."""
        if self.full_texts <= 0:
            return 0.0
        return round(self.full_texts_with_authors / self.full_texts, 4)

    @property
    def note(self) -> str:
        """Klartext zur Lücke; bei voller Abdeckung eine kurze Bestätigung."""
        if self.full_texts <= 0:
            return "Der Index enthält keine Volltexte."
        if self.full_texts_with_authors >= self.full_texts:
            return f"Alle {self.full_texts} Volltexte tragen belegte Autoren."
        percent = round(self.share * 100)
        return (
            f"Nur {self.full_texts_with_authors} von {self.full_texts} Volltexten ({percent} %) "
            "tragen belegte Autoren. Paper ohne belegte Zitierdaten fehlen auf der "
            "Personenebene; ein fehlender Treffer heißt nicht, dass die Person nichts im Korpus "
            "hat."
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Block (Teil jeder Antwort der Personen-Werkzeuge)."""
        return {
            "full_texts_with_authors": self.full_texts_with_authors,
            "full_texts": self.full_texts,
            "share": self.share,
            "note": self.note,
        }


@dataclass(frozen=True)
class PaperBrief:
    """Kurzangabe eines Papers: Titel, Jahr und die Angaben zum Weiterzitieren."""

    paper_id: str
    title: str
    year: int
    document_kind: str
    source_uri: str
    citation_key: str
    identifiers: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Kurzangabe (``year`` ist ``null``, wenn es unbekannt ist)."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "year": self.year or None,
            "document_kind": self.document_kind,
            "source_uri": self.source_uri,
            "citation_key": self.citation_key,
            "identifiers": dict(self.identifiers),
        }


@dataclass(frozen=True)
class AuthorCandidate:
    """Ein Personen-Kandidat der Namenssuche."""

    person_key: str
    identity: str
    openalex_id: str
    orcid: str
    names: tuple[str, ...]
    n_papers: int
    year_span: tuple[int, int] | None
    sample_titles: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Kandidaten."""
        return {
            "person_key": self.person_key,
            "identity": self.identity,
            "openalex_id": self.openalex_id,
            "orcid": self.orcid,
            "names": list(self.names),
            "n_papers": self.n_papers,
            "year_span": list(self.year_span) if self.year_span else None,
            "sample_titles": list(self.sample_titles),
        }


@dataclass(frozen=True)
class AuthorSearchResult:
    """Ergebnis von :func:`search_authors` (Output-Schema von ``search_authors``)."""

    query: str
    candidates: tuple[AuthorCandidate, ...]
    total_matching: int
    coverage: Coverage

    @property
    def ambiguous(self) -> bool:
        """``True``, sobald mehr als ein Kandidat passt – der Aufrufer wählt."""
        return self.total_matching > 1

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis."""
        return {
            "query": self.query,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "total_matching": self.total_matching,
            "ambiguous": self.ambiguous,
            "coverage": self.coverage.to_dict(),
        }


@dataclass(frozen=True)
class AuthorPaper:
    """Ein Paper im Profil einer Person samt ihrer Autorposition."""

    paper: PaperBrief
    position: int

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Eintrag (Kurzangabe plus 1-basierte Position)."""
        payload = self.paper.to_dict()
        payload["position"] = self.position
        return payload


@dataclass(frozen=True)
class AuthorCommunity:
    """Eine Themen-Community, in der Paper der Person liegen."""

    community_id: int
    n_papers: int
    keywords: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Community-Angabe."""
        return {
            "community_id": self.community_id,
            "n_papers": self.n_papers,
            "keywords": list(self.keywords),
        }


@dataclass(frozen=True)
class Coauthor:
    """Ein direkter Mitautor mit der Zahl gemeinsamer Paper."""

    person_key: str
    identity: str
    names: tuple[str, ...]
    n_shared: int

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Mitautor."""
        return {
            "person_key": self.person_key,
            "identity": self.identity,
            "names": list(self.names),
            "n_shared": self.n_shared,
        }


@dataclass(frozen=True)
class AuthorProfile:
    """Ergebnis von :func:`get_author` (Output-Schema von ``get_author``)."""

    person_key: str
    identity: str
    openalex_id: str
    orcid: str
    names: tuple[str, ...]
    papers: tuple[AuthorPaper, ...]
    papers_total: int
    year_span: tuple[int, int] | None
    communities: tuple[AuthorCommunity, ...]
    communities_total: int
    coauthors: tuple[Coauthor, ...]
    coauthors_total: int
    coverage: Coverage

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Profil."""
        return {
            "person_key": self.person_key,
            "identity": self.identity,
            "openalex_id": self.openalex_id,
            "orcid": self.orcid,
            "names": list(self.names),
            "papers": [paper.to_dict() for paper in self.papers],
            "papers_total": self.papers_total,
            "year_span": list(self.year_span) if self.year_span else None,
            "communities": [community.to_dict() for community in self.communities],
            "communities_total": self.communities_total,
            "coauthors": [coauthor.to_dict() for coauthor in self.coauthors],
            "coauthors_total": self.coauthors_total,
            "coverage": self.coverage.to_dict(),
        }


@dataclass(frozen=True)
class AuthorPapersResult:
    """Ergebnis von :func:`search_author_papers` (Output-Schema von ``search_author_papers``)."""

    person_key: str
    query: str
    papers_searched: int
    citations: tuple[Citation, ...]
    coverage: Coverage

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis (``citations`` im Contract von ``search_basic``)."""
        return {
            "person_key": self.person_key,
            "query": self.query,
            "papers_searched": self.papers_searched,
            "citations": [citation.to_dict() for citation in self.citations],
            "coverage": self.coverage.to_dict(),
        }


@dataclass(frozen=True)
class AuthorCitationLink:
    """Ein Gegenüber im Zitationsnetz der Person."""

    paper: PaperBrief
    via: tuple[str, ...]
    methods: tuple[str, ...]
    self_citation: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Gegenüber (``self`` markiert ein Selbstzitat)."""
        return {
            "paper": self.paper.to_dict(),
            "via": list(self.via),
            "methods": list(self.methods),
            "self": self.self_citation,
        }


@dataclass(frozen=True)
class AuthorCitationsResult:
    """Ergebnis von :func:`get_author_citations` (Output-Schema von ``get_author_citations``)."""

    person_key: str
    cites: tuple[AuthorCitationLink, ...]
    cites_total: int
    cited_by: tuple[AuthorCitationLink, ...]
    cited_by_total: int
    coverage: Coverage

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis samt Reichweite ``corpus``."""
        return {
            "person_key": self.person_key,
            "scope": SCOPE_CORPUS,
            "note": CORPUS_SCOPE_NOTE,
            "cites": [link.to_dict() for link in self.cites],
            "cites_total": self.cites_total,
            "cited_by": [link.to_dict() for link in self.cited_by],
            "cited_by_total": self.cited_by_total,
            "coverage": self.coverage.to_dict(),
        }


def coverage_of(db_path: str | Path) -> Coverage:
    """Liest die Abdeckung der Personenebene aus dem Index."""
    covered, total = author_coverage(db_path)
    return Coverage(full_texts_with_authors=covered, full_texts=total)


def _check_limit(name: str, value: int) -> None:
    """Prüft einen Deckel-Parameter (``0 < value <= MAX_RESULT_COUNT``)."""
    if value <= 0:
        raise DomainError(ErrorCode.INVALID_INPUT, f"{name} muss > 0 sein.")
    check_max_count(name, value)


def _check_person_key(person_key: str) -> str:
    """Prüft den Personenschlüssel und liefert ihn ohne Randleerzeichen."""
    key = person_key.strip()
    if not key:
        raise DomainError(ErrorCode.INVALID_INPUT, "Leerer person_key.")
    return key


def _not_found(message: str, db_path: str | Path, coverage: Coverage) -> DomainError:
    """Baut ``not_found`` mit der Abdeckung (und dem Neubau-Hinweis bei altem Index)."""
    detail = coverage.note
    if not has_author_index(db_path):
        detail = REBUILD_HINT
    return DomainError(ErrorCode.NOT_FOUND, f"{message} {detail}")


def _person_rows(db_path: str | Path, person_key: str, coverage: Coverage) -> tuple[AuthorRow, ...]:
    """Lädt die Zeilen einer Person (``not_found``, wenn der Schlüssel unbekannt ist)."""
    rows = load_author_rows(db_path, person_keys=[person_key])
    if not rows:
        raise _not_found(f"Unbekannter Personenschlüssel: {person_key}.", db_path, coverage)
    return rows


def _most_common(values: Iterable[str]) -> str:
    """Häufigster nicht leerer Wert (bei Gleichstand der alphabetisch erste), sonst leer."""
    counts = Counter(value for value in values if value)
    if not counts:
        return ""
    return min(counts, key=lambda value: (-counts[value], value))


def _brief(assembler: ProvenanceAssembler, paper_id: str) -> PaperBrief:
    """Kurzangabe eines Papers aus dem (prozessweit gecachten) Provenienz-Assembler."""
    ref = assembler.paper_ref(paper_id)
    metadata = assembler.metadata(paper_id)
    return PaperBrief(
        paper_id=paper_id,
        title=metadata.title,
        year=metadata.year,
        document_kind=ref.document_kind,
        source_uri=ref.source_uri,
        citation_key=ref.citation_key,
        identifiers=ref.identifiers,
    )


def _newest_first(briefs: Iterable[PaperBrief]) -> list[PaperBrief]:
    """Sortiert nach Jahr (absteigend, unbekanntes Jahr zuletzt), dann ``paper_id``."""
    return sorted(briefs, key=lambda brief: (-brief.year, brief.paper_id))


def _year_span(briefs: Iterable[PaperBrief]) -> tuple[int, int] | None:
    """Jahresspanne der Paper mit bekanntem Jahr (``None`` ohne Jahresangabe)."""
    years = [brief.year for brief in briefs if brief.year > 0]
    if not years:
        return None
    return min(years), max(years)


def _positions(rows: Sequence[AuthorRow]) -> dict[str, int]:
    """Autorposition je Paper (steht eine Person doppelt in einer Liste, zählt die erste)."""
    positions: dict[str, int] = {}
    for row in rows:
        positions[row.paper_id] = min(positions.get(row.paper_id, row.position), row.position)
    return positions


def _candidate(rows: Sequence[AuthorRow], assembler: ProvenanceAssembler) -> AuthorCandidate:
    """Fasst die Zeilen **eines** Personenschlüssels zu einem Kandidaten zusammen."""
    first = rows[0]
    briefs = _newest_first(_brief(assembler, paper_id) for paper_id in _positions(rows))
    return AuthorCandidate(
        person_key=first.person_key,
        identity=first.identity,
        openalex_id=_most_common(row.openalex_id for row in rows),
        orcid=_most_common(row.orcid for row in rows),
        names=tuple(sorted({row.name for row in rows})),
        n_papers=len(briefs),
        year_span=_year_span(briefs),
        sample_titles=tuple(brief.title for brief in briefs[:MAX_SAMPLE_TITLES] if brief.title),
    )


def _group(rows: Iterable[AuthorRow]) -> dict[str, list[AuthorRow]]:
    """Gruppiert Zeilen nach Personenschlüssel."""
    grouped: dict[str, list[AuthorRow]] = {}
    for row in rows:
        grouped.setdefault(row.person_key, []).append(row)
    return grouped


def search_authors(
    db_path: str | Path, name: str, *, limit: int = DEFAULT_CANDIDATE_LIMIT
) -> AuthorSearchResult:
    """Findet die Personen-Kandidaten zu einem Namen oder Namensteil.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        name: Name oder Namensteil in beliebiger Schreibweise („Asai, Akari“, „Y. Wang“).
        limit: Höchstzahl der Kandidaten (``0 < limit <= MAX_RESULT_COUNT``).

    Returns:
        Ein :class:`AuthorSearchResult`; je Personenschlüssel **ein** Kandidat, sortiert nach
        Paperzahl (absteigend), dann Schlüssel. Namen und Paperzahl umfassen **alle** Paper der
        Person, auch unter einer Schreibweise, die nicht zur Anfrage passt.

    Raises:
        DomainError: ``invalid_input`` bei leerem oder zeichenlosem Namen bzw. ungültigem
            ``limit``; ``not_found`` ohne Kandidaten (die Meldung nennt die Abdeckung) oder bei
            fehlender Index-Datei.
    """
    if not name.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leerer Name.")
    _check_limit("limit", limit)
    keys = search_name_keys(db_path, name)
    coverage = coverage_of(db_path)
    matching = load_author_rows(db_path, name_keys=keys) if keys else ()
    person_keys = {row.person_key for row in matching}
    if not person_keys:
        raise _not_found(f"Kein Autor passt zu „{name.strip()}“.", db_path, coverage)

    assembler = ProvenanceAssembler.load(db_path)
    grouped = _group(load_author_rows(db_path, person_keys=person_keys))
    candidates = sorted(
        (_candidate(rows, assembler) for rows in grouped.values()),
        key=lambda candidate: (-candidate.n_papers, candidate.person_key),
    )
    return AuthorSearchResult(
        query=name,
        candidates=tuple(candidates[:limit]),
        total_matching=len(candidates),
        coverage=coverage,
    )


def _communities(db_path: str | Path, paper_ids: Iterable[str]) -> list[AuthorCommunity]:
    """Communities der Paper samt Anzahl (leer, wenn kein Graph gebaut wurde)."""
    try:
        views = load_communities(db_path)
    except DomainError as exc:
        if exc.code is ErrorCode.CONSTRAINT_VIOLATION:
            return []
        raise
    community_of = {member: view for view in views for member in view.members}
    counts: Counter[int] = Counter()
    keywords: dict[int, tuple[str, ...]] = {}
    for paper_id in paper_ids:
        view = community_of.get(paper_id)
        if view is None:
            continue
        counts[view.community_id] += 1
        keywords[view.community_id] = view.keywords[:COMMUNITY_KEYWORDS]
    return [
        AuthorCommunity(community_id=cid, n_papers=counts[cid], keywords=keywords[cid])
        for cid in sorted(counts, key=lambda cid: (-counts[cid], cid))
    ]


def _coauthors(db_path: str | Path, person_key: str, paper_ids: Iterable[str]) -> list[Coauthor]:
    """Direkte Mitautoren je Personenschlüssel mit der Zahl gemeinsamer Paper."""
    grouped = _group(
        row
        for row in load_author_rows(db_path, paper_ids=paper_ids)
        if row.person_key != person_key
    )
    coauthors = [
        Coauthor(
            person_key=key,
            identity=rows[0].identity,
            names=tuple(sorted({row.name for row in rows})),
            n_shared=len({row.paper_id for row in rows}),
        )
        for key, rows in grouped.items()
    ]
    return sorted(coauthors, key=lambda coauthor: (-coauthor.n_shared, coauthor.person_key))


def get_author(
    db_path: str | Path, person_key: str, *, limit: int = MAX_RESULT_COUNT
) -> AuthorProfile:
    """Stellt das schlanke Profil einer Person zusammen.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        person_key: Personenschlüssel aus :func:`search_authors`.
        limit: Höchstzahl je Liste (Paper, Communities, Mitautoren).

    Returns:
        Ein :class:`AuthorProfile`; Paper nach Jahr (absteigend), dann ``paper_id``. Ohne
        Ähnlichkeitsgraphen bleibt die Community-Liste leer.

    Raises:
        DomainError: ``invalid_input`` bei leerem Schlüssel oder ungültigem ``limit``;
            ``not_found`` bei unbekanntem Schlüssel oder fehlender Index-Datei.
    """
    key = _check_person_key(person_key)
    _check_limit("limit", limit)
    coverage = coverage_of(db_path)
    rows = _person_rows(db_path, key, coverage)
    positions = _positions(rows)
    assembler = ProvenanceAssembler.load(db_path)
    briefs = _newest_first(_brief(assembler, paper_id) for paper_id in positions)
    papers = [AuthorPaper(paper=brief, position=positions[brief.paper_id]) for brief in briefs]
    communities = _communities(db_path, positions)
    coauthors = _coauthors(db_path, key, positions)
    return AuthorProfile(
        person_key=key,
        identity=rows[0].identity,
        openalex_id=_most_common(row.openalex_id for row in rows),
        orcid=_most_common(row.orcid for row in rows),
        names=tuple(sorted({row.name for row in rows})),
        papers=tuple(papers[:limit]),
        papers_total=len(papers),
        year_span=_year_span(briefs),
        communities=tuple(communities[:limit]),
        communities_total=len(communities),
        coauthors=tuple(coauthors[:limit]),
        coauthors_total=len(coauthors),
        coverage=coverage,
    )


def search_author_papers(
    db_path: str | Path, person_key: str, query: str, *, k: int = 5
) -> AuthorPapersResult:
    """Basic-Suche (Hybrid-Wertung), beschränkt auf die Paper einer Person.

    Dieselbe Suche und derselbe ``Citation``-Contract wie ``search_basic``; Local wird bewusst
    nicht angeboten, weil Nachbarschaft und Fan-out die Paper der Person verlassen (ADR 0043).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        person_key: Personenschlüssel aus :func:`search_authors`.
        query: Natürlichsprachige Anfrage (nicht leer).
        k: Höchstzahl der Zitate (``0 < k <= MAX_RESULT_COUNT``).

    Returns:
        Ein :class:`AuthorPapersResult`; ``citations`` ist leer, wenn kein Chunk passt.

    Raises:
        DomainError: ``invalid_input`` bei leerem Schlüssel, leerer Anfrage oder ungültigem
            ``k``; ``not_found`` bei unbekanntem Schlüssel oder fehlender Index-Datei;
            ``constraint_violation``, wenn der Index keine Chunks enthält.
    """
    key = _check_person_key(person_key)
    if not query.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leere Anfrage.")
    _check_limit("k", k)
    coverage = coverage_of(db_path)
    paper_ids = set(_positions(_person_rows(db_path, key, coverage)))
    hits = TfidfIndex.load(db_path).search(query, k, paper_ids=paper_ids)
    return AuthorPapersResult(
        person_key=key,
        query=query,
        papers_searched=len(paper_ids),
        citations=tuple(Citation.from_hit(hit) for hit in hits),
        coverage=coverage,
    )


def _links(
    assembler: ProvenanceAssembler,
    edges: Mapping[str, Mapping[str, set[str]]],
    own_papers: set[str],
) -> list[AuthorCitationLink]:
    """Baut die Gegenüber einer Richtung (sortiert nach Zahl beteiligter Paper, dann ID)."""
    links = [
        AuthorCitationLink(
            paper=_brief(assembler, other),
            via=tuple(sorted(via)),
            methods=tuple(sorted({method for methods in via.values() for method in methods})),
            self_citation=other in own_papers,
        )
        for other, via in edges.items()
    ]
    return sorted(links, key=lambda link: (-len(link.via), link.paper.paper_id))


def get_author_citations(
    db_path: str | Path, person_key: str, *, limit: int = MAX_RESULT_COUNT
) -> AuthorCitationsResult:
    """Zitationsnetz einer Person innerhalb des Korpus in beide Richtungen.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        person_key: Personenschlüssel aus :func:`search_authors`.
        limit: Höchstzahl **je Richtung** (``0 < limit <= MAX_RESULT_COUNT``).

    Returns:
        Ein :class:`AuthorCitationsResult`. Je Gegenüber ein Eintrag mit den beteiligten Papern
        der Person (``via``) und den Kriterien der Kanten; Selbstzitate sind markiert.

    Raises:
        DomainError: ``invalid_input`` bei leerem Schlüssel oder ungültigem ``limit``;
            ``not_found`` bei unbekanntem Schlüssel oder fehlender Index-Datei;
            ``constraint_violation``, wenn der Index keinen Zitationsgraphen enthält.
    """
    key = _check_person_key(person_key)
    _check_limit("limit", limit)
    coverage = coverage_of(db_path)
    own_papers = set(_positions(_person_rows(db_path, key, coverage)))
    cites: dict[str, dict[str, set[str]]] = {}
    cited_by: dict[str, dict[str, set[str]]] = {}
    for paper_id in sorted(own_papers):
        view = load_citations(db_path, paper_id)
        for edge in view.cites:
            target = cites.setdefault(edge.target_paper_id, {})
            target.setdefault(paper_id, set()).add(edge.method)
        for edge in view.cited_by:
            source = cited_by.setdefault(edge.source_paper_id, {})
            source.setdefault(paper_id, set()).add(edge.method)
    assembler = ProvenanceAssembler.load(db_path)
    cites_links = _links(assembler, cites, own_papers)
    cited_by_links = _links(assembler, cited_by, own_papers)
    return AuthorCitationsResult(
        person_key=key,
        cites=tuple(cites_links[:limit]),
        cites_total=len(cites_links),
        cited_by=tuple(cited_by_links[:limit]),
        cited_by_total=len(cited_by_links),
        coverage=coverage,
    )
