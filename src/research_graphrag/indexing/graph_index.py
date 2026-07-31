"""Paper-Ähnlichkeitsgraph & Louvain-Communities (Offline-Hybrid, Option B, Phase 3).

Baut aus den Canonical-Papers einen **deterministischen Paper-Ähnlichkeitsgraphen** auf
TF-IDF-Basis, erkennt **Communities** via Louvain (``networkx``) und persistiert Knoten,
Kanten und **extraktive** Community-Zusammenfassungen in die bestehende SQLite-Index-Datei
(Source of Truth). Grundsatz: docs/adr/0007-graphrag-index-phase3-option-b.md.

Determinismus: fixer Seed, stabile Tie-Breaks (``paper_id``) und ein einmal frisch
rekonstruierter TF-IDF-Raum – es werden bewusst keine ``sklearn``/``networkx``-Objekte
serialisiert (kein pickle, keine Versions-Kopplung). Kanten entstehen als *mutual top-k*
oberhalb einer Mindest-Ähnlichkeit; die Kantenmenge ist damit unabhängig von der
Eingabereihenfolge der Papers (nur inhaltsbestimmt).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.algorithms.community import louvain_communities
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper

GRAPH_SCHEMA_VERSION = "0.1.0"
"""Version des Graph-Teilschemas in ``index.sqlite`` (für spätere Migrationen)."""

DEFAULT_K = 8
"""Maximale Nachbarzahl je Paper (Kandidaten für *mutual top-k*)."""

DEFAULT_MIN_SIMILARITY = 0.10
"""Mindest-Kosinus-Ähnlichkeit, damit eine Kante überhaupt in Frage kommt."""

DEFAULT_SEED = 42
"""Fixer Seed für die (sonst zufallsbehaftete) Louvain-Community-Detection."""

DEFAULT_RESOLUTION = 1.0
"""Louvain-Auflösung (größer → mehr, kleinere Communities)."""

TOP_KEYWORDS = 10
"""Anzahl der extraktiven Top-TF-IDF-Keywords je Community."""

TOP_REPRESENTATIVES = 3
"""Anzahl der repräsentativen Paper (höchste Intra-Community-Zentralität)."""

_SNIPPET_LIMIT = 200

_GRAPH_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
DROP TABLE IF EXISTS community_members;
DROP TABLE IF EXISTS communities;
DROP TABLE IF EXISTS graph_edges;
DROP TABLE IF EXISTS graph_nodes;
CREATE TABLE graph_nodes (
    paper_id     TEXT PRIMARY KEY,
    degree       INTEGER NOT NULL,
    community_id INTEGER NOT NULL
);
CREATE TABLE graph_edges (
    source_paper_id TEXT NOT NULL,
    target_paper_id TEXT NOT NULL,
    weight          REAL NOT NULL,
    PRIMARY KEY (source_paper_id, target_paper_id)
);
CREATE TABLE communities (
    community_id INTEGER PRIMARY KEY,
    size         INTEGER NOT NULL,
    keywords     TEXT NOT NULL,
    summary      TEXT NOT NULL
);
CREATE TABLE community_members (
    community_id      INTEGER NOT NULL,
    paper_id          TEXT NOT NULL,
    centrality        REAL NOT NULL,
    is_representative INTEGER NOT NULL,
    PRIMARY KEY (community_id, paper_id)
);
"""


@dataclass(frozen=True)
class GraphBuildReport:
    """Zählwerte eines Graph-Baus."""

    n_nodes: int
    n_edges: int
    n_communities: int


