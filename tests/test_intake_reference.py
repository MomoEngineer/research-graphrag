"""Tests für den zweiten Dokumenttyp im Intake (Phase 13 / R2, ADR 0030).

Ergänzt ``test_intake.py`` um die Referenz-Einträge: Sie durchlaufen dieselben drei Prüfstufen,
werden nach ihrem **Titel** benannt und werden von einem später eintreffenden Volltext abgelöst.
Der Upgrade-Pfad ist der heikelste Punkt der Phase – ohne ihn wanderte das echte Paper in die
Quarantäne, während der Abstract-Stub im Korpus bliebe.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from research_graphrag.extraction.model import DOCUMENT_KIND_REFERENCE
from research_graphrag.extraction.quality import FLAG_REFERENCE_WITHOUT_ABSTRACT
from research_graphrag.extraction.refstub import STUB_SUFFIX
from research_graphrag.intake import (
    ACTION_ACCEPTED,
    ACTION_DELETED,
    ACTION_KEPT,
    ACTION_QUARANTINED,
    INTAKE_LOG,
    QUARANTINE_DIR,
    REASON_DUPLICATE_IDENTIFIER,
    REASON_DUPLICATE_SHA256,
    REASON_INVALID_STUB,
    REASON_NEW,
    REASON_SUPERSEDED,
    REASON_UPGRADE,
    IntakeReport,
    run_intake,
    safe_stub_name,
)
from research_graphrag.overview.drafts import REFERENCE_DRAFT_PREFIX
from research_graphrag.pipeline import ingest

MakePdf = Callable[..., Path]

_UEBERSICHT = (
    "# Übersicht\n\n"
    "| ID | Name | Themenfokus | Keyword | Kompakte Zusammenfassung | Interner Link "
    "| Relevanz fuer Expose | SRQ-Zuordnung | Externer Link/Indetifikator |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    "| A1 | Bestehend | x | k | s "
    "| [Quelle](papers/Bestehendes%20Paper%20ueber%20Graph%20Retrieval.pdf) | hoch | SRQ1 | y |\n"
)

_CORPUS_PDF = "Bestehendes Paper ueber Graph Retrieval.pdf"
_BODY = "Retrieval augmented generation over scientific documents is evaluated here. " * 4

_STUB_TITLE = "Towards Identity Anonymization on Graphs at Scale"
_STUB_DOI = "10.1145/1376616.1376629"
_STUB_ARXIV = "2404.16130"
_STUB_ABSTRACT = "Wir zeigen, dass k-Isomorphie eine praktikable Anonymisierung erlaubt. " * 3


def _pages(title: str, identifier: str = "") -> list[str]:
    """Baut zwei Seitentexte mit Titel, optionalem Identifikator und genug Textmasse."""
    return [
        f"{title}\n{identifier}\n1 Introduction\n{_BODY}",
        "2 Evaluation\nThe benchmark reports an F1 score of 0.87 for the proposed system. " + _BODY,
    ]


def _stub_payload(**overrides: object) -> dict[str, object]:
    """Baut den Inhalt einer Stub-Datei in der Form, die R1 schreibt."""
    payload: dict[str, object] = {
        "schema_version": "0.1.0",
        "document_kind": DOCUMENT_KIND_REFERENCE,
        "requested": f"doi:{_STUB_DOI}",
        "title": _STUB_TITLE,
        "authors": ["Anna Beispiel"],
        "year": 2008,
        "venue": "Proceedings of SIGMOD",
        "doi": _STUB_DOI,
        "arxiv_id": "",
        "url": "https://example.org/paper.pdf",
        "source": "OpenAlex",
        "source_url": "https://api.openalex.org/works",
        "retrieved_at": "2026-08-09T10:11:12Z",
        "note": "",
        "abstract": _STUB_ABSTRACT,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def workspace(tmp_path: Path, make_pdf: MakePdf) -> dict[str, Path]:
    """Baut einen Mini-Korpus (1 indiziertes Paper) samt Eingangsordner und Übersicht."""
    make_pdf(
        _pages("Bestehendes Paper ueber Graph Retrieval", "arXiv:2401.11111v1"),
        f"papers/{_CORPUS_PDF}",
    )
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    ingest(papers, data)

    inbox = tmp_path / "new_papers"
    inbox.mkdir()
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_bytes(_UEBERSICHT.encode("utf-8"))
    return {"papers": papers, "data": data, "inbox": inbox, "uebersicht": uebersicht}


def _drop_stub(
    workspace: dict[str, Path], name: str = "ref-x.refjson", **overrides: object
) -> Path:
    """Legt eine Stub-Datei in den Eingangsordner."""
    target = workspace["inbox"] / name
    target.write_text(json.dumps(_stub_payload(**overrides), ensure_ascii=False), encoding="utf-8")
    return target


def _run(workspace: dict[str, Path], *, dry_run: bool = False) -> IntakeReport:
    return run_intake(
        inbox_dir=workspace["inbox"],
        papers_dir=workspace["papers"],
        data_dir=workspace["data"],
        uebersicht_path=workspace["uebersicht"],
        dry_run=dry_run,
    )


def _tree_digest(root: Path) -> dict[str, str]:
    """Hash-Abbild eines Verzeichnisbaums – erkennt jede Änderung an Inhalt oder Bestand."""
    return {
        str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --------------------------------------------------------------------------------------
# Der reguläre Weg
# --------------------------------------------------------------------------------------


def test_a_stub_passes_the_intake_and_is_named_after_its_title(
    workspace: dict[str, Path],
) -> None:
    """Die Konvention „Dateiname = Titel" gilt auch für den zweiten Dokumenttyp."""
    _drop_stub(workspace)

    report = _run(workspace)

    decision = report.decisions[0]
    assert decision.action == ACTION_ACCEPTED
    assert decision.reason == REASON_NEW
    assert decision.target_name == f"{_STUB_TITLE}{STUB_SUFFIX}"
    assert (workspace["papers"] / f"{_STUB_TITLE}{STUB_SUFFIX}").is_file()
    assert not (workspace["inbox"] / "ref-x.refjson").exists()


