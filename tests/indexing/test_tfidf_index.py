"""Tests für den TF-IDF/SQLite-Index (AP2, Offline-Hybrid)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sklearn.feature_extraction.text import TfidfVectorizer

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.fusion import RRF_K
from research_graphrag.indexing.tfidf_index import TfidfIndex, _snippet, build_index


def _paper(paper_id: str, texts: Sequence[str]) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-p{index + 1}",
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


def test_build_and_search_returns_provenance(tmp_path: Path) -> None:
    """Ein Treffer trägt die korrekte Seiten-/Paper-Provenienz."""
    paper = _paper("aaaa1111", ["transformer attention mechanism", "graph message passing"])
    db = tmp_path / "index" / "index.sqlite"

    n = build_index([paper], db)
    index = TfidfIndex.load(db)
    hits = index.search("attention", k=3)

    assert n == 2
    assert index.size == 2
    assert hits[0].chunk_id == "aaaa1111-p1"
    assert hits[0].page_number == 1
    assert hits[0].paper_id == "aaaa1111"
    assert hits[0].score > 0.0
    assert hits[0].source_uri == "file:///aaaa1111.pdf"


def test_search_ranks_relevant_chunk_first(tmp_path: Path) -> None:
    """Der thematisch passende Chunk steht vorn."""
    paper = _paper("bbbb2222", ["clustering of citation networks", "reinforcement learning agents"])
    db = tmp_path / "index.sqlite"
    build_index([paper], db)

    hits = TfidfIndex.load(db).search("reinforcement learning", k=2)

    assert hits[0].page_number == 2


def test_no_match_returns_empty(tmp_path: Path) -> None:
    """Ohne Vokabular-Überschneidung gibt es keine Treffer."""
    paper = _paper("cccc3333", ["semantic parsing of queries"])
    db = tmp_path / "index.sqlite"
    build_index([paper], db)

    assert TfidfIndex.load(db).search("banana smoothie", k=5) == []


def test_build_without_text_raises_invalid_input(tmp_path: Path) -> None:
    """Nur leere Chunks -> invalid_input."""
    paper = _paper("dddd4444", ["", "   "])
    with pytest.raises(DomainError) as excinfo:
        build_index([paper], tmp_path / "index.sqlite")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_empty_query_raises_invalid_input(tmp_path: Path) -> None:
    """Leere Anfrage -> invalid_input."""
    paper = _paper("eeee5555", ["content for the index"])
    db = tmp_path / "index.sqlite"
    build_index([paper], db)
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db).search("  ", k=3)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_load_missing_db_raises_not_found(tmp_path: Path) -> None:
    """Fehlende Index-Datei -> not_found."""
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(tmp_path / "absent.sqlite")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_reindex_is_deterministic(tmp_path: Path) -> None:
    """Zweimaliger Bau + Suche liefert identische Top-Treffer (Determinismus)."""
    paper = _paper("ffff6666", ["alpha beta gamma", "delta epsilon zeta"])
    db = tmp_path / "index.sqlite"

    build_index([paper], db)
    first = TfidfIndex.load(db).search("alpha", k=1)
    build_index([paper], db)
    second = TfidfIndex.load(db).search("alpha", k=1)

    assert first[0].chunk_id == second[0].chunk_id
    assert first[0].score == pytest.approx(second[0].score)


def test_multi_paper_index_and_k_limit(tmp_path: Path) -> None:
    """Zwei Papers werden gemeinsam indexiert; k begrenzt die Trefferzahl."""
    p1 = _paper("aaaa0001", ["neural network training", "gradient descent optimization"])
    p2 = _paper("bbbb0002", ["bayesian inference methods", "gradient boosting trees"])
    db = tmp_path / "index.sqlite"

    n = build_index([p1, p2], db)
    index = TfidfIndex.load(db)
    hits = index.search("gradient", k=1)

    assert n == 4
    assert index.size == 4
    assert len(hits) == 1
    assert "gradient" in hits[0].snippet.lower()


def test_search_snippet_is_truncated(tmp_path: Path) -> None:
    """Lange Chunk-Texte werden im Snippet auf das Limit gekürzt."""
    long_text = "alpha " + "lorem ipsum dolor sit amet consectetur " * 20
    db = tmp_path / "index.sqlite"
    build_index([_paper("cccc0003", [long_text])], db)

    hit = TfidfIndex.load(db).search("alpha", k=1)[0]

    assert len(hit.snippet) <= 200
    assert hit.snippet.endswith("…")


def test_constraint_violation_when_index_has_no_chunks(tmp_path: Path) -> None:
    """Ein Index ohne Chunks (manuell geleert) -> constraint_violation."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("dddd0004", ["content to be removed"])], db)
    connection = sqlite3.connect(str(db))
    connection.execute("DELETE FROM chunks")
    connection.commit()
    connection.close()

    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db)
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


