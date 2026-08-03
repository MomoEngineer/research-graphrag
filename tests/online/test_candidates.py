"""Tests für Kandidaten-Modell und Deduplikation (Phase 9 / S1)."""

from __future__ import annotations

import pytest

from research_graphrag.intake import CorpusView
from research_graphrag.online.candidates import (
    MATCH_IDENTIFIER,
    MATCH_TITLE,
    SOURCE_ARXIV,
    SOURCE_OPENALEX,
    Candidate,
    classify,
    filter_recent,
    merge_candidates,
    partition,
)

_TITLE = "Graph Retrieval Augmented Generation for Scientific Corpora"
_OTHER = "Infrastructure as Code Defect Prediction with Language Models"


def _candidate(**overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "title": _TITLE,
        "year": 2025,
        "sources": (SOURCE_ARXIV,),
        "arxiv_id": "2501.00001",
        "doi": "",
        "abstract": "kurz",
        "url": "https://example.org/a.pdf",
        "license": "",
        "query_id": "C1",
        "reason": "Community 1",
    }
    defaults.update(overrides)
    return Candidate(**defaults)  # type: ignore[arg-type]


def _corpus(
    *, identifiers: dict[tuple[str, str], str] | None = None, titles: dict[str, str] | None = None
) -> CorpusView:
    return CorpusView(
        sha256_to_name={},
        identifier_to_paper=identifiers or {},
        titles=titles or {},
    )


def test_identifier_prefers_arxiv_over_doi() -> None:
    """Für die Anzeige ist die arXiv-ID der sprechendere Identifikator."""
    candidate = _candidate(arxiv_id="2501.00001", doi="10.1000/xyz")

    assert candidate.identifier == "arXiv:2501.00001"


def test_identifier_falls_back_to_doi() -> None:
    """Ohne arXiv-ID wird der DOI ausgewiesen."""
    assert _candidate(arxiv_id="", doi="10.1000/xyz").identifier == "10.1000/xyz"


def test_merge_joins_same_paper_from_both_sources() -> None:
    """Der in S0 gemessene Fall: dasselbe Paper, zwei Quellen, verschiedene Identifikatoren."""
    from_arxiv = _candidate(arxiv_id="2501.00001", doi="", sources=(SOURCE_ARXIV,))
    from_openalex = _candidate(
        arxiv_id="",
        doi="10.1000/abc",
        sources=(SOURCE_OPENALEX,),
        abstract="deutlich ausführlicherer Abstract",
        license="cc-by",
        url="",
    )

    merged = merge_candidates([from_arxiv, from_openalex])

    assert len(merged) == 1
    assert merged[0].sources == (SOURCE_ARXIV, SOURCE_OPENALEX)
    assert merged[0].arxiv_id == "2501.00001"
    assert merged[0].doi == "10.1000/abc"
    assert merged[0].abstract == "deutlich ausführlicherer Abstract"
    assert merged[0].license == "cc-by"
    assert merged[0].url == "https://example.org/a.pdf"


def test_merge_keeps_earliest_year() -> None:
    """Ein Preprint bleibt maßgeblich – sonst umgeht ein Nachdruck den Aktualitätsfilter."""
    merged = merge_candidates(
        [_candidate(year=2019, doi="10.1000/abc"), _candidate(year=2025, doi="10.1000/abc")]
    )

    assert merged[0].year == 2019


def test_merge_keeps_distinct_papers_apart() -> None:
    """Verschiedene Paper werden nicht zusammengelegt."""
    merged = merge_candidates(
        [_candidate(), _candidate(title=_OTHER, arxiv_id="2501.00002", doi="")]
    )

    assert len(merged) == 2


def test_merge_preserves_first_appearance_order() -> None:
    """Die Reihenfolge des ersten Auftretens bleibt erhalten (Determinismus)."""
    first = _candidate(title=_OTHER, arxiv_id="2501.00002")
    second = _candidate()

    merged = merge_candidates([first, second, _candidate(arxiv_id="2501.00001")])

    assert [item.arxiv_id for item in merged] == ["2501.00002", "2501.00001"]


def test_classify_detects_known_identifier() -> None:
    """Ein Identifikator-Treffer gegen den Korpus wird mit Beleg gemeldet."""
    corpus = _corpus(identifiers={("arxiv", "2501.00001"): "paper-1"})

    verdict = classify(_candidate(), corpus)

    assert verdict is not None
    assert verdict.match == MATCH_IDENTIFIER
    assert verdict.evidence == "arxiv:2501.00001"


def test_classify_detects_known_title() -> None:
    """Ohne Identifikator greift der Titelabgleich mit der Schwelle des Intake."""
    corpus = _corpus(titles={"graph retrieval augmented generation for scientific corpora": _TITLE})

    verdict = classify(_candidate(arxiv_id="", doi=""), corpus)

    assert verdict is not None
    assert verdict.match == MATCH_TITLE
    assert _TITLE in verdict.evidence


def test_classify_returns_none_for_unknown_paper() -> None:
    """Ein unbekanntes Paper bleibt ein Vorschlag."""
    assert (
        classify(_candidate(arxiv_id="", doi=""), _corpus(titles={"etwas ganz anderes": "x"}))
        is None
    )


def test_classify_ignores_titles_below_the_minimum() -> None:
    """Zu kurze Titel taugen nicht als Beleg – Präzision vor Recall."""
    corpus = _corpus(titles={"kurz": "Kurz"})

    assert classify(_candidate(title="Kurz", arxiv_id="", doi=""), corpus) is None


def test_known_limit_short_title_without_identifier_is_reported_as_new() -> None:
    """Bekannte Grenze: ohne Identifikator **und** mit zu kurzem Titel greift kein Schlüssel.

    Am realen Korpus trifft das genau ein Paper. Die Folge ist hinnehmbar, weil dieser Abgleich
    eine Bequemlichkeit ist – die Absicherung gegen Doppelbestand liegt beim Intake, der beim
    Übernehmen bitgenau über sha256 prüft (ADR 0020, Abschnitt „Konsequenzen").
    """
    corpus = _corpus(titles={"agentic code reasoning": "Agentic Code Reasoning"})

    verdict = classify(_candidate(title="Agentic Code Reasoning", arxiv_id="", doi=""), corpus)

    assert verdict is None


def test_partition_splits_new_from_known() -> None:
    """Die Trennung erhält die Eingabereihenfolge beider Gruppen."""
    corpus = _corpus(identifiers={("arxiv", "2501.00001"): "paper-1"})
    fresh, known = partition(
        [_candidate(), _candidate(title=_OTHER, arxiv_id="2501.99999")], corpus
    )

    assert [item.arxiv_id for item in fresh] == ["2501.99999"]
    assert [item.candidate.arxiv_id for item in known] == ["2501.00001"]


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2026, True), (2021, True), (2020, False), (0, True)],
)
def test_filter_recent_applies_threshold(year: int, expected: bool) -> None:
    """Ab der Grenze bleiben Kandidaten; eine fehlende Angabe belegt keine Veralterung."""
    kept = filter_recent([_candidate(year=year)], 2021)

    assert bool(kept) is expected
