"""Tests für die Personenkennung der Autoren (Phase 17 / A2, ADR 0041).

Geprüft werden drei Dinge getrennt: die **Prüfung** fremder Kennungen (eine falsche Kennung ist
schlimmer als keine), die **Positionsgleichheit** zur Namensliste und die **additive**
Speicherform (alte Dateien laden unverändert, Datensätze ohne Kennung schreiben sich wie zuvor).
"""

from __future__ import annotations

import pytest

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    IDENTITY_NAME,
    IDENTITY_OPENALEX,
    IDENTITY_ORCID,
    ORIGIN_MANUAL,
    ORIGIN_RESOLVED,
    AuthorIdentity,
    MetadataRecord,
    PaperMetadata,
    aligned_identifiers,
    identities_of,
    normalize_openalex_author_id,
    normalize_orcid,
    person_key,
    person_name_key,
)
from research_graphrag.bibliography.resolve import resolve_metadata

_ORCID = "0000-0002-1825-0097"
"""Offizielles Beispiel der ORCID-Dokumentation (Prüfziffer 7)."""

_ORCID_X = "0000-0002-1694-233X"
"""Offizielles Beispiel mit Prüfziffer ``X``."""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://openalex.org/A5023888391", "A5023888391"),
        ("A5023888391", "A5023888391"),
        ("a5023888391", "A5023888391"),
        ("  https://openalex.org/A5023888391  ", "A5023888391"),
        ("https://openalex.org/W2741809807", ""),
        ("A12", ""),
        ("A5023888391; DROP TABLE", ""),
        ("", ""),
        (None, ""),
        (42, ""),
    ],
)
def test_openalex_author_ids_are_checked_not_only_shortened(raw: object, expected: str) -> None:
    """Nur das Muster ``A`` + Ziffern gilt; eine Werk-ID oder ein Fremdwert wird leer."""
    assert normalize_openalex_author_id(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f"https://orcid.org/{_ORCID}", _ORCID),
        (_ORCID, _ORCID),
        (_ORCID_X.lower(), _ORCID_X),
        ("0000-0002-1825-0098", ""),
        ("0000-0002-1825-009", ""),
        ("orcid", ""),
        (None, ""),
    ],
)
def test_orcids_are_validated_including_the_check_digit(raw: object, expected: str) -> None:
    """Die Prüfziffer nach ISO 7064 fängt Tippfehler ab, die sonst eine fremde Person trafen."""
    assert normalize_orcid(raw) == expected


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Asai, Akari", "Akari Asai"),
        ("Müller, Jörg", "Jörg Müller"),
        ("Jean-Pierre Dupont", "Jean Pierre Dupont"),
        ("  Anna   Beispiel ", "Anna Beispiel"),
    ],
)
def test_both_name_notations_fall_together(left: str, right: str) -> None:
    """„Nachname, Vorname" und „Vorname Nachname" ergeben denselben Schlüssel."""
    assert person_name_key(left) == person_name_key(right)


def test_the_name_key_folds_like_the_citation_key() -> None:
    """Es gibt nur **eine** Faltung: Umlaute werden transliteriert, Initialen bleiben erhalten."""
    assert person_name_key("Müller, Jörg") == "joerg mueller"
    assert person_name_key("Y. Wang") == "y wang"
    assert person_name_key("  ") == ""


def test_person_key_prefers_the_identifier_and_marks_bare_names() -> None:
    """Kennung vor Name; eine reine Namensidentität ist am Präfix erkennbar."""
    assert person_key("Akari Asai", "A5023888391", _ORCID) == "A5023888391"
    assert person_key("Akari Asai", "", _ORCID) == f"orcid:{_ORCID}"
    assert person_key("Asai, Akari") == "name:akari asai"


def test_identity_status_is_reported_per_author() -> None:
    """Die Ausgabe nennt je Autor den Identitätsstatus – nie still eine Namensgleichheit."""
    assert AuthorIdentity("A", openalex_id="A1234").identity == IDENTITY_OPENALEX
    assert AuthorIdentity("A", orcid=_ORCID).identity == IDENTITY_ORCID
    assert AuthorIdentity("A").identity == IDENTITY_NAME
    assert AuthorIdentity("Anna Beispiel", openalex_id="A1234").to_dict() == {
        "name": "Anna Beispiel",
        "openalex_id": "A1234",
        "orcid": "",
        "person_key": "A1234",
        "identity": IDENTITY_OPENALEX,
    }