@given(st.text(), st.integers(min_value=1, max_value=60))
def test_snippet_never_exceeds_limit(text: str, limit: int) -> None:
    """Eigenschaft: _snippet ist einzeilig und überschreitet das Limit nie."""
    snippet = _snippet(text, limit)
    assert len(snippet) <= limit
    assert "\n" not in snippet


def test_non_positive_k_raises_invalid_input(tmp_path: Path) -> None:
    """k <= 0 -> invalid_input."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("iiii9999", ["content for the index"])], db)
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db).search("content", k=0)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_k_above_max_result_count_raises_invalid_input(tmp_path: Path) -> None:
    """k > MAX_RESULT_COUNT -> invalid_input (ADR 0037)."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("iiii9999", ["content for the index"])], db)
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db).search("content", k=51)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def _sectioned_paper(paper_id: str, texts: Sequence[str], section: str) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index + 1:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_title=section,
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


def test_section_title_is_persisted_and_returned(tmp_path: Path) -> None:
    """Die Abschnitts-Provenienz (section_title) überlebt Persistenz und Laden (Schema 0.2.0)."""
    db = tmp_path / "index.sqlite"
    build_index([_sectioned_paper("aaaa0001", ["transformer attention mechanism"], "Methoden")], db)

    hit = TfidfIndex.load(db).search("attention", k=1)[0]

    assert hit.section_title == "Methoden"


def test_search_paper_ids_filter_restricts_results(tmp_path: Path) -> None:
    """Der paper_ids-Filter beschränkt die Treffer auf die erlaubten Paper."""
    p1 = _paper("aaaa0001", ["gradient descent optimization", "neural network training"])
    p2 = _paper("bbbb0002", ["gradient boosting trees", "bayesian inference methods"])
    db = tmp_path / "index.sqlite"
    build_index([p1, p2], db)

    hits = TfidfIndex.load(db).search("gradient", k=5, paper_ids={"bbbb0002"})

    assert hits
    assert all(hit.paper_id == "bbbb0002" for hit in hits)


def test_neighbors_of_chunk_excludes_seed(tmp_path: Path) -> None:
    """Die Chunk-Nachbarschaft enthält den Ausgangs-Chunk nicht und rankt Ähnliches vorn."""
    paper = _paper(
        "aaaa0001",
        ["transformer attention encoder", "transformer attention decoder", "unrelated cooking"],
    )
    db = tmp_path / "index.sqlite"
    build_index([paper], db)

    neighbors = TfidfIndex.load(db).neighbors_of_chunk("aaaa0001-p1", k=5)

    chunk_ids = [hit.chunk_id for hit in neighbors]
    assert "aaaa0001-p1" not in chunk_ids
    assert "aaaa0001-p2" in chunk_ids  # thematisch ähnlichster Nachbar