@dataclass(frozen=True)
class CommunityView:
    """Read-only-Sicht auf eine persistierte Community.

    Genutzt von ``scripts/graph_info.py`` und dem MCP-Tool ``list_topics``
    (siehe docs/adr/0009-mcp-server-stdio-phase5.md).
    """

    community_id: int
    size: int
    keywords: tuple[str, ...]
    summary: str
    members: tuple[str, ...]
    representatives: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Community-Sicht (Output-Schema des Tools ``list_topics``)."""
        return {
            "community_id": self.community_id,
            "size": self.size,
            "keywords": list(self.keywords),
            "summary": self.summary,
            "members": list(self.members),
            "representatives": list(self.representatives),
        }


@dataclass(frozen=True)
class _CommunityRecord:
    """Interner Datensatz einer Community vor dem Persistieren."""

    community_id: int
    members: tuple[str, ...]
    keywords: tuple[str, ...]
    summary: str
    representatives: frozenset[str]


def _snippet(text: str, limit: int = _SNIPPET_LIMIT) -> str:
    """Erzeugt einen einzeiligen, gekürzten Ausschnitt (für die Community-Zusammenfassung)."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _unique_indexable(papers: Sequence[CanonicalPaper]) -> list[CanonicalPaper]:
    """Filtert auf eindeutige Paper (per ``paper_id``) mit mindestens einem nicht-leeren Chunk."""
    seen: set[str] = set()
    unique: list[CanonicalPaper] = []
    for paper in papers:
        if paper.paper_id in seen:
            continue
        if not any(chunk.text.strip() for chunk in paper.chunks):
            continue
        seen.add(paper.paper_id)
        unique.append(paper)
    return unique


def _paper_document(paper: CanonicalPaper) -> str:
    """Fügt die nicht-leeren Chunk-Texte eines Papers zu einem Dokument zusammen."""
    return "\n".join(chunk.text for chunk in paper.chunks if chunk.text.strip())


def _leading_snippet(paper: CanonicalPaper) -> str:
    """Liefert den Ausschnitt des ersten nicht-leeren Chunks (extraktiver Provenienz-Anker)."""
    for chunk in paper.chunks:
        if chunk.text.strip():
            return _snippet(chunk.text)
    return ""


def _mutual_topk_edges(
    paper_ids: list[str], sims: list[list[float]], k: int, min_similarity: float
) -> list[tuple[str, str, float]]:
    """Bildet die *mutual top-k*-Kantenmenge (ungerichtet, ``source < target``).

    Eine Kante ``(i, j)`` entsteht nur, wenn ``j`` unter den Top-``k``-Nachbarn von ``i``
    **und** ``i`` unter denen von ``j`` liegt (jeweils oberhalb ``min_similarity``). Das hält
    den Graphen dünn und vermeidet Hubs. Tie-Break der Nachbarn: ``(-Ähnlichkeit, paper_id)``.
    """
    n = len(paper_ids)
    neighbors: list[set[int]] = []
    for i in range(n):
        candidates = [
            (-sims[i][j], paper_ids[j], j)
            for j in range(n)
            if j != i and sims[i][j] >= min_similarity
        ]
        candidates.sort()
        neighbors.append({index for _neg_sim, _paper_id, index in candidates[:k]})

    edges: list[tuple[str, str, float]] = []
    for i in range(n):
        for j in neighbors[i]:
            if i < j and i in neighbors[j]:
                first, second = paper_ids[i], paper_ids[j]
                source, target = (first, second) if first < second else (second, first)
                edges.append((source, target, sims[i][j]))
    return sorted(edges)