def test_the_stub_reaches_index_and_overview(workspace: dict[str, Path]) -> None:
    """Der Eintrag ist danach auffindbar und in der Übersicht als solcher gekennzeichnet."""
    _drop_stub(workspace)

    report = _run(workspace)

    assert report.ingest is not None
    assert report.ingest.n_papers == 2
    overview = workspace["uebersicht"].read_text(encoding="utf-8")
    assert _STUB_TITLE in overview
    assert REFERENCE_DRAFT_PREFIX in overview


def test_a_stub_without_abstract_is_flagged(workspace: dict[str, Path]) -> None:
    """Genau ein Befund – die Volltext-Gates gelten hier nicht."""
    _drop_stub(workspace, abstract="")

    report = _run(workspace)

    assert report.decisions[0].flags == (FLAG_REFERENCE_WITHOUT_ABSTRACT,)


def test_the_quality_flags_of_full_text_papers_stay_unchanged(
    workspace: dict[str, Path],
) -> None:
    """Der zweite Dokumenttyp darf den Report der Volltext-Paper nicht verändern."""
    report_path = workspace["data"] / "quality_report.json"
    before = {
        entry["paper_id"]: entry["flags"]
        for entry in json.loads(report_path.read_text(encoding="utf-8"))["papers"]
    }
    _drop_stub(workspace)

    _run(workspace)

    after = {
        entry["paper_id"]: entry["flags"]
        for entry in json.loads(report_path.read_text(encoding="utf-8"))["papers"]
    }
    assert {key: after[key] for key in before} == before


def test_dry_run_changes_nothing(workspace: dict[str, Path], tmp_path: Path) -> None:
    """Die Vorschau zeigt dieselbe Entscheidung und verändert **nichts**."""
    _drop_stub(workspace)
    before = _tree_digest(tmp_path)

    report = _run(workspace, dry_run=True)

    assert report.decisions[0].action == ACTION_ACCEPTED
    assert report.ingest is None
    assert _tree_digest(tmp_path) == before


