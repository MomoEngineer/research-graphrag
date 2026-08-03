"""Tests für die Multi-Hop-Evaluation gegen den Zitationsgraphen (Phase 10 / V3, ADR 0023)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.evaluation.multihop import (
    GRAPH,
    LEVELS,
    MULTIHOP_GOLD_VERSION,
    MultiHopGoldSet,
    MultiHopParameters,
    MultiHopQuestion,
    RecallBounds,
    build_multihop_gold,
    derive_questions,
    evaluate_level,
    evaluate_multihop,
    is_reference_section,
    load_multihop_gold,
    recall_bounds,
    save_multihop_gold,
    verify_questions,
)
from research_graphrag.evaluation.report import render_multihop_report
from research_graphrag.extraction.model import SECTION_KIND_BODY, SECTION_KIND_REFERENCES, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.citation_graph import build_citation_graph
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.retrieval.basic import search_basic

_TITLE_A = "Graph Retrieval Augmented Generation for Scientific Corpora"
_TITLE_B = "Neural Ranking Models for Passage Retrieval Benchmarks"
_TITLE_C = "Community Detection in Large Citation Networks"
_TITLE_D = "Prompt Engineering Patterns for Code Generation Tasks"
_TITLE_E = "Short Note"
_ARXIV_A = "2501.01234"

_PARAMS = MultiHopParameters()


def _paper(
    paper_id: str,
    title: str,
    *,
    body: str,
    extra_body: Sequence[str] = (),
    identifiers: dict[str, str] | None = None,
    references: Sequence[str] = (),
) -> CanonicalPaper:
    """Baut ein Canonical-Paper mit Body- und (optionalem) Referenzabschnitt."""
    sections = [
        Section(
            section_id="s-body",
            title="Introduction",
            kind=SECTION_KIND_BODY,
            level=1,
            page_number=1,
            order=0,
        )
    ]
    chunks = [
        Chunk(
            chunk_id=f"{paper_id}-c{index:04d}",
            paper_id=paper_id,
            page_number=1,
            text=text,
            char_count=len(text),
            section_id="s-body",
            section_title="Introduction",
        )
        for index, text in enumerate([body, *extra_body], start=1)
    ]
    if references:
        sections.append(
            Section(
                section_id="s-refs",
                title="References",
                kind=SECTION_KIND_REFERENCES,
                level=1,
                page_number=2,
                order=1,
            )
        )
        for index, entry in enumerate(references, start=len(chunks) + 1):
            chunks.append(
                Chunk(
                    chunk_id=f"{paper_id}-c{index:04d}",
                    paper_id=paper_id,
                    page_number=2,
                    text=entry,
                    char_count=len(entry),
                    section_id="s-refs",
                    section_title="References",
                )
            )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{quote(title)}.pdf",
        source_sha256="0" * 64,
        n_pages=2 if references else 1,
        chunks=tuple(chunks),
        quality_flags=(),
        sections=tuple(sections),
        identifiers=identifiers or {},
    )


def _corpus() -> list[CanonicalPaper]:
    """Fünf Paper: ein Anker mit drei Zitierenden, ein Randfall ohne Bibliografie."""
    return [
        _paper(
            "aaaa0001",
            _TITLE_A,
            body=_TITLE_A,  # der Titel steht auch im eigenen Text -> Anker ist Top-1
            extra_body=[
                f"arXiv:{_ARXIV_A} graph retrieval augmented generation over scientific "
                "corpora with provenance"
            ],
            identifiers={"arxiv": _ARXIV_A},
        ),
        _paper(
            "bbbb0001",
            _TITLE_B,
            body="neural ranking models rerank passages for retrieval benchmarks",
            references=[f"{_TITLE_A}. Proceedings, 2026."],
        ),
        _paper(
            "bbbb0002",
            _TITLE_C,
            body="graph retrieval augmented generation and community detection in corpora",
            references=[f"{_TITLE_A}. Proceedings, 2026.", f"{_TITLE_B}. Journal, 2025."],
        ),
        _paper(
            "bbbb0003",
            _TITLE_D,
            body="prompt engineering patterns guide code generation tasks",
            references=[f"{_TITLE_A}. Proceedings, 2026."],
        ),
        _paper("cccc0001", _TITLE_E, body="a very short standalone note without any bibliography"),
    ]


def _build(tmp_path: Path, *, citations: bool = True) -> Path:
    """Baut den Fixture-Index (optional ohne Zitationsgraph, für den Fehlerpfad)."""
    papers = _corpus()
    db = tmp_path / "index" / "index.sqlite"
    build_index(papers, db)
    build_graph(papers, db)
    if citations:
        build_citation_graph(papers, db)
    return db


def _gold(tmp_path: Path) -> tuple[Path, MultiHopGoldSet]:
    db = _build(tmp_path)
    return db, build_multihop_gold(db, _PARAMS)


# --------------------------------------------------------------------- Ableitung


def test_questions_are_derived_deterministically_from_the_graph(tmp_path: Path) -> None:
    """Anker sind genau die Paper mit genug Zitierenden – Labels sind die Zitierenden."""
    db = _build(tmp_path)

    questions = derive_questions(db, _PARAMS)

    assert [question.qid for question in questions] == ["C01"]
    question = questions[0]
    assert question.anchor_paper_id == "aaaa0001"
    assert question.anchor_title == _TITLE_A
    assert question.expected_paper_ids == ("bbbb0001", "bbbb0002", "bbbb0003")
    assert question.label_source == "citation_graph"
    assert question.topic_terms  # aus dem Chunk-Text abgeleitet, nicht kuratiert


def test_a_second_run_derives_the_same_questions(tmp_path: Path) -> None:
    """Determinismus: dieselbe Datenlage ergibt dasselbe Gold-Set."""
    db = _build(tmp_path)

    assert derive_questions(db, _PARAMS) == derive_questions(db, _PARAMS)


def test_the_threshold_keeps_thinly_cited_papers_out(tmp_path: Path) -> None:
    """``min_citing`` steuert die Ankermenge – mit 1 kommt das einfach zitierte Paper dazu."""
    db = _build(tmp_path)

    anchors = {
        question.anchor_paper_id
        for question in derive_questions(db, MultiHopParameters(min_citing=1))
    }

    assert anchors == {"aaaa0001", "bbbb0001"}


def test_queries_share_one_frame_and_differ_only_in_the_payload(tmp_path: Path) -> None:
    """Beide Anfrageformen isolieren genau einen Unterschied: die Nutzlast."""
    _db, gold = _gold(tmp_path)
    question = gold.questions[0]

    assert question.query_title == f"Which papers build on {_TITLE_A}?"
    assert question.query_topic == f"Which papers build on {', '.join(question.topic_terms)}?"


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (3, "zitiert 3-4"),
        (4, "zitiert 3-4"),
        (5, "zitiert 5-9"),
        (9, "zitiert 5-9"),
        (10, "zitiert 10+"),
    ],
)
def test_questions_are_grouped_by_citation_frequency(count: int, expected: str) -> None:
    """Die Gruppen beantworten, ob ein Verfahren nur stark zitierte Hubs findet."""
    question = MultiHopQuestion(
        qid="C01",
        anchor_paper_id="aaaa0001",
        anchor_title=_TITLE_A,
        topic_terms=("graph",),
        expected_paper_ids=tuple(f"p{index:04d}" for index in range(count)),
    )

    assert question.kind == expected


# --------------------------------------------------------------------- Persistenz


def test_gold_set_survives_a_round_trip(tmp_path: Path) -> None:
    """Die Datei ist die Single Source of Truth – Schreiben und Lesen sind verlustfrei."""
    db, gold = _gold(tmp_path)
    path = tmp_path / "eval" / "citation-gold.json"

    save_multihop_gold(gold, path, _PARAMS)

    assert load_multihop_gold(path) == gold
    assert gold.version == MULTIHOP_GOLD_VERSION
    payload = path.read_text(encoding="utf-8")
    assert "label_rule" in payload and "query_frame" in payload
    assert str(db)  # der Index selbst wird nicht in die Datei geschrieben


def test_a_missing_gold_set_is_a_domain_error(tmp_path: Path) -> None:
    """Kein stiller Lauf gegen nichts."""
    with pytest.raises(DomainError) as excinfo:
        load_multihop_gold(tmp_path / "fehlt.json")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


# --------------------------------------------------------------------- Verifikation


def test_unchanged_labels_verify_cleanly(tmp_path: Path) -> None:
    """Das eingefrorene Gold-Set ist gegen den Index nachrechenbar."""
    db, gold = _gold(tmp_path)

    assert verify_questions(db, gold, _PARAMS) == ()


@pytest.mark.parametrize(
    ("field", "value", "marker"),
    [
        ("expected_paper_ids", ("bbbb0001",), "erwartet"),
        ("anchor_title", "Ein anderer Titel", "Titel"),
        ("topic_terms", ("erfunden",), "Themen-Terme"),
        ("label_source", "mechanical", "Label-Quelle"),
        ("anchor_paper_id", "bbbb0001", "Anker"),
    ],
)
def test_tampered_labels_are_reported(
    tmp_path: Path, field: str, value: object, marker: str
) -> None:
    """Jede aus dem Index stammende Angabe wird nachgerechnet, nicht nur die Ziel-Paper."""
    db, gold = _gold(tmp_path)
    tampered = MultiHopGoldSet(
        version=gold.version,
        questions=(
            MultiHopQuestion(
                **{
                    **{
                        "qid": gold.questions[0].qid,
                        "anchor_paper_id": gold.questions[0].anchor_paper_id,
                        "anchor_title": gold.questions[0].anchor_title,
                        "topic_terms": gold.questions[0].topic_terms,
                        "expected_paper_ids": gold.questions[0].expected_paper_ids,
                        "label_source": gold.questions[0].label_source,
                    },
                    field: value,
                }
            ),
        ),
    )

    findings = verify_questions(db, tampered, _PARAMS)

    assert any(marker in finding for finding in findings)


def test_missing_and_surplus_questions_are_reported(tmp_path: Path) -> None:
    """Beide Richtungen fallen auf: eingefroren ohne Ableitung und umgekehrt."""
    db, gold = _gold(tmp_path)
    surplus = MultiHopQuestion(
        qid="C99",
        anchor_paper_id="zzzz9999",
        anchor_title="Erfundenes Paper ohne jede Entsprechung",
        topic_terms=("erfunden",),
        expected_paper_ids=("bbbb0001",),
    )

    only_surplus = verify_questions(db, MultiHopGoldSet(gold.version, (surplus,)), _PARAMS)

    assert any("nicht mehr ableitbar" in finding for finding in only_surplus)
    assert any("nicht eingefroren" in finding for finding in only_surplus)


# --------------------------------------------------------------------- Bewertung


def test_the_anchor_paper_is_removed_from_every_bundle(tmp_path: Path) -> None:
    """Der Anker kann nie ein erwartetes Paper sein – er darf keinen Rang verbrauchen."""
    db, gold = _gold(tmp_path)
    question = gold.questions[0]

    raw = search_basic(db, question.query_title, _PARAMS.k)
    assert raw.citations[0].paper_id == question.anchor_paper_id  # ohne Filter Rang 1

    report = evaluate_level(db, gold, "basic_title", _PARAMS)

    assert report.scores[0].first_rank == 1  # der Zitierende rückt auf Rang 1 vor


def test_hits_from_a_bibliography_are_marked_as_such(tmp_path: Path) -> None:
    """Der lexikalische Kurzschluss über die Bibliografie wird ausgewiesen, nicht versteckt."""
    db, gold = _gold(tmp_path)

    report = evaluate_level(db, gold, "basic_title", _PARAMS)

    assert report.scores[0].diagnosis == "chunk:ref"


def test_the_topic_form_reports_body_hits_as_such(tmp_path: Path) -> None:
    """Die Diagnose folgt dem Abschnitt des Belegs, nicht der Anfrageform."""
    db, gold = _gold(tmp_path)
    body_only = MultiHopGoldSet(
        version=gold.version,
        questions=(
            MultiHopQuestion(
                qid="C01",
                anchor_paper_id="aaaa0001",
                anchor_title=_TITLE_A,
                topic_terms=("rerank", "passages", "benchmarks"),
                expected_paper_ids=("bbbb0001",),
            ),
        ),
    )

    report = evaluate_level(db, body_only, "basic_topic", _PARAMS)

    assert report.scores[0].diagnosis == "chunk:body"


def test_the_structural_level_needs_no_query(tmp_path: Path) -> None:
    """Die Graph-Ebene bewertet die Nachbarn des Ankers, nicht eine Textanfrage."""
    db, gold = _gold(tmp_path)

    report = evaluate_level(db, gold, GRAPH, _PARAMS)

    assert report.scores[0].diagnosis in (None, "neighbor")
    labels = [stats.label for stats in report.coverage]
    assert labels == [f"Graph-Top-{_PARAMS.k}", f"zufällig-{_PARAMS.k}"]


def test_only_the_structural_level_carries_coverage(tmp_path: Path) -> None:
    """Coverage ist eine Aussage über eine Auswahl – die Textebenen treffen keine."""
    db, gold = _gold(tmp_path)

    assert evaluate_level(db, gold, "local_title", _PARAMS).coverage == ()


def test_all_levels_are_measured_in_report_order(tmp_path: Path) -> None:
    """Ein Durchgang liefert jede Ebene genau einmal, in Berichtsreihenfolge."""
    db, gold = _gold(tmp_path)

    reports = evaluate_multihop(db, gold, _PARAMS)

    assert tuple(reports) == LEVELS
    assert all(report.label == level for level, report in reports.items())


def test_evaluation_is_deterministic(tmp_path: Path) -> None:
    """Zwei Läufe liefern denselben Rang je Frage."""
    db, gold = _gold(tmp_path)

    first = evaluate_level(db, gold, "local_topic", _PARAMS)
    second = evaluate_level(db, gold, "local_topic", _PARAMS)

    assert [score.first_rank for score in first.scores] == [
        score.first_rank for score in second.scores
    ]


def test_an_unknown_level_is_invalid_input(tmp_path: Path) -> None:
    """Ein Tippfehler wird gemeldet, nicht still übergangen."""
    db, gold = _gold(tmp_path)

    with pytest.raises(DomainError) as excinfo:
        evaluate_level(db, gold, "globaal", _PARAMS)

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_parameters_are_serialised_for_the_fingerprint() -> None:
    """Eigene Parameter statt einer Erweiterung von ``RunParameters`` – sie gehen in den
    Fingerprint der **eigenen** Baseline ein."""
    payload = MultiHopParameters().to_dict()

    assert set(payload) == {"k", "fan_out", "seeds", "min_citing", "scoring"}
    assert payload["min_citing"] == 3


def test_a_fan_out_neighbour_without_evidence_is_still_reported(tmp_path: Path) -> None:
    """Ein Graph-Nachbar ohne passenden Chunk bleibt Beleg-los – die Diagnose behauptet nichts."""
    seed_paper = _paper(
        "dddd0001",
        "Anker mit einem sehr eindeutigen Suchbegriff im Text",
        body="alpha alpha alpha",
        extra_body=["beta gamma delta epsilon zeta"],
    )
    neighbour = _paper(
        "dddd0002",
        "Nachbarpaper ohne den eindeutigen Suchbegriff im Text",
        body="beta gamma delta epsilon zeta",
    )
    db = tmp_path / "index" / "index.sqlite"
    build_index([seed_paper, neighbour], db)
    build_graph([seed_paper, neighbour], db)
    gold = MultiHopGoldSet(
        version="test-1.0.0",
        questions=(
            MultiHopQuestion(
                qid="C01",
                anchor_paper_id="zzzz9999",  # nicht im Index: der Anker spielt hier keine Rolle
                anchor_title="Egal",
                topic_terms=("alpha",),
                expected_paper_ids=("dddd0002",),
            ),
        ),
    )

    report = evaluate_level(db, gold, "local_topic", _PARAMS)

    assert report.scores[0].diagnosis == "fan_out"


# --------------------------------------------------------------------- Fehlerpfade


def test_a_missing_index_is_a_domain_error(tmp_path: Path) -> None:
    """Ohne Index gibt es keine Ableitung."""
    with pytest.raises(DomainError) as excinfo:
        derive_questions(tmp_path / "fehlt.sqlite", _PARAMS)

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_an_index_without_a_citation_graph_is_a_constraint_violation(tmp_path: Path) -> None:
    """Die Messung braucht ``citation_edges`` – ein leerer Bericht wäre irreführend."""
    db = _build(tmp_path, citations=False)

    with pytest.raises(DomainError) as excinfo:
        derive_questions(db, _PARAMS)

    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


# --------------------------------------------------------------------- Recall-Schranken


def test_reference_sections_are_recognised_from_the_section_title() -> None:
    """Dieselbe Heuristik wie bei der Extraktion – ohne Zugriff auf die Canonical-Dateien."""
    assert is_reference_section("References")
    assert is_reference_section("BIBLIOGRAPHY")
    assert not is_reference_section("Introduction")
    assert not is_reference_section("")


def test_recall_bounds_name_the_structurally_unreachable_papers(tmp_path: Path) -> None:
    """Die Schranken sind eine obere Grenze der Vollständigkeit, kein gemessener Recall."""
    db = _build(tmp_path)

    bounds = recall_bounds(db)

    assert bounds.n_papers == 5
    assert "cccc0001" in bounds.without_reference_section  # kann nicht zitieren
    assert "cccc0001" in bounds.without_title_key  # Titel zu kurz
    assert "cccc0001" in bounds.without_identifier_key
    assert bounds.unreachable_targets == ("cccc0001",)
    assert "aaaa0001" not in bounds.without_identifier_key  # arXiv-ID auf der Titelseite belegt


def test_unreachable_targets_are_the_intersection() -> None:
    """Ein Paper ist erst unerreichbar, wenn **beide** Schlüssel fehlen."""
    bounds = RecallBounds(
        n_papers=3,
        without_reference_section=(),
        without_title_key=("a", "b"),
        without_identifier_key=("b", "c"),
    )

    assert bounds.unreachable_targets == ("b",)


# --------------------------------------------------------------------- Bericht


def test_the_report_names_its_reference_points(tmp_path: Path) -> None:
    """Ohne Oberwert, Zufalls-Baseline und Schranken sind die Zahlen nicht lesbar."""
    db, gold = _gold(tmp_path)
    reports = evaluate_multihop(db, gold, _PARAMS)

    text = render_multihop_report(reports, gold, recall_bounds(db))

    assert "get_citations" in text
    assert "zufällig-" in text and "Lift" in text
    assert "obere Schranke" in text
    assert "Aussagegrenze" in text
    assert "Zitationshäufigkeit" in text


def test_the_report_works_without_recall_bounds(tmp_path: Path) -> None:
    """Die Schranken sind eine Zugabe, kein Pflichtbestandteil der Darstellung."""
    db, gold = _gold(tmp_path)

    text = render_multihop_report(evaluate_multihop(db, gold, _PARAMS), gold)

    assert "obere Schranke" not in text
    assert "Aussagegrenze" in text


def test_index_without_papers_yields_no_coverage(tmp_path: Path) -> None:
    """Ein leerer Bestand liefert keine Coverage statt einer Division durch null."""
    db = tmp_path / "index" / "index.sqlite"
    build_index(_corpus(), db)
    build_citation_graph(_corpus(), db)
    connection = sqlite3.connect(str(db))
    connection.execute("DELETE FROM papers")
    connection.commit()
    connection.close()

    report = evaluate_level(db, MultiHopGoldSet("test-1.0.0", ()), GRAPH, _PARAMS)

    assert report.coverage == ()
