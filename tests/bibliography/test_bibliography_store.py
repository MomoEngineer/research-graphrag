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
    MetadataRecord,
)
from research_graphrag.bibliography.store import (
    METADATA_DIR,
    METADATA_FILENAME,
    SCHEMA_VERSION,
    load_records,
    metadata_path,
    save_records,
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
