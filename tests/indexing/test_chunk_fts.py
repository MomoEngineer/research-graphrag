"""Tests für den FTS5-Phrasenindex über ``chunks`` (Phase 16 / F2, ADR 0044).

Geprüft werden: Aufbau samt ``meta``-Eintrag, Phrase/Präfix/Nähe, Paper-Filter, Gesamtzahl und
Obergrenze, Entschärfung von FTS5-Sonderzeichen (kein ``sqlite3.OperationalError`` an der
Grenze), Rückfall ohne Tokenizer, ein Index ohne Tabelle, Determinismus – und dass die
Infrastruktur keine Suche des Retrievals verändert.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing import chunk_fts
from research_graphrag.indexing.chunk_fts import (
    CHUNK_FTS_VERSION,
    CHUNK_SEARCH_FTS,
    CHUNK_SEARCH_UNAVAILABLE,
    MAX_NEAR_DISTANCE,
    build_chunk_fts,
    search_near,
    search_phrase,
    search_prefix,
)
from research_graphrag.indexing.fts import quote_near, quote_phrase, quote_prefix
from research_graphrag.indexing.tfidf_index import TfidfIndex, build_index
from research_graphrag.limits import MAX_RESULT_COUNT


def _paper(paper_id: str, texts: Sequence[str]) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-p{index + 1}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_title="Related Work" if index else "Introduction",
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


_PAPERS = (
    _paper(
        "aaaa0001",
        [
            "Retrieval-augmented generation grounds answers in documents.",
            "As shown by Lewis et al. (2020), retrieval helps knowledge-intensive tasks.",
        ],
    ),
    _paper(
        "bbbb0002",
        [
            "We compare generation augmented retrieval with RAG baselines.",
            "Müller and Lewis propose a graph retriever; see also Patrick Lewis.",
        ],
    ),
)


def _index(tmp_path: Path) -> Path:
    db = tmp_path / "index.sqlite"
    build_index(list(_PAPERS), db)
    report = build_chunk_fts(db)
    assert report.search == CHUNK_SEARCH_FTS
    assert report.n_chunks == 4
    return db


def test_build_records_version_and_search_in_meta(tmp_path: Path) -> None:
    """Die Tabelle trägt ihre eigene Version; die schema_version des Index bleibt unberührt."""
    db = _index(tmp_path)
    connection = sqlite3.connect(db)
    meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
    connection.close()

    assert meta["chunk_fts_version"] == CHUNK_FTS_VERSION
    assert meta["chunk_search"] == CHUNK_SEARCH_FTS
    assert meta["schema_version"] == "0.6.0"


def test_phrase_matches_the_word_sequence_only(tmp_path: Path) -> None:
    """Eine Phrase trifft die Folge – nicht dieselben Wörter in anderer Reihenfolge."""
    result = search_phrase(_index(tmp_path), "retrieval augmented generation")

    assert result.total_matching == 1
    assert [m.chunk_id for m in result.matches] == ["aaaa0001-p1"]
    match = result.matches[0]
    assert (match.paper_id, match.page_number, match.page_end) == ("aaaa0001", 1, 1)
    assert match.section_title == "Introduction"
    assert "«" in match.snippet and "»" in match.snippet


def test_phrase_ignores_case_and_diacritics(tmp_path: Path) -> None:
    """``remove_diacritics``: „Muller“ findet „Müller“, Großschreibung ist egal."""
    db = _index(tmp_path)

    assert search_phrase(db, "MULLER AND LEWIS").total_matching == 1
    assert search_phrase(db, "müller").total_matching == 1


def test_prefix_matches_word_beginnings(tmp_path: Path) -> None:
    """``retriev`` trifft retrieval und retriever."""
    result = search_prefix(_index(tmp_path), "retriev")

    assert result.total_matching == 4


def test_prefix_rejects_too_short_words(tmp_path: Path) -> None:
    """Ein zu kurzes Präfix würde fast alles treffen → invalid_input."""
    with pytest.raises(DomainError) as excinfo:
        search_prefix(_index(tmp_path), "re")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_near_respects_the_distance(tmp_path: Path) -> None:
    """„patrick“ und „lewis“ stehen direkt nebeneinander, „graph“ und „lewis“ weiter weg."""
    db = _index(tmp_path)

    assert search_near(db, ["patrick", "lewis"], distance=0).total_matching == 1
    assert search_near(db, ["graph", "lewis"], distance=1).total_matching == 0
    assert search_near(db, ["graph", "lewis"], distance=10).total_matching == 1


def test_near_validates_terms_and_distance(tmp_path: Path) -> None:
    """Weniger als zwei Begriffe oder ein Abstand außerhalb der Grenzen → invalid_input."""
    db = _index(tmp_path)
    for terms, distance in ((["lewis"], 5), (["a", "b"], -1), (["a", "b"], MAX_NEAR_DISTANCE + 1)):
        with pytest.raises(DomainError) as excinfo:
            search_near(db, terms, distance=distance)
        assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_paper_filter_and_total_count(tmp_path: Path) -> None:
    """Der Filter schränkt auf Paper ein; ``total_matching`` zählt unabhängig von ``limit``."""
    db = _index(tmp_path)

    everywhere = search_phrase(db, "lewis", limit=1)
    only_b = search_phrase(db, "lewis", paper_ids={"bbbb0002"})

    assert everywhere.total_matching == 2
    assert len(everywhere.matches) == 1
    assert {m.paper_id for m in only_b.matches} == {"bbbb0002"}
    assert search_phrase(db, "lewis", paper_ids=set()).total_matching == 0


def test_limit_follows_the_shared_ceiling(tmp_path: Path) -> None:
    """``limit`` ist durch ``MAX_RESULT_COUNT`` gedeckelt (ADR 0037) und muss > 0 sein."""
    db = _index(tmp_path)
    for limit in (0, MAX_RESULT_COUNT + 1):
        with pytest.raises(DomainError) as excinfo:
            search_phrase(db, "lewis", limit=limit)
        assert excinfo.value.code is ErrorCode.INVALID_INPUT


@pytest.mark.parametrize(
    "hostile",
    [
        '"',
        '""lewis"" OR "',
        "NEAR(lewis retrieval, 2)",
        "lewis*",
        "text: lewis",
        "(lewis OR retrieval) AND NOT graph",
        "^lewis",
        "lewis )",
    ],
)
def test_fts5_syntax_is_neutralised(tmp_path: Path, hostile: str) -> None:
    """FTS5-Operatoren in der Eingabe sind wirkungslos; nie ein OperationalError an der Grenze."""
    db = _index(tmp_path)
    for search in (search_phrase, search_prefix):
        try:
            result = search(db, hostile)
        except DomainError as exc:
            assert exc.code is ErrorCode.INVALID_INPUT
        else:
            assert result.total_matching >= 0
    result = search_near(db, [hostile, "lewis"], distance=5)
    assert result.total_matching >= 0


def test_quoting_produces_literal_fts5_strings() -> None:
    """Die Entschärfung setzt String-Literale; der Abstand ist eine geprüfte Zahl."""
    assert quote_phrase('say "hi"') == '"say ""hi"""'
    assert quote_prefix("retriev") == '"retriev" *'
    assert quote_near(["a", 'b"'], 3) == 'NEAR("a" "b""", 3)'
    for bad in ("", "   "):
        with pytest.raises(DomainError):
            quote_phrase(bad)