# --------------------------------------------------------------------------------------
# Die drei Prüfstufen gelten unverändert
# --------------------------------------------------------------------------------------


def test_an_identical_stub_is_deleted(workspace: dict[str, Path]) -> None:
    """Stufe 1 ist dateiformatunabhängig – der bitgenaue Treffer löscht."""
    _drop_stub(workspace)
    _run(workspace)
    again = _drop_stub(workspace, name="nochmal.refjson")

    report = _run(workspace)

    assert report.decisions[0].action == ACTION_DELETED
    assert report.decisions[0].reason == REASON_DUPLICATE_SHA256
    assert not again.exists()


def test_a_stub_for_a_known_identifier_is_quarantined(workspace: dict[str, Path]) -> None:
    """Ein Stub zu einem bereits vorhandenen Paper ist ein Duplikat, kein Upgrade."""
    _drop_stub(workspace, doi="", arxiv_id="2401.11111")

    report = _run(workspace)

    assert report.decisions[0].action == ACTION_QUARANTINED
    assert report.decisions[0].reason == REASON_DUPLICATE_IDENTIFIER
    assert (workspace["inbox"] / QUARANTINE_DIR / "ref-x.refjson").is_file()


def test_a_second_stub_for_the_same_work_is_quarantined(workspace: dict[str, Path]) -> None:
    """Auch Stub gegen Stub greift Stufe 2 – nur der Volltext löst ab."""
    _drop_stub(workspace)
    _run(workspace)
    _drop_stub(workspace, name="zweiter.refjson", abstract="Andere Fassung desselben Werks.")

    report = _run(workspace)

    assert report.decisions[0].action == ACTION_QUARANTINED
    assert report.decisions[0].reason == REASON_DUPLICATE_IDENTIFIER


def test_a_broken_stub_stays_put(workspace: dict[str, Path]) -> None:
    """Die Formatprüfung ist für Stubs, was die PDF-Signatur für PDFs ist."""
    target = workspace["inbox"] / "kaputt.refjson"
    target.write_text("{kein json", encoding="utf-8")

    report = _run(workspace)

    assert report.decisions[0].action == ACTION_KEPT
    assert report.decisions[0].reason == REASON_INVALID_STUB
    assert target.is_file()


def test_a_stub_whose_title_collides_stays_put(workspace: dict[str, Path]) -> None:
    """Die Namenskollision ist eine Tatsache über den Zielort – sie wird zuerst gemeldet."""
    (workspace["papers"] / f"{_STUB_TITLE}{STUB_SUFFIX}").write_text("{}", encoding="utf-8")
    _drop_stub(workspace)

    report = _run(workspace)

    assert report.decisions[0].action == ACTION_KEPT
    assert (workspace["inbox"] / "ref-x.refjson").is_file()


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Ein/Titel: mit \\ Zeichen?", "Ein Titel mit Zeichen.refjson"),
        ("   ", "Referenz-Eintrag.refjson"),
        ("A" * 300, "A" * 120 + ".refjson"),
    ],
)
def test_the_stub_filename_is_filesystem_safe(title: str, expected: str) -> None:
    """Der Titel ist eine fremde Zeichenkette – der Name entsteht über eine Filterung."""
    assert safe_stub_name(title) == expected


# --------------------------------------------------------------------------------------
# Upgrade-Pfad: „Volltext schlägt Referenz-Eintrag"
# --------------------------------------------------------------------------------------


