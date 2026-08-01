"""Tests für die Reciprocal Rank Fusion (Phase 7 / A4)."""

from __future__ import annotations

import pytest

from research_graphrag.indexing.fusion import RRF_K, fuse_rankings


def test_single_ranking_matches_formula() -> None:
    """Der Wert eines Elements ist exakt ``1 / (K + Rang)`` mit Rängen ab 1."""
    fused = fuse_rankings([[7, 3]])

    assert fused[7] == pytest.approx(1.0 / (RRF_K + 1))
    assert fused[3] == pytest.approx(1.0 / (RRF_K + 2))


def test_agreement_beats_single_list_leader() -> None:
    """Ein in beiden Listen mittelmäßiges Element schlägt einen einseitigen Spitzenreiter."""
    fused = fuse_rankings([[1, 2], [3, 2]])

    assert fused[2] > fused[1]
    assert fused[2] > fused[3]


def test_only_ranked_items_appear() -> None:
    """Enthalten sind genau die Elemente aus mindestens einer Rangliste."""
    assert set(fuse_rankings([[4], [5, 4]])) == {4, 5}


def test_empty_rankings_yield_empty_result() -> None:
    """Leere Eingaben ergeben eine leere Bewertung (kein Sonderfall im Aufrufer nötig)."""
    assert fuse_rankings([]) == {}
    assert fuse_rankings([[], []]) == {}


def test_smaller_k_sharpens_the_top_ranks() -> None:
    """Ein kleineres ``K`` spreizt die vorderen Ränge stärker."""
    sharp = fuse_rankings([[1, 2]], rrf_k=1)
    flat = fuse_rankings([[1, 2]], rrf_k=1000)

    assert sharp[1] - sharp[2] > flat[1] - flat[2]


def test_fusion_is_deterministic() -> None:
    """Gleiche Ranglisten erzeugen dieselben Werte."""
    rankings = [[9, 8, 7], [7, 9]]

    assert fuse_rankings(rankings) == fuse_rankings(rankings)
