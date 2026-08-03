"""Multi-Hop-Evaluation gegen den Zitationsgraphen (Phase 10 / V3).

**Die zweite Label-Quelle des Repos – und die einzige nicht-lexikalische.** Während das
Retrieval-Gold-Set seine Ziel-Paper aus dem Chunk-Text ableitet (``mechanical``, siehe
:mod:`research_graphrag.evaluation.gold`), stammen die Labels hier aus den ``CITES``-Kanten
(docs/adr/0011-intra-corpus-citation-graph-phase7.md): Zu einem **Ankerpaper** gelten genau die
Paper als relevant, die es zitieren. Damit ist der Fragetyp „Zitations-/Methodennetze
(Multi-Hop)" aus dem README-Contract erstmals gemessen – objektiv und trotzdem nachrechenbar
(docs/adr/0023-multihop-citation-evaluation-phase10.md).

Bewusst getrennt vom Retrieval-Gold-Set: Eigenes Gold-Set, eigene Ebenen, eigene Baseline. Sonst
mischten sich zwei unvergleichbare Fragetypen in dieselben Aggregate und die seit
docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md fortgeschriebene Kennzahlreihe verlöre ihren
Bezug.

Drei Eigenheiten, die aus der Vorabmessung stammen und nicht verhandelbar sind:

* **Das Ankerpaper wird aus jedem Bündel entfernt.** Es kann per Konstruktion nie ein erwartetes
  Paper sein (Selbstzitate sind ausgeschlossen), besetzt aber die vordersten Ränge.
* **Zwei Anfrageformen aus demselben Rahmen.** Die Titel-Form ist die realistische Nutzerfrage,
  nimmt aber die Abkürzung über die Bibliografie der zitierenden Paper; die Themen-Form ist die
  saubere Gegenprobe. Welcher Beleg woher stammt, weist die Diagnose aus (``…:ref``/``…:body``).
* **``get_citations`` ist keine Kennzahl, sondern der triviale Oberwert.** Das Werkzeug liest
  genau die Tabelle, aus der die Labels stammen.
"""

from __future__ import annotations

import json
import random
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.evaluation.gold import CITATION_LABEL_SOURCE, CITATION_LABELS
from research_graphrag.evaluation.metrics import (
    CoverageStats,
    EvaluationReport,
    QuestionScore,
    first_hit,
)
from research_graphrag.extraction.model import SECTION_KIND_REFERENCES
from research_graphrag.extraction.structure import detect_heading
from research_graphrag.indexing.citation_graph import (
    MIN_TITLE_CHARS,
    MIN_TITLE_WORDS,
    TITLE_PAGE_PAGES,
    normalize_title,
    title_from_uri,
)
from research_graphrag.indexing.graph_index import load_neighbors
from research_graphrag.indexing.tfidf_index import DEFAULT_SCORING, Scoring
from research_graphrag.overview.drafts import keyword_table
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.local import DEFAULT_FANOUT, DEFAULT_SEEDS, search_local

MULTIHOP_GOLD_VERSION = "1.0.0"
"""Version des Multi-Hop-Gold-Sets (geht in den Baseline-Fingerprint ein)."""

QUERY_FRAME = "Which papers build on {payload}?"
"""Gemeinsamer Rahmen beider Anfrageformen – nur die Nutzlast unterscheidet sie."""

GRAPH = "graph"
"""Strukturelle Ebene: der Paper-Ähnlichkeitsgraph **ohne** Textanfrage."""

LEVELS = (GRAPH, "basic_title", "local_title", "basic_topic", "local_topic")
"""Alle messbaren Ebenen in Berichtsreihenfolge."""

RANDOM_DRAWS = 100
"""Ziehungen der zufälligen Paper-Baseline (mittelt die Einzelziehungs-Streuung heraus)."""

RANDOM_SEED = 42
"""Fester Seed der zufälligen Baseline – die Messung bleibt reproduzierbar."""