def test_empty_query_is_invalid_input(tmp_path: Path) -> None:
    """Leere Eingabe → invalid_input, nicht eine leere Trefferliste."""
    with pytest.raises(DomainError) as excinfo:
        search_phrase(_index(tmp_path), "   ")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_missing_tokenizer_leaves_no_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ohne FTS5/Tokenizer entsteht keine Tabelle; der Befund steht im meta, Anfragen scheitern
    als ``constraint_violation`` statt mit einem sqlite3-Fehler."""
    db = tmp_path / "index.sqlite"
    build_index(list(_PAPERS), db)
    monkeypatch.setattr(chunk_fts, "tokenizer_available", lambda *_a, **_k: False)

    assert build_chunk_fts(db).search == CHUNK_SEARCH_UNAVAILABLE
    with pytest.raises(DomainError) as excinfo:
        search_phrase(db, "lewis")
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_index_without_table_is_constraint_violation(tmp_path: Path) -> None:
    """Ein vor F2 gebauter Index wird erkannt; ein fehlender Index ist ``not_found``."""
    db = tmp_path / "index.sqlite"
    build_index(list(_PAPERS), db)

    with pytest.raises(DomainError) as excinfo:
        search_phrase(db, "lewis")
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION
    for call in (
        lambda: search_phrase(tmp_path / "fehlt.sqlite", "lewis"),
        lambda: build_chunk_fts(tmp_path / "fehlt.sqlite"),
    ):
        with pytest.raises(DomainError) as excinfo:
            call()
        assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_two_builds_answer_identically(tmp_path: Path) -> None:
    """Determinismus: Zwei Bauten liefern dieselben Fundstellen in derselben Reihenfolge."""
    first = search_prefix(_index(tmp_path / "a"), "retriev")
    second = search_prefix(_index(tmp_path / "b"), "retriev")

    assert [m.to_dict() for m in first.matches] == [m.to_dict() for m in second.matches]


def test_infrastructure_does_not_change_retrieval(tmp_path: Path) -> None:
    """Die Tabelle verändert keine Suche: gleiche Treffer mit und ohne Phrasenindex."""
    plain = tmp_path / "plain" / "index.sqlite"
    build_index(list(_PAPERS), plain)
    with_fts = _index(tmp_path)

    for query in ("retrieval augmented generation", "lewis graph"):
        before = [(h.chunk_id, h.score) for h in TfidfIndex.load(plain).search(query, k=4)]
        after = [(h.chunk_id, h.score) for h in TfidfIndex.load(with_fts).search(query, k=4)]
        assert before == after
