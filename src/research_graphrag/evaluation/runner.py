"""Ausführung der Retrieval-Evaluation gegen einen realen Index (Phase 7 / A6).

Gemessen werden zwei Ebenen:

1. Die **geteilte lexikalische Primitive** ``TfidfIndex.search`` – der Pfad, den Basic, der
   Local-Seed, der Local-Fan-out und die DRIFT-Verfeinerung teilen (das Messgerät aus
   docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).
2. Die **Modi als Ganzes**: Jeder Modus liefert ein Evidenz-Bündel, dessen Paper-Reihenfolge
   einheitlich gegen die Gold-Labels gewertet wird. Dazu kommen zwei Diagnosen, die
   Auswahlfehler von Rankingfehlern trennen – der Local-Baustein-Beitrag und die
   DRIFT-/Global-Deckelung (docs/adr/0016-quantitative-retrieval-evaluation-phase7.md).

Die Modus-Funktionen laden den Index bewusst selbst (On-Read,
docs/adr/0010-drop-in-workflow-and-qa-phase6.md); der Retrieval-Contract bleibt unangetastet.
Das macht einen vollständigen Lauf spürbar langsam – eine dokumentierte, bewusste Abwägung für
ein selten laufendes Werkzeug.
"""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.evaluation.gold import GoldQuestion, GoldSet
from research_graphrag.evaluation.metrics import (
    CoverageStats,
    EvaluationReport,
    QuestionScore,
    first_hit,
)
from research_graphrag.indexing.graph_index import load_communities
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, Scoring, TfidfIndex
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.drift import search_drift
from research_graphrag.retrieval.global_search import search_global
from research_graphrag.retrieval.local import DEFAULT_SEEDS, search_local

PRIMITIVE = "primitive"
"""Bezeichner der geteilten Chunk-Primitive (kein Suchmodus)."""

MODES = ("basic", "local", "global", "drift")
"""Die vier Retrieval-Modi in Berichtsreihenfolge."""

LABELS = (PRIMITIVE, *MODES)
"""Alle messbaren Ebenen (Primitive + Modi)."""

RANDOM_DRAWS = 100
"""Ziehungen der zufälligen Community-Baseline (mittelt die Einzelziehungs-Streuung heraus)."""

RANDOM_SEED = 42
"""Fester Seed der zufälligen Baseline – die Messung bleibt reproduzierbar."""


