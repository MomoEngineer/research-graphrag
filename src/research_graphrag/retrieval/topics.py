"""list_topics: gefilterte Community-Übersicht + Einzelabruf (ADR 0037).

Die ursprüngliche, parameterlose Fassung von ``list_topics`` lieferte unbedingt **jede**
Community des Korpus inklusive ihrer vollen ``members``-Liste. Gemessen am realen Index
(3.461 Paper, 1.170 Communities, davon 951 Singleton-Communities) sind das 555 KB – mehr als die
Hälfte der MCP-Transportgrenze von 1 MB, unabhängig von jedem Aufrufer-Verhalten
(docs/adr/0037-mcp-tool-response-size-ceiling.md).

Dieses Modul trennt deshalb zwei Fälle: :func:`list_topics` liefert eine gefilterte, gedeckelte
**Übersicht** ohne Mitgliederliste (Größe, Keywords, Summary, Vertreter genügen für den
Überblicks-Zweck); :func:`get_topic` liefert **eine** Community mit voller Mitgliederliste, für
den Moment, in dem ein Aufrufer sie nach der Auswahl tatsächlich braucht.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.indexing.graph_index import CommunityView, load_communities
from research_graphrag.limits import MAX_RESULT_COUNT, check_max_count

DEFAULT_MIN_SIZE = 2
"""Standard-Untergrenze der Community-Größe für die Übersicht.

Eine Singleton-Community (ein einziges Paper) trägt keine cross-paper-Synthese und ist damit kein
sinnvolles „Themencluster" im Sinn des Werkzeugs; am realen Korpus sind das 951 von 1.170
Communities (docs/adr/0037-mcp-tool-response-size-ceiling.md)."""

DEFAULT_LIMIT = MAX_RESULT_COUNT
"""Standard-Deckel der Trefferzahl der Übersicht – dieselbe geteilte Obergrenze wie bei den
übrigen Retrieval-Werkzeugen (:data:`research_graphrag.limits.MAX_RESULT_COUNT`)."""


@dataclass(frozen=True)
class TopicSummary:
    """Schlanke Community-Sicht für die Übersicht – bewusst **ohne** ``members``."""

    community_id: int
    size: int
    keywords: tuple[str, ...]
    summary: str
    representatives: tuple[str, ...]

    @classmethod
    def from_view(cls, view: CommunityView) -> TopicSummary:
        """Übernimmt die Übersichts-Felder einer :class:`CommunityView` (ohne ``members``)."""
        return cls(
            community_id=view.community_id,
            size=view.size,
            keywords=view.keywords,
            summary=view.summary,
            representatives=view.representatives,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Übersichts-Sicht (Teil des Output-Schemas von ``list_topics``)."""
        return {
            "community_id": self.community_id,
            "size": self.size,
            "keywords": list(self.keywords),
            "summary": self.summary,
            "representatives": list(self.representatives),
        }


@dataclass(frozen=True)
class TopicsOverview:
    """Gefilterte, gedeckelte Community-Übersicht (Output-Schema von ``list_topics`` ohne
    ``community_id``)."""

    topics: tuple[TopicSummary, ...]
    total_matching: int
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Übersicht inklusive der Transparenz-Felder."""
        return {
            "topics": [topic.to_dict() for topic in self.topics],
            "total_matching": self.total_matching,
            "truncated": self.truncated,
        }


def list_topics(
    db_path: str | Path, *, min_size: int = DEFAULT_MIN_SIZE, limit: int = DEFAULT_LIMIT
) -> TopicsOverview:
    """Liefert eine nach Größe sortierte, gefilterte und gedeckelte Community-Übersicht.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        min_size: Blendet Communities mit weniger Mitgliedern aus (``>= 1``); Default
            :data:`DEFAULT_MIN_SIZE`.
        limit: Maximale Zahl der Communities in der Übersicht
            (``0 < limit <= MAX_RESULT_COUNT``); Default :data:`DEFAULT_LIMIT`.

    Returns:
        Eine :class:`TopicsOverview`, absteigend nach Größe sortiert (Tie-Break: kleinere
        ``community_id``). ``total_matching`` ist die Zahl aller Communities mit
        ``size >= min_size`` **vor** ``limit``; ``truncated`` ist ``true``, wenn ``limit``
        tatsächlich etwas abgeschnitten hat.

    Raises:
        DomainError: ``invalid_input`` bei ``min_size < 1``, ``limit <= 0`` oder
            ``limit > MAX_RESULT_COUNT`` (ADR 0037); ``not_found`` wenn die Index-Datei fehlt;
            ``constraint_violation`` wenn kein Graph/keine Communities gebaut wurden (siehe
            docs/error-model.md).
    """
    if min_size < 1:
        raise DomainError(ErrorCode.INVALID_INPUT, "min_size muss >= 1 sein.")
    if limit <= 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "limit muss > 0 sein.")
    check_max_count("limit", limit)

    matching = [view for view in load_communities(db_path) if view.size >= min_size]
    matching.sort(key=lambda view: (-view.size, view.community_id))
    total_matching = len(matching)
    selected = matching[:limit]
    return TopicsOverview(
        topics=tuple(TopicSummary.from_view(view) for view in selected),
        total_matching=total_matching,
        truncated=total_matching > limit,
    )


def get_topic(db_path: str | Path, community_id: int) -> CommunityView:
    """Liefert eine einzelne Community mit ihrer vollständigen Mitgliederliste.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        community_id: Die gesuchte Community-ID.

    Returns:
        Die vollständige :class:`CommunityView` (inklusive ``members``).

    Raises:
        DomainError: ``not_found`` wenn die Index-Datei fehlt (siehe ``load_communities``) oder
            die ``community_id`` unbekannt ist; ``constraint_violation`` wenn kein Graph/keine
            Communities gebaut wurden (siehe docs/error-model.md).
    """
    for view in load_communities(db_path):
        if view.community_id == community_id:
            return view
    raise DomainError(ErrorCode.NOT_FOUND, f"Community nicht gefunden: {community_id}")
