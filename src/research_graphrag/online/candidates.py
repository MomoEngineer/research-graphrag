"""Kandidaten-Modell und Deduplikation der Online-Suche.

Enthält den quellenunabhängigen Datentyp :class:`Candidate` sowie die beiden Filterstufen des
Online-Modus (docs/adr/0020-online-candidate-search-phase9.md):

1. :func:`merge_candidates` führt **quellenübergreifende Dubletten** zusammen – dasselbe Paper
   erscheint bei arXiv und OpenAlex unter verschiedenen Identifikatoren.
2. :func:`partition` trennt neue Kandidaten von solchen, die bereits im Korpus liegen. Die
   Prüfung nutzt ausdrücklich die **bestehende** Grundlage des Intake
   (docs/adr/0019-corpus-intake-new-papers-phase8.md) statt einer zweiten Logik.

Das Modul ist netzfrei: Es kennt weder HTTP noch die einzelnen Quellen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..indexing.citation_graph import MIN_TITLE_CHARS, MIN_TITLE_WORDS, normalize_title
from ..intake import TITLE_SIMILARITY, CorpusView, best_title_match

SOURCE_ARXIV = "arXiv"
"""Quellenkennung der arXiv-API."""

SOURCE_OPENALEX = "OpenAlex"
"""Quellenkennung der OpenAlex-API."""

MATCH_IDENTIFIER = "identifier"
"""Belegart: Übereinstimmung über DOI oder arXiv-ID."""

MATCH_TITLE = "title"
"""Belegart: Übereinstimmung über den normalisierten Titel."""


@dataclass(frozen=True)
class Candidate:
    """Ein Vorschlag auf Metadatenebene – ohne Volltext.

    Attributes:
        title: Titel wie von der Quelle geliefert.
        year: Erscheinungsjahr; ``0`` wenn die Quelle keines nennt.
        sources: Quellen, die diesen Kandidaten geliefert haben (sortiert, dedupliziert).
        arxiv_id: arXiv-Identifikator ohne Version, sonst leer.
        doi: DOI ohne URL-Präfix, sonst leer.
        abstract: Abstract als Fließtext, sonst leer.
        url: Volltext- oder Landing-Link, sonst leer.
        license: Lizenzangabe der Quelle, sonst leer.
        query_id: Kennung der auslösenden Anfrage.
        reason: Klartext-Begründung, warum der Kandidat vorgeschlagen wurde.
    """

    title: str
    year: int
    sources: tuple[str, ...]
    arxiv_id: str = ""
    doi: str = ""
    abstract: str = ""
    url: str = ""
    license: str = ""
    query_id: str = ""
    reason: str = ""

    @property
    def identifier(self) -> str:
        """Sprechender Identifikator für die Anzeige (arXiv bevorzugt, sonst DOI)."""
        if self.arxiv_id:
            return f"arXiv:{self.arxiv_id}"
        return self.doi


@dataclass(frozen=True)
class KnownCandidate:
    """Ein Kandidat, der bereits im Korpus liegt – samt Beleg dafür.

    Attributes:
        candidate: Der betroffene Kandidat.
        match: Belegart, :data:`MATCH_IDENTIFIER` oder :data:`MATCH_TITLE`.
        evidence: Nachvollziehbarer Beleg (Identifikator bzw. Korpus-Titel mit Ähnlichkeit).
    """

    candidate: Candidate
    match: str
    evidence: str


def _merge_keys(candidate: Candidate) -> list[str]:
    """Bildet die Schlüssel, unter denen ein Kandidat wiedererkannt wird."""
    keys: list[str] = []
    if candidate.arxiv_id:
        keys.append(f"arxiv:{candidate.arxiv_id.lower()}")
    if candidate.doi:
        keys.append(f"doi:{candidate.doi.lower()}")
    normalized = normalize_title(candidate.title)
    if len(normalized) >= MIN_TITLE_CHARS and len(normalized.split()) >= MIN_TITLE_WORDS:
        keys.append(f"title:{normalized}")
    return keys


def _combine(first: Candidate, second: Candidate) -> Candidate:
    """Führt zwei Sichten desselben Papers zusammen (erste Sicht führt, Lücken werden gefüllt).

    Das Jahr wird auf die **früheste** bekannte Angabe gesetzt: Ein Preprint von 2019, das 2025
    in einem Sammelband erscheint, ist kein neues Paper – der Aktualitätsfilter soll darauf
    hereinfallen können.
    """
    years = [year for year in (first.year, second.year) if year > 0]
    return replace(
        first,
        year=min(years) if years else 0,
        sources=tuple(sorted(set(first.sources) | set(second.sources), key=str.lower)),
        arxiv_id=first.arxiv_id or second.arxiv_id,
        doi=first.doi or second.doi,
        abstract=max((first.abstract, second.abstract), key=len),
        url=first.url or second.url,
        license=first.license or second.license,
    )


def merge_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Führt Dubletten **innerhalb** einer Trefferliste zusammen.

    Zwei Einträge gelten als dasselbe Paper, wenn sie eine arXiv-ID, einen DOI **oder** einen
    normalisierten Titel teilen. Ohne diesen Schritt erscheint dasselbe Paper doppelt, sobald es
    von beiden Quellen unter verschiedenen Identifikatoren geliefert wird.

    Args:
        candidates: Kandidaten in Fundreihenfolge.

    Returns:
        Zusammengeführte Kandidaten; die Reihenfolge des jeweils ersten Auftretens bleibt erhalten.
    """
    merged: list[Candidate] = []
    positions: dict[str, int] = {}
    for candidate in candidates:
        keys = _merge_keys(candidate)
        hit = next((positions[key] for key in keys if key in positions), None)
        if hit is None:
            merged.append(candidate)
            positions.update({key: len(merged) - 1 for key in keys})
            continue
        merged[hit] = _combine(merged[hit], candidate)
        positions.update({key: hit for key in _merge_keys(merged[hit])})
    return merged


