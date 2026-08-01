"""Quantitative, offline Retrieval-Evaluation (Hit@k / MRR) gegen ein versioniertes Gold-Set.

Das Skript misst die **gemeinsame lexikalische Primitive** aller Chunk-Modi
(:meth:`research_graphrag.indexing.tfidf_index.TfidfIndex.search`) – also den Pfad, den
Basic, der Local-Seed, der Local-Fan-out und DRIFT teilen. Es ist damit das Messgerät für
die Hybrid-Wertung aus Roadmap-Punkt A4 (siehe
docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).

**Ground Truth ohne Retriever-Zirkelschluss:** Die erwarteten Paper werden nicht kuratiert,
sondern **mechanisch aus dem Chunk-Text abgeleitet** – ein Paper gilt als relevant, wenn
mindestens einer seiner Chunks alle Strings der Regel ``match_all`` (case-insensitive)
enthält. Die abgeleiteten IDs sind im Gold-Set eingefroren und über ``--verify-labels``
jederzeit gegen den Index nachprüfbar.

Aufruf::

    python -m scripts.eval_retrieval
    python -m scripts.eval_retrieval --k 10 --scoring tfidf
    python -m scripts.eval_retrieval --verify-labels
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, Scoring, TfidfIndex

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_GOLD = _REPO_ROOT / "eval" / "retrieval-gold.json"


@dataclass(frozen=True)
class GoldQuestion:
    """Eine Gold-Frage samt mechanischer Label-Regel und eingefrorenen Ziel-Papern."""

    qid: str
    query: str
    kind: str
    match_all: tuple[str, ...]
    expected_paper_ids: tuple[str, ...]


@dataclass(frozen=True)
class GoldSet:
    """Versioniertes Gold-Set (Datei ist die Single Source of Truth)."""

    version: str
    questions: tuple[GoldQuestion, ...]


@dataclass(frozen=True)
class QuestionScore:
    """Bewertung einer Frage: Treffer und Kehrwert des ersten relevanten Rangs."""

    qid: str
    kind: str
    hit: bool
    reciprocal_rank: float
    first_rank: int | None


@dataclass(frozen=True)
class EvaluationReport:
    """Aggregierte Kennzahlen eines Laufs (Hit@k und MRR@k über alle Fragen)."""

    k: int
    scoring: str
    scores: tuple[QuestionScore, ...]

    @property
    def hit_rate(self) -> float:
        """Anteil der Fragen mit mindestens einem relevanten Paper unter den Top-k."""
        if not self.scores:
            return 0.0
        return sum(1.0 for score in self.scores if score.hit) / len(self.scores)

    @property
    def mrr(self) -> float:
        """Mittlerer Kehrwert des Rangs des ersten relevanten Papers (0.0 ohne Treffer)."""
        if not self.scores:
            return 0.0
        return sum(score.reciprocal_rank for score in self.scores) / len(self.scores)

    def by_kind(self) -> dict[str, tuple[float, float, int]]:
        """Kennzahlen je Fragetyp: ``kind -> (Hit@k, MRR@k, Anzahl)``."""
        kinds: dict[str, list[QuestionScore]] = {}
        for score in self.scores:
            kinds.setdefault(score.kind, []).append(score)
        return {
            kind: (
                sum(1.0 for score in group if score.hit) / len(group),
                sum(score.reciprocal_rank for score in group) / len(group),
                len(group),
            )
            for kind, group in sorted(kinds.items())
        }


def load_gold_set(path: str | Path = _DEFAULT_GOLD) -> GoldSet:
    """Lädt das Gold-Set aus JSON.

    Args:
        path: Pfad zur Gold-Set-Datei.

    Returns:
        Das geladene :class:`GoldSet` in Dateireihenfolge.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    questions = tuple(
        GoldQuestion(
            qid=str(entry["qid"]),
            query=str(entry["query"]),
            kind=str(entry["kind"]),
            match_all=tuple(str(term) for term in entry["match_all"]),
            expected_paper_ids=tuple(str(pid) for pid in entry["expected_paper_ids"]),
        )
        for entry in payload["questions"]
    )
    return GoldSet(version=str(payload["gold_set_version"]), questions=questions)


def derive_expected_papers(db_path: str | Path, match_all: tuple[str, ...]) -> tuple[str, ...]:
    """Leitet die relevanten Paper mechanisch aus dem Chunk-Text ab (Label-Regel).

    Relevant ist ein Paper, wenn mindestens **einer** seiner Chunks **alle** Strings aus
    ``match_all`` (case-insensitive) enthält. Die Regel ist bewusst unabhängig von jeder
    Ranking-Funktion, damit die Messung nicht das eigene Verfahren bestätigt.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        match_all: Nicht-leere Folge von Suchstrings.

    Returns:
        Aufsteigend sortierte Paper-IDs.
    """
    condition = " AND ".join("LOWER(text) LIKE ?" for _ in match_all)
    parameters = [f"%{term.lower()}%" for term in match_all]
    connection = sqlite3.connect(str(db_path))
    try:
        rows = connection.execute(
            f"SELECT DISTINCT paper_id FROM chunks WHERE {condition}", parameters
        ).fetchall()
    finally:
        connection.close()
    return tuple(sorted(str(row[0]) for row in rows))


