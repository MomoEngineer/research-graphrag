"""Tests für die Datentypen der bibliografischen Metadaten (Phase 12 / K1, ADR 0025)."""

from __future__ import annotations

import pytest

from research_graphrag.bibliography.model import (
    CONFIDENCE_NONE,
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_CURATED,
    ORIGIN_EXTRACTED,
    ORIGIN_MANUAL,
    MetadataRecord,
    PaperMetadata,
    empty_metadata,
    lowest_confidence,
    surname_of,
)


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        ("Anna Beispiel", "Beispiel"),
        ("Beispiel, Anna", "Beispiel"),
        ("Anna Maria Beispiel", "Beispiel"),
        ("  Beispiel , Anna ", "Beispiel"),
        ("Cher", "Cher"),
        ("", ""),
    ],
)
def test_surname_handles_both_notations(author: str, expected: str) -> None:
    """Der Nachname wird aus beiden gängigen Schreibweisen gelesen."""
    assert surname_of(author) == expected


def test_record_has_reports_only_non_empty_fields() -> None:
    """``has`` unterscheidet gefüllte von leeren Feldern (auch bei Tupeln und Zahlen)."""
    record = MetadataRecord(
        paper_id="p1", origin=ORIGIN_EXTRACTED, title="Ein Titel", authors=(), year=0, doi="10.1/x"
    )

    assert record.has("title") is True
    assert record.has("authors") is False
    assert record.has("year") is False
    assert record.has("doi") is True
    assert record.value_of("title") == "Ein Titel"


def test_has_returns_true_for_an_explicitly_cleared_empty_field() -> None:
    """Ein in ``cleared_fields`` genanntes Feld gilt als "hat eine Aussage" (ADR 0040)."""
    record = MetadataRecord(
        paper_id="p1",
        origin=ORIGIN_EXTRACTED,
        arxiv_id="",
        doi="",
        cleared_fields=frozenset({"arxiv_id"}),
    )

    assert record.has("arxiv_id") is True
    assert record.has("doi") is False
    assert record.value_of("arxiv_id") == ""


def test_record_round_trip_keeps_cleared_fields() -> None:
    """``cleared_fields`` übersteht die Speicherform unverändert, sortiert serialisiert."""
    record = MetadataRecord(
        paper_id="p1",
        origin=ORIGIN_MANUAL,
        cleared_fields=frozenset({"arxiv_id", "venue"}),
    )

    payload = record.to_dict()
    assert payload["cleared_fields"] == ["arxiv_id", "venue"]
    assert MetadataRecord.from_dict("p1", payload) == record


def test_record_from_dict_tolerates_a_missing_cleared_fields_key() -> None:
    """Eine vor ADR 0040 geschriebene Zeile ohne ``cleared_fields`` bleibt gültig."""
    record = MetadataRecord.from_dict("p1", {"origin": "manual", "arxiv_id": ""})

    assert record.cleared_fields == frozenset()
    assert record.has("arxiv_id") is False


def test_record_round_trip_keeps_every_field() -> None:
    """Ein Datensatz übersteht die Speicherform unverändert."""
    record = MetadataRecord(
        paper_id="p1",
        origin=ORIGIN_CURATED,
        title="Titel",
        authors=("Anna Beispiel", "Bert Muster"),
        year=2024,
        venue="Proceedings",
        doi="10.1/x",
        arxiv_id="2401.00001",
        url="https://example.org",
        confidence=CONFIDENCE_STRONG,
        evidence="Übersicht.md Zeile A3",
    )

    assert MetadataRecord.from_dict("p1", record.to_dict()) == record


def test_record_from_dict_tolerates_a_single_author_string() -> None:
    """Ein einzelner Autor als Zeichenkette wird zu einem Tupel normalisiert."""
    record = MetadataRecord.from_dict("p1", {"origin": "manual", "authors": "Anna Beispiel"})

    assert record.authors == ("Anna Beispiel",)