def test_identifier_lists_must_stand_parallel_to_the_names() -> None:
    """Passt die Länge nicht, ist die Zuordnung nicht belegbar – die Liste entfällt ganz."""
    authors = ("Anna Beispiel", "Bert Muster")
    assert aligned_identifiers(authors, ("A1234", "")) == ("A1234", "")
    assert aligned_identifiers(authors, ("A1234",)) == ()
    assert aligned_identifiers(authors, ("", "")) == ()
    assert aligned_identifiers(authors, ()) == ()


def test_identities_pair_names_with_their_identifiers() -> None:
    """Namen und Kennungen werden positionsgleich verbunden."""
    identities = identities_of(("Anna Beispiel", "Bert Muster"), ("A1234", ""), ("", _ORCID))

    assert [entry.person_key for entry in identities] == ["A1234", f"orcid:{_ORCID}"]


def test_a_record_with_identifiers_survives_the_round_trip() -> None:
    """Die Kennungen werden gespeichert und unverändert wieder gelesen."""
    record = MetadataRecord(
        paper_id="p1",
        origin=ORIGIN_RESOLVED,
        authors=("Anna Beispiel", "Bert Muster"),
        author_ids=("A1234", ""),
        author_orcids=(_ORCID, ""),
    )

    payload = record.to_dict()
    restored = MetadataRecord.from_dict("p1", payload)

    assert payload["author_ids"] == ["A1234", ""]
    assert restored == record
    assert [entry.identity for entry in restored.author_identities] == [
        IDENTITY_OPENALEX,
        IDENTITY_NAME,
    ]


def test_a_record_without_identifiers_is_written_as_before() -> None:
    """Ohne Kennung entstehen keine neuen Schlüssel – alte Dateien bleiben byte-identisch."""
    payload = MetadataRecord(paper_id="p1", origin=ORIGIN_MANUAL, authors=("A B",)).to_dict()

    assert "author_ids" not in payload
    assert "author_orcids" not in payload


def test_an_old_file_without_the_keys_loads_unchanged() -> None:
    """Ein vor ADR 0041 geschriebener Datensatz liest sich ohne Kennungen, ohne Fehler."""
    record = MetadataRecord.from_dict(
        "p1", {"origin": ORIGIN_RESOLVED, "authors": ["Anna Beispiel"], "year": 2024}
    )

    assert record.author_ids == ()
    assert record.author_orcids == ()


def test_hand_edited_identifiers_are_checked_again() -> None:
    """Eine ungültige Kennung wird leer, eine verschobene Liste entfällt ganz."""
    shifted = MetadataRecord.from_dict(
        "p1",
        {
            "origin": ORIGIN_RESOLVED,
            "authors": ["Anna Beispiel", "Bert Muster"],
            "author_ids": ["A1234"],
            "author_orcids": ["0000-0002-1825-0098", _ORCID],
        },
    )

    assert shifted.author_ids == ()
    assert shifted.author_orcids == ("", _ORCID)


def test_identifiers_travel_with_the_winning_author_list() -> None:
    """Eine Kennung darf nie an einen Namen aus einer anderen Quelle geraten."""
    resolved = MetadataRecord(
        paper_id="p1",
        origin=ORIGIN_RESOLVED,
        title="Titel",
        authors=("Anna Beispiel",),
        author_ids=("A1234",),
        confidence=CONFIDENCE_STRONG,
    )
    manual = MetadataRecord(
        paper_id="p1",
        origin=ORIGIN_MANUAL,
        authors=("Anna Beispiel-Neu",),
        confidence=CONFIDENCE_STRONG,
    )

    only_resolved = resolve_metadata("p1", [resolved])
    with_manual = resolve_metadata("p1", [resolved, manual])

    assert only_resolved.author_ids == ("A1234",)
    assert with_manual.authors == ("Anna Beispiel-Neu",)
    assert with_manual.author_ids == ()
    assert with_manual.author_identities[0].identity == IDENTITY_NAME


def test_paper_metadata_exposes_the_identities_additively() -> None:
    """``author_identities`` ergänzt die Ausgabe; ``authors`` bleibt unverändert."""
    payload = PaperMetadata(
        paper_id="p1", authors=("Anna Beispiel",), author_ids=("A1234",)
    ).to_dict()

    assert payload["authors"] == ["Anna Beispiel"]
    assert payload["author_identities"][0]["person_key"] == "A1234"