CITING_BUCKETS = ((10, "zitiert 10+"), (5, "zitiert 5-9"), (0, "zitiert 3-4"))
"""Untergrenze → Gruppenname für die Aufschlüsselung nach Zitationshäufigkeit.

Die Schnitte sind nicht geraten, sondern so gewählt, dass die Gruppen am realen Korpus
vergleichbar groß sind (17 / 17 / 10 von 44 Ankern). Sie beantworten die naheliegende
Rückfrage, ob ein Verfahren nur die stark zitierten Hubs findet.
"""


@dataclass(frozen=True)
class MultiHopParameters:
    """Parameter eines Multi-Hop-Laufs (gehen in den Baseline-Fingerprint ein).

    Bewusst **eigene** Parameter statt einer Erweiterung von
    :class:`~research_graphrag.evaluation.runner.RunParameters`: Ein zusätzliches Feld dort
    hätte den Fingerprint der eingefrorenen Retrieval-Baseline invalidiert.
    """

    k: int = 5
    fan_out: int = DEFAULT_FANOUT
    seeds: int = DEFAULT_SEEDS
    min_citing: int = 3
    scoring: Scoring = DEFAULT_SCORING

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Parameter (Reihenfolge stabil für den Fingerprint-Vergleich)."""
        return {
            "k": self.k,
            "fan_out": self.fan_out,
            "seeds": self.seeds,
            "min_citing": self.min_citing,
            "scoring": self.scoring,
        }


DEFAULT_MULTIHOP_PARAMETERS = MultiHopParameters()
"""Vorgabewerte eines Multi-Hop-Laufs (als Singleton, damit sie als Default dienen können)."""


@dataclass(frozen=True)
class MultiHopQuestion:
    """Eine Multi-Hop-Frage: ein Ankerpaper und die Paper, die es zitieren."""

    qid: str
    anchor_paper_id: str
    anchor_title: str
    topic_terms: tuple[str, ...]
    expected_paper_ids: tuple[str, ...]
    label_source: str = CITATION_LABEL_SOURCE

    @property
    def query_title(self) -> str:
        """Die realistische Nutzerfrage – Nutzlast ist der Titel des Ankerpapers."""
        return QUERY_FRAME.format(payload=self.anchor_title)

    @property
    def query_topic(self) -> str:
        """Die Gegenprobe ohne Titelwörter – Nutzlast sind die Top-Terme des Ankerpapers."""
        return QUERY_FRAME.format(payload=", ".join(self.topic_terms))

    @property
    def kind(self) -> str:
        """Gruppe nach Zitationshäufigkeit (siehe :data:`CITING_BUCKETS`)."""
        count = len(self.expected_paper_ids)
        return next(name for threshold, name in CITING_BUCKETS if count >= threshold)

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Frage (Dateiformat des Gold-Sets)."""
        return {
            "qid": self.qid,
            "anchor_paper_id": self.anchor_paper_id,
            "anchor_title": self.anchor_title,
            "topic_terms": list(self.topic_terms),
            "expected_paper_ids": list(self.expected_paper_ids),
            "label_source": self.label_source,
        }


@dataclass(frozen=True)
class MultiHopGoldSet:
    """Versioniertes Multi-Hop-Gold-Set (die Datei ist die Single Source of Truth)."""

    version: str
    questions: tuple[MultiHopQuestion, ...]


@dataclass(frozen=True)
class RecallBounds:
    """Strukturelle Grenzen des Zitationsgraphen – eine **obere Schranke**, kein Recall.

    Aus ``citation_edges`` abgeleitete Labels können eine **fehlende** Kante nicht aufdecken;
    messbar ist nur, welche Paper als Quelle oder Ziel prinzipiell ausscheiden
    (docs/adr/0023-multihop-citation-evaluation-phase10.md).
    """

    n_papers: int
    without_reference_section: tuple[str, ...]
    without_title_key: tuple[str, ...]
    without_identifier_key: tuple[str, ...]

    @property
    def unreachable_targets(self) -> tuple[str, ...]:
        """Paper, die weder über den Titel noch über einen Identifikator gefunden werden können."""
        return tuple(sorted(set(self.without_title_key) & set(self.without_identifier_key)))


