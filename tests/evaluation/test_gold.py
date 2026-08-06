"""Tests für das Gold-Set und die mechanische Label-Regel, Phase 7 / A4 + A6."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from scripts.eval_retrieval import main as eval_main

from research_graphrag.evaluation.gold import (
    MECHANICAL_LABELS,
    GoldQuestion,
    GoldSet,
    derive_expected_papers,
    load_gold_set,
    relabel_gold_set,
    save_gold_set,
    unlabelled_questions,
    verify_labels,
)
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.tfidf_index import build_index

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GOLD_SET = _REPO_ROOT / "eval" / "retrieval-gold.json"


def _paper(paper_id: str, texts: Sequence[str]) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index + 1:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
        )
        for index, text in enumerate(texts)
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=len(texts),
        chunks=chunks,
        quality_flags=(),
    )


def _build(tmp_path: Path) -> Path:
    papers = [
        _paper("aaaa0001", ["graph retrieval with communities", "evaluation on faiss benchmarks"]),
        _paper("bbbb0002", ["transformer attention mechanism", "unrelated cooking recipes"]),
    ]
    db = tmp_path / "index.sqlite"
    build_index(papers, db)
    return db


def test_derive_expected_papers_requires_all_terms(tmp_path: Path) -> None:
    """Die Label-Regel verlangt alle Strings in **einem** Chunk."""
    db = _build(tmp_path)

    assert derive_expected_papers(db, ("faiss",)) == ("aaaa0001",)
    assert derive_expected_papers(db, ("faiss", "benchmarks")) == ("aaaa0001",)
    assert derive_expected_papers(db, ("faiss", "attention")) == ()


def test_derive_expected_papers_is_case_insensitive(tmp_path: Path) -> None:
    """Groß-/Kleinschreibung spielt für die Ableitung keine Rolle."""
    assert derive_expected_papers(_build(tmp_path), ("FAISS",)) == ("aaaa0001",)


def test_verify_labels_detects_stale_expectations(tmp_path: Path) -> None:
    """Eingefrorene Labels, die der Index nicht mehr hergibt, werden gemeldet."""
    db = _build(tmp_path)
    good = GoldQuestion("G01", "faiss?", "fact", ("faiss",), ("aaaa0001",))
    stale = GoldQuestion("G02", "faiss?", "fact", ("faiss",), ("bbbb0002",))

    assert verify_labels(db, GoldSet("1.0.0", (good,))) == ()
    findings = verify_labels(db, GoldSet("1.0.0", (good, stale)))
    assert len(findings) == 1
    assert findings[0].startswith("G02")


def test_verify_labels_skips_non_mechanical_sources(tmp_path: Path) -> None:
    """Nur mechanisch abgeleitete Labels sind nachrechenbar – andere werden übersprungen."""
    db = _build(tmp_path)
    judged = GoldQuestion("J01", "faiss?", "fact", ("faiss",), ("bbbb0002",), label_source="judged")

    assert verify_labels(db, GoldSet("1.0.0", (judged,))) == ()


def test_gold_question_defaults_to_the_mechanical_label_source() -> None:
    """Ohne Angabe gilt die nachrechenbare mechanische Regel."""
    question = GoldQuestion("G01", "faiss?", "fact", ("faiss",), ("aaaa0001",))

    assert question.label_source in MECHANICAL_LABELS


def test_versioned_gold_set_is_wellformed() -> None:
    """Das versionierte Gold-Set ist ladbar und vollständig annotiert."""
    gold = load_gold_set(_GOLD_SET)

    assert gold.version
    assert gold.questions
    assert all(question.query and question.match_all for question in gold.questions)
    assert all(question.expected_paper_ids for question in gold.questions)
    assert len({question.qid for question in gold.questions}) == len(gold.questions)
    assert {question.label_source for question in gold.questions} == set(MECHANICAL_LABELS)
    assert "label_rule" in json.loads(_GOLD_SET.read_text(encoding="utf-8"))


def test_relabel_updates_mechanical_labels_from_the_index(tmp_path: Path) -> None:
    """Nach einem Korpuswachstum werden die Labels aus dem Index neu abgeleitet."""
    db = _build(tmp_path)
    stale = GoldQuestion("G01", "faiss?", "fact", ("faiss",), ("veraltet",))

    updated = relabel_gold_set(db, GoldSet("1.0.0", (stale,)), version="1.1.0")

    assert updated.version == "1.1.0"
    assert updated.questions[0].expected_paper_ids == ("aaaa0001",)
    assert verify_labels(db, updated) == ()


def test_relabel_leaves_non_mechanical_sources_untouched(tmp_path: Path) -> None:
    """Was nicht nachrechenbar ist, darf auch nicht überschrieben werden."""
    db = _build(tmp_path)
    judged = GoldQuestion("J01", "faiss?", "fact", ("faiss",), ("bbbb0002",), label_source="judged")

    updated = relabel_gold_set(db, GoldSet("1.0.0", (judged,)), version="1.1.0")

    assert updated.questions[0].expected_paper_ids == ("bbbb0002",)


def test_relabel_keeps_question_order_and_wording(tmp_path: Path) -> None:
    """Die Fragen selbst bleiben unverändert – nur die Ziele werden neu bestimmt."""
    db = _build(tmp_path)
    gold = GoldSet(
        "1.0.0",
        (
            GoldQuestion("G02", "attention?", "concept", ("attention",), ()),
            GoldQuestion("G01", "faiss?", "fact", ("faiss",), ()),
        ),
    )

    updated = relabel_gold_set(db, gold, version="1.1.0")

    assert [q.qid for q in updated.questions] == ["G02", "G01"]
    assert [q.query for q in updated.questions] == ["attention?", "faiss?"]
    assert [q.kind for q in updated.questions] == ["concept", "fact"]


def test_relabel_reports_questions_without_any_target(tmp_path: Path) -> None:
    """Eine Frage, die im Korpus kein Ziel mehr hat, ist ein Befund – keine leere Zeile."""
    db = _build(tmp_path)
    orphan = GoldQuestion("G09", "quantum?", "fact", ("quantum",), ("aaaa0001",))

    updated = relabel_gold_set(db, GoldSet("1.0.0", (orphan,)), version="1.1.0")

    assert updated.questions[0].expected_paper_ids == ()
    assert unlabelled_questions(updated) == ("G09",)


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """Ein geschriebenes Gold-Set lässt sich unverändert zurücklesen."""
    db = _build(tmp_path)
    gold = relabel_gold_set(
        db,
        GoldSet("1.0.0", (GoldQuestion("G01", "faiss?", "fact", ("faiss",), ()),)),
        version="1.1.0",
    )
    path = tmp_path / "gold.json"

    save_gold_set(db, gold, path, note="Test")

    reloaded = load_gold_set(path)
    assert reloaded.version == gold.version
    assert reloaded.questions == gold.questions


def test_saved_gold_set_records_the_corpus_it_was_derived_from(tmp_path: Path) -> None:
    """Ohne Korpus-Angabe wäre nicht nachvollziehbar, wogegen die Labels abgeleitet wurden."""
    db = _build(tmp_path)
    gold = relabel_gold_set(
        db,
        GoldSet("1.0.0", (GoldQuestion("G01", "faiss?", "fact", ("faiss",), ()),)),
        version="1.1.0",
    )
    path = tmp_path / "gold.json"

    save_gold_set(db, gold, path, note="Nachweis")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["corpus"] == {"papers": 2, "chunks": 4}
    assert payload["updated_for"] == "Nachweis"
    assert payload["label_rule"]
    assert b"\r\n" not in path.read_bytes()


def test_cli_write_gold_relabels_the_file(tmp_path: Path) -> None:
    """`--write-gold` schreibt die neu abgeleiteten Labels und meldet den Umfang."""
    db = _build(tmp_path)
    path = tmp_path / "gold.json"
    save_gold_set(
        db,
        GoldSet("1.0.0", (GoldQuestion("G01", "faiss?", "fact", ("faiss",), ("veraltet",)),)),
        path,
        note="Ausgangsstand",
    )

    exit_code = eval_main(
        ["--index", str(db), "--gold", str(path), "--write-gold", "--gold-version", "1.1.0"]
    )

    assert exit_code == 0
    reloaded = load_gold_set(path)
    assert reloaded.version == "1.1.0"
    assert reloaded.questions[0].expected_paper_ids == ("aaaa0001",)
    assert verify_labels(db, reloaded) == ()


def test_cli_write_gold_signals_questions_without_targets(tmp_path: Path) -> None:
    """Eine Frage ohne Ziel ist ein Befund: Exit-Code 1 statt stiller Nullmessung."""
    db = _build(tmp_path)
    path = tmp_path / "gold.json"
    save_gold_set(
        db,
        GoldSet("1.0.0", (GoldQuestion("G09", "quantum?", "fact", ("quantum",), ()),)),
        path,
        note="Ausgangsstand",
    )

    assert eval_main(["--index", str(db), "--gold", str(path), "--write-gold"]) == 1


def test_saved_gold_set_keeps_a_non_default_label_source(tmp_path: Path) -> None:
    """Eine abweichende Label-Quelle überlebt den Round-Trip; die Vorgabe bleibt implizit."""
    db = _build(tmp_path)
    path = tmp_path / "gold.json"
    gold = GoldSet(
        "1.0.0",
        (
            GoldQuestion("J01", "faiss?", "fact", ("faiss",), ("bbbb0002",), label_source="judged"),
            GoldQuestion("G01", "faiss?", "fact", ("faiss",), ("aaaa0001",)),
        ),
    )

    save_gold_set(db, gold, path, note="Gemischte Quellen")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["questions"][0]["label_source"] == "judged"
    assert "label_source" not in payload["questions"][1]
    assert load_gold_set(path).questions == gold.questions