def test_neighbors_of_chunk_unknown_chunk_raises_not_found(tmp_path: Path) -> None:
    """Eine unbekannte chunk_id -> not_found."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("aaaa0001", ["transformer attention encoder"])], db)
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db).neighbors_of_chunk("does-not-exist", k=3)
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_neighbors_of_chunk_non_positive_k_raises_invalid_input(tmp_path: Path) -> None:
    """k <= 0 -> invalid_input."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("aaaa0001", ["transformer attention encoder"])], db)
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db).neighbors_of_chunk("aaaa0001-p1", k=0)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_neighbors_of_chunk_k_above_max_result_count_raises_invalid_input(tmp_path: Path) -> None:
    """k > MAX_RESULT_COUNT -> invalid_input (ADR 0037)."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("aaaa0001", ["transformer attention encoder"])], db)
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db).neighbors_of_chunk("aaaa0001-p1", k=51)
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


# --------------------------------------------------------------------------------------
# Hybrid-Wertung (BM25 + TF-IDF), siehe docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md
# --------------------------------------------------------------------------------------


def _hybrid_corpus(tmp_path: Path) -> Path:
    papers = [
        _paper("aaaa0001", ["transformer attention mechanism", "graph neural message passing"]),
        _paper("bbbb0002", ["retrieval augmented generation with faiss", "evaluation protocol"]),
        _paper("cccc0003", ["knowledge graph construction", "attention attention attention"]),
    ]
    db = tmp_path / "index.sqlite"
    build_index(papers, db)
    return db


def test_tfidf_space_matches_the_previous_vectorizer(tmp_path: Path) -> None:
    """Regressionsbeweis: CountVectorizer + TfidfTransformer == früherer TfidfVectorizer."""
    texts = [
        "transformer attention mechanism",
        "graph neural message passing",
        "retrieval augmented generation with faiss",
        "evaluation protocol",
        "knowledge graph construction",
        "attention attention attention",
    ]
    index = TfidfIndex.load(_hybrid_corpus(tmp_path))

    reference = TfidfVectorizer()
    expected = reference.fit_transform(texts)
    expected_query = reference.transform(["attention mechanism"])
    actual_query = index._transformer.transform(
        index._vectorizer.transform(["attention mechanism"])
    )

    assert index._matrix.toarray() == pytest.approx(expected.toarray())
    assert actual_query.toarray() == pytest.approx(expected_query.toarray())


def test_tfidf_scoring_returns_cosine_values(tmp_path: Path) -> None:
    """Mit ``scoring='tfidf'`` ist ``score`` weiterhin der Kosinus (Rückwärtskompatibilität)."""
    hits = TfidfIndex.load(_hybrid_corpus(tmp_path)).search("attention", k=3, scoring="tfidf")

    assert hits
    assert all(0.0 < hit.score <= 1.0 for hit in hits)
    assert all(hit.score == hit.score_tfidf for hit in hits)
    assert hits == sorted(hits, key=lambda hit: -hit.score)


def test_bm25_scoring_returns_bm25_values(tmp_path: Path) -> None:
    """Mit ``scoring='bm25'`` ist ``score`` der BM25-Wert."""
    hits = TfidfIndex.load(_hybrid_corpus(tmp_path)).search("attention", k=3, scoring="bm25")

    assert hits
    assert all(hit.score == hit.score_bm25 for hit in hits)
    assert all(hit.score > 0.0 for hit in hits)


def test_hybrid_reports_both_component_scores(tmp_path: Path) -> None:
    """Die Standard-Wertung liefert den Fusionswert plus beide Rohwerte."""
    hits = TfidfIndex.load(_hybrid_corpus(tmp_path)).search("attention", k=3)

    assert hits
    top = hits[0]
    assert top.score_tfidf > 0.0
    assert top.score_bm25 > 0.0
    assert 0.0 < top.score <= 2.0 / (RRF_K + 1)


def test_hybrid_prefers_agreement_of_both_rankings(tmp_path: Path) -> None:
    """Ein Chunk, den beide Verfahren vorn sehen, gewinnt gegen einen einseitigen Favoriten."""
    index = TfidfIndex.load(_hybrid_corpus(tmp_path))

    hybrid_top = index.search("attention mechanism", k=1)[0]
    tfidf_top = index.search("attention mechanism", k=1, scoring="tfidf")[0]
    bm25_top = index.search("attention mechanism", k=1, scoring="bm25")[0]

    assert hybrid_top.chunk_id in {tfidf_top.chunk_id, bm25_top.chunk_id}


def test_hybrid_no_match_stays_empty(tmp_path: Path) -> None:
    """Ohne lexikalische Überschneidung bleibt jede Wertung leer."""
    index = TfidfIndex.load(_hybrid_corpus(tmp_path))

    assert index.search("zzzqqqwww xxyyzzq", k=5) == []
    assert index.search("zzzqqqwww xxyyzzq", k=5, scoring="tfidf") == []
    assert index.search("zzzqqqwww xxyyzzq", k=5, scoring="bm25") == []


def test_hybrid_respects_paper_ids_filter(tmp_path: Path) -> None:
    """Der paper_ids-Filter wirkt auch in der Fusion."""
    hits = TfidfIndex.load(_hybrid_corpus(tmp_path)).search(
        "attention", k=5, paper_ids={"cccc0003"}
    )

    assert hits
    assert all(hit.paper_id == "cccc0003" for hit in hits)


def test_unknown_scoring_raises_invalid_input(tmp_path: Path) -> None:
    """Eine unbekannte Wertung -> invalid_input (statt stiller Rückfall auf hybrid)."""
    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(_hybrid_corpus(tmp_path)).search("attention", k=3, scoring="fuzzy")  # type: ignore[arg-type]
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_score_chunks_by_paper_groups_all_positive_chunks(tmp_path: Path) -> None:
    """Liefert jeden positiv bewerteten Chunk, gruppiert nach Paper (Phase 10 / V4)."""
    index = TfidfIndex.load(_hybrid_corpus(tmp_path))

    by_paper = index.score_chunks_by_paper("attention")

    assert set(by_paper) == {"aaaa0001", "cccc0003"}
    assert all(score > 0.0 for scores in by_paper.values() for score in scores)
    # cccc0003 traegt den staerksten Einzeltreffer ("attention attention attention").
    assert max(by_paper["cccc0003"]) > max(by_paper["aaaa0001"])


def test_score_chunks_by_paper_matches_search_top_hit(tmp_path: Path) -> None:
    """Der hoechste gruppierte Score stimmt mit dem Top-Treffer von ``search`` ueberein."""
    index = TfidfIndex.load(_hybrid_corpus(tmp_path))

    top_hit = index.search("attention mechanism", k=1)[0]
    by_paper = index.score_chunks_by_paper("attention mechanism")

    assert max(by_paper[top_hit.paper_id]) == pytest.approx(top_hit.score)


def test_score_chunks_by_paper_no_match_returns_empty_mapping(tmp_path: Path) -> None:
    """Ohne lexikalische Ueberschneidung bleibt die Abbildung leer."""
    index = TfidfIndex.load(_hybrid_corpus(tmp_path))

    assert index.score_chunks_by_paper("zzzqqqwww xxyyzzq") == {}


def test_score_chunks_by_paper_empty_query_raises_invalid_input(tmp_path: Path) -> None:
    """Leere Anfrage -> invalid_input, wie bei ``search``."""
    index = TfidfIndex.load(_hybrid_corpus(tmp_path))
    with pytest.raises(DomainError) as excinfo:
        index.score_chunks_by_paper("   ")
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_score_chunks_by_paper_unknown_scoring_raises_invalid_input(tmp_path: Path) -> None:
    """Unbekannte Wertung -> invalid_input, wie bei ``search``."""
    index = TfidfIndex.load(_hybrid_corpus(tmp_path))
    with pytest.raises(DomainError) as excinfo:
        index.score_chunks_by_paper("attention", scoring="fuzzy")  # type: ignore[arg-type]
    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_score_chunks_by_paper_respects_tfidf_and_bm25_scoring(tmp_path: Path) -> None:
    """``scoring='tfidf'``/``'bm25'`` liefern die jeweiligen Rohwerte statt des Fusionswerts."""
    index = TfidfIndex.load(_hybrid_corpus(tmp_path))

    tfidf_top = index.search("attention", k=1, scoring="tfidf")[0]
    bm25_top = index.search("attention", k=1, scoring="bm25")[0]

    tfidf_scores = index.score_chunks_by_paper("attention", scoring="tfidf")
    bm25_scores = index.score_chunks_by_paper("attention", scoring="bm25")

    assert max(tfidf_scores[tfidf_top.paper_id]) == pytest.approx(tfidf_top.score)
    assert max(bm25_scores[bm25_top.paper_id]) == pytest.approx(bm25_top.score)


def test_search_is_deterministic_across_loads(tmp_path: Path) -> None:
    """Zwei unabhängige Ladevorgänge liefern identische Trefferlisten."""
    db = _hybrid_corpus(tmp_path)

    first = TfidfIndex.load(db).search("attention mechanism", k=5)
    second = TfidfIndex.load(db).search("attention mechanism", k=5)

    assert first == second


def test_neighbors_of_chunk_stays_tfidf_only(tmp_path: Path) -> None:
    """Die Chunk-Nachbarschaft bleibt Kosinus – BM25 trägt dort bewusst nicht bei."""
    neighbors = TfidfIndex.load(_hybrid_corpus(tmp_path)).neighbors_of_chunk("aaaa0001-p1", k=3)

    assert neighbors
    assert all(hit.score_bm25 == 0.0 for hit in neighbors)
    assert all(hit.score == hit.score_tfidf for hit in neighbors)


# --------------------------------------------------------------------------------------
# Prozess-Cache (Weg C) und persistierter Vokabular-/Zähl-Zustand (Weg A), Phase 15 / G2.
# --------------------------------------------------------------------------------------


def test_load_returns_cached_instance_when_file_unchanged(tmp_path: Path) -> None:
    """Zwei Ladevorgänge über dieselbe unveränderte Datei liefern dasselbe Objekt (Cache-Hit)."""
    db = _hybrid_corpus(tmp_path)

    first = TfidfIndex.load(db)
    second = TfidfIndex.load(db)

    assert first is second


def test_load_reloads_after_index_rebuilt_at_same_path(tmp_path: Path) -> None:
    """Ein neu gebauter Index am selben Pfad wirkt beim nächsten Laden sofort (kein Cache-Leck)."""
    db = tmp_path / "index.sqlite"
    build_index([_paper("aaaa0001", ["alpha beta gamma content"])], db)
    first = TfidfIndex.load(db)
    assert first is not None

    build_index([_paper("bbbb0002", ["zylophon distinctive singular token"])], db)
    second = TfidfIndex.load(db)

    assert second is not first
    hits = second.search("zylophon distinctive", k=5)
    assert hits
    assert hits[0].paper_id == "bbbb0002"


def test_load_uses_persisted_vocabulary_without_refitting_from_text(tmp_path: Path) -> None:
    """Suchergebnisse hängen nur an der persistierten Vokabular-/Zähl-Matrix, nicht am Text."""
    db = tmp_path / "index.sqlite"
    paper = _paper("cccc0003", ["neural retrieval augmented generation", "graph clustering"])
    build_index([paper], db)

    # Chunk-Text in der DB manipulieren (simuliert eine abweichende Quelle) – der bereits
    # persistierte Vokabular-/Zähl-Zustand bleibt davon unberührt, nur der SNIPPET ändert sich.
    connection = sqlite3.connect(str(db))
    try:
        connection.execute(
            "UPDATE chunks SET text = ? WHERE chunk_id = ?",
            ("manipulierter anzeige-text", "cccc0003-p1"),
        )
        connection.commit()
    finally:
        connection.close()

    hits = TfidfIndex.load(db).search("neural retrieval augmented generation", k=1)

    assert hits[0].chunk_id == "cccc0003-p1"
    assert hits[0].snippet == "manipulierter anzeige-text"
    assert hits[0].score > 0.0


def test_load_missing_tfidf_state_raises_constraint_violation(tmp_path: Path) -> None:
    """Ein Index ohne persistierten Vokabular-Zustand (z. B. Vor-G2-Schema) -> constraint_violation."""
    db = tmp_path / "index.sqlite"
    connection = sqlite3.connect(str(db))
    try:
        connection.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE papers (
                paper_id TEXT PRIMARY KEY, source_uri TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                n_pages INTEGER NOT NULL, identifiers TEXT NOT NULL DEFAULT '{}',
                document_kind TEXT NOT NULL DEFAULT 'full'
            );
            CREATE TABLE chunks (
                chunk_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, page_number INTEGER NOT NULL,
                page_end INTEGER NOT NULL DEFAULT 0, text TEXT NOT NULL, char_count INTEGER NOT NULL,
                section_title TEXT NOT NULL DEFAULT '', row_index INTEGER NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO papers (paper_id, source_uri, source_sha256, n_pages) "
            "VALUES ('dddd0004', 'file:///d.pdf', '0', 1)"
        )
        connection.execute(
            "INSERT INTO chunks (chunk_id, paper_id, page_number, text, char_count, row_index) "
            "VALUES ('dddd0004-p1', 'dddd0004', 1, 'legacy content', 15, 0)"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(DomainError) as excinfo:
        TfidfIndex.load(db)
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION
