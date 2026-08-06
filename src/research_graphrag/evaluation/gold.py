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

CITATION_LABEL_SOURCE = "citation_graph"
"""Label-Quelle des Multi-Hop-Gold-Sets: die ``CITES``-Kanten des Zitationsgraphen.

Die zugehörigen Fragen leben bewusst in einem **eigenen** Gold-Set
(:mod:`research_graphrag.evaluation.multihop`); hier steht nur der Bezeichner, damit das
Vokabular der Label-Quellen an einer Stelle gepflegt wird
(docs/adr/0023-multihop-citation-evaluation-phase10.md).
"""

CITATION_LABELS = frozenset({CITATION_LABEL_SOURCE})
"""Label-Quellen, die aus dem Zitationsgraphen stammen."""

DEFAULT_LABEL_SOURCE = "mechanical"
"""Quelle, wenn das Gold-Set nichts anderes angibt."""

INDEX_SCHEMA_VERSION = "0.4.0"
"""Index-Schema, gegen das die Labels abgeleitet werden."""

LABEL_RULE = (
    "Ein Paper gilt als relevant, wenn mindestens einer seiner Chunks alle Strings aus "
    "match_all (case-insensitive) enthaelt. Die Labels sind damit unabhaengig von jeder "
    "Ranking-Funktion und ueber 'python -m scripts.eval_retrieval --verify-labels' "
    "reproduzierbar."
)
"""Die Label-Regel im Klartext (steht so in der Gold-Set-Datei)."""

GOLD_SET_ORIGIN = (
    "Roadmap A4 (Hybrid-Retrieval BM25 + TF-IDF), "
    "docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md; Teil-Vorgriff auf A6"
)
"""Anlass, aus dem das Fragenset ursprünglich entstanden ist (bleibt konstant)."""

GOLD_SET_SPLITS = {
    "G*": "Entwicklungsfragen (vor der Implementierung eingefroren)",
    "V*": "unabhaengiges Validierungsset (nach der Implementierung mechanisch abgeleitet)",
}
"""Bedeutung der Fragekennungen (Entwicklungs- gegen Validierungsset)."""


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


def relabel_gold_set(db_path: str | Path, gold: GoldSet, *, version: str) -> GoldSet:
    """Leitet die mechanischen Labels neu aus dem Index ab (nach einem Korpuswechsel).

    Die **Fragen** bleiben unverändert – Wortlaut, Reihenfolge, Art und Label-Regel. Neu bestimmt
    werden ausschließlich die Ziel-Paper, und das auch nur für nachrechenbare Quellen: Ein
    kuratiertes oder anderweitig geurteiltes Label würde sonst still überschrieben.

    Nötig wird das, weil die ``paper_id`` der sha256-Hash der Datei ist. Wird ein PDF durch eine
    andere Fassung ersetzt, zeigt ein eingefrorenes Label ins Leere – unabhängig davon, ob der
    Inhalt noch im Korpus steht
    (docs/adr/0016-quantitative-retrieval-evaluation-phase7.md).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        gold: Das bisherige Gold-Set.
        version: Version des neuen Standes (die Fragen ändern sich nicht, die Labels schon).

    Returns:
        Ein neues :class:`GoldSet` mit aktualisierten Zielen.
    """
    questions = tuple(
        question
        if question.label_source not in MECHANICAL_LABELS
        else GoldQuestion(
            qid=question.qid,
            query=question.query,
            kind=question.kind,
            match_all=question.match_all,
            expected_paper_ids=derive_expected_papers(db_path, question.match_all),
            label_source=question.label_source,
        )
        for question in gold.questions
    )
    return GoldSet(version=version, questions=questions)


def unlabelled_questions(gold: GoldSet) -> tuple[str, ...]:
    """Nennt die Fragen ohne jedes Ziel-Paper.

    Eine solche Frage misst nichts mehr: Sie kann nie einen Treffer erzeugen und zieht damit die
    Kennzahlen nach unten, ohne eine Aussage zu tragen. Nach einem Korpuswechsel ist das ein
    **Befund**, der eine Entscheidung verlangt (Frage anpassen oder entfernen).

    Args:
        gold: Das geladene Gold-Set.

    Returns:
        Die betroffenen Fragekennungen in Dateireihenfolge.
    """
    return tuple(question.qid for question in gold.questions if not question.expected_paper_ids)


def _corpus_size(db_path: str | Path) -> dict[str, int]:
    """Liest Paper- und Chunk-Zahl des Index (Herkunftsnachweis im Gold-Set)."""
    connection = sqlite3.connect(str(db_path))
    try:
        papers = int(connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0])
        chunks = int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    finally:
        connection.close()
    return {"papers": papers, "chunks": chunks}


def save_gold_set(db_path: str | Path, gold: GoldSet, path: str | Path, *, note: str) -> None:
    """Schreibt das Gold-Set als JSON – mit dem Korpus, gegen den es abgeleitet wurde.

    Die Korpus-Angabe ist kein Beiwerk: Ohne sie lässt sich später nicht entscheiden, ob eine
    abweichende Messung am Verfahren oder am Bestand liegt.

    Args:
        db_path: Index, aus dem die Labels stammen (nur für die Korpus-Angabe gelesen).
        gold: Das zu schreibende Gold-Set.
        path: Zieldatei.
        note: Kurze Begründung des Standes (landet in ``updated_for``).
    """
    payload = {
        "gold_set_version": gold.version,
        "created_for": GOLD_SET_ORIGIN,
        "updated_for": note,
        "index_schema_version": INDEX_SCHEMA_VERSION,
        "corpus": _corpus_size(db_path),
        "label_rule": LABEL_RULE,
        "questions": [
            {
                "qid": question.qid,
                "kind": question.kind,
                "query": question.query,
                "match_all": list(question.match_all),
                "expected_paper_ids": list(question.expected_paper_ids),
                **(
                    {}
                    if question.label_source == DEFAULT_LABEL_SOURCE
                    else {"label_source": question.label_source}
                ),
            }
            for question in gold.questions
        ],
        "splits": GOLD_SET_SPLITS,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    target.write_bytes(text.encode("utf-8"))
