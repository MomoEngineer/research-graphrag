"""CLI: Prüf-Fragen je Suchmodus durchspielen und die belegte Provenienz zeigen (Phase 6).

Spielt das feste Prüf-Fragen-Set ([eval/pruef-fragen.md](../eval/pruef-fragen.md)) über die
erwarteten Retrieval-Modi (Basic/Local/Global/DRIFT) und druckt je Frage die gelieferte
Provenienz (Paper · Abschnitt · Seite bzw. Community · Vertreter). Die inhaltliche Bewertung
bleibt beim Menschen – dies ist eine **wiederholbare Stichprobe**, keine automatische Bewertung
(siehe docs/adr/0010-drop-in-workflow-and-qa-phase6.md). ``QUESTIONS`` ist die Single Source of
Truth und wird auch vom Regressionstest ``tests/retrieval/test_qa.py`` konsumiert.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.qa
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.drift import search_drift
from research_graphrag.retrieval.global_search import search_global
from research_graphrag.retrieval.local import search_local

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"


@dataclass(frozen=True)
class Question:
    """Eine feste Prüf-Frage mit erwartetem Modus und (narrativer) Provenienz-Erwartung."""

    qid: str
    query: str
    mode: str
    expectation: str


QUESTIONS: tuple[Question, ...] = (
    Question(
        "D1",
        "Which datasets are used to evaluate GraphRAG approaches?",
        "local",
        "GraphRAG-Evaluationspaper, Abschnitt Datasets/Evaluation",
    ),
    Question(
        "D2",
        "What are the key stages of the GraphRAG workflow?",
        "local",
        "GraphRAG-Survey, Workflow-Abschnitt",
    ),
    Question(
        "S1",
        "Which research directions emerge across the corpus?",
        "global",
        "mehrere Communities mit repräsentativen Papern",
    ),
    Question(
        "S2",
        "Which thematic clusters combine graphs and retrieval?",
        "global",
        "GraphRAG-/KG-RAG-Community",
    ),
    Question(
        "N1",
        "Which papers build on knowledge graph methods?",
        "local",
        "über Graph-Kanten verknüpfte Nachbarpaper",
    ),
    Question(
        "N2",
        "Which works relate to knowledge-graph-based code generation?",
        "local",
        "thematisch benachbarte Code-KG-Paper",
    ),
    Question(
        "F1",
        "What F1 score is reported for the evaluation?",
        "basic",
        "Paper mit Ergebnis-Tabelle/-Abschnitt",
    ),
    Question(
        "F2",
        "Which benchmarking datasets are named?",
        "basic",
        "Paper mit Datensatz-Nennung",
    ),
    Question(
        "W1",
        "Compare vector and graph retrieval approaches.",
        "drift",
        ">= 2 Paper der passenden Community",
    ),
    Question(
        "W2",
        "How do RAG and GraphRAG differ for agentic search?",
        "drift",
        "Community + gegenüberstellende Belege",
    ),
)
"""Festes Prüf-Fragen-Set über alle fünf Fragetypen (Single Source of Truth)."""


@dataclass(frozen=True)
class QAResult:
    """Ergebnis einer durchgespielten Prüf-Frage: uniforme Provenienz-Einträge."""

    question: Question
    provenance: tuple[dict[str, Any], ...]

    @property
    def n_results(self) -> int:
        """Anzahl der gelieferten Provenienz-Einträge (0 = kein Beleg)."""
        return len(self.provenance)


def _from_citation(citation: Any) -> dict[str, Any]:
    """Bildet ein Chunk-:class:`Citation` auf einen uniformen Provenienz-Eintrag ab."""
    return {
        "kind": "chunk",
        "paper_id": citation.paper_id,
        "page_number": citation.page_number,
        "section_title": citation.section_title,
        "source_uri": citation.source_uri,
    }


def _from_community(match: Any) -> dict[str, Any]:
    """Bildet einen Community-Treffer auf einen uniformen Provenienz-Eintrag ab."""
    return {
        "kind": "community",
        "community_id": match.community_id,
        "size": match.size,
        "keywords": list(match.keywords),
        "representatives": [ref.paper_id for ref in match.representatives],
    }


def run_question(index: str | Path, question: Question, k: int = 5) -> QAResult:
    """Führt eine Prüf-Frage im erwarteten Modus aus und sammelt die Provenienz.

    Args:
        index: Pfad zur SQLite-Index-Datei.
        question: Die auszuführende Prüf-Frage (bestimmt den Modus).
        k: Trefferzahl je Modus (> 0).

    Returns:
        Ein :class:`QAResult` mit uniformen Provenienz-Einträgen (``kind`` = ``chunk``/
        ``community``).
    """
    provenance: list[dict[str, Any]] = []
    if question.mode == "basic":
        result_basic = search_basic(index, question.query, k)
        provenance.extend(_from_citation(c) for c in result_basic.citations)
    elif question.mode == "local":
        local_result = search_local(index, question.query, k=k)
        if local_result.seed is not None:
            provenance.append(_from_citation(local_result.seed))
        provenance.extend(_from_citation(c) for c in local_result.neighborhood)
        provenance.extend(
            _from_citation(n.citation) for n in local_result.fan_out if n.citation is not None
        )
    elif question.mode == "global":
        provenance.extend(
            _from_community(m) for m in search_global(index, question.query, k).communities
        )
    elif question.mode == "drift":
        drift_result = search_drift(index, question.query, k=k)
        if drift_result.community is not None:
            provenance.append(_from_community(drift_result.community))
        provenance.extend(_from_citation(c) for c in drift_result.citations)
    else:  # pragma: no cover - QUESTIONS.mode ist stets gültig
        raise ValueError(f"Unbekannter Modus: {question.mode}")
    return QAResult(question=question, provenance=tuple(provenance))


def _format_prov(entry: dict[str, Any]) -> str:
    """Formatiert einen Provenienz-Eintrag als kompakte Zeile für die Anzeige."""
    if entry["kind"] == "chunk":
        section = f" · Abschnitt {entry['section_title']}" if entry["section_title"] else ""
        return f"Paper {entry['paper_id']} · Seite {entry['page_number']}{section}"
    keywords = ", ".join(entry["keywords"][:5]) or "(keine)"
    reps = ", ".join(entry["representatives"]) or "(keine)"
    return (
        f"Community #{entry['community_id']} ({entry['size']} Paper) · "
        f"{keywords} · Vertreter: {reps}"
    )


def main() -> int:
    """Spielt alle Prüf-Fragen über den Index und zeigt die Provenienz (Exit-Code 0)."""
    # Robuste Unicode-Ausgabe (Snippets/Keywords enthalten Zeichen außerhalb von cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Prüf-Fragen je Modus durchspielen (Phase 6).")
    parser.add_argument("--index", default=str(_DEFAULT_INDEX), help="Pfad zur Index-SQLite")
    parser.add_argument("-k", type=int, default=5, help="Trefferzahl je Modus (> 0)")
    args = parser.parse_args()

    print(f"[qa] Spiele {len(QUESTIONS)} Prüf-Fragen über den Index {args.index}:")
    answered = 0
    for question in QUESTIONS:
        try:
            result = run_question(args.index, question, args.k)
        except DomainError as exc:
            print(f"  [{question.qid}] Fehler [{exc.code.value}]: {exc.message}")
            return 1
        marker = "OK " if result.n_results else "-- "
        print(f"  {marker}[{question.qid}] ({question.mode}) {question.query}")
        print(f"      erwartet: {question.expectation}")
        for entry in result.provenance[: args.k]:
            print(f"      -> {_format_prov(entry)}")
        if result.n_results:
            answered += 1
    print(f"[qa] {answered}/{len(QUESTIONS)} Prüf-Fragen mit belegter Provenienz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
