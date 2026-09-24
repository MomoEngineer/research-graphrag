"""Tests für die Persistenz der bibliografischen Datensätze (Phase 12 / K1, ADR 0025)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    ORIGIN_MANUAL,
    ORIGIN_RESOLVED,
    REVIEW_UNRESOLVABLE,
    MetadataRecord,
    Rejection,
)
from research_graphrag.bibliography.store import (
    METADATA_DIR,
    METADATA_FILENAME,
    SCHEMA_VERSION,
    add_rejection,
    load_records,
    load_reviews,
    metadata_path,
    save_records,
    set_review_status,
    upsert_records,
)
from research_graphrag.errors import DomainError, ErrorCode


def _record(paper_id: str, origin: str, title: str) -> MetadataRecord:
    """Baut einen Datensatz mit Titel und starkem Beleg."""
    return MetadataRecord(
        paper_id=paper_id,
        origin=origin,
        title=title,
        authors=("Anna Beispiel",),
        year=2024,
        confidence=CONFIDENCE_STRONG,
        evidence="Test",
    )


def test_metadata_path_points_into_the_versioned_folder(tmp_path: Path) -> None:
    """Die Datei liegt unter ``metadata/`` und damit außerhalb der abgeleiteten Artefakte."""
    path = metadata_path(tmp_path)

    assert path.parent.name == METADATA_DIR
    assert path.name == METADATA_FILENAME


def test_round_trip_preserves_every_record(tmp_path: Path) -> None:
    """Gespeicherte Datensätze werden unverändert zurückgelesen."""
    target = tmp_path / "paper_metadata.json"
    records = (_record("p2", ORIGIN_MANUAL, "Zweitens"), _record("p1", ORIGIN_RESOLVED, "Erstens"))

    assert save_records(target, records) == 2
    assert set(load_records(target)) == set(records)


def test_written_file_is_deterministic_and_uses_lf(tmp_path: Path) -> None:
    """Zwei Läufe schreiben byte-identisch – auch unter Windows (kein CRLF)."""
    target = tmp_path / "paper_metadata.json"
    records = [_record("p2", ORIGIN_MANUAL, "Zweitens"), _record("p1", ORIGIN_RESOLVED, "Erstens")]

    save_records(target, records)
    first = target.read_bytes()
    save_records(target, list(reversed(records)))

    assert target.read_bytes() == first
    assert b"\r\n" not in first
    assert json.loads(first.decode("utf-8"))["schema_version"] == SCHEMA_VERSION


def test_no_temporary_file_remains(tmp_path: Path) -> None:
    """Der atomare Schreibvorgang lässt keine Temporärdatei zurück."""
    target = tmp_path / "paper_metadata.json"
    save_records(target, [_record("p1", ORIGIN_MANUAL, "Titel")])

    assert list(tmp_path.iterdir()) == [target]


def test_concurrent_saves_do_not_crash_on_a_shared_temp_path(tmp_path: Path) -> None:
    """Nahezu gleichzeitige ``save_records``-Aufrufe kollidieren nicht mehr auf einem festen
    ``*.tmp``-Pfad (ADR 0039, Nachtrag) – siehe die analoge Begründung in
    ``test_online_report.test_concurrent_appends_do_not_crash_on_a_shared_temp_path``. Relevant,
    weil ein MCP-Client zwei ``correct_paper_metadata``-Aufrufe ohne Warten auf die erste Antwort
    abschicken kann.
    """
    target = tmp_path / "paper_metadata.json"
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []

    def write(index: int) -> None:
        barrier.wait()
        try:
            save_records(target, [_record(f"p{index}", ORIGIN_MANUAL, f"Titel {index}")])
        except BaseException as exc:  # noqa: BLE001 - jede Ausnahme ist hier ein Testfehlschlag
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert target.is_file()
    assert list(tmp_path.glob("*.tmp")) == []


def test_missing_file_is_not_an_error(tmp_path: Path) -> None:
    """Ohne Datei gibt es schlicht keine Datensätze."""
    assert load_records(tmp_path / "fehlt.json") == ()


def test_broken_json_is_reported_as_parse_error(tmp_path: Path) -> None:
    """Defektes JSON ist ein fachlicher Parse-Fehler."""
    target = tmp_path / "paper_metadata.json"
    target.write_text("{kein json", encoding="utf-8")

    with pytest.raises(DomainError) as excinfo:
        load_records(target)

    assert excinfo.value.code is ErrorCode.PARSE_ERROR


@pytest.mark.parametrize(
    "payload",
    [
        '["kein objekt"]',
        '{"schema_version": "9.9.9", "papers": {}}',
        '{"schema_version": "0.1.0", "papers": []}',
        '{"schema_version": "0.1.0", "papers": {"p1": {"origin": "manual"}}}',
        '{"schema_version": "0.1.0", "papers": {"p1": ["kein objekt"]}}',
    ],
)
def test_unexpected_structure_is_a_constraint_violation(tmp_path: Path, payload: str) -> None:
    """Falsche Struktur oder Version wird abgelehnt statt still fehlinterpretiert."""
    target = tmp_path / "paper_metadata.json"
    target.write_text(payload, encoding="utf-8")

    with pytest.raises(DomainError) as excinfo:
        load_records(target)

    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_upsert_replaces_per_paper_and_origin(tmp_path: Path) -> None:
    """Ein erneuter Lauf überschreibt seine eigenen Ergebnisse, nicht die Handpflege."""
    existing = [
        _record("p1", ORIGIN_MANUAL, "von Hand"),
        _record("p1", ORIGIN_RESOLVED, "alt aufgelöst"),
    ]
    merged = upsert_records(existing, [_record("p1", ORIGIN_RESOLVED, "neu aufgelöst")])

    titles = {record.origin: record.title for record in merged}
    assert titles == {ORIGIN_MANUAL: "von Hand", ORIGIN_RESOLVED: "neu aufgelöst"}


def test_upsert_keeps_records_of_other_papers() -> None:
    """Datensätze anderer Paper bleiben unangetastet."""
    merged = upsert_records(
        [_record("p1", ORIGIN_RESOLVED, "eins")], [_record("p2", ORIGIN_RESOLVED, "zwei")]
    )

    assert {record.paper_id for record in merged} == {"p1", "p2"}


# --------------------------------------------------------------------------------------
# Prüfstand: Ablehnungsvermerke und Status (Phase 17 / A1, ADR 0042)
# --------------------------------------------------------------------------------------

_REJECTION = Rejection(doi="10.1/fremd", title="Fremdes Paper", reason="Test", date="2026-09-24")


def test_writing_only_records_never_loses_a_rejection(tmp_path: Path) -> None:
    """Auflösungslauf und Korrektur-Tool schreiben nur Datensätze – der Vermerk muss bleiben."""
    target = tmp_path / "paper_metadata.json"
    reviews = add_rejection({}, "p1", _REJECTION)
    save_records(target, [_record("p1", ORIGIN_MANUAL, "A")], reviews=reviews)

    save_records(target, [_record("p1", ORIGIN_MANUAL, "B")])

    assert load_reviews(target)["p1"].rejections == (_REJECTION,)
    assert load_records(target)[0].title == "B"


def test_a_file_without_reviews_stays_byte_identical(tmp_path: Path) -> None:
    """Der Schlüssel ist additiv: ohne Prüfstand kein neuer Schlüssel in der Datei."""
    target = tmp_path / "paper_metadata.json"
    save_records(target, [_record("p1", ORIGIN_RESOLVED, "Titel")])

    assert "reviews" not in json.loads(target.read_text(encoding="utf-8"))
    assert load_reviews(target) == {}
    assert load_reviews(tmp_path / "fehlt.json") == {}


def test_a_rejection_is_recorded_once() -> None:
    """Derselbe Vermerk wird nicht doppelt geführt."""
    reviews = add_rejection(add_rejection({}, "p1", _REJECTION), "p1", _REJECTION)

    assert reviews["p1"].rejections == (_REJECTION,)


def test_the_status_needs_a_known_value_and_a_reason() -> None:
    """„Nicht auflösbar“ ist eine begründete Aussage, kein Schalter."""
    with pytest.raises(DomainError) as unknown:
        set_review_status({}, "p1", "vielleicht", "Grund")
    with pytest.raises(DomainError) as missing:
        set_review_status({}, "p1", REVIEW_UNRESOLVABLE, "  ")

    assert unknown.value.code is ErrorCode.INVALID_INPUT
    assert missing.value.code is ErrorCode.INVALID_INPUT


def test_the_status_can_be_set_and_cleared(tmp_path: Path) -> None:
    """Ein gesetzter Status überlebt das Speichern; ein aufgehobener verschwindet samt Grund."""
    target = tmp_path / "paper_metadata.json"
    marked = set_review_status({}, "p1", REVIEW_UNRESOLVABLE, "nur als Buchkapitel")
    save_records(target, [], reviews=marked)

    loaded = load_reviews(target)
    cleared = set_review_status(loaded, "p1", "", "")
    save_records(target, [], reviews=cleared)

    assert (loaded["p1"].status, loaded["p1"].reason) == (
        REVIEW_UNRESOLVABLE,
        "nur als Buchkapitel",
    )
    assert load_reviews(target) == {}


def test_an_unknown_status_in_the_file_counts_as_unset(tmp_path: Path) -> None:
    """Eine von Hand eingetragene Fantasie-Angabe wird nicht als Status ausgewiesen."""
    target = tmp_path / "paper_metadata.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "papers": {},
                "reviews": {"p1": {"status": "irgendwas", "reason": "x", "rejections": ["kaputt"]}},
            }
        ),
        encoding="utf-8",
    )

    assert load_reviews(target) == {}


def test_reviews_that_are_no_object_are_a_constraint_violation(tmp_path: Path) -> None:
    """Eine strukturell falsche Datei wird gemeldet, nicht still übergangen."""
    target = tmp_path / "paper_metadata.json"
    target.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "papers": {}, "reviews": []}),
        encoding="utf-8",
    )

    with pytest.raises(DomainError) as excinfo:
        load_reviews(target)

    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION
