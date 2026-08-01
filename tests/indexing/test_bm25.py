"""Tests für die handimplementierte BM25-Wertung (Phase 7 / A4)."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.feature_extraction.text import CountVectorizer

from research_graphrag.indexing import bm25


def _counts(documents: list[str]) -> tuple[CountVectorizer, object]:
    vectorizer = CountVectorizer()
    return vectorizer, vectorizer.fit_transform(documents)


def test_weights_keep_sparsity_pattern() -> None:
    """Die Gewichtsmatrix hat dieselbe Gestalt und Besetzung wie die Häufigkeiten."""
    _, counts = _counts(["alpha beta beta", "beta gamma", "delta"])

    weights = bm25.build_weights(counts)

    assert weights.shape == counts.shape
    assert weights.nnz == counts.nnz
    assert (weights.indices == counts.tocsr().indices).all()


def test_term_frequency_saturates() -> None:
    """Zehnfache Termhäufigkeit ergibt deutlich weniger als das Zehnfache an Gewicht."""
    vectorizer, counts = _counts(["alpha " * 1, "alpha " * 10, "beta gamma delta"])
    weights = bm25.build_weights(counts)
    query = vectorizer.transform(["alpha"])

    scores = bm25.score(weights, query)

    assert scores[1] > scores[0]
    assert scores[1] < 10 * scores[0]


def test_longer_document_is_penalised() -> None:
    """Bei gleicher Termhäufigkeit gewinnt das kürzere Dokument (Längennormalisierung)."""
    vectorizer, counts = _counts(["alpha beta", "alpha " + " ".join(f"w{i}" for i in range(50))])
    weights = bm25.build_weights(counts)

    scores = bm25.score(weights, vectorizer.transform(["alpha"]))

    assert scores[0] > scores[1]


def test_rare_term_outweighs_common_term() -> None:
    """Ein seltener Term trägt mehr Gewicht als ein in allen Dokumenten übliches Wort."""
    vectorizer, counts = _counts(["common rare", "common filler", "common other"])
    weights = bm25.build_weights(counts)

    rare = bm25.score(weights, vectorizer.transform(["rare"]))[0]
    common = bm25.score(weights, vectorizer.transform(["common"]))[0]

    assert rare > common


def test_idf_stays_positive_for_ubiquitous_terms() -> None:
    """Die Lucene-IDF bleibt positiv – ein überall vorkommender Term kehrt Ränge nicht um."""
    vectorizer, counts = _counts(["common alpha", "common beta"])
    weights = bm25.build_weights(counts)

    assert (bm25.score(weights, vectorizer.transform(["common"])) > 0.0).all()


def test_repeated_query_term_counts_twice() -> None:
    """Ein doppelt genannter Anfrage-Term zählt doppelt (klassisches BM25)."""
    vectorizer, counts = _counts(["alpha beta", "gamma delta"])
    weights = bm25.build_weights(counts)

    single = bm25.score(weights, vectorizer.transform(["alpha"]))[0]
    double = bm25.score(weights, vectorizer.transform(["alpha alpha"]))[0]

    assert double == pytest.approx(2 * single)


def test_unknown_query_terms_score_zero() -> None:
    """Ohne Vokabular-Überschneidung ist jeder Wert 0 (Grundlage der Leer-Semantik)."""
    vectorizer, counts = _counts(["alpha beta"])
    weights = bm25.build_weights(counts)

    assert (bm25.score(weights, vectorizer.transform(["zzzqqqwww"])) == 0.0).all()


def test_empty_vocabulary_does_not_divide_by_zero() -> None:
    """Dokumente ohne verwertbare Token führen nicht zu NaN (neutrale Längennorm)."""
    vectorizer = CountVectorizer(vocabulary={"alpha": 0})
    counts = vectorizer.transform(["beta gamma", "delta"])

    weights = bm25.build_weights(counts)

    assert not np.isnan(weights.toarray()).any()


def test_weights_are_deterministic() -> None:
    """Gleiche Eingabe erzeugt bitgleiche Gewichte."""
    _, counts = _counts(["alpha beta beta", "beta gamma", "delta epsilon"])

    first = bm25.build_weights(counts).toarray()
    second = bm25.build_weights(counts).toarray()

    assert (first == second).all()
