"""Tests für den Nachtrag der Personenkennungen aus den Rohantworten (Phase 17 / A2, Punkt 3).

Geprüft werden die drei Regeln aus ADR 0041: Zuordnung über die **Werk-DOI**, Übernahme nur bei
**identischer Namensliste**, Widersprüche werden **ausgewiesen, nicht aufgelöst** – dazu die
Anreicherung eines Referenz-Eintrags, dessen Stub-Datei noch keine Kennung trägt.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from scripts import backfill_author_ids

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_MANUAL,
    ORIGIN_RESOLVED,
    MetadataRecord,
    PaperMetadata,
)
from research_graphrag.bibliography.resolve import IDENTITY_ORIGIN_KEY, resolve_metadata
from research_graphrag.bibliography.store import load_records, save_records
from research_graphrag.bibliography.triage import IndexedPaper
from research_graphrag.online.backfill import (
    ACTION_ADDED,
    ACTION_CONFLICT,
    ACTION_MISMATCH,
    ACTION_UPDATED,
    backfill_identities,
    load_raw_authorships,
    render_backfill,
    work_keys,
)

_ORCID = "0000-0002-1825-0097"


def _work(doi: str, authors: list[tuple[str, str, str]]) -> dict[str, object]:
    """Ein OpenAlex-Werk mit Autorennennungen ``(Name, ID, ORCID)``."""
    return {
        "id": "https://openalex.org/W1",
        "doi": f"https://doi.org/{doi}",
        "title": "Ein Werk",
        "authorships": [
            {
                "author": {
                    "display_name": name,
                    "id": f"https://openalex.org/{author_id}" if author_id else None,
                    "orcid": f"https://orcid.org/{orcid}" if orcid else None,
                }
            }
            for name, author_id, orcid in authors
        ],
    }


def _write(raw: Path, name: str, payload: object) -> None:
    """Legt eine Rohantwort ab (Unterordner je Lauf, wie ``store_raw``)."""
    path = raw / "20260901T100000Z" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _paper(
    paper_id: str, authors: tuple[str, ...], *, doi: str = "", arxiv: str = ""
) -> IndexedPaper:
    """Ein Paper des Index, dessen gewonnene Autoren noch keine Kennung tragen."""
    return IndexedPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{paper_id}.pdf",
        document_kind="full",
        metadata=PaperMetadata(paper_id=paper_id, authors=authors, doi=doi, arxiv_id=arxiv),
    )


def test_both_response_forms_are_read_and_xml_is_ignored(tmp_path: Path) -> None:
    """Einzelwerk und Trefferliste zählen; arXiv-XML und Kaputtes werden nicht zum Abbruch."""
    raw = tmp_path / "online_raw"
    _write(raw, "01-openalex.json", _work("10.1145/1111", [("Anna Beispiel", "A1111", "")]))
    _write(
        raw,
        "02-openalex.json",
        {"results": [_work("10.48550/arXiv.2401.00001", [("Bert Muster", "", _ORCID)])]},
    )
    _write(raw, "03-openalex.json", _work("10.1145/3333", [("Ohne Kennung", "", "")]))
    (raw / "20260901T100000Z" / "04-arxiv.xml").write_text("<feed/>", encoding="utf-8")
    (raw / "20260901T100000Z" / "05-openalex.json").write_text("{kaputt", encoding="utf-8")

    index, n_files, n_unreadable = load_raw_authorships(raw)

    assert (n_files, n_unreadable) == (4, 1)
    assert set(index) == {"10.1145/1111", "10.48550/arxiv.2401.00001"}
    assert index["10.1145/1111"][0].author_ids == ("A1111",)
    assert index["10.1145/1111"][0].source == "20260901T100000Z/01-openalex.json"
    assert load_raw_authorships(tmp_path / "fehlt") == ({}, 0, 0)


def test_the_work_key_covers_the_datacite_doi_of_a_preprint() -> None:
    """Ein Preprint wird über ``10.48550/arxiv.<ID>`` gefunden."""
    assert work_keys("10.1145/ABC", "2401.00001") == (
        "10.1145/abc",
        "10.48550/arxiv.2401.00001",
    )


def test_identifiers_are_taken_over_only_for_the_identical_name_list(tmp_path: Path) -> None:
    """Gleiche DOI, andere Namensliste ⇒ keine Zuordnung Kennung ↔ Name belegt."""
    raw = tmp_path / "raw"
    _write(raw, "01-openalex.json", _work("10.1145/1111", [("Anna Beispiel", "A1111", "")]))
    index, _, _ = load_raw_authorships(raw)
    stored = MetadataRecord(
        paper_id="p1",
        origin=ORIGIN_RESOLVED,
        authors=("Anna Beispiel",),
        doi="10.1145/1111",
        confidence=CONFIDENCE_WEAK,
    )

    same = backfill_identities(
        [_paper("p1", ("Anna Beispiel",), doi="10.1145/1111")], [stored], index
    )
    other = backfill_identities(
        [_paper("p1", ("A. Beispiel",), doi="10.1145/1111")], [stored], index
    )

    assert [decision.action for decision in same.decisions] == [ACTION_UPDATED]
    assert same.records[0].author_ids == ("A1111",)
    assert same.records[0].confidence == CONFIDENCE_WEAK
    assert other.decisions == ()
    assert other.records == (stored,)


def test_contradicting_raw_responses_are_reported_not_resolved(tmp_path: Path) -> None:
    """Zwei Rohantworten, zwei Kennungen für dieselbe Person – das entscheidet kein Skript."""
    raw = tmp_path / "raw"
    _write(raw, "01-openalex.json", _work("10.1145/1111", [("Anna Beispiel", "A1111", "")]))
    _write(raw, "02-openalex.json", _work("10.1145/1111", [("Anna Beispiel", "A9999", "")]))
    index, _, _ = load_raw_authorships(raw)

    run = backfill_identities([_paper("p1", ("Anna Beispiel",), doi="10.1145/1111")], [], index)

    assert [decision.action for decision in run.decisions] == [ACTION_CONFLICT]
    assert run.records == ()
    assert "Konflikte (nichts übernommen)" in "\n".join(render_backfill("20260924T1", run))


def test_a_stored_hit_with_another_name_list_is_left_alone(tmp_path: Path) -> None:
    """Die gewonnenen Namen stammen aus ``manual``; der ``resolved``-Datensatz weicht ab."""
    raw = tmp_path / "raw"
    _write(raw, "01-openalex.json", _work("10.1145/1111", [("Anna Beispiel", "A1111", "")]))
    index, _, _ = load_raw_authorships(raw)
    stored = MetadataRecord(paper_id="p1", origin=ORIGIN_RESOLVED, authors=("Jemand Anders",))

    run = backfill_identities(
        [_paper("p1", ("Anna Beispiel",), doi="10.1145/1111")], [stored], index
    )

    assert [decision.action for decision in run.decisions] == [ACTION_MISMATCH]
    assert run.records == (stored,)


def test_a_reference_entry_gets_its_identifiers_through_an_identity_record(
    tmp_path: Path,
) -> None:
    """Die Stub-Datei bleibt unangetastet (sonst änderte sich die Paper-ID); ein Kennungs-Datensatz
    trägt die Kennungen und reichert die identische Namensliste an."""
    raw = tmp_path / "raw"
    _write(
        raw,
        "01-openalex.json",
        _work("10.1145/1111", [("Kun Liu", "A1111", ""), ("Evimaria Terzi", "", _ORCID)]),
    )
    index, _, _ = load_raw_authorships(raw)

    run = backfill_identities(
        [_paper("p1", ("Kun Liu", "Evimaria Terzi"), doi="10.1145/1111")], [], index
    )
    (added,) = run.records
    stub = MetadataRecord(
        paper_id="p1",
        origin=ORIGIN_RESOLVED,
        title="Towards Identity Anonymization on Graphs",
        authors=("Kun Liu", "Evimaria Terzi"),
        year=2008,
        confidence=CONFIDENCE_STRONG,
    )
    resolved = resolve_metadata("p1", [stub, added])

    assert [decision.action for decision in run.decisions] == [ACTION_ADDED]
    assert (added.title, added.year, added.confidence) == ("", 0, CONFIDENCE_STRONG)
    assert resolved.title == "Towards Identity Anonymization on Graphs"
    assert resolved.author_ids == ("A1111", "")
    assert resolved.author_orcids == ("", _ORCID)
    assert resolved.origins[IDENTITY_ORIGIN_KEY] == ORIGIN_RESOLVED
    assert resolved.confidence == CONFIDENCE_STRONG


def test_identifiers_never_reach_a_different_name_list() -> None:
    """Die Anreicherung verlangt dieselbe Liste Position für Position – auch gegenüber ``manual``."""
    resolved_record = MetadataRecord(
        paper_id="p1",
        origin=ORIGIN_RESOLVED,
        authors=("Anna Beispiel", "Bert Muster"),
        author_ids=("A1111", "A2222"),
    )
    reordered = MetadataRecord(
        paper_id="p1", origin=ORIGIN_MANUAL, authors=("Bert Muster", "Anna Beispiel")
    )
    identical = MetadataRecord(
        paper_id="p1", origin=ORIGIN_MANUAL, authors=("Anna Beispiel", "Bert Muster")
    )

    assert resolve_metadata("p1", [resolved_record, reordered]).author_ids == ()
    enriched = resolve_metadata("p1", [resolved_record, identical])
    assert enriched.author_ids == ("A1111", "A2222")
    assert enriched.origins["authors"] == ORIGIN_MANUAL
    assert enriched.origins[IDENTITY_ORIGIN_KEY] == ORIGIN_RESOLVED


def test_papers_that_already_carry_identifiers_are_skipped(tmp_path: Path) -> None:
    """Ein zweiter Lauf nach dem Ingest ändert nichts."""
    raw = tmp_path / "raw"
    _write(raw, "01-openalex.json", _work("10.1145/1111", [("Anna Beispiel", "A1111", "")]))
    index, _, _ = load_raw_authorships(raw)
    paper = IndexedPaper(
        paper_id="p1",
        source_uri="file:///papers/p1.pdf",
        document_kind="full",
        metadata=PaperMetadata(
            paper_id="p1", authors=("Anna Beispiel",), doi="10.1145/1111", author_ids=("A1111",)
        ),
    )

    assert backfill_identities([paper], [], index).decisions == ()


def _run_cli(args: list[str]) -> int:
    """Ruft die CLI mit den gegebenen Argumenten auf."""
    original = sys.argv
    sys.argv = ["backfill_author_ids", *args]
    try:
        return backfill_author_ids.main()
    finally:
        sys.argv = original


def test_the_cli_dry_run_writes_nothing_and_the_run_writes_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--dry-run`` bleibt folgenlos; der echte Lauf schreibt Datensätze und Protokoll."""
    data = tmp_path / "data"
    _write(
        data / "online_raw",
        "01-openalex.json",
        _work("10.1145/1111", [("Anna Beispiel", "A1111", "")]),
    )
    metadata = tmp_path / "metadata" / "paper_metadata.json"
    save_records(
        metadata,
        [MetadataRecord(paper_id="p1", origin=ORIGIN_RESOLVED, authors=("Anna Beispiel",))],
    )
    monkeypatch.setattr(
        backfill_author_ids,
        "load_indexed_papers",
        lambda _path: (_paper("p1", ("Anna Beispiel",), doi="10.1145/1111"),),
    )
    args = ["--data", str(data), "--metadaten", str(metadata), "--index", str(tmp_path / "x")]
    before = metadata.read_bytes()

    assert _run_cli([*args, "--dry-run"]) == 0
    assert metadata.read_bytes() == before

    assert _run_cli(args) == 0
    assert load_records(metadata)[0].author_ids == ("A1111",)
    assert "## Nachtrag Personenkennungen" in (data / "metadata_log.md").read_text(encoding="utf-8")
