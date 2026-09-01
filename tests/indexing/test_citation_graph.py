"""Tests für den Intra-Korpus-Zitationsgraphen (Phase 7 / A2, ADR 0011)."""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SECTION_KIND_BODY, SECTION_KIND_REFERENCES, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.citation_graph import (
    CITATION_SCHEMA_VERSION,
    _MultiPatternMatcher,
    build_citation_graph,
    load_citations,
)
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index

_TITLE_A = "Graph Retrieval Augmented Generation for Scientific Corpora"
_DOI_A = "10.1234/grag.2026"
_ARXIV_A = "2501.01234"


def _paper(
    paper_id: str,
    title: str,
    *,
    body: str = "retrieval augmented generation over scientific papers",
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
            chunk_id=f"{paper_id}-c0001",
            paper_id=paper_id,
            page_number=1,
            text=body,
            char_count=len(body),
            section_id="s-body",
            section_title="Introduction",
        )
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
        for index, entry in enumerate(references, start=2):
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


def _cited_paper() -> CanonicalPaper:
    """Das Zielpaper, auf das die übrigen Fixtures verweisen (IDs auf der Titelseite belegt)."""
    return _paper(
        "aaaa0001",
        _TITLE_A,
        body=f"{_TITLE_A} arXiv:{_ARXIV_A} doi:{_DOI_A} retrieval augmented generation",
        identifiers={"doi": _DOI_A, "arxiv": _ARXIV_A},
    )


def _edges(db: Path) -> list[tuple[str, str, str]]:
    """Liest alle Zitationskanten in stabiler Reihenfolge."""
    connection = sqlite3.connect(str(db))
    try:
        rows = connection.execute(
            "SELECT source_paper_id, target_paper_id, method FROM citation_edges "
            "ORDER BY source_paper_id, target_paper_id"
        ).fetchall()
    finally:
        connection.close()
    return [(str(source), str(target), str(method)) for source, target, method in rows]


def test_doi_match_creates_directed_edge(tmp_path: Path) -> None:
    """Eine DOI im Referenzabschnitt erzeugt genau eine gerichtete Kante."""
    citing = _paper(
        "bbbb0001",
        "Benchmarking Retrieval Pipelines in Practice",
        references=[f"[1] Some Authors. A study. 2026. doi:{_DOI_A}"],
    )
    db = tmp_path / "index.sqlite"

    report = build_citation_graph([_cited_paper(), citing], db)

    assert report.n_edges == 1
    assert report.n_papers_with_refs == 1
    assert _edges(db) == [("bbbb0001", "aaaa0001", "doi")]


@pytest.mark.parametrize(
    ("reference", "expected_method"),
    [
        (f"[1] doi:{_DOI_A} · arXiv:{_ARXIV_A} · {_TITLE_A}", "doi"),
        (f"[1] arXiv:{_ARXIV_A} · {_TITLE_A}", "arxiv"),
        (f"[1] Some Authors. {_TITLE_A}. 2026.", "title"),
    ],
)
def test_method_precedence_doi_over_arxiv_over_title(
    tmp_path: Path, reference: str, expected_method: str
) -> None:
    """Je Zielpaper wird das präziseste Match-Kriterium gespeichert."""
    citing = _paper("bbbb0001", "Benchmarking Retrieval Pipelines", references=[reference])
    db = tmp_path / "index.sqlite"

    build_citation_graph([_cited_paper(), citing], db)

    assert _edges(db) == [("bbbb0001", "aaaa0001", expected_method)]


def test_self_citation_is_ignored(tmp_path: Path) -> None:
    """Ein Paper, das seine eigene DOI im Referenzteil führt, zitiert sich nicht selbst."""
    self_citing = _paper(
        "aaaa0001",
        _TITLE_A,
        body=f"{_TITLE_A} doi:{_DOI_A}",
        identifiers={"doi": _DOI_A},
        references=[f"[1] Eigenzitat. doi:{_DOI_A} – {_TITLE_A}"],
    )
    db = tmp_path / "index.sqlite"

    report = build_citation_graph([self_citing], db)

    assert report.n_edges == 0
    assert report.n_papers_with_refs == 1
    assert _edges(db) == []


def test_identifiers_not_on_title_page_are_ignored(tmp_path: Path) -> None:
    """Eine ID, die nur im Fließtext des Zielpapers steht, taugt nicht als Zielschlüssel.

    Die Extraktion kann eine **zitierte** fremde ID als eigene erfassen; solche Werte würden
    hier viele falsche Kanten erzeugen (ADR 0011, Präzision vor Recall).
    """
    foreign_id = "2108.07732"
    mislabeled = _paper(
        "aaaa0001",
        "A Paper Whose Identifier Was Misextracted From Its Body",
        body="page one without any identifier",
        identifiers={"arxiv": foreign_id},
        references=[f"[1] fremde Arbeit. arXiv:{foreign_id}"],
    )
    citing = _paper(
        "bbbb0001",
        "Benchmarking Retrieval Pipelines",
        references=[f"[1] fremde Arbeit. arXiv:{foreign_id}"],
    )
    db = tmp_path / "index.sqlite"

    report = build_citation_graph([mislabeled, citing], db)

    assert report.n_edges == 0


