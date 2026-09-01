"""Tests für den Korpus-Intake (Phase 8, docs/adr/0019-corpus-intake-new-papers-phase8.md).

Deckt die drei Prüfstufen mit ihren **abgestuften** Konsequenzen ab, die Wirkungslosigkeit von
``--dry-run``, die Idempotenz der Übersicht-Zeile sowie die beiden Härtungen des
Identifikator-Vergleichs (Frontmatter-Beleg und Eindeutigkeit).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import (
    SECTION_KIND_REFERENCES,
    CanonicalPaper,
    Chunk,
    Section,
)
from research_graphrag.intake import (
    ACTION_ACCEPTED,
    ACTION_DELETED,
    ACTION_KEPT,
    ACTION_QUARANTINED,
    INTAKE_LOG,
    QUARANTINE_DIR,
    REASON_DUPLICATE_IDENTIFIER,
    REASON_DUPLICATE_SHA256,
    REASON_NAME_COLLISION,
    REASON_NOT_A_PDF,
    REASON_TITLE_SUSPICION,
    REASON_UNREADABLE,
    IntakeReport,
    _identifier_keys,
    best_title_match,
    run_intake,
    title_candidates,
)
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


def _pages(title: str, identifier: str = "") -> list[str]:
    """Baut zwei Seitentexte mit Titel, optionalem Identifikator und genug Textmasse."""
    return [
        f"{title}\n{identifier}\n1 Introduction\n{_BODY}",
        "2 Evaluation\nThe benchmark reports an F1 score of 0.87 for the proposed system. " + _BODY,
    ]


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


def _run(
    workspace: dict[str, Path],
    *,
    dry_run: bool = False,
    delete_identifier_duplicates: bool = False,
) -> IntakeReport:
    return run_intake(
        inbox_dir=workspace["inbox"],
        papers_dir=workspace["papers"],
        data_dir=workspace["data"],
        uebersicht_path=workspace["uebersicht"],
        dry_run=dry_run,
        delete_identifier_duplicates=delete_identifier_duplicates,
    )


def _tree_state(root: Path) -> dict[str, str]:
    """Hash-Abbild aller Dateien unterhalb von ``root`` (Nachweis für ``--dry-run``)."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_new_paper_is_accepted_and_indexed_without_a_new_overview_row(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Ein neues PDF wandert nach papers/ und wird indiziert - seit G4 ohne Übersicht-Zeile."""
    make_pdf(_pages("Ein völlig neues Paper", "arXiv:2402.22222v1"), "new_papers/Neu.pdf")

    report = _run(workspace)

    assert [item.action for item in report.decisions] == [ACTION_ACCEPTED]
    assert (workspace["papers"] / "Neu.pdf").is_file()
    assert not (workspace["inbox"] / "Neu.pdf").exists()
    assert report.ingest is not None and report.ingest.n_papers == 2
    assert report.overview is None
    body = workspace["uebersicht"].read_text(encoding="utf-8")
    assert body == _UEBERSICHT, "die Übersicht bleibt außer Dienst unverändert"


