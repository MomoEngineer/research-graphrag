"""Tests der Personen-Werkzeuge (Phase 17 / A4, ADR 0043).

Grundlage ist der Personen-Index aus ``tests/conftest.py`` (``make_person_index``). Geprüft
werden: Kandidaten je Personenschlüssel ohne stille Zusammenführung, die Abdeckung in jeder
Antwort, das Profil mit Mitautoren und Communities, die auf die Person beschränkte Suche, das
Zitationsnetz mit Selbstzitaten, die Kappung und alle Fehlerfälle.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.retrieval.authors import (
    CORPUS_SCOPE_NOTE,
    SCOPE_CORPUS,
    Coverage,
    coverage_of,
    get_author,
    get_author_citations,
    search_author_papers,
    search_authors,
)
from research_graphrag.retrieval.basic import search_basic

ASAI = "A5023888391"
HAJISHIRZI = "A5000000003"


@pytest.fixture
def person_db(make_person_index: Callable[..., Path]) -> Path:
    """Vollständiger Personen-Index (Graph, Zitationen, Autorenindex)."""
    return make_person_index()


def _code(error: pytest.ExceptionInfo[DomainError]) -> ErrorCode:
    """Fehlerkategorie einer erwarteten :class:`DomainError`."""
    return error.value.code


# --- search_authors -----------------------------------------------------------------------------


def test_search_lists_one_candidate_per_person_key(person_db: Path) -> None:
    """Kennung und gleichnamige Namensidentität bleiben zwei Kandidaten – mehrdeutig."""
    result = search_authors(person_db, "Asai")

    assert [candidate.person_key for candidate in result.candidates] == [ASAI, "name:akari asai"]
    assert result.total_matching == 2
    assert result.ambiguous is True
    first, second = result.candidates
    assert first.identity == "openalex"
    assert first.openalex_id == ASAI
    assert first.names == ("Akari Asai", "Asai, Akari")
    assert first.n_papers == 2
    assert first.year_span == (2024, 2025)
    assert second.identity == "name"
    assert second.openalex_id == ""
    assert second.n_papers == 1


def test_search_leaves_out_weakly_backed_papers(person_db: Path) -> None:
    """``dddd0001`` nennt Asai, ist aber nur ``weak`` belegt – es zählt nicht zur Person."""
    candidate = search_authors(person_db, "Asai").candidates[0]

    assert "Attention Heads" not in candidate.sample_titles
    assert candidate.sample_titles == (
        "Reflection Tokens for Retrieval",
        "Self-RAG: Learning to Retrieve, Generate, and Critique",
    )


@pytest.mark.parametrize("query", ["Asai, Akari", "akari asai", "ASAI"])
def test_search_folds_spelling_and_order(person_db: Path, query: str) -> None:
    """Beide Schreibweisen und Groß-/Kleinschreibung finden dieselben Personen."""
    keys = [candidate.person_key for candidate in search_authors(person_db, query).candidates]

    assert keys == [ASAI, "name:akari asai"]


def test_search_matches_an_initial_as_word_start(person_db: Path) -> None:
    """„B. Muster“ findet Bert Muster (kurze Suchwörter als Wortanfang)."""
    result = search_authors(person_db, "B. Muster")

    assert [candidate.person_key for candidate in result.candidates] == ["name:bert muster"]
    assert result.ambiguous is False
    assert result.candidates[0].n_papers == 2


def test_search_limit_caps_the_list_but_reports_the_total(person_db: Path) -> None:
    """Die Kappung bleibt sichtbar: ``total_matching`` zählt vor dem Deckel."""
    result = search_authors(person_db, "Asai", limit=1)

    assert len(result.candidates) == 1
    assert result.total_matching == 2
    assert result.ambiguous is True
    assert result.to_dict()["total_matching"] == 2


def test_search_result_carries_the_coverage(person_db: Path) -> None:
    """Vier von sechs Volltexten tragen belegte Autoren – die Lücke steht in der Antwort."""
    payload = search_authors(person_db, "Hajishirzi").to_dict()

    assert payload["coverage"]["full_texts_with_authors"] == 4
    assert payload["coverage"]["full_texts"] == 6
    assert payload["coverage"]["share"] == pytest.approx(0.6667)
    assert "4 von 6" in payload["coverage"]["note"]


def test_unknown_name_is_not_found_and_names_the_coverage(person_db: Path) -> None:
    """Kein Kandidat ist ``not_found``; die Meldung nennt die Abdeckung."""
    with pytest.raises(DomainError) as error:
        search_authors(person_db, "Nobody")

    assert _code(error) is ErrorCode.NOT_FOUND
    assert "4 von 6" in error.value.message


@pytest.mark.parametrize(
    ("name", "limit"),
    [("", 20), ("   ", 20), ("!!", 20), ("Asai", 0), ("Asai", 51)],
)
def test_search_rejects_invalid_input(person_db: Path, name: str, limit: int) -> None:
    """Leerer oder zeichenloser Name bzw. ungültiger Deckel sind ``invalid_input``."""
    with pytest.raises(DomainError) as error:
        search_authors(person_db, name, limit=limit)

    assert _code(error) is ErrorCode.INVALID_INPUT


def test_index_without_person_level_points_to_the_rebuild(
    make_person_index: Callable[..., Path],
) -> None:
    """Ein Index von vor Phase 17 / A3 meldet ``not_found`` samt Neubau-Hinweis."""
    db = make_person_index(authors=False)

    with pytest.raises(DomainError) as error:
        search_authors(db, "Asai")

    assert _code(error) is ErrorCode.NOT_FOUND
    assert "scripts.ingest" in error.value.message
    assert coverage_of(db) == Coverage(full_texts_with_authors=0, full_texts=6)


def test_missing_index_is_not_found(tmp_path: Path) -> None:
    """Ohne Index-Datei antwortet jedes Werkzeug mit ``not_found``."""
    with pytest.raises(DomainError) as error:
        search_authors(tmp_path / "fehlt.sqlite", "Asai")

    assert _code(error) is ErrorCode.NOT_FOUND


# --- Coverage -----------------------------------------------------------------------------------


def test_coverage_note_confirms_full_coverage() -> None:
    """Volle Abdeckung wird kurz bestätigt statt als Lücke beschrieben."""
    coverage = Coverage(full_texts_with_authors=3, full_texts=3)

    assert coverage.share == 1.0
    assert coverage.note == "Alle 3 Volltexte tragen belegte Autoren."


def test_coverage_without_full_texts_has_share_zero() -> None:
    """Ein Index ohne Volltexte teilt nicht durch null."""
    coverage = Coverage(full_texts_with_authors=0, full_texts=0)

    assert coverage.share == 0.0
    assert coverage.note == "Der Index enthält keine Volltexte."


# --- get_author ---------------------------------------------------------------------------------


def test_profile_lists_papers_newest_first_with_positions(person_db: Path) -> None:
    """Paperliste nach Jahr absteigend, mit Autorposition, Titel und Zitierschlüssel."""
    profile = get_author(person_db, ASAI)

    assert [entry.paper.paper_id for entry in profile.papers] == ["aaaa0002", "aaaa0001"]
    assert [entry.position for entry in profile.papers] == [1, 1]
    assert profile.papers[0].paper.title == "Reflection Tokens for Retrieval"
    assert profile.papers[0].paper.citation_key == "Asai2025"
    assert profile.papers[0].paper.identifiers == {"doi": "10.1000/reflect"}
    assert profile.papers_total == 2
    assert profile.year_span == (2024, 2025)
    assert profile.identity == "openalex"
    assert profile.names == ("Akari Asai", "Asai, Akari")
    entry = profile.to_dict()["papers"][0]
    assert entry["position"] == 1
    assert entry["year"] == 2025


def test_profile_counts_shared_papers_per_coauthor(person_db: Path) -> None:
    """Direkte Mitautoren nach Zahl gemeinsamer Paper; Namensidentitäten bleiben erkennbar."""
    profile = get_author(person_db, ASAI)

    assert [(c.person_key, c.n_shared) for c in profile.coauthors] == [
        ("name:zeqiu wu", 2),
        (HAJISHIRZI, 1),
        ("name:bert muster", 1),
    ]
    assert profile.coauthors[0].identity == "name"
    assert profile.coauthors[1].identity == "openalex"
    assert profile.coauthors_total == 3


def test_profile_names_the_communities_of_the_papers(person_db: Path) -> None:
    """Communities der Paper samt Anzahl; je höchstens fünf Keywords."""
    profile = get_author(person_db, ASAI)

    assert sum(community.n_papers for community in profile.communities) == 2
    assert profile.communities_total == len(profile.communities) >= 1
    assert all(len(community.keywords) <= 5 for community in profile.communities)


def test_profile_without_graph_has_no_communities(make_person_index: Callable[..., Path]) -> None:
    """Ohne Ähnlichkeitsgraphen bleibt die Community-Liste leer – kein Fehler."""
    profile = get_author(make_person_index(graph=False), ASAI)

    assert profile.communities == ()
    assert profile.communities_total == 0
    assert profile.papers_total == 2


def test_profile_limit_caps_every_list(person_db: Path) -> None:
    """``limit`` kappt Paper und Mitautoren; ``*_total`` zählt davor."""
    payload = get_author(person_db, ASAI, limit=1).to_dict()

    assert len(payload["papers"]) == 1
    assert payload["papers_total"] == 2
    assert len(payload["coauthors"]) == 1
    assert payload["coauthors_total"] == 3


def test_profile_of_a_name_identity(person_db: Path) -> None:
    """Ein ``name:``-Schlüssel ist abfragbar und bleibt als Namensidentität ausgewiesen."""
    profile = get_author(person_db, "name:akari asai")

    assert profile.identity == "name"
    assert [entry.paper.paper_id for entry in profile.papers] == ["bbbb0001"]
    assert profile.coauthors == ()


def test_profile_of_an_unknown_key_is_not_found(person_db: Path) -> None:
    """Unbekannter Schlüssel: ``not_found`` mit Abdeckung in der Meldung."""
    with pytest.raises(DomainError) as error:
        get_author(person_db, "A999")

    assert _code(error) is ErrorCode.NOT_FOUND
    assert "4 von 6" in error.value.message


@pytest.mark.parametrize(("key", "limit"), [("", 50), (" ", 50), (ASAI, 0), (ASAI, 51)])
def test_profile_rejects_invalid_input(person_db: Path, key: str, limit: int) -> None:
    """Leerer Schlüssel oder ungültiger Deckel sind ``invalid_input``."""
    with pytest.raises(DomainError) as error:
        get_author(person_db, key, limit=limit)

    assert _code(error) is ErrorCode.INVALID_INPUT


# --- search_author_papers -----------------------------------------------------------------------


def test_search_stays_within_the_papers_of_the_person(person_db: Path) -> None:
    """``dddd0001`` gewinnt die offene Suche, gehört aber nicht zur Person und fehlt."""
    assert search_basic(person_db, "attention", k=1).citations[0].paper_id == "dddd0001"

    result = search_author_papers(person_db, ASAI, "attention", k=5)

    assert result.papers_searched == 2
    assert {citation.paper_id for citation in result.citations} == {"aaaa0001", "aaaa0002"}
    assert result.citations[0].section_title == "Introduction"


def test_search_uses_the_citation_contract_of_search_basic(person_db: Path) -> None:
    """Die Zitate tragen dieselben Felder wie bei ``search_basic``."""
    person = search_author_papers(person_db, ASAI, "attention", k=1).to_dict()
    basic = search_basic(person_db, "attention", k=1).to_dict()

    assert set(person["citations"][0]) == set(basic["citations"][0])
    assert person["coverage"]["full_texts"] == 6


def test_search_without_matching_chunk_is_empty(person_db: Path) -> None:
    """„louvain“ steht nur in einem fremden Paper – leeres Ergebnis, kein Fehler."""
    result = search_author_papers(person_db, ASAI, "louvain")

    assert result.citations == ()
    assert result.papers_searched == 2


@pytest.mark.parametrize(
    ("key", "query", "k", "code"),
    [
        ("", "attention", 5, ErrorCode.INVALID_INPUT),
        (ASAI, "  ", 5, ErrorCode.INVALID_INPUT),
        (ASAI, "attention", 0, ErrorCode.INVALID_INPUT),
        (ASAI, "attention", 51, ErrorCode.INVALID_INPUT),
        ("A999", "attention", 5, ErrorCode.NOT_FOUND),
    ],
)
def test_search_author_papers_errors(
    person_db: Path, key: str, query: str, k: int, code: ErrorCode
) -> None:
    """Fehlerfälle der personenbezogenen Suche."""
    with pytest.raises(DomainError) as error:
        search_author_papers(person_db, key, query, k=k)

    assert _code(error) is code


# --- get_author_citations -----------------------------------------------------------------------


def test_citations_in_both_directions_mark_self_citations(person_db: Path) -> None:
    """``cites``/``cited_by`` je Gegenüber, mit beteiligten Papern und Selbstzitat-Marke."""
    result = get_author_citations(person_db, ASAI)

    assert [(link.paper.paper_id, link.self_citation) for link in result.cites] == [
        ("aaaa0001", True),
        ("cccc0001", False),
    ]
    assert result.cites[0].via == ("aaaa0002",)
    assert result.cites[0].methods == ("doi",)
    assert [link.paper.paper_id for link in result.cited_by] == ["cccc0001", "aaaa0002", "bbbb0001"]
    assert result.cited_by[0].via == ("aaaa0001", "aaaa0002")
    assert result.cited_by[1].self_citation is True
    assert result.cited_by[2].self_citation is False
    assert (result.cites_total, result.cited_by_total) == (2, 3)


def test_citations_state_the_corpus_scope(person_db: Path) -> None:
    """Die Grenze „nur innerhalb des Korpus“ steht in jeder Antwort."""
    payload = get_author_citations(person_db, ASAI).to_dict()

    assert payload["scope"] == SCOPE_CORPUS
    assert payload["note"] == CORPUS_SCOPE_NOTE
    assert payload["cited_by"][0]["paper"]["title"] == "Louvain Communities Revisited"
    assert payload["cited_by"][0]["self"] is False
    assert payload["coverage"]["full_texts_with_authors"] == 4


def test_citations_limit_applies_per_direction(person_db: Path) -> None:
    """``limit`` kappt jede Richtung für sich; die Totale zählen davor."""
    result = get_author_citations(person_db, ASAI, limit=1)

    assert len(result.cites) == 1
    assert len(result.cited_by) == 1
    assert (result.cites_total, result.cited_by_total) == (2, 3)


def test_citations_without_citation_graph_violate_a_constraint(
    make_person_index: Callable[..., Path],
) -> None:
    """Ohne Zitationsgraph: ``constraint_violation``."""
    with pytest.raises(DomainError) as error:
        get_author_citations(make_person_index(citations=False), ASAI)

    assert _code(error) is ErrorCode.CONSTRAINT_VIOLATION


@pytest.mark.parametrize(
    ("key", "limit", "code"),
    [
        ("", 50, ErrorCode.INVALID_INPUT),
        (ASAI, 0, ErrorCode.INVALID_INPUT),
        (ASAI, 51, ErrorCode.INVALID_INPUT),
        ("A999", 50, ErrorCode.NOT_FOUND),
    ],
)
def test_citations_errors(person_db: Path, key: str, limit: int, code: ErrorCode) -> None:
    """Fehlerfälle der Zitationsabfrage."""
    with pytest.raises(DomainError) as error:
        get_author_citations(person_db, key, limit=limit)

    assert _code(error) is code