def test_a_full_text_replaces_its_reference_entry(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Ohne diese Regel wanderte das **echte** Paper in die Quarantäne."""
    _drop_stub(workspace, doi="", arxiv_id=_STUB_ARXIV)
    _run(workspace)
    stub_name = f"{_STUB_TITLE}{STUB_SUFFIX}"
    assert (workspace["papers"] / stub_name).is_file()

    make_pdf(
        _pages(_STUB_TITLE, f"arXiv:{_STUB_ARXIV}v1"),
        f"new_papers/{_STUB_TITLE}.pdf",
    )
    report = _run(workspace)

    decision = report.decisions[0]
    assert decision.action == ACTION_ACCEPTED
    assert decision.reason == REASON_UPGRADE
    assert decision.replaces == stub_name
    assert (workspace["papers"] / f"{_STUB_TITLE}.pdf").is_file()
    assert not (workspace["papers"] / stub_name).exists()


def test_the_replacement_is_logged_with_its_own_hash(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Die einzige Löschung in ``papers/`` bekommt eine eigene Zeile mit eigenem Hash."""
    _drop_stub(workspace, doi="", arxiv_id=_STUB_ARXIV)
    _run(workspace)
    stub_hash = hashlib.sha256(
        (workspace["papers"] / f"{_STUB_TITLE}{STUB_SUFFIX}").read_bytes()
    ).hexdigest()

    make_pdf(_pages(_STUB_TITLE, f"arXiv:{_STUB_ARXIV}v1"), f"new_papers/{_STUB_TITLE}.pdf")
    _run(workspace)

    log = (workspace["data"] / INTAKE_LOG).read_text(encoding="utf-8")
    assert REASON_SUPERSEDED in log
    assert stub_hash in log
    assert f"| {ACTION_DELETED} | {_STUB_TITLE}{STUB_SUFFIX} |" in log


def test_the_overview_row_is_retargeted_not_duplicated(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Eine zweite Zeile wäre eine Dublette, keine Zeile ein toter Link."""
    _drop_stub(workspace, doi="", arxiv_id=_STUB_ARXIV)
    _run(workspace)
    rows_before = workspace["uebersicht"].read_text(encoding="utf-8").count("\n|")

    make_pdf(_pages(_STUB_TITLE, f"arXiv:{_STUB_ARXIV}v1"), f"new_papers/{_STUB_TITLE}.pdf")
    _run(workspace)

    overview = workspace["uebersicht"].read_text(encoding="utf-8")
    assert overview.count("\n|") == rows_before
    assert f"{_STUB_TITLE}.pdf" in overview.replace("%20", " ")
    assert STUB_SUFFIX not in overview


def test_the_replaced_stub_leaves_no_orphan(workspace: dict[str, Path], make_pdf: MakePdf) -> None:
    """Ohne das Vergessen bliebe das Canonical des Stubs liegen – das Paper wäre doppelt."""
    _drop_stub(workspace, doi="", arxiv_id=_STUB_ARXIV)
    _run(workspace)

    make_pdf(_pages(_STUB_TITLE, f"arXiv:{_STUB_ARXIV}v1"), f"new_papers/{_STUB_TITLE}.pdf")
    report = _run(workspace)

    assert report.ingest is not None
    assert report.ingest.n_papers == 2  # Bestandspaper und Volltext – kein Stub mehr
    manifest = json.loads((workspace["data"] / "manifest.json").read_text(encoding="utf-8"))
    assert f"{_STUB_TITLE}{STUB_SUFFIX}" not in manifest
    assert len(list((workspace["data"] / "canonical").glob("*.json"))) == 2


def test_the_curated_columns_survive_the_upgrade(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Nur ``Name`` und ``Interner Link`` werden angefasst – Kuratierung bleibt erhalten."""
    _drop_stub(workspace, doi="", arxiv_id=_STUB_ARXIV)
    _run(workspace)
    text = workspace["uebersicht"].read_text(encoding="utf-8")
    curated = text.replace("| (manuell) | (manuell) |", "| sehr hoch | SRQ2 |")
    workspace["uebersicht"].write_bytes(curated.encode("utf-8"))
    first_row = curated.splitlines()[3]

    make_pdf(_pages(_STUB_TITLE, f"arXiv:{_STUB_ARXIV}v1"), f"new_papers/{_STUB_TITLE}.pdf")
    _run(workspace)

    lines = workspace["uebersicht"].read_text(encoding="utf-8").splitlines()
    assert lines[3] == first_row  # die kuratierte Bestandszeile bleibt unberührt
    assert "sehr hoch" in "\n".join(lines)
    assert "SRQ2" in "\n".join(lines)
