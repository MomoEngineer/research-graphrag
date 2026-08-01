"""Reciprocal Rank Fusion (RRF) für die Hybrid-Wertung (Offline-Hybrid, Phase 7 / A4).

Fusioniert mehrere unabhängige Ranglisten **allein über die Ränge**, nicht über die rohen
Scores – BM25- und Kosinus-Werte liegen auf unterschiedlichen, nicht vergleichbaren Skalen,
eine Addition oder Normalisierung wäre daher von der Trefferverteilung der jeweiligen Anfrage
abhängig (Grundsatz: docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).

Für ein Element :math:`d` gilt

.. math:: \\mathrm{RRF}(d) = \\sum_{r \\in R} \\frac{1}{K + \\mathrm{rank}_r(d)}

mit Rängen ab 1. Ein Element, das nur in einer Rangliste auftaucht, erhält nur einen Summanden.
Das Verfahren ist rein und deterministisch (keine Zufallsanteile, keine Zeitabhängigkeit).
"""

from __future__ import annotations

from collections.abc import Sequence

RRF_K = 60
"""Dämpfungskonstante der Rang-Fusion (Standardwert nach Cormack et al., 2009).

Je größer ``K``, desto flacher der Abfall über die Ränge – kleine ``K`` lassen die jeweils
ersten Plätze dominieren. Der Wert ist bewusst eine **feste Konstante** (kein Umgebungs- oder
CLI-Schalter), damit Ergebnisse reproduzierbar bleiben."""


def fuse_rankings(rankings: Sequence[Sequence[int]], *, rrf_k: int = RRF_K) -> dict[int, float]:
    """Fusioniert mehrere Ranglisten zu einer Bewertung je Element.

    Args:
        rankings: Ranglisten von Element-IDs (hier: Zeilenindizes des Index), jeweils
            absteigend nach Relevanz sortiert. Leere Ranglisten sind zulässig.
        rrf_k: Dämpfungskonstante ``K`` (> 0); Default :data:`RRF_K`.

    Returns:
        Abbildung Element-ID → Fusionswert. Enthalten sind genau die Elemente, die in
        mindestens einer Rangliste vorkommen. Die Reihenfolge des Dictionaries ist **nicht**
        die Rangfolge – die Sortierung (inkl. Tie-Break) obliegt dem Aufrufer.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (rrf_k + rank)
    return fused