def test_short_titles_are_not_matched(tmp_path: Path) -> None:
    """Zu kurze Titel bleiben aus dem Titel-Matching heraus (Präzision vor Recall)."""
    short = _paper("cccc0001", "RAG")
    citing = _paper("bbbb0001", "Benchmarking Retrieval Pipelines", references=["[1] RAG. 2026."])
    db = tmp_path / "index.sqlite"

    report = build_citation_graph([short, citing], db)

    assert report.n_edges == 0


def test_papers_without_reference_section_yield_no_edges(tmp_path: Path) -> None:
    """Ohne erkannten Referenzabschnitt entstehen keine ausgehenden Kanten."""
    without_refs = _paper("bbbb0001", "Benchmarking Retrieval Pipelines", body=f"cites {_DOI_A}")
    db = tmp_path / "index.sqlite"

    report = build_citation_graph([_cited_paper(), without_refs], db)

    assert report.n_edges == 0
    assert report.n_papers_with_refs == 0


def test_duplicate_papers_are_deduplicated(tmp_path: Path) -> None:
    """Doppelt übergebene Paper (gleiche ``paper_id``) zählen nur einmal."""
    citing = _paper(
        "bbbb0001",
        "Benchmarking Retrieval Pipelines",
        references=[f"[1] doi:{_DOI_A}"],
    )
    db = tmp_path / "index.sqlite"

    report = build_citation_graph([_cited_paper(), citing, citing], db)

    assert report.n_papers_with_refs == 1
    assert _edges(db) == [("bbbb0001", "aaaa0001", "doi")]


def test_build_is_deterministic(tmp_path: Path) -> None:
    """Zwei Läufe über denselben Korpus liefern identische Kanten."""
    corpus = [
        _cited_paper(),
        _paper("bbbb0001", "Benchmarking Retrieval Pipelines", references=[f"[1] doi:{_DOI_A}"]),
        _paper("cccc0001", "Evaluating Graph Indexes", references=[f"[1] arXiv:{_ARXIV_A}"]),
    ]
    first = tmp_path / "first.sqlite"
    second = tmp_path / "second.sqlite"

    report_first = build_citation_graph(corpus, first)
    report_second = build_citation_graph(list(reversed(corpus)), second)

    assert report_first == report_second
    assert _edges(first) == _edges(second)
    assert _edges(first) == [
        ("bbbb0001", "aaaa0001", "doi"),
        ("cccc0001", "aaaa0001", "arxiv"),
    ]


def test_rebuild_replaces_previous_edges(tmp_path: Path) -> None:
    """Der Bau ist ein voller Re-Build: alte Kanten verschwinden."""
    db = tmp_path / "index.sqlite"
    citing = _paper(
        "bbbb0001", "Benchmarking Retrieval Pipelines", references=[f"[1] doi:{_DOI_A}"]
    )
    build_citation_graph([_cited_paper(), citing], db)

    build_citation_graph([_cited_paper()], db)

    assert _edges(db) == []


def test_persistence_is_additive(tmp_path: Path) -> None:
    """Index- und Graph-Tabellen bleiben unangetastet; das Teilschema wird versioniert."""
    db = tmp_path / "index.sqlite"
    corpus = [
        _cited_paper(),
        _paper("bbbb0001", "Benchmarking Retrieval Pipelines", references=[f"[1] doi:{_DOI_A}"]),
    ]
    build_index(corpus, db)
    build_graph(corpus, db)
    connection = sqlite3.connect(str(db))
    try:
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("papers", "chunks", "graph_nodes", "communities")
        }
    finally:
        connection.close()

    build_citation_graph(corpus, db)

    connection = sqlite3.connect(str(db))
    try:
        after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("papers", "chunks", "graph_nodes", "communities")
        }
        version = connection.execute(
            "SELECT value FROM meta WHERE key = 'citation_schema_version'"
        ).fetchone()
        schema_version = connection.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    finally:
        connection.close()

    assert after == before
    assert version[0] == CITATION_SCHEMA_VERSION
    assert schema_version is not None, "Das Index-Schema darf nicht überschrieben werden."


def test_load_citations_returns_both_directions(tmp_path: Path) -> None:
    """``load_citations`` liefert ausgehende und eingehende Kanten samt Methode."""
    db = tmp_path / "index.sqlite"
    corpus = [
        _cited_paper(),
        _paper("bbbb0001", "Benchmarking Retrieval Pipelines", references=[f"[1] doi:{_DOI_A}"]),
        _paper("cccc0001", "Evaluating Graph Indexes", references=[f"[1] arXiv:{_ARXIV_A}"]),
    ]
    build_index(corpus, db)
    build_citation_graph(corpus, db)

    cited = load_citations(db, "aaaa0001")
    citing = load_citations(db, "bbbb0001")

    assert cited.cites == ()
    assert [edge.source_paper_id for edge in cited.cited_by] == ["bbbb0001", "cccc0001"]
    assert [edge.method for edge in cited.cited_by] == ["doi", "arxiv"]
    assert [edge.target_paper_id for edge in citing.cites] == ["aaaa0001"]
    assert citing.cited_by == ()


