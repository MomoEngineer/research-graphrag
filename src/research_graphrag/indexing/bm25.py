"""BM25-Wertung, handimplementiert über die Term-Häufigkeiten des Index (Phase 7 / A4).

Ergänzt die TF-IDF-Kosinus-Wertung um ein **probabilistisches Rankingmodell** mit zwei
Eigenschaften, die der Kosinus nicht hat (Grundsatz:
docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md):

* **Term-Sättigung** (:data:`K1`) – der zwanzigste Treffer eines Terms trägt kaum mehr bei als
  der zweite; entscheidend ist, *dass* ein Term vorkommt.
* **Längennormalisierung** (:data:`B`) – lange Chunks werden gegenüber kurzen nicht bevorzugt.

Gewicht eines Terms :math:`t` in einem Chunk :math:`d`:

.. math::

    w_{d,t} = \\mathrm{idf}_t \\cdot \\frac{f_{d,t}\\,(k_1 + 1)}
    {f_{d,t} + k_1\\left(1 - b + b\\,\\frac{|d|}{\\overline{|d|}}\\right)},
    \\qquad
    \\mathrm{idf}_t = \\ln\\left(1 + \\frac{N - n_t + 0.5}{n_t + 0.5}\\right)

Die IDF-Variante (Lucene) ist stets positiv; sehr häufige Terme können damit keine negativen
Beiträge und keine Rang-Inversionen erzeugen. Die Gewichte selbst werden **nicht** persistiert –
sie werden bei jedem Laden des Index aus der (seit Phase 15 / G2 additiv persistierten)
Term-Häufigkeitsmatrix neu berechnet (docs/adr/0005-graphrag-index-backend-open.md,
docs/adr/0033-response-latency-cache-and-persisted-tfidf-state-phase15.md).
"""

from __future__ import annotations

from typing import Any

import numpy as np

K1 = 1.5
"""Sättigungsparameter der Termhäufigkeit (Standardwert)."""

B = 0.75
"""Stärke der Längennormalisierung: ``0`` = keine, ``1`` = volle (Standardwert)."""


def build_weights(counts: Any, *, copy: bool = True) -> Any:
    """Berechnet die BM25-Gewichtsmatrix aus einer Term-Häufigkeitsmatrix.

    Args:
        counts: Dünnbesetzte Matrix ``(Chunks × Terme)`` mit rohen Termhäufigkeiten, wie sie
            ``sklearn.feature_extraction.text.CountVectorizer`` liefert. Vorausgesetzt wird die
            dort übliche Form **ohne explizit gespeicherte Nullen** (die Dokumentfrequenz wird
            aus der Besetzungsstruktur abgelesen).

        copy: ``False`` erlaubt, eine ``float64``-CSR-Matrix **in place** in die Gewichte zu
            verwandeln (der Lader braucht die Zählwerte danach nicht mehr, Phase 16 / F3). Andere
            Eingaben werden immer kopiert.

    Returns:
        Eine Matrix gleicher Gestalt und Besetzung mit den BM25-Gewichten je Term und Chunk.
    """
    in_place = not copy and counts.format == "csr" and counts.dtype == np.float64
    matrix = counts if in_place else counts.tocsr().astype(np.float64)
    n_documents = matrix.shape[0]
    document_frequency = np.bincount(matrix.indices, minlength=matrix.shape[1])
    inverse_document_frequency = np.log(
        1.0 + (n_documents - document_frequency + 0.5) / (document_frequency + 0.5)
    )

    lengths = matrix.sum(axis=1).A1
    average_length = float(lengths.mean()) if n_documents else 0.0
    if average_length <= 0.0:
        average_length = 1.0  # leeres Vokabular: Längennormalisierung neutralisieren

    length_norm = K1 * (1.0 - B + B * lengths / average_length)
    # In place, aber in derselben Reihenfolge wie
    # ``data * (K1 + 1) / (data + norm) * idf`` – die Werte bleiben bitgleich, es entstehen nur
    # keine Zwischen-Arrays von Matrixgröße (Phase 16 / F3; Nachweis im Test).
    denominator = np.repeat(length_norm, np.diff(matrix.indptr))
    denominator += matrix.data
    data = matrix.data
    data *= K1 + 1.0
    data /= denominator
    data *= inverse_document_frequency[matrix.indices]
    return matrix


def score(weights: Any, query_counts: Any) -> Any:
    """Bewertet eine Anfrage gegen die BM25-Gewichte.

    Der Wert eines Chunks ist die Summe der Gewichte aller Anfrage-Terme; mehrfach genannte
    Anfrage-Terme zählen entsprechend mehrfach (klassisches BM25 ohne Anfrage-Sättigung).

    Args:
        weights: Gewichtsmatrix aus :func:`build_weights`.
        query_counts: Dünnbesetzte Termhäufigkeiten der Anfrage ``(1 × Terme)``, erzeugt mit
            demselben Vektorisierer wie ``counts``.

    Returns:
        Eindimensionales Array mit einem Wert je Chunk (Reihenfolge = Zeilen der Matrix).
    """
    return (weights @ query_counts.T).toarray().ravel()