def is_reference_section(section_title: str) -> bool:
    """Erkennt, ob eine Abschnittsüberschrift einen Referenzabschnitt bezeichnet.

    Genutzt wird dieselbe Heuristik wie bei der Extraktion
    (:func:`research_graphrag.extraction.structure.detect_heading`). Am realen Korpus stimmt
    das Ergebnis **exakt** mit der Section-Art im Canonical Model überein; die Evaluation bleibt
    dadurch allein auf ``index.sqlite`` angewiesen.

    Args:
        section_title: Die Abschnittsüberschrift eines Chunks (darf leer sein).

    Returns:
        ``True``, wenn die Überschrift als Bibliografie gelesen wird.
    """
    heading = detect_heading(section_title)
    return heading is not None and heading.kind == SECTION_KIND_REFERENCES


def _connect(db_path: str | Path) -> sqlite3.Connection:
    """Öffnet den Index und stellt sicher, dass ein Zitationsgraph vorhanden ist.

    Raises:
        DomainError: ``not_found`` wenn die Index-Datei fehlt; ``constraint_violation`` wenn
            kein Zitationsgraph gebaut wurde (siehe docs/error-model.md).
    """
    path = Path(db_path)
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")
    connection = sqlite3.connect(str(path))
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'citation_edges'"
    ).fetchone()
    if exists is None:
        connection.close()
        raise DomainError(
            ErrorCode.CONSTRAINT_VIOLATION,
            "Kein Zitationsgraph im Index – die Multi-Hop-Evaluation braucht 'citation_edges'.",
        )
    return connection


def _paper_texts(connection: sqlite3.Connection) -> dict[str, str]:
    """Sammelt je Paper den vollständigen Chunk-Text in Dokumentreihenfolge."""
    parts: dict[str, list[str]] = {}
    for paper_id, text in connection.execute(
        "SELECT paper_id, text FROM chunks ORDER BY paper_id, row_index"
    ):
        parts.setdefault(str(paper_id), []).append(str(text))
    return {paper_id: "\n".join(chunks) for paper_id, chunks in parts.items()}


def derive_questions(
    db_path: str | Path, params: MultiHopParameters = DEFAULT_MULTIHOP_PARAMETERS
) -> tuple[MultiHopQuestion, ...]:
    """Erzeugt die Multi-Hop-Fragen **deterministisch** aus dem Index.

    Anker sind alle Paper mit mindestens ``params.min_citing`` zitierenden Korpus-Papern,
    aufsteigend nach ``paper_id`` durchnummeriert (``C01``, ``C02``, …). Die Themen-Terme
    entstehen über :func:`research_graphrag.overview.drafts.keyword_table` – derselbe
    Mechanismus wie bei den Übersicht-Entwürfen, kein zweiter Keyword-Pfad.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        params: Messparameter; genutzt wird ``min_citing``.

    Returns:
        Die Fragen in stabiler Reihenfolge.

    Raises:
        DomainError: ``not_found``/``constraint_violation`` wie in :func:`_connect`.
    """
    connection = _connect(db_path)
    try:
        citing: dict[str, set[str]] = {}
        for source, target in connection.execute(
            "SELECT source_paper_id, target_paper_id FROM citation_edges"
        ):
            citing.setdefault(str(target), set()).add(str(source))
        uris = {
            str(paper_id): str(source_uri)
            for paper_id, source_uri in connection.execute(
                "SELECT paper_id, source_uri FROM papers"
            )
        }
        texts = _paper_texts(connection)
    finally:
        connection.close()

    ordered = sorted(uris)
    terms = dict(
        zip(ordered, keyword_table([texts.get(paper_id, "") for paper_id in ordered]), strict=True)
    )
    anchors = sorted(
        paper_id
        for paper_id, sources in citing.items()
        if len(sources) >= params.min_citing and paper_id in uris
    )
    return tuple(
        MultiHopQuestion(
            qid=f"C{position:02d}",
            anchor_paper_id=paper_id,
            anchor_title=title_from_uri(uris[paper_id]),
            topic_terms=tuple(terms[paper_id]),
            expected_paper_ids=tuple(sorted(citing[paper_id])),
        )
        for position, paper_id in enumerate(anchors, start=1)
    )