def verify_labels(db_path: str | Path, gold: GoldSet) -> tuple[str, ...]:
    """Prüft die eingefrorenen Labels gegen die Ableitung aus dem Index.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        gold: Das geladene Gold-Set.

    Returns:
        Meldungen zu abweichenden Fragen; leer, wenn alle Labels reproduzierbar sind.
    """
    findings: list[str] = []
    for question in gold.questions:
        derived = derive_expected_papers(db_path, question.match_all)
        if derived != tuple(sorted(question.expected_paper_ids)):
            findings.append(
                f"{question.qid}: erwartet {len(question.expected_paper_ids)} Paper, "
                f"abgeleitet {len(derived)}"
            )
    return tuple(findings)


def evaluate_question(
    index: TfidfIndex, question: GoldQuestion, k: int, scoring: Scoring = DEFAULT_SCORING
) -> QuestionScore:
    """Bewertet eine Gold-Frage gegen die Top-k-Chunks des Index.

    Args:
        index: Geladener Index (einmal laden, viele Fragen bewerten).
        question: Die zu bewertende Gold-Frage.
        k: Rang-Tiefe für Hit@k/MRR@k (> 0).
        scoring: Zu messende Wertung (``hybrid``/``tfidf``/``bm25``).

    Returns:
        Ein :class:`QuestionScore`; ohne relevanten Treffer ist ``reciprocal_rank`` ``0.0``.
    """
    expected = set(question.expected_paper_ids)
    for rank, hit in enumerate(index.search(question.query, k, scoring=scoring), start=1):
        if hit.paper_id in expected:
            return QuestionScore(
                qid=question.qid,
                kind=question.kind,
                hit=True,
                reciprocal_rank=1.0 / rank,
                first_rank=rank,
            )
    return QuestionScore(
        qid=question.qid, kind=question.kind, hit=False, reciprocal_rank=0.0, first_rank=None
    )


def evaluate(
    index: TfidfIndex, gold: GoldSet, k: int = 5, scoring: Scoring = DEFAULT_SCORING
) -> EvaluationReport:
    """Bewertet das gesamte Gold-Set.

    Args:
        index: Geladener Index.
        gold: Das Gold-Set.
        k: Rang-Tiefe für Hit@k/MRR@k (> 0).
        scoring: Zu messende Wertung (``hybrid``/``tfidf``/``bm25``).

    Returns:
        Der aggregierte :class:`EvaluationReport`.
    """
    return EvaluationReport(
        k=k,
        scoring=scoring,
        scores=tuple(evaluate_question(index, question, k, scoring) for question in gold.questions),
    )


def render(report: EvaluationReport, gold: GoldSet) -> str:
    """Formatiert einen Evaluationsbericht als Text (eine Zeile je Frage plus Aggregate)."""
    lines = [
        f"Gold-Set {gold.version} · {len(report.scores)} Fragen · k = {report.k} "
        f"· Wertung = {report.scoring}",
        "",
    ]
    for score, question in zip(report.scores, gold.questions, strict=True):
        rank = str(score.first_rank) if score.first_rank is not None else "-"
        lines.append(
            f"  {score.qid} [{score.kind:10s}] Rang {rank:>2s} · RR {score.reciprocal_rank:.3f} "
            f"· {question.query}"
        )
    lines.append("")
    for kind, (hit_rate, mrr, count) in report.by_kind().items():
        lines.append(f"  {kind:10s} (n={count:2d}): Hit@{report.k} {hit_rate:.3f} · MRR {mrr:.3f}")
    lines.append("")
    lines.append(f"  GESAMT      (n={len(report.scores):2d}): ")
    lines[-1] += f"Hit@{report.k} {report.hit_rate:.3f} · MRR {report.mrr:.3f}"
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Führt die Evaluation aus (CLI-Einstiegspunkt)."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(
        description="Quantitative Retrieval-Evaluation (Hit@k/MRR) gegen das Gold-Set."
    )
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-Datei.")
    parser.add_argument("--gold", default=str(_DEFAULT_GOLD), help="Pfad zum Gold-Set (JSON).")
    parser.add_argument("--k", type=int, default=5, help="Rang-Tiefe für Hit@k/MRR@k.")
    parser.add_argument(
        "--scoring",
        choices=("hybrid", "tfidf", "bm25"),
        default=DEFAULT_SCORING,
        help="Zu messende Wertung (Default 'hybrid').",
    )
    parser.add_argument(
        "--verify-labels",
        action="store_true",
        help="Nur die Labels gegen den Index nachrechnen (kein Retrieval).",
    )
    args = parser.parse_args(argv)

    gold = load_gold_set(args.gold)
    if args.verify_labels:
        findings = verify_labels(args.index, gold)
        for finding in findings:
            print(f"  ! {finding}")
        print(f"Labels: {len(gold.questions) - len(findings)}/{len(gold.questions)} reproduzierbar")
        return 1 if findings else 0

    index = TfidfIndex.load(args.index)
    print(render(evaluate(index, gold, args.k, args.scoring), gold))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