def test_identifiers_follow_the_citation_precedence() -> None:
    """Die Identifikator-Abbildung nennt DOI vor arXiv vor URL und lässt Leeres weg."""
    metadata = PaperMetadata(
        paper_id="p1", doi="10.1/x", arxiv_id="2401.00001", url="https://example.org"
    )

    assert list(metadata.identifiers) == ["doi", "arxiv", "url"]
    assert PaperMetadata(paper_id="p1", arxiv_id="2401.00001").identifiers == {
        "arxiv": "2401.00001"
    }
    assert empty_metadata("p1").identifiers == {}


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (PaperMetadata(paper_id="p1", doi="10.1/x", arxiv_id="2401.1"), "https://doi.org/10.1/x"),
        (PaperMetadata(paper_id="p1", arxiv_id="2401.1"), "https://arxiv.org/abs/2401.1"),
        (PaperMetadata(paper_id="p1", url="https://example.org"), "https://example.org"),
        (PaperMetadata(paper_id="p1"), ""),
    ],
)
def test_preferred_url_prefers_the_doi(metadata: PaperMetadata, expected: str) -> None:
    """Der bevorzugte Link folgt DOI vor arXiv vor bereits bekannter URL."""
    assert metadata.preferred_url == expected


def test_citation_key_uses_surname_and_year() -> None:
    """Der Zitierschlüssel besteht aus Nachname und Jahr und ist ASCII-sicher."""
    metadata = PaperMetadata(paper_id="abcdef1234567890", authors=("Anna Müßig",), year=2023)

    assert metadata.citation_key() == "Muessig2023"


def test_citation_key_falls_back_to_title_then_paper_id() -> None:
    """Ohne Autor tritt das erste bedeutungstragende Titelwort ein, sonst die paper_id."""
    by_title = PaperMetadata(paper_id="abcdef1234567890", title="The Graph Retrieval", year=2021)

    assert by_title.citation_key() == "Graph2021"
    assert PaperMetadata(paper_id="abcdef1234567890").citation_key() == "abcdef12"
    assert PaperMetadata(paper_id="p1", authors=("Anna Beispiel",)).citation_key() == "Beispiel"


def test_is_citable_requires_title_authors_and_year() -> None:
    """Eine vollständige Angabe braucht Titel, Autoren und Jahr."""
    complete = PaperMetadata(paper_id="p1", title="Titel", authors=("Anna Beispiel",), year=2024)

    assert complete.is_citable() is True
    assert PaperMetadata(paper_id="p1", title="Titel", year=2024).is_citable() is False
    assert PaperMetadata(paper_id="p1", authors=("A B",), year=2024).is_citable() is False
    assert PaperMetadata(paper_id="p1", title="Titel", authors=("A B",)).is_citable() is False


def test_metadata_to_dict_shape() -> None:
    """Die Serialisierung liefert die dokumentierten Schlüssel ohne Stil-Formen."""
    payload = PaperMetadata(
        paper_id="p1",
        title="Titel",
        authors=("Anna Beispiel",),
        year=2024,
        doi="10.1/x",
        origins={"title": ORIGIN_CURATED, "doi": ORIGIN_EXTRACTED},
        confidence=CONFIDENCE_WEAK,
    ).to_dict()

    assert set(payload) == {
        "paper_id",
        "title",
        "authors",
        "year",
        "venue",
        "doi",
        "arxiv_id",
        "url",
        "identifiers",
        "citation_key",
        "origins",
        "confidence",
        "citable",
        "author_identities",
    }
    assert payload["citable"] is True
    assert payload["author_identities"] == [
        {
            "name": "Anna Beispiel",
            "openalex_id": "",
            "orcid": "",
            "person_key": "name:anna beispiel",
            "identity": "name",
        }
    ]
    assert payload["origins"] == {"title": ORIGIN_CURATED, "doi": ORIGIN_EXTRACTED}


def test_lowest_confidence_picks_the_weakest_contribution() -> None:
    """Die Gesamtkonfidenz ist die schwächste beteiligte Stufe."""
    assert lowest_confidence([CONFIDENCE_STRONG, CONFIDENCE_WEAK]) == CONFIDENCE_WEAK
    assert lowest_confidence([CONFIDENCE_STRONG, CONFIDENCE_STRONG]) == CONFIDENCE_STRONG
    assert lowest_confidence([CONFIDENCE_WEAK, CONFIDENCE_NONE]) == CONFIDENCE_NONE
    assert lowest_confidence([]) == CONFIDENCE_NONE