def build_multihop_gold(
    db_path: str | Path,
    params: MultiHopParameters = DEFAULT_MULTIHOP_PARAMETERS,
    version: str = MULTIHOP_GOLD_VERSION,
) -> MultiHopGoldSet:
    """Baut ein vollständiges Gold-Set aus dem Index (zum Einfrieren)."""
    return MultiHopGoldSet(version=version, questions=derive_questions(db_path, params))


def save_multihop_gold(
    gold: MultiHopGoldSet,
    path: str | Path,
    params: MultiHopParameters = DEFAULT_MULTIHOP_PARAMETERS,
) -> None:
    """Schreibt das Gold-Set als JSON (UTF-8, eingerückt, selbsterklärend)."""
    payload = {
        "multihop_gold_version": gold.version,
        "label_source": CITATION_LABEL_SOURCE,
        "label_rule": (
            "Zu einem Ankerpaper gelten genau die Paper als relevant, die es laut "
            "'citation_edges' zitieren. Anker sind alle Paper mit mindestens "
            f"{params.min_citing} zitierenden Korpus-Papern. Labels, Titel und Themen-Terme "
            "sind über 'python -m scripts.eval_retrieval --zitationen --verify-labels' "
            "reproduzierbar."
        ),
        "query_frame": QUERY_FRAME,
        "min_citing": params.min_citing,
        "questions": [question.to_dict() for question in gold.questions],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_multihop_gold(path: str | Path) -> MultiHopGoldSet:
    """Lädt das Multi-Hop-Gold-Set aus JSON.

    Args:
        path: Pfad zur Gold-Set-Datei.

    Returns:
        Das geladene :class:`MultiHopGoldSet` in Dateireihenfolge.

    Raises:
        DomainError: ``not_found``, wenn die Datei fehlt (kein stiller Lauf gegen nichts).
    """
    source = Path(path)
    if not source.is_file():
        raise DomainError(
            ErrorCode.NOT_FOUND,
            f"Multi-Hop-Gold-Set nicht gefunden: {source}. Zuerst mit '--write-gold' erzeugen.",
        )
    payload = json.loads(source.read_text(encoding="utf-8"))
    questions = tuple(
        MultiHopQuestion(
            qid=str(entry["qid"]),
            anchor_paper_id=str(entry["anchor_paper_id"]),
            anchor_title=str(entry["anchor_title"]),
            topic_terms=tuple(str(term) for term in entry["topic_terms"]),
            expected_paper_ids=tuple(str(pid) for pid in entry["expected_paper_ids"]),
            label_source=str(entry.get("label_source", CITATION_LABEL_SOURCE)),
        )
        for entry in payload["questions"]
    )
    return MultiHopGoldSet(version=str(payload["multihop_gold_version"]), questions=questions)


def verify_questions(
    db_path: str | Path,
    gold: MultiHopGoldSet,
    params: MultiHopParameters = DEFAULT_MULTIHOP_PARAMETERS,
) -> tuple[str, ...]:
    """Rechnet das eingefrorene Gold-Set gegen den Index nach.

    Geprüft wird **alles**, was aus dem Index stammt: die Ankermenge, der Titel, die
    Themen-Terme und die erwarteten Paper. Das ist das Pendant zu ``--verify-labels`` des
    Retrieval-Gold-Sets und zugleich der Fail-fast des Regressions-Checks: Ändern sich die
    ``CITES``-Kanten, ohne dass sich Paper- oder Chunk-Zahl ändert, fällt es hier auf.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        gold: Das geladene Gold-Set.
        params: Messparameter (``min_citing`` bestimmt die Ankermenge).

    Returns:
        Meldungen zu abweichenden Fragen; leer, wenn alles reproduzierbar ist.
    """
    derived = {question.qid: question for question in derive_questions(db_path, params)}
    frozen = {question.qid: question for question in gold.questions}
    findings: list[str] = []
    for qid in sorted(set(derived) | set(frozen)):
        if qid not in frozen:
            findings.append(f"{qid}: im Index abgeleitet, aber nicht eingefroren")
            continue
        if qid not in derived:
            findings.append(f"{qid}: eingefroren, aber nicht mehr ableitbar")
            continue
        mine, theirs = frozen[qid], derived[qid]
        if mine.label_source not in CITATION_LABELS:
            findings.append(f"{qid}: unerwartete Label-Quelle {mine.label_source!r}")
        if mine.anchor_paper_id != theirs.anchor_paper_id:
            findings.append(f"{qid}: Anker {mine.anchor_paper_id} statt {theirs.anchor_paper_id}")
        if mine.anchor_title != theirs.anchor_title:
            findings.append(f"{qid}: Titel weicht ab ({mine.anchor_title!r})")
        if mine.topic_terms != theirs.topic_terms:
            findings.append(f"{qid}: Themen-Terme weichen ab ({', '.join(mine.topic_terms)})")
        if mine.expected_paper_ids != theirs.expected_paper_ids:
            findings.append(
                f"{qid}: erwartet {len(mine.expected_paper_ids)} Paper, "
                f"abgeleitet {len(theirs.expected_paper_ids)}"
            )
    return tuple(findings)


def recall_bounds(db_path: str | Path) -> RecallBounds:
    """Ermittelt die strukturellen Grenzen des Zitationsgraphen aus dem Index.

    Ein Paper kann **nicht zitieren**, wenn kein Referenzabschnitt erkannt wurde; es kann
    **nicht zitiert werden**, wenn weder sein Titel die Mindestmaße erreicht noch einer seiner
    Identifikatoren auf der eigenen Titelseite belegt ist (Präzisions-Guard aus
    docs/adr/0011-intra-corpus-citation-graph-phase7.md).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.

    Returns:
        Die :class:`RecallBounds` des aktuellen Index.

    Raises:
        DomainError: ``not_found``/``constraint_violation`` wie in :func:`_connect`.
    """
    connection = _connect(db_path)
    try:
        papers = {
            str(paper_id): (str(source_uri), json.loads(identifiers))
            for paper_id, source_uri, identifiers in connection.execute(
                "SELECT paper_id, source_uri, identifiers FROM papers"
            )
        }
        with_references: set[str] = set()
        front: dict[str, list[str]] = {paper_id: [] for paper_id in papers}
        for paper_id, page_end, section_title, text in connection.execute(
            "SELECT paper_id, page_end, section_title, text FROM chunks"
        ):
            if is_reference_section(str(section_title)):
                with_references.add(str(paper_id))
            elif int(page_end) <= TITLE_PAGE_PAGES and str(paper_id) in front:
                front[str(paper_id)].append(str(text))
    finally:
        connection.close()

    without_title = []
    without_identifier = []
    for paper_id, (source_uri, identifiers) in papers.items():
        title = normalize_title(title_from_uri(source_uri))
        if len(title) < MIN_TITLE_CHARS or len(title.split()) < MIN_TITLE_WORDS:
            without_title.append(paper_id)
        blob = " ".join(front[paper_id]).lower()
        if not any(value and str(value).lower() in blob for value in identifiers.values()):
            without_identifier.append(paper_id)
    return RecallBounds(
        n_papers=len(papers),
        without_reference_section=tuple(sorted(set(papers) - with_references)),
        without_title_key=tuple(sorted(without_title)),
        without_identifier_key=tuple(sorted(without_identifier)),
    )


def _component(prefix: str, section_title: str) -> str:
    """Baut die Diagnose eines Belegs: Baustein plus Herkunft (Bibliografie vs. Fließtext)."""
    return f"{prefix}:{'ref' if is_reference_section(section_title) else 'body'}"


def _graph_entries(
    db_path: str | Path, question: MultiHopQuestion, params: MultiHopParameters
) -> list[tuple[str, str]]:
    """Bündel der strukturellen Ebene: die Graph-Nachbarn des Ankerpapers, ohne Textanfrage."""
    neighbors = load_neighbors(db_path, question.anchor_paper_id)[: params.k]
    return [(paper_id, "neighbor") for paper_id, _weight in neighbors]


def _basic_entries(
    db_path: str | Path, query: str, params: MultiHopParameters
) -> list[tuple[str, str]]:
    """Bündel der Basic Search (lexikalische Vergleichsbasis)."""
    result = search_basic(db_path, query, params.k, scoring=params.scoring)
    return [
        (citation.paper_id, _component("chunk", citation.section_title))
        for citation in result.citations
    ]


def _local_entries(
    db_path: str | Path, query: str, params: MultiHopParameters
) -> list[tuple[str, str]]:
    """Bündel der Local Search: Seeds → Chunk-Nachbarschaft → Paper-Fan-out."""
    result = search_local(
        db_path,
        query,
        k=params.k,
        fan_out=params.fan_out,
        seeds=params.seeds,
        scoring=params.scoring,
    )
    entries = [
        (citation.paper_id, _component("seed", citation.section_title)) for citation in result.seeds
    ]
    entries.extend(
        (citation.paper_id, _component("neighborhood", citation.section_title))
        for citation in result.neighborhood
    )
    entries.extend(
        (
            neighbor.paper_id,
            "fan_out"
            if neighbor.citation is None
            else _component("fan_out", neighbor.citation.section_title),
        )
        for neighbor in result.fan_out
    )
    return entries


def _entries(
    db_path: str | Path, question: MultiHopQuestion, level: str, params: MultiHopParameters
) -> list[tuple[str, str]]:
    """Baut das Evidenz-Bündel einer Ebene (ohne die Anker-Filterung)."""
    if level == GRAPH:
        return _graph_entries(db_path, question, params)
    mode, _, form = level.partition("_")
    query = question.query_title if form == "title" else question.query_topic
    if mode == "basic":
        return _basic_entries(db_path, query, params)
    return _local_entries(db_path, query, params)


def _graph_coverage(
    db_path: str | Path, gold: MultiHopGoldSet, params: MultiHopParameters
) -> tuple[CoverageStats, ...]:
    """Coverage der strukturellen Ebene – nie ohne Selektivität und Zufalls-Baseline.

    Die Ablesevorschrift ist dieselbe wie bei der Community-Auswahl
    (docs/adr/0016-quantitative-retrieval-evaluation-phase7.md): *Lift 1,0 = Zufall*.
    """
    connection = _connect(db_path)
    try:
        papers = sorted(
            str(row[0]) for row in connection.execute("SELECT paper_id FROM papers").fetchall()
        )
    finally:
        connection.close()
    if not papers or not gold.questions:
        return ()

    rng = random.Random(RANDOM_SEED)
    real: list[tuple[float, float]] = []
    chance: list[tuple[float, float]] = []
    for question in gold.questions:
        expected = set(question.expected_paper_ids)
        neighbors = {
            paper_id
            for paper_id, _weight in load_neighbors(db_path, question.anchor_paper_id)[: params.k]
        }
        real.append(
            (
                len(neighbors & expected) / len(expected) if expected else 0.0,
                len(neighbors) / len(papers),
            )
        )
        pool = [paper_id for paper_id in papers if paper_id != question.anchor_paper_id]
        size = min(params.k, len(pool))
        draws = [set(rng.sample(pool, size)) for _ in range(RANDOM_DRAWS)]
        chance.append(
            (
                sum(len(draw & expected) / len(expected) if expected else 0.0 for draw in draws)
                / len(draws),
                size / len(papers),
            )
        )
    return (
        _stats("Graph-Top-" + str(params.k), real),
        _stats(f"zufällig-{params.k}", chance),
    )


def _stats(label: str, samples: Sequence[tuple[float, float]]) -> CoverageStats:
    """Mittelt Coverage und Selektivität über alle Fragen einer Strategie.

    ``samples`` ist nie leer: :func:`_graph_coverage` steigt vorher aus, wenn es keine Fragen
    oder keine Paper gibt.
    """
    return CoverageStats(
        label=label,
        coverage=sum(coverage for coverage, _ in samples) / len(samples),
        selectivity=sum(selectivity for _, selectivity in samples) / len(samples),
    )


def evaluate_level(
    db_path: str | Path,
    gold: MultiHopGoldSet,
    level: str,
    params: MultiHopParameters = DEFAULT_MULTIHOP_PARAMETERS,
) -> EvaluationReport:
    """Bewertet eine Ebene gegen die Zitations-Labels.

    Das **Ankerpaper wird aus jedem Bündel entfernt**: Es ist per Konstruktion nie ein
    erwartetes Paper, besetzt aber die vordersten Ränge und würde den Kehrwert verzerren
    (docs/adr/0023-multihop-citation-evaluation-phase10.md).

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        gold: Das geladene Gold-Set.
        level: Eine Ebene aus :data:`LEVELS`.
        params: Messparameter.

    Returns:
        Der aggregierte :class:`~research_graphrag.evaluation.metrics.EvaluationReport`;
        für ``graph`` zusätzlich mit Coverage-Kennzahlen und Zufalls-Baseline.

    Raises:
        DomainError: ``invalid_input`` bei unbekannter Ebene; die Modi selbst melden
            ``not_found``/``constraint_violation`` weiter (siehe docs/error-model.md).
    """
    if level not in LEVELS:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            f"Unbekannte Ebene: {level!r}. Erlaubt: {', '.join(LEVELS)}.",
        )
    scores: list[QuestionScore] = []
    for question in gold.questions:
        expected = set(question.expected_paper_ids)
        entries = [
            entry
            for entry in _entries(db_path, question, level, params)
            if entry[0] != question.anchor_paper_id
        ]
        rank, component = first_hit(entries, expected)
        scores.append(
            QuestionScore(
                qid=question.qid, kind=question.kind, first_rank=rank, diagnosis=component
            )
        )
    return EvaluationReport(
        label=level,
        k=params.k,
        scoring=params.scoring,
        scores=tuple(scores),
        coverage=_graph_coverage(db_path, gold, params) if level == GRAPH else (),
    )


def evaluate_multihop(
    db_path: str | Path,
    gold: MultiHopGoldSet,
    params: MultiHopParameters = DEFAULT_MULTIHOP_PARAMETERS,
    levels: Sequence[str] = LEVELS,
) -> dict[str, EvaluationReport]:
    """Führt alle Multi-Hop-Ebenen in einem Durchgang aus.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        gold: Das geladene Gold-Set.
        params: Messparameter.
        levels: Zu messende Ebenen (Teilmenge von :data:`LEVELS`, Reihenfolge bleibt erhalten).

    Returns:
        Berichte je Ebene in der Reihenfolge von ``levels``.

    Raises:
        DomainError: ``invalid_input`` bei unbekannter Ebene.
    """
    return {level: evaluate_level(db_path, gold, level, params) for level in levels}