def test_citation_view_to_dict_shape(tmp_path: Path) -> None:
    """Die serialisierte Sicht trägt die vereinbarten Schlüssel."""
    db = tmp_path / "index.sqlite"
    corpus = [
        _cited_paper(),
        _paper("bbbb0001", "Benchmarking Retrieval Pipelines", references=[f"[1] doi:{_DOI_A}"]),
    ]
    build_index(corpus, db)
    build_citation_graph(corpus, db)

    payload = load_citations(db, "bbbb0001").to_dict()

    assert set(payload) == {"paper_id", "cites", "cited_by"}
    assert payload["cites"] == [
        {"source_paper_id": "bbbb0001", "target_paper_id": "aaaa0001", "method": "doi"}
    ]


def test_load_citations_rejects_empty_paper_id(tmp_path: Path) -> None:
    """Eine leere ``paper_id`` wird vor jedem Index-Zugriff abgewiesen."""
    with pytest.raises(DomainError) as excinfo:
        load_citations(tmp_path / "missing.sqlite", "   ")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_load_citations_missing_index(tmp_path: Path) -> None:
    """Ein fehlender Index meldet ``not_found``."""
    with pytest.raises(DomainError) as excinfo:
        load_citations(tmp_path / "missing.sqlite", "aaaa0001")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_load_citations_without_citation_graph(tmp_path: Path) -> None:
    """Ein Index ohne Zitationsgraph meldet ``constraint_violation``."""
    db = tmp_path / "index.sqlite"
    build_index([_cited_paper()], db)

    with pytest.raises(DomainError) as excinfo:
        load_citations(db, "aaaa0001")

    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_load_citations_unknown_paper(tmp_path: Path) -> None:
    """Eine unbekannte ``paper_id`` meldet ``not_found``."""
    db = tmp_path / "index.sqlite"
    build_index([_cited_paper()], db)
    build_citation_graph([_cited_paper()], db)

    with pytest.raises(DomainError) as excinfo:
        load_citations(db, "zzzz9999")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------
# _MultiPatternMatcher (Phase 15 / G1): Aho-Corasick statt N Einzelsuchen.
# Muss fuer JEDEN Text und JEDE Musterliste dasselbe Ergebnis wie die brachiale
# Substring-Suche liefern - das ist die Voraussetzung fuer die Byte-Identitaet
# von build_citation_graph.
# ---------------------------------------------------------------------------


def _brute_force_search(patterns: Sequence[str], text: str) -> set[int]:
    """Referenzimplementierung: ``pattern in text`` je Muster (die alte Semantik)."""
    return {index for index, pattern in enumerate(patterns) if pattern and pattern in text}


@pytest.mark.parametrize(
    ("patterns", "text"),
    [
        ([], "beliebiger text"),
        (["abc"], ""),
        (["abc"], "xxxabcxxx"),
        (["abc", "bcd"], "abcd"),  # überlappende Muster
        (["ab", "abc", "abcd"], "xabcdx"),  # Muster sind Präfixe voneinander
        (["10.1145/123", "10.1145/1234"], "ref 10.1145/1234 more"),
        (["abc"], "abcabcabc"),  # mehrfaches Vorkommen desselben Musters
        (["nichtvorhanden"], "abc def ghi"),
        (["a", "b", "c"], "abcabc"),
        (
            ["match"],
            "MATCH",
        ),  # Groß-/Kleinschreibung wird NICHT normalisiert (Aufgabe des Aufrufers)
    ],
)
def test_multi_pattern_matcher_matches_brute_force(patterns: Sequence[str], text: str) -> None:
    """Der Automat findet exakt dieselben Muster wie eine Einzelsuche je Muster."""
    matcher = _MultiPatternMatcher(patterns)
    found = {patterns[index] for index in matcher.search(text)}
    expected = {patterns[index] for index in _brute_force_search(patterns, text)}
    assert found == expected


def test_multi_pattern_matcher_random_agrees_with_brute_force() -> None:
    """Zufällige Muster/Texte über einem kleinen Alphabet: kein Fall weicht ab."""
    rng = random.Random(20260901)
    alphabet = "ab10./"
    for _ in range(200):
        n_patterns = rng.randint(0, 6)
        patterns = ["".join(rng.choices(alphabet, k=rng.randint(1, 5))) for _ in range(n_patterns)]
        text = "".join(rng.choices(alphabet, k=rng.randint(0, 40)))
        matcher = _MultiPatternMatcher(patterns)
        found = {patterns[index] for index in matcher.search(text)}
        expected = {patterns[index] for index in _brute_force_search(patterns, text)}
        assert found == expected, f"patterns={patterns!r} text={text!r}"