def test_identical_file_is_deleted_and_logged(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Stufe 1: Ein byte-identisches PDF wird gelöscht und mit Hash protokolliert."""
    source = workspace["papers"] / _CORPUS_PDF
    target = workspace["inbox"] / "Kopie mit anderem Namen.pdf"
    shutil.copyfile(source, target)
    expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    report = _run(workspace)

    decision = report.decisions[0]
    assert decision.action == ACTION_DELETED
    assert decision.reason == REASON_DUPLICATE_SHA256
    assert not target.exists()
    log = (workspace["data"] / INTAKE_LOG).read_text(encoding="utf-8")
    assert expected_hash in log
    assert "Kopie mit anderem Namen.pdf" in log


def test_identifier_duplicate_is_quarantined_not_deleted(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Stufe 2: Gleiche arXiv-ID ⇒ Quarantäne – die Datei bleibt erhalten (ADR 0019)."""
    make_pdf(_pages("Andere Fassung derselben Arbeit", "arXiv:2401.11111v2"), "new_papers/v2.pdf")

    report = _run(workspace)

    decision = report.decisions[0]
    assert decision.action == ACTION_QUARANTINED
    assert decision.reason == REASON_DUPLICATE_IDENTIFIER
    assert not (workspace["inbox"] / "v2.pdf").exists()
    assert (workspace["inbox"] / QUARANTINE_DIR / "v2.pdf").is_file()
    assert report.ingest is None


def test_identifier_duplicate_can_be_deleted_on_demand(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Das harte Löschen der Stufe 2 ist ein ausdrückliches Opt-in."""
    make_pdf(_pages("Andere Fassung derselben Arbeit", "arXiv:2401.11111v2"), "new_papers/v2.pdf")

    report = _run(workspace, delete_identifier_duplicates=True)

    assert report.decisions[0].action == ACTION_QUARANTINED
    assert not (workspace["inbox"] / "v2.pdf").exists()
    assert not (workspace["inbox"] / QUARANTINE_DIR).exists()


def test_title_suspicion_never_deletes(workspace: dict[str, Path], make_pdf: MakePdf) -> None:
    """Stufe 3: Ein ähnlicher Titel erzeugt einen Befund – die Datei bleibt liegen."""
    make_pdf(
        _pages("Bestehendes Paper ueber Graph Retrieval"),
        "new_papers/irgendein-download-2401.pdf",
    )
    dropped = workspace["inbox"] / "irgendein-download-2401.pdf"

    report = _run(workspace)

    decision = report.decisions[0]
    assert decision.action == ACTION_KEPT
    assert decision.reason == REASON_TITLE_SUSPICION
    assert dropped.is_file(), "Verdacht darf niemals löschen"


def test_name_collision_keeps_file(workspace: dict[str, Path], make_pdf: MakePdf) -> None:
    """Gleicher Dateiname bei anderem Inhalt überschreibt nichts."""
    make_pdf(_pages("Ein ganz anderes Werk zu Netzwerken"), f"new_papers/{_CORPUS_PDF}")

    report = _run(workspace)

    decision = report.decisions[0]
    assert decision.action == ACTION_KEPT
    assert decision.reason == REASON_NAME_COLLISION
    assert (workspace["inbox"] / _CORPUS_PDF).is_file()


def test_file_without_pdf_signature_is_not_taken_over(workspace: dict[str, Path]) -> None:
    """Robustheits-Gate: Eine HTML-Fehlerseite mit .pdf-Endung wird nicht übernommen."""
    (workspace["inbox"] / "fehlerseite.pdf").write_text("<html>404</html>", encoding="utf-8")

    report = _run(workspace)

    decision = report.decisions[0]
    assert decision.action == ACTION_KEPT
    assert decision.reason == REASON_NOT_A_PDF
    assert (workspace["inbox"] / "fehlerseite.pdf").is_file()


def test_dry_run_changes_nothing(workspace: dict[str, Path], make_pdf: MakePdf) -> None:
    """``--dry-run`` verändert nachweislich keine einzige Datei."""
    make_pdf(_pages("Ein völlig neues Paper", "arXiv:2402.22222v1"), "new_papers/Neu.pdf")
    source = workspace["papers"] / _CORPUS_PDF
    shutil.copyfile(source, workspace["inbox"] / "Kopie.pdf")
    root = workspace["inbox"].parent
    before = _tree_state(root)

    report = _run(workspace, dry_run=True)

    assert _tree_state(root) == before
    assert report.dry_run is True
    assert {item.action for item in report.decisions} == {
        ACTION_ACCEPTED,
        ACTION_DELETED,
    }
    assert not (workspace["data"] / INTAKE_LOG).exists()


def test_second_run_is_idempotent(workspace: dict[str, Path], make_pdf: MakePdf) -> None:
    """Dieselbe Datei erneut eingeworfen: gelöscht, keine zweite Übersicht-Zeile."""
    pdf = make_pdf(_pages("Ein völlig neues Paper", "arXiv:2402.22222v1"), "new_papers/Neu.pdf")
    raw = pdf.read_bytes()
    _run(workspace)
    after_first = workspace["uebersicht"].read_bytes()

    (workspace["inbox"] / "Neu.pdf").write_bytes(raw)
    second = _run(workspace)

    assert second.decisions[0].action == ACTION_DELETED
    assert workspace["uebersicht"].read_bytes() == after_first


def test_empty_inbox_reports_nothing_to_do(workspace: dict[str, Path]) -> None:
    """Ein leerer Eingangsordner liefert einen leeren, fehlerfreien Bericht."""
    report = _run(workspace)

    assert report.decisions == ()
    assert report.ingest is None
    assert not (workspace["data"] / INTAKE_LOG).exists()


def test_unreadable_pdf_is_kept_with_finding(workspace: dict[str, Path]) -> None:
    """Ein defektes PDF bricht den Lauf nicht ab, sondern bleibt mit Befund liegen."""
    (workspace["inbox"] / "kaputt.pdf").write_bytes(b"%PDF-1.7\nnicht wirklich ein PDF")

    report = _run(workspace)

    decision = report.decisions[0]
    assert decision.action == ACTION_KEPT
    assert decision.reason == REASON_UNREADABLE
    assert (workspace["inbox"] / "kaputt.pdf").is_file()


def test_decision_to_dict_shape(workspace: dict[str, Path], make_pdf: MakePdf) -> None:
    """Die serialisierte Entscheidung trägt die acht vereinbarten Schlüssel."""
    make_pdf(_pages("Ein völlig neues Paper", "arXiv:2402.22222v1"), "new_papers/Neu.pdf")

    payload = _run(workspace, dry_run=True).decisions[0].to_dict()

    assert set(payload) == {
        "filename",
        "sha256",
        "action",
        "reason",
        "detail",
        "flags",
        "target_name",
        "replaces",
    }
    assert payload["filename"] == "Neu.pdf"
    assert payload["action"] == ACTION_ACCEPTED


def test_stale_manifest_entry_does_not_delete(workspace: dict[str, Path]) -> None:
    """Zeigt ein Manifest-Eintrag ins Leere, wird **nicht** gelöscht (Beleg wird nachgerechnet)."""
    original = workspace["papers"] / _CORPUS_PDF
    (workspace["inbox"] / "wiederherstellung.pdf").write_bytes(original.read_bytes())
    original.unlink()

    report = _run(workspace)

    assert report.decisions[0].action != ACTION_DELETED
    assert not (workspace["inbox"] / "wiederherstellung.pdf").is_file(), "Datei wurde bewegt"
    assert (workspace["inbox"] / QUARANTINE_DIR / "wiederherstellung.pdf").is_file()


def test_missing_uebersicht_aborts_before_any_file_moves(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Fehlt die Übersicht, bricht der Lauf ab, **bevor** eine Datei bewegt wird."""
    make_pdf(_pages("Ein völlig neues Paper", "arXiv:2402.22222v1"), "new_papers/Neu.pdf")
    workspace["uebersicht"].unlink()
    before = _tree_state(workspace["inbox"].parent)

    with pytest.raises(DomainError) as excinfo:
        _run(workspace)

    assert excinfo.value.code is ErrorCode.NOT_FOUND
    assert _tree_state(workspace["inbox"].parent) == before


def test_missing_inbox_raises_not_found(workspace: dict[str, Path]) -> None:
    """Fehlt der Eingangsordner, wird not_found gemeldet."""
    with pytest.raises(DomainError) as excinfo:
        run_intake(
            inbox_dir=workspace["inbox"] / "weg",
            papers_dir=workspace["papers"],
            data_dir=workspace["data"],
            uebersicht_path=workspace["uebersicht"],
        )
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_missing_papers_dir_raises_not_found(workspace: dict[str, Path]) -> None:
    """Fehlt der Korpus-Ordner, wird not_found gemeldet."""
    with pytest.raises(DomainError) as excinfo:
        run_intake(
            inbox_dir=workspace["inbox"],
            papers_dir=workspace["papers"] / "weg",
            data_dir=workspace["data"],
            uebersicht_path=workspace["uebersicht"],
        )
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_quality_flags_of_accepted_papers_are_reported(
    workspace: dict[str, Path], make_pdf: MakePdf
) -> None:
    """Angenommene Paper weisen ihre Qualitäts-Flags im Bericht aus (Robustheits-Gate)."""
    make_pdf(_pages("Ein völlig neues Paper", "arXiv:2402.22222v1"), "new_papers/Neu.pdf")

    report = _run(workspace)
    accepted = report.accepted[0]

    quality = json.loads((workspace["data"] / "quality_report.json").read_text(encoding="utf-8"))
    expected = next(
        tuple(entry["flags"])
        for entry in quality["papers"]
        if entry["source_uri"].endswith("Neu.pdf")
    )
    assert accepted.flags == expected


def _paper(
    paper_id: str, identifiers: dict[str, str], front: str, refs: str = ""
) -> CanonicalPaper:
    """Baut ein Canonical-Paper mit Frontmatter- und optionalem Referenz-Chunk."""
    chunks = [Chunk(f"{paper_id}-c0000", paper_id, 1, front, len(front), f"{paper_id}-s000", "")]
    sections: list[Section] = []
    if refs:
        sections.append(Section(f"{paper_id}-s001", "References", SECTION_KIND_REFERENCES, 1, 9, 1))
        chunks.append(
            Chunk(
                f"{paper_id}-c0001",
                paper_id,
                9,
                refs,
                len(refs),
                f"{paper_id}-s001",
                "References",
            )
        )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=9,
        chunks=tuple(chunks),
        quality_flags=(),
        sections=tuple(sections),
        identifiers=identifiers,
    )


def test_identifier_keys_require_front_matter_proof() -> None:
    """Härtung 1: Ein nur in der Bibliografie belegter Identifikator ist kein Löschschlüssel."""
    proven = _paper("aaaa", {"arxiv": "2401.11111"}, "Titel arXiv:2401.11111 Abstract")
    unproven = _paper("bbbb", {"arxiv": "2108.07732"}, "Titel ohne ID", refs="see arXiv:2108.07732")

    keys = _identifier_keys([proven, unproven])

    assert keys == {("arxiv", "2401.11111"): "aaaa"}


def test_identifier_keys_drop_ambiguous_values() -> None:
    """Härtung 2: Ein Wert mit mehreren Trägern (Vorlagen-Platzhalter) zählt nicht."""
    placeholder = "10.1145/nnnnnnn.nnnnnnn"
    first = _paper("aaaa", {"doi": placeholder}, f"Titel {placeholder} Abstract")
    second = _paper("bbbb", {"doi": placeholder}, f"Titel {placeholder} Abstract")

    assert _identifier_keys([first, second]) == {}


def test_title_candidates_use_filename_and_front_page() -> None:
    """Titelkandidaten kommen aus Dateiname *und* Titelseite; zu kurze entfallen."""
    candidates = title_candidates(
        "2310.11511v1.pdf", ["Self-RAG Learning To Retrieve Generate And Critique\nAbstract\nWe"]
    )

    assert "self rag learning to retrieve generate and critique" in candidates
    assert all(len(candidate) >= 30 for candidate in candidates)


def test_best_title_match_reports_ratio_and_title() -> None:
    """Die Verdachtsstufe meldet den besten Treffer samt Ähnlichkeit."""
    corpus = {"graph retrieval augmented generation survey": "Graph Retrieval Survey"}

    ratio, matched = best_title_match(["graph retrieval augmented generation survey"], corpus)

    assert ratio == pytest.approx(1.0)
    assert matched == "Graph Retrieval Survey"
    assert best_title_match([], corpus) == (0.0, "")