def _community_keywords(rows: list[int], matrix: Any, features: Any) -> tuple[str, ...]:
    """Ermittelt die Top-TF-IDF-Keywords über die aggregierten Zeilen der Community-Paper."""
    summed = matrix[rows].sum(axis=0).A1
    scored = [
        (float(summed[term]), str(features[term]))
        for term in range(len(features))
        if float(summed[term]) > 0.0
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(term for _score, term in scored[:TOP_KEYWORDS])


def build_graph(
    papers: Sequence[CanonicalPaper],
    db_path: str | Path,
    *,
    k: int = DEFAULT_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    seed: int = DEFAULT_SEED,
    resolution: float = DEFAULT_RESOLUTION,
) -> GraphBuildReport:
    """Baut den Paper-Ähnlichkeitsgraphen samt Louvain-Communities und persistiert ihn.

    Die Graph-Tabellen werden **additiv** in die bestehende Index-Datei geschrieben
    (voller Re-Build: vorhandene Graph-Tabellen werden zuvor verworfen). Der übrige Index
    (``papers``/``chunks``) bleibt unangetastet.

    Args:
        papers: Extrahierte Papers (siehe :mod:`research_graphrag.extraction.pdf`).
        db_path: Pfad zur SQLite-Index-Datei; Elternordner wird angelegt.
        k: Maximale Nachbarzahl je Paper für die *mutual top-k*-Kanten.
        min_similarity: Mindest-Kosinus-Ähnlichkeit einer Kante.
        seed: Fixer Seed der Louvain-Community-Detection (Reproduzierbarkeit).
        resolution: Louvain-Auflösung.

    Returns:
        Ein :class:`GraphBuildReport` mit Knoten-, Kanten- und Community-Zahl.

    Raises:
        DomainError: ``invalid_input``, wenn keine indexierbaren Paper vorhanden sind
            (siehe docs/error-model.md).
    """
    unique = _unique_indexable(papers)
    if not unique:
        raise DomainError(ErrorCode.INVALID_INPUT, "Keine indexierbaren Paper für den Graphen.")

    paper_ids = [paper.paper_id for paper in unique]
    documents = [_paper_document(paper) for paper in unique]
    snippets = {paper.paper_id: _leading_snippet(paper) for paper in unique}
    row_of = {paper_id: index for index, paper_id in enumerate(paper_ids)}

    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(documents)
    features = vectorizer.get_feature_names_out()
    similarity = linear_kernel(matrix, matrix)
    n = len(unique)
    sims = [[float(similarity[i][j]) for j in range(n)] for i in range(n)]

    edges = _mutual_topk_edges(paper_ids, sims, k, min_similarity)

    graph = nx.Graph()
    for paper_id in sorted(paper_ids):
        graph.add_node(paper_id)
    for source, target, weight in edges:
        graph.add_edge(source, target, weight=weight)

    community_sets = louvain_communities(graph, weight="weight", resolution=resolution, seed=seed)
    ordered = sorted(
        (tuple(sorted(members)) for members in community_sets),
        key=lambda members: (-len(members), members[0]),
    )

    node_community = {paper_id: cid for cid, members in enumerate(ordered) for paper_id in members}
    centrality = {paper_id: 0.0 for paper_id in paper_ids}
    for source, target, weight in edges:
        if node_community[source] == node_community[target]:
            centrality[source] += weight
            centrality[target] += weight

    records: list[_CommunityRecord] = []
    for cid, members in enumerate(ordered):
        rows = [row_of[paper_id] for paper_id in members]
        keywords = _community_keywords(rows, matrix, features)
        ranked_members = sorted(members, key=lambda paper_id: (-centrality[paper_id], paper_id))
        representatives = ranked_members[:TOP_REPRESENTATIVES]
        summary = snippets.get(representatives[0], "") if representatives else ""
        records.append(
            _CommunityRecord(
                community_id=cid,
                members=members,
                keywords=keywords,
                summary=summary,
                representatives=frozenset(representatives),
            )
        )

    _persist(db_path, paper_ids, graph, node_community, centrality, edges, records)
    return GraphBuildReport(n_nodes=n, n_edges=len(edges), n_communities=len(ordered))


def _persist(
    db_path: str | Path,
    paper_ids: list[str],
    graph: Any,
    node_community: dict[str, int],
    centrality: dict[str, float],
    edges: list[tuple[str, str, float]],
    records: list[_CommunityRecord],
) -> None:
    """Schreibt Knoten, Kanten und Communities deterministisch in die Index-Datei."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(_GRAPH_SCHEMA)
        connection.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('graph_schema_version', ?)",
            (GRAPH_SCHEMA_VERSION,),
        )
        for paper_id in sorted(paper_ids):
            connection.execute(
                "INSERT INTO graph_nodes (paper_id, degree, community_id) VALUES (?, ?, ?)",
                (paper_id, int(graph.degree(paper_id)), node_community[paper_id]),
            )
        for source, target, weight in edges:
            connection.execute(
                "INSERT INTO graph_edges (source_paper_id, target_paper_id, weight) "
                "VALUES (?, ?, ?)",
                (source, target, weight),
            )
        for record in records:
            connection.execute(
                "INSERT INTO communities (community_id, size, keywords, summary) "
                "VALUES (?, ?, ?, ?)",
                (
                    record.community_id,
                    len(record.members),
                    json.dumps(list(record.keywords), ensure_ascii=False),
                    record.summary,
                ),
            )
            for paper_id in sorted(record.members):
                connection.execute(
                    "INSERT INTO community_members "
                    "(community_id, paper_id, centrality, is_representative) VALUES (?, ?, ?, ?)",
                    (
                        record.community_id,
                        paper_id,
                        float(centrality[paper_id]),
                        1 if paper_id in record.representatives else 0,
                    ),
                )
        connection.commit()
    finally:
        connection.close()


def load_communities(db_path: str | Path) -> list[CommunityView]:
    """Lädt die persistierten Communities (aufsteigend nach ``community_id``).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.

    Returns:
        Die Communities als :class:`CommunityView` (Keywords, Summary, Mitglieder, Vertreter).

    Raises:
        DomainError: ``not_found`` wenn die Index-Datei fehlt; ``constraint_violation`` wenn
            kein Graph gebaut wurde oder keine Communities vorhanden sind
            (siehe docs/error-model.md).
    """
    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")

    connection = sqlite3.connect(str(path))
    try:
        has_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'communities'"
        ).fetchone()
        if has_table is None:
            raise DomainError(
                ErrorCode.CONSTRAINT_VIOLATION, "Kein Graph im Index (Phase 3 nicht gebaut?)."
            )
        community_rows = connection.execute(
            "SELECT community_id, size, keywords, summary FROM communities ORDER BY community_id"
        ).fetchall()
        member_rows = connection.execute(
            "SELECT community_id, paper_id, is_representative FROM community_members "
            "ORDER BY community_id, paper_id"
        ).fetchall()
    finally:
        connection.close()

    if not community_rows:
        raise DomainError(ErrorCode.CONSTRAINT_VIOLATION, "Index enthält keine Communities.")

    members_by_cid: dict[int, list[str]] = {}
    reps_by_cid: dict[int, list[str]] = {}
    for cid, paper_id, is_representative in member_rows:
        members_by_cid.setdefault(int(cid), []).append(str(paper_id))
        if int(is_representative) == 1:
            reps_by_cid.setdefault(int(cid), []).append(str(paper_id))

    return [
        CommunityView(
            community_id=int(cid),
            size=int(size),
            keywords=tuple(json.loads(keywords)),
            summary=str(summary),
            members=tuple(members_by_cid.get(int(cid), [])),
            representatives=tuple(reps_by_cid.get(int(cid), [])),
        )
        for cid, size, keywords, summary in community_rows
    ]


def load_neighbors(db_path: str | Path, paper_id: str) -> list[tuple[str, float]]:
    """Lädt die Graph-Nachbarn eines Papers (für den Local-Fan-out, Phase 4).

    Die ``graph_edges`` sind ungerichtet einmal gespeichert (``source < target``); ein Paper
    kann daher Quelle **oder** Ziel einer Kante sein. Nachbarn werden über beide Richtungen
    gesammelt und absteigend nach Kantengewicht sortiert (Tie-Break ``paper_id``).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        paper_id: Ausgangspaper.

    Returns:
        Liste aus ``(neighbor_paper_id, weight)``; leer, wenn das Paper keine Kanten hat
        (z. B. Singleton-Community).

    Raises:
        DomainError: ``not_found`` wenn die Index-Datei fehlt; ``constraint_violation`` wenn
            kein Graph gebaut wurde (siehe docs/error-model.md).
    """
    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")

    connection = sqlite3.connect(str(path))
    try:
        has_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'graph_edges'"
        ).fetchone()
        if has_table is None:
            raise DomainError(
                ErrorCode.CONSTRAINT_VIOLATION, "Kein Graph im Index (Phase 3 nicht gebaut?)."
            )
        rows = connection.execute(
            "SELECT target_paper_id, weight FROM graph_edges WHERE source_paper_id = ? "
            "UNION ALL "
            "SELECT source_paper_id, weight FROM graph_edges WHERE target_paper_id = ?",
            (paper_id, paper_id),
        ).fetchall()
    finally:
        connection.close()

    neighbors = [(str(target), float(weight)) for target, weight in rows]
    neighbors.sort(key=lambda item: (-item[1], item[0]))
    return neighbors