@dataclass(frozen=True)
class RunParameters:
    """Parameter eines Messlaufs (gehen in den Baseline-Fingerprint ein)."""

    k: int = 5
    fan_out: int = 5
    seeds: int = DEFAULT_SEEDS
    drift_k: int = 6
    global_n: int = 5
    scoring: Scoring = DEFAULT_SCORING

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Parameter (Reihenfolge stabil für den Fingerprint-Vergleich)."""
        return {
            "k": self.k,
            "fan_out": self.fan_out,
            "seeds": self.seeds,
            "drift_k": self.drift_k,
            "global_n": self.global_n,
            "scoring": self.scoring,
        }


DEFAULT_PARAMETERS = RunParameters()
"""Vorgabewerte eines Messlaufs (als Singleton, damit sie als Default dienen können)."""


def _count_papers(db_path: str | Path) -> int:
    """Zählt die Paper im Index (Bezugsgröße der Selektivität)."""
    connection = sqlite3.connect(str(db_path))
    try:
        return int(connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0])
    finally:
        connection.close()


def evaluate_primitive(
    index: TfidfIndex, gold: GoldSet, params: RunParameters = DEFAULT_PARAMETERS
) -> EvaluationReport:
    """Bewertet die geteilte Chunk-Primitive (ein Index-Ladevorgang für alle Fragen).

    Args:
        index: Geladener Index (einmal laden, viele Fragen bewerten).
        gold: Das Gold-Set.
        params: Messparameter; genutzt werden ``k`` und ``scoring``.

    Returns:
        Der aggregierte :class:`~research_graphrag.evaluation.metrics.EvaluationReport`.
    """
    scores: list[QuestionScore] = []
    for question in gold.questions:
        expected = set(question.expected_paper_ids)
        hits = index.search(question.query, params.k, scoring=params.scoring)
        rank, _ = first_hit([(hit.paper_id, "chunk") for hit in hits], expected)
        scores.append(QuestionScore(qid=question.qid, kind=question.kind, first_rank=rank))
    return EvaluationReport(
        label=PRIMITIVE, k=params.k, scoring=params.scoring, scores=tuple(scores)
    )


def _basic_bundle(
    db_path: str | Path, question: GoldQuestion, params: RunParameters
) -> list[tuple[str, str]]:
    """Evidenz-Bündel der Basic Search (identisch zur Primitive, per Contract-Test belegt)."""
    result = search_basic(db_path, question.query, params.k, scoring=params.scoring)
    return [(citation.paper_id, "citation") for citation in result.citations]


def _local_bundle(
    db_path: str | Path, question: GoldQuestion, params: RunParameters
) -> list[tuple[str, str]]:
    """Evidenz-Bündel der Local Search: Seeds → Chunk-Nachbarschaft → Paper-Fan-out."""
    result = search_local(
        db_path,
        question.query,
        k=params.k,
        fan_out=params.fan_out,
        seeds=params.seeds,
        scoring=params.scoring,
    )
    entries: list[tuple[str, str]] = [(citation.paper_id, "seed") for citation in result.seeds]
    entries.extend((citation.paper_id, "neighborhood") for citation in result.neighborhood)
    entries.extend((neighbor.paper_id, "fan_out") for neighbor in result.fan_out)
    return entries


def _chunk_scores(
    db_path: str | Path,
    gold: GoldSet,
    params: RunParameters,
    label: str,
) -> tuple[QuestionScore, ...]:
    """Bewertet die chunk-basierten Modi (Basic/Local) über ihr jeweiliges Bündel.

    Nur Local führt eine Diagnose: Sein Bündel besteht aus drei Bausteinen (Seed,
    Nachbarschaft, Fan-out), während Basic nur eine Belegsorte kennt.
    """
    builder = _basic_bundle if label == "basic" else _local_bundle
    scores: list[QuestionScore] = []
    for question in gold.questions:
        expected = set(question.expected_paper_ids)
        rank, component = first_hit(builder(db_path, question, params), expected)
        scores.append(
            QuestionScore(
                qid=question.qid,
                kind=question.kind,
                first_rank=rank,
                diagnosis=component if label == "local" else None,
            )
        )
    return tuple(scores)


def _coverage(
    expected: Collection[str], members: Collection[str], n_papers: int
) -> tuple[float, float]:
    """Berechnet Coverage (Anteil erwarteter Paper) und Selektivität (Korpusanteil)."""
    unique = set(members)
    coverage = len(unique & set(expected)) / len(expected) if expected else 0.0
    return coverage, len(unique) / n_papers if n_papers else 0.0


def _global_report(db_path: str | Path, gold: GoldSet, params: RunParameters) -> EvaluationReport:
    """Bewertet die Community-Auswahl – Coverage stets neben Selektivität und Baselines."""
    communities = load_communities(db_path)
    members_by_id = {community.community_id: community.members for community in communities}
    n_papers = _count_papers(db_path)

    largest = sorted(communities, key=lambda c: (-c.size, c.community_id))[: params.global_n]
    largest_members = [paper_id for community in largest for paper_id in community.members]
    rng = random.Random(RANDOM_SEED)
    draws = [
        [
            paper_id
            for community in rng.sample(communities, min(params.global_n, len(communities)))
            for paper_id in community.members
        ]
        for _ in range(RANDOM_DRAWS)
    ]

    scores: list[QuestionScore] = []
    real: list[tuple[float, float]] = []
    trivial: list[tuple[float, float]] = []
    chance: list[tuple[float, float]] = []
    for question in gold.questions:
        expected = set(question.expected_paper_ids)
        result = search_global(db_path, question.query, params.global_n)

        rank: int | None = None
        selected: list[str] = []
        for position, match in enumerate(result.communities, start=1):
            members = members_by_id.get(match.community_id, ())
            if rank is None and set(members) & expected:
                rank = position
            selected.extend(members)

        if not result.communities:
            diagnosis = "no_community"
        elif rank is None:
            diagnosis = "community_missed"
        else:
            diagnosis = "in_community"
        scores.append(
            QuestionScore(
                qid=question.qid, kind=question.kind, first_rank=rank, diagnosis=diagnosis
            )
        )

        real.append(_coverage(expected, selected, n_papers))
        trivial.append(_coverage(expected, largest_members, n_papers))
        drawn = [_coverage(expected, draw, n_papers) for draw in draws]
        chance.append(
            (
                sum(value for value, _ in drawn) / len(drawn),
                sum(value for _, value in drawn) / len(drawn),
            )
        )

    return EvaluationReport(
        label="global",
        k=params.global_n,
        scoring=params.scoring,
        scores=tuple(scores),
        coverage=(
            _stats("global", real),
            _stats(f"größte-{params.global_n}", trivial),
            _stats(f"zufällig-{params.global_n}", chance),
        ),
    )


def _stats(label: str, samples: Sequence[tuple[float, float]]) -> CoverageStats:
    """Mittelt Coverage und Selektivität über alle Fragen einer Strategie."""
    if not samples:
        return CoverageStats(label=label, coverage=0.0, selectivity=0.0)
    return CoverageStats(
        label=label,
        coverage=sum(coverage for coverage, _ in samples) / len(samples),
        selectivity=sum(selectivity for _, selectivity in samples) / len(samples),
    )


def _drift_report(db_path: str | Path, gold: GoldSet, params: RunParameters) -> EvaluationReport:
    """Bewertet DRIFT und weist aus, ob schon die Community-Wahl den Treffer ausschließt."""
    communities = load_communities(db_path)
    members_by_id = {community.community_id: community.members for community in communities}

    scores: list[QuestionScore] = []
    for question in gold.questions:
        expected = set(question.expected_paper_ids)
        result = search_drift(db_path, question.query, k=params.drift_k, scoring=params.scoring)
        if result.community is None:
            scores.append(
                QuestionScore(
                    qid=question.qid,
                    kind=question.kind,
                    first_rank=None,
                    diagnosis="no_community",
                )
            )
            continue
        members = set(members_by_id.get(result.community.community_id, ()))
        rank, _ = first_hit(
            [(citation.paper_id, "citation") for citation in result.citations], expected
        )
        scores.append(
            QuestionScore(
                qid=question.qid,
                kind=question.kind,
                first_rank=rank,
                diagnosis="in_community" if members & expected else "community_missed",
            )
        )
    return EvaluationReport(
        label="drift", k=params.drift_k, scoring=params.scoring, scores=tuple(scores)
    )


def evaluate_mode(
    db_path: str | Path, gold: GoldSet, mode: str, params: RunParameters = DEFAULT_PARAMETERS
) -> EvaluationReport:
    """Bewertet einen Suchmodus als Ganzes (Evidenz-Bündel statt nur der Primitive).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        gold: Das Gold-Set.
        mode: Einer der Modi aus :data:`MODES`.
        params: Messparameter (k, Fan-out, DRIFT-k, Community-Zahl, Wertung).

    Returns:
        Der aggregierte :class:`~research_graphrag.evaluation.metrics.EvaluationReport`;
        für ``global`` zusätzlich mit Coverage-Kennzahlen und Trivial-Baselines.

    Raises:
        DomainError: ``invalid_input`` bei unbekanntem Modus; die Modi selbst melden
            ``not_found``/``constraint_violation`` weiter (siehe docs/error-model.md).
    """
    if mode not in MODES:
        raise DomainError(
            ErrorCode.INVALID_INPUT, f"Unbekannter Modus: {mode!r}. Erlaubt: {', '.join(MODES)}."
        )
    if mode == "global":
        return _global_report(db_path, gold, params)
    if mode == "drift":
        return _drift_report(db_path, gold, params)
    return EvaluationReport(
        label=mode,
        k=params.k,
        scoring=params.scoring,
        scores=_chunk_scores(db_path, gold, params, mode),
    )


def evaluate_all(
    db_path: str | Path,
    gold: GoldSet,
    params: RunParameters = DEFAULT_PARAMETERS,
    labels: Sequence[str] = LABELS,
) -> dict[str, EvaluationReport]:
    """Führt Primitive und Modi in einem Durchgang aus.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        gold: Das Gold-Set.
        params: Messparameter.
        labels: Zu messende Ebenen (Teilmenge von :data:`LABELS`, Reihenfolge bleibt erhalten).

    Returns:
        Berichte je Ebene in der Reihenfolge von ``labels``.

    Raises:
        DomainError: ``invalid_input`` bei unbekannter Ebene.
    """
    reports: dict[str, EvaluationReport] = {}
    for label in labels:
        if label == PRIMITIVE:
            reports[label] = evaluate_primitive(TfidfIndex.load(db_path), gold, params)
        else:
            reports[label] = evaluate_mode(db_path, gold, label, params)
    return reports
