"""Gold-Set und mechanische Label-Regel der Retrieval-Evaluation (Phase 7 / A4 + A6).

**Ground Truth ohne Retriever-Zirkelschluss:** Die erwarteten Paper werden nicht kuratiert,
sondern **mechanisch aus dem Chunk-Text abgeleitet** – ein Paper gilt als relevant, wenn
mindestens einer seiner Chunks alle Strings der Regel ``match_all`` (case-insensitive) enthält.
Die abgeleiteten IDs sind im Gold-Set eingefroren und jederzeit gegen den Index nachprüfbar;
genau diese Nachrechenbarkeit hat in A5 den Re-Ingest abgesichert.

Jede Frage weist ihre **Label-Quelle** aus. Heute ist das ausschließlich die mechanische Regel;
spätere Quellen (z. B. der Zitationsgraph oder eingefrorene Urteile) treten additiv daneben,
ohne die verifizierbare Basis zu verdrängen
(docs/adr/0016-quantitative-retrieval-evaluation-phase7.md).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

MECHANICAL_LABELS = frozenset({"mechanical"})
"""Label-Quellen, die sich aus dem Index nachrechnen lassen."""

DEFAULT_LABEL_SOURCE = "mechanical"
"""Quelle, wenn das Gold-Set nichts anderes angibt."""


@dataclass(frozen=True)
class GoldQuestion:
    """Eine Gold-Frage samt Label-Regel, eingefrorenen Ziel-Papern und Label-Quelle."""

    qid: str
    query: str
    kind: str
    match_all: tuple[str, ...]
    expected_paper_ids: tuple[str, ...]
    label_source: str = DEFAULT_LABEL_SOURCE


@dataclass(frozen=True)
class GoldSet:
    """Versioniertes Gold-Set (die Datei ist die Single Source of Truth)."""

    version: str
    questions: tuple[GoldQuestion, ...]


def load_gold_set(path: str | Path) -> GoldSet:
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
            label_source=str(entry.get("label_source", DEFAULT_LABEL_SOURCE)),
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

    Fragen mit einer nicht-mechanischen Label-Quelle werden übersprungen – sie sind per
    Definition nicht nachrechenbar.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        gold: Das geladene Gold-Set.

    Returns:
        Meldungen zu abweichenden Fragen; leer, wenn alle Labels reproduzierbar sind.
    """
    findings: list[str] = []
    for question in gold.questions:
        if question.label_source not in MECHANICAL_LABELS:
            continue
        derived = derive_expected_papers(db_path, question.match_all)
        if derived != tuple(sorted(question.expected_paper_ids)):
            findings.append(
                f"{question.qid}: erwartet {len(question.expected_paper_ids)} Paper, "
                f"abgeleitet {len(derived)}"
            )
    return tuple(findings)
