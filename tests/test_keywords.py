"""Tests für die kuratierte Keyword-Politik (Phase 7 / A5, ADR 0015)."""

from __future__ import annotations

from research_graphrag.keywords import DOMAIN_STOPWORDS, filter_terms, is_noise_term


def test_domain_stopwords_are_noise() -> None:
    """Kuratierte Bibliografie-Token gelten als Rauschen."""
    for term in ("et", "al", "arxiv", "preprint", "doi", "https"):
        assert is_noise_term(term), term


def test_stopword_matching_is_case_insensitive() -> None:
    """Die Prüfung ist unabhängig von der Schreibweise."""
    assert is_noise_term("ArXiv")


def test_pure_numbers_and_years_are_noise() -> None:
    """Rein numerische Token (inklusive Jahreszahlen) tragen kein Thema."""
    assert is_noise_term("2024")
    assert is_noise_term("00")
    assert is_noise_term("492")


def test_glyph_artifacts_are_noise() -> None:
    """``uniXXXXXXXX``-Glyphen werden defensiv gefiltert (ältere Canonical-Daten)."""
    assert is_noise_term("uni00000013")
    assert is_noise_term("UNI0000004A")


def test_blank_term_is_noise() -> None:
    """Ein leerer Term trägt kein Thema."""
    assert is_noise_term("   ")


def test_alphanumeric_model_names_are_kept() -> None:
    """Modell-/Größenangaben wie ``7b`` oder ``4o`` sind echtes Signal."""
    for term in ("7b", "4o", "34b", "py", "gpt", "bm25"):
        assert not is_noise_term(term), term


def test_filter_terms_preserves_order_and_removes_noise() -> None:
    """Der Filter erhält die Rangfolge und entfernt nur Rausch-Terme."""
    terms = ["graph", "al", "retrieval", "et", "2024", "entity"]
    assert filter_terms(terms) == ["graph", "retrieval", "entity"]


def test_filter_terms_refills_up_to_the_limit() -> None:
    """Verdrängte Rausch-Slots werden durch nachrückende Terme aufgefüllt."""
    terms = ["al", "et", "graph", "retrieval", "entity", "rag"]
    assert filter_terms(terms, limit=3) == ["graph", "retrieval", "entity"]


def test_filter_terms_stops_at_the_limit() -> None:
    """Ohne Rauschen entspricht das Ergebnis dem einfachen Anschnitt."""
    terms = ["graph", "retrieval", "entity", "rag"]
    assert filter_terms(terms, limit=2) == ["graph", "retrieval"]


def test_filter_terms_without_limit_returns_all_signal_terms() -> None:
    """Ohne ``limit`` bleiben alle Nicht-Rausch-Terme erhalten."""
    assert filter_terms(["al", "graph", "2024", "rag"]) == ["graph", "rag"]


def test_stopwords_are_lowercase_and_non_empty() -> None:
    """Die kuratierte Liste ist normalisiert (Voraussetzung für den Abgleich)."""
    assert DOMAIN_STOPWORDS
    assert all(word == word.lower() and word.strip() for word in DOMAIN_STOPWORDS)
