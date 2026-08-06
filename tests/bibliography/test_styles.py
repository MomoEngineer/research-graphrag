"""Tests für die Literaturangaben in Harvard und APA (Phase 12 / K1, ADR 0025)."""

from __future__ import annotations

import pytest

from research_graphrag.bibliography.model import PaperMetadata
from research_graphrag.bibliography.styles import (
    STYLE_APA,
    STYLE_HARVARD,
    STYLES,
    format_in_text,
    format_reference,
    reference_payload,
)
from research_graphrag.errors import DomainError, ErrorCode


def _metadata(**fields: object) -> PaperMetadata:
    """Baut einen Metadaten-Datensatz mit sinnvollen Vorgaben."""
    base: dict[str, object] = {
        "paper_id": "p1",
        "title": "Graph Retrieval for Scientific Corpora",
        "authors": ("Anna Beispiel", "Bert Muster"),
        "year": 2024,
        "venue": "Proceedings of ACL",
        "doi": "10.1145/abc",
    }
    base.update(fields)
    return PaperMetadata(**base)  # type: ignore[arg-type]


def test_apa_reference_uses_ampersand_and_initials_with_spaces() -> None:
    """APA nennt Nachname, Initialen mit Leerzeichen und verbindet mit ``&``."""
    reference = format_reference(_metadata(), STYLE_APA)

    assert reference == (
        "Beispiel, A., & Muster, B. (2024). Graph Retrieval for Scientific Corpora. "
        "Proceedings of ACL. https://doi.org/10.1145/abc"
    )


def test_harvard_reference_quotes_the_title_and_prefixes_the_link() -> None:
    """Harvard setzt den Titel in einfache Anführungszeichen und nennt ``Available at``."""
    reference = format_reference(_metadata(), STYLE_HARVARD)

    assert reference == (
        "Beispiel, A. and Muster, B. (2024) 'Graph Retrieval for Scientific Corpora', "
        "Proceedings of ACL. Available at: https://doi.org/10.1145/abc"
    )


def test_harvard_shortens_from_the_fourth_author() -> None:
    """Ab vier Autoren kürzt Cite Them Right mit ``et al.``."""
    many = _metadata(authors=("A Eins", "B Zwei", "C Drei", "D Vier"))

    assert format_reference(many, STYLE_HARVARD).startswith("Eins, A. et al. (2024)")
    assert "Vier" in format_reference(many, STYLE_APA)


def test_apa_shortens_only_beyond_twenty_authors() -> None:
    """APA listet bis zu 20 Autoren und kürzt danach mit einer Auslassung."""
    authors = tuple(f"Vorname{index} Nachname{index}" for index in range(1, 26))

    reference = format_reference(_metadata(authors=authors), STYLE_APA)

    assert "..." in reference
    assert "Nachname25, V." in reference
    assert "Nachname20" not in reference


def test_missing_year_is_marked_per_style_instead_of_guessed() -> None:
    """Ein fehlendes Jahr wird stiltypisch gekennzeichnet, nie geraten."""
    without_year = _metadata(year=0)

    assert "(n.d.)." in format_reference(without_year, STYLE_APA)
    assert "(no date)" in format_reference(without_year, STYLE_HARVARD)


def test_missing_authors_move_the_title_to_the_front() -> None:
    """Ohne Autoren beginnt die Angabe mit dem Titel."""
    anonymous = _metadata(authors=())

    assert format_reference(anonymous, STYLE_APA).startswith(
        "Graph Retrieval for Scientific Corpora. (2024)."
    )
    assert format_reference(anonymous, STYLE_HARVARD).startswith(
        "Graph Retrieval for Scientific Corpora (2024)"
    )


def test_empty_metadata_stays_readable() -> None:
    """Ein völlig leerer Datensatz erzeugt eine erkennbare Platzhalter-Angabe."""
    empty = PaperMetadata(paper_id="p1")

    assert format_reference(empty, STYLE_APA) == "Ohne Titel. (n.d.)."
    assert format_in_text(empty, STYLE_APA) == "(Ohne Titel, n.d.)"


def test_reference_without_identifier_omits_the_link() -> None:
    """Ohne DOI/arXiv/URL entfällt der Linkteil, statt leer zu bleiben."""
    reference = format_reference(_metadata(doi=""), STYLE_HARVARD)

    assert "Available at" not in reference
    assert reference.endswith("Proceedings of ACL.")


def test_arxiv_only_metadata_links_to_arxiv() -> None:
    """Ohne DOI verweist die Angabe auf die arXiv-Seite."""
    reference = format_reference(_metadata(doi="", arxiv_id="2401.00001"), STYLE_APA)

    assert reference.endswith("https://arxiv.org/abs/2401.00001")


@pytest.mark.parametrize(
    ("authors", "style", "expected"),
    [
        (("Anna Beispiel",), STYLE_APA, "(Beispiel, 2024)"),
        (("Anna Beispiel", "Bert Muster"), STYLE_APA, "(Beispiel & Muster, 2024)"),
        (("Anna Beispiel", "Bert Muster"), STYLE_HARVARD, "(Beispiel and Muster, 2024)"),
        (("A Eins", "B Zwei", "C Drei"), STYLE_APA, "(Eins et al., 2024)"),
        (("A Eins", "B Zwei", "C Drei"), STYLE_HARVARD, "(Eins et al., 2024)"),
    ],
)
def test_in_text_citation_follows_the_style(
    authors: tuple[str, ...], style: str, expected: str
) -> None:
    """Der Kurzbeleg folgt den Verbindungs- und Kürzungsregeln des jeweiligen Stils."""
    assert format_in_text(_metadata(authors=authors), style) == expected


def test_initials_come_from_every_given_name() -> None:
    """Mehrere Vornamen ergeben mehrere Initialen (APA mit, Harvard ohne Leerzeichen)."""
    metadata = _metadata(authors=("Anna Maria Beispiel",))

    assert format_reference(metadata, STYLE_APA).startswith("Beispiel, A. M. (2024)")
    assert format_reference(metadata, STYLE_HARVARD).startswith("Beispiel, A.M. (2024)")


def test_surname_first_notation_is_accepted() -> None:
    """Die Schreibweise ``Nachname, Vorname`` liefert dasselbe Ergebnis."""
    assert format_reference(_metadata(authors=("Beispiel, Anna",)), STYLE_APA).startswith(
        "Beispiel, A. (2024)"
    )


def test_unknown_style_is_rejected_with_a_domain_error() -> None:
    """Ein unbekannter Stil ist ein fachlicher Eingabefehler."""
    with pytest.raises(DomainError) as excinfo:
        format_reference(_metadata(), "chicago")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT
    assert "harvard" in excinfo.value.message

    with pytest.raises(DomainError):
        format_in_text(_metadata(), "mla")


def test_style_names_are_case_insensitive() -> None:
    """Groß-/Kleinschreibung des Stilnamens spielt keine Rolle."""
    assert format_reference(_metadata(), "APA") == format_reference(_metadata(), STYLE_APA)


def test_payload_adds_both_styles_to_the_data() -> None:
    """Die Ausgabeform ergänzt die Felder um beide Stile und die Kurzbelege."""
    payload = reference_payload(_metadata())

    assert payload["harvard"].startswith("Beispiel, A. and Muster, B.")
    assert payload["apa"].startswith("Beispiel, A., & Muster, B.")
    assert set(payload["in_text"]) == set(STYLES)
    assert payload["citation_key"] == "Beispiel2024"
    assert payload["citable"] is True