def classify(candidate: Candidate, corpus: CorpusView) -> KnownCandidate | None:
    """Prüft einen Kandidaten gegen den Korpus.

    Args:
        candidate: Der zu prüfende Kandidat.
        corpus: Prüfgrundlage aus :func:`research_graphrag.intake.load_corpus`.

    Returns:
        Einen :class:`KnownCandidate` mit Beleg, wenn das Paper bereits im Korpus liegt, sonst
        ``None``.
    """
    for kind, value in (("arxiv", candidate.arxiv_id), ("doi", candidate.doi)):
        lowered = value.lower()
        if lowered and (kind, lowered) in corpus.identifier_to_paper:
            return KnownCandidate(candidate, MATCH_IDENTIFIER, f"{kind}:{lowered}")
    normalized = normalize_title(candidate.title)
    if len(normalized) < MIN_TITLE_CHARS or len(normalized.split()) < MIN_TITLE_WORDS:
        return None
    ratio, match = best_title_match([normalized], corpus.titles)
    if ratio >= TITLE_SIMILARITY:
        return KnownCandidate(candidate, MATCH_TITLE, f"{ratio:.2f} ~ {match}")
    return None


def partition(
    candidates: Sequence[Candidate], corpus: CorpusView
) -> tuple[list[Candidate], list[KnownCandidate]]:
    """Trennt neue Kandidaten von bereits vorhandenen.

    Args:
        candidates: Zu prüfende Kandidaten.
        corpus: Prüfgrundlage aus :func:`research_graphrag.intake.load_corpus`.

    Returns:
        Die neuen Kandidaten und die bereits bekannten (mit Beleg), beide in Eingabereihenfolge.
    """
    fresh: list[Candidate] = []
    known: list[KnownCandidate] = []
    for candidate in candidates:
        verdict = classify(candidate, corpus)
        if verdict is None:
            fresh.append(candidate)
        else:
            known.append(verdict)
    return fresh, known


def filter_recent(candidates: Sequence[Candidate], min_year: int) -> list[Candidate]:
    """Behält nur Kandidaten ab ``min_year``.

    Kandidaten ohne Jahresangabe (``year == 0``) bleiben erhalten – eine fehlende Angabe ist kein
    Beleg für Veralterung.

    Args:
        candidates: Zu filternde Kandidaten.
        min_year: Frühestes zulässiges Erscheinungsjahr.

    Returns:
        Die verbleibenden Kandidaten in Eingabereihenfolge.
    """
    return [item for item in candidates if item.year == 0 or item.year >= min_year]
