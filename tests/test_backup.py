"""Tests für die Korpus-Sicherung (Phase 11 / B1, ADR 0027).

Drei Zusicherungen tragen hier mehr als die Abdeckung:

* **Abgeleitetes wird nicht gesichert** – ein Index im Sicherungsstand verleitet dazu, ihn
  zurückzuspielen, obwohl er zum wiederhergestellten ``papers/`` nicht passen muss.
* **``--dry-run`` verändert nichts** – belegt über ein Hash-Abbild des gesamten Zielbaums.
* **Die Kopie ist bitgenau** – geprüft über sha256, nicht über die Dateigröße.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.backup import main as cli_main

import research_graphrag.backup as backup_module
from research_graphrag.backup import (
    ACTION_COPIED,
    ACTION_MISSING,
    ACTION_UNCHANGED,
    BACKUP_MANIFEST_NAME,
    SOURCE_DIRECTORIES,
    SOURCE_FILES,
    create_backup,
    verify_backup,
)
from research_graphrag.errors import DomainError, ErrorCode


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_digest(root: Path) -> dict[str, str]:
    """Hash-Abbild eines Verzeichnisbaums – erkennt jede Änderung an Inhalt oder Bestand."""
    return {
        str(p.relative_to(root)).replace("\\", "/"): _digest(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Ein Miniatur-Repository mit Quell- **und** abgeleiteten Artefakten."""
    root = tmp_path / "repo"
    (root / "papers").mkdir(parents=True)
    (root / "papers" / "Erstes Paper.pdf").write_bytes(b"%PDF-1.7\nerstes\n")
    (root / "papers" / "Zweites (RAG) Über Ähnlichkeit.pdf").write_bytes(b"%PDF-1.7\nzweites\n")
    (root / "papers" / "README.md").write_text("# papers\n", encoding="utf-8")

    (root / "Übersicht.md").write_bytes(b"| Nr | Name |\n| --- | --- |\n")

    (root / "metadata").mkdir()
    (root / "metadata" / "paper_metadata.json").write_bytes(b'{"papers": {}}')
    (root / "metadata" / "curation.json").write_bytes(b'{"papers": {}}')

    (root / "new_papers").mkdir()
    (root / "new_papers" / "referenzen.txt").write_bytes(b"# Kennungen\n10.1145/x\n")

    data = root / "data"
    data.mkdir()
    (data / "manifest.json").write_bytes(b'{"files": {}}')
    (data / "intake_log.md").write_bytes(b"# Intake\n")
    (data / "metadata_log.md").write_bytes(b"# Metadaten\n")
    (data / "online_candidates.md").write_bytes(b"# Kandidaten\n")
    (data / "references_log.md").write_bytes("# Referenz-Einträge\n".encode())

    # Abgeleitet – darf NICHT in der Sicherung landen.
    (data / "canonical").mkdir()
    (data / "canonical" / "abc.json").write_bytes(b"{}")
    (data / "index").mkdir()
    (data / "index" / "index.sqlite").write_bytes(b"SQLite format 3\x00")
    (data / "quality_report.json").write_bytes(b"{}")
    return root


def test_collects_the_declared_sources(workspace: Path, tmp_path: Path) -> None:
    """Gesichert wird genau der festgelegte Umfang – Verzeichnisse rekursiv, Dateien einzeln."""
    report = create_backup(workspace, tmp_path / "sicherung")

    paths = {item.relative_path for item in report.items}
    assert "papers/Erstes Paper.pdf" in paths
    assert "papers/Zweites (RAG) Über Ähnlichkeit.pdf" in paths
    for name in SOURCE_FILES:
        assert name in paths
    assert set(SOURCE_DIRECTORIES) == {"papers"}


def test_derived_artefacts_are_never_backed_up(workspace: Path, tmp_path: Path) -> None:
    """Index, Canonical und Qualitätsbericht sind reproduzierbar und bleiben draußen."""
    target = tmp_path / "sicherung"
    create_backup(workspace, target)

    assert not (target / "data" / "index").exists()
    assert not (target / "data" / "canonical").exists()
    assert not (target / "data" / "quality_report.json").exists()


def test_copy_is_byte_identical(workspace: Path, tmp_path: Path) -> None:
    """Die Kopie wird über sha256 geprüft, nicht über die Größe."""
    target = tmp_path / "sicherung"
    create_backup(workspace, target)

    for name in ("papers/Erstes Paper.pdf", "Übersicht.md", "data/manifest.json"):
        assert (target / name).read_bytes() == (workspace / name).read_bytes()


def test_manifest_records_every_backed_up_file(workspace: Path, tmp_path: Path) -> None:
    """Das Manifest ist der Prüfnachweis: je Datei sha256 und Größe."""
    target = tmp_path / "sicherung"
    report = create_backup(workspace, target)

    payload = json.loads((target / BACKUP_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert payload["schema_version"]
    assert payload["created_at"]
    stored = {entry["relative_path"]: entry for entry in payload["files"]}
    present = {item.relative_path for item in report.items if item.action != ACTION_MISSING}
    assert set(stored) == present
    entry = stored["papers/Erstes Paper.pdf"]
    assert entry["sha256"] == _digest(workspace / "papers" / "Erstes Paper.pdf")
    assert entry["size"] == (workspace / "papers" / "Erstes Paper.pdf").stat().st_size


def test_manifest_has_no_carriage_returns(workspace: Path, tmp_path: Path) -> None:
    """Das Manifest wird binär geschrieben – unter Windows dreht ``write_text`` sonst alle Zeilen."""
    target = tmp_path / "sicherung"
    create_backup(workspace, target)

    assert b"\r\n" not in (target / BACKUP_MANIFEST_NAME).read_bytes()


def test_dry_run_changes_nothing(workspace: Path, tmp_path: Path) -> None:
    """Die Vorschau darf weder Ziel noch Quelle anfassen."""
    target = tmp_path / "sicherung"
    target.mkdir()
    before_target = _tree_digest(target)
    before_source = _tree_digest(workspace)

    report = create_backup(workspace, target, dry_run=True)

    assert report.dry_run is True
    assert _tree_digest(target) == before_target
    assert _tree_digest(workspace) == before_source
    assert report.n_copied > 0  # die Vorschau benennt trotzdem, was zu tun wäre


def test_dry_run_matches_the_real_run(workspace: Path, tmp_path: Path) -> None:
    """Vorschau und echter Lauf treffen dieselben Entscheidungen je Datei."""
    preview = create_backup(workspace, tmp_path / "sicherung", dry_run=True)
    real = create_backup(workspace, tmp_path / "sicherung")

    assert [(i.relative_path, i.action) for i in preview.items] == [
        (i.relative_path, i.action) for i in real.items
    ]


def test_second_run_is_idempotent(workspace: Path, tmp_path: Path) -> None:
    """Unveränderte Dateien werden übersprungen – sonst liefe die Sicherung nie regelmäßig."""
    target = tmp_path / "sicherung"
    first = create_backup(workspace, target)
    second = create_backup(workspace, target)

    assert first.n_copied > 0
    assert second.n_copied == 0
    assert second.n_unchanged == first.n_copied
    assert all(item.action == ACTION_UNCHANGED for item in second.items)


def test_changed_source_is_copied_again(workspace: Path, tmp_path: Path) -> None:
    """Ein geänderter Inhalt wird erkannt, auch wenn die Größe gleich bleibt."""
    target = tmp_path / "sicherung"
    create_backup(workspace, target)
    (workspace / "papers" / "Erstes Paper.pdf").write_bytes(b"%PDF-1.7\nERSTES\n")

    report = create_backup(workspace, target)

    changed = [i for i in report.items if i.action == ACTION_COPIED]
    assert [i.relative_path for i in changed] == ["papers/Erstes Paper.pdf"]
    assert (target / "papers" / "Erstes Paper.pdf").read_bytes() == b"%PDF-1.7\nERSTES\n"


def test_missing_optional_source_is_reported_not_fatal(workspace: Path, tmp_path: Path) -> None:
    """Ein noch nie geschriebenes Protokoll darf die Sicherung nicht abbrechen."""
    (workspace / "data" / "metadata_log.md").unlink()

    report = create_backup(workspace, tmp_path / "sicherung")

    missing = [i.relative_path for i in report.items if i.action == ACTION_MISSING]
    assert missing == ["data/metadata_log.md"]
    assert report.n_missing == 1


def test_missing_corpus_directory_is_not_found(tmp_path: Path) -> None:
    """Ohne ``papers/`` gibt es nichts zu sichern – das ist ein Fehler, kein leerer Lauf."""
    root = tmp_path / "leer"
    root.mkdir()

    with pytest.raises(DomainError) as excinfo:
        create_backup(root, tmp_path / "sicherung")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_target_inside_the_repository_is_rejected(workspace: Path) -> None:
    """Ein Ziel in der Arbeitskopie würde sich selbst sichern und bei jedem Lauf wachsen."""
    with pytest.raises(DomainError) as excinfo:
        create_backup(workspace, workspace / "data" / "sicherung")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_target_equal_to_the_repository_is_rejected(workspace: Path) -> None:
    """Auch das Wurzelverzeichnis selbst ist kein zulässiges Ziel."""
    with pytest.raises(DomainError) as excinfo:
        create_backup(workspace, workspace)

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_verify_accepts_an_untouched_backup(workspace: Path, tmp_path: Path) -> None:
    """Ein frischer Sicherungsstand prüft sich fehlerfrei."""
    target = tmp_path / "sicherung"
    create_backup(workspace, target)

    result = verify_backup(target)

    assert result.ok
    assert result.n_checked > 0
    assert result.mismatched == ()
    assert result.missing == ()


def test_verify_detects_a_modified_file(workspace: Path, tmp_path: Path) -> None:
    """Eine stille Veränderung am Sicherungsstand wird benannt."""
    target = tmp_path / "sicherung"
    create_backup(workspace, target)
    (target / "papers" / "Erstes Paper.pdf").write_bytes(b"kaputt")

    result = verify_backup(target)

    assert not result.ok
    assert result.mismatched == ("papers/Erstes Paper.pdf",)


def test_verify_detects_a_deleted_file(workspace: Path, tmp_path: Path) -> None:
    """Eine fehlende Datei ist ein anderer Befund als eine veränderte."""
    target = tmp_path / "sicherung"
    create_backup(workspace, target)
    (target / "data" / "manifest.json").unlink()

    result = verify_backup(target)

    assert not result.ok
    assert result.missing == ("data/manifest.json",)
    assert result.mismatched == ()


def test_verify_without_manifest_is_not_found(tmp_path: Path) -> None:
    """Ohne Manifest ist ein Verzeichnis kein Sicherungsstand."""
    target = tmp_path / "irgendwas"
    target.mkdir()

    with pytest.raises(DomainError) as excinfo:
        verify_backup(target)

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_verify_with_broken_manifest_is_parse_error(workspace: Path, tmp_path: Path) -> None:
    """Ein beschädigtes Manifest ist ein Lesefehler, kein fehlender Sicherungsstand."""
    target = tmp_path / "sicherung"
    create_backup(workspace, target)
    (target / BACKUP_MANIFEST_NAME).write_bytes(b"{kein json")

    with pytest.raises(DomainError) as excinfo:
        verify_backup(target)

    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_declared_directory_that_does_not_exist_is_skipped(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ein zusätzlich deklariertes, aber fehlendes Verzeichnis bricht den Lauf nicht ab."""
    monkeypatch.setattr(backup_module, "SOURCE_DIRECTORIES", ("papers", "gibt_es_nicht"))

    report = create_backup(workspace, tmp_path / "sicherung")

    assert not any(i.relative_path.startswith("gibt_es_nicht") for i in report.items)
    assert any(i.relative_path.startswith("papers/") for i in report.items)


def test_progress_callback_reports_every_source(workspace: Path, tmp_path: Path) -> None:
    """Der Fortschritt zählt bis zur Gesamtzahl – Grundlage der Anzeige in der CLI."""
    seen: list[tuple[str, int, int]] = []

    report = create_backup(
        workspace,
        tmp_path / "sicherung",
        progress=lambda name, current, total: seen.append((name, current, total)),
    )

    assert len(seen) == len(report.items)
    assert seen[-1][1] == seen[-1][2] == len(report.items)


def test_report_totals_match_the_items(workspace: Path, tmp_path: Path) -> None:
    """Die Kennzahlen sind aus den Einzelbefunden abgeleitet, nicht separat gezählt."""
    report = create_backup(workspace, tmp_path / "sicherung")

    assert report.n_copied + report.n_unchanged + report.n_missing == len(report.items)
    assert report.total_bytes == sum(i.size for i in report.items if i.action != ACTION_MISSING)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def test_cli_backs_up_and_reports(
    workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Der Standardlauf schreibt die Sicherung und endet mit Exit-Code 0."""
    target = tmp_path / "sicherung"
    monkeypatch.setattr(sys, "argv", ["backup", "--ziel", str(target), "--root", str(workspace)])

    assert cli_main() == 0

    out = capsys.readouterr().out
    assert str(target) in out
    assert (target / BACKUP_MANIFEST_NAME).is_file()


def test_cli_dry_run_writes_nothing(
    workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Die Vorschau ist als solche gekennzeichnet und legt kein Ziel an."""
    target = tmp_path / "sicherung"
    monkeypatch.setattr(
        sys, "argv", ["backup", "--ziel", str(target), "--root", str(workspace), "--dry-run"]
    )

    assert cli_main() == 0

    assert "VORSCHAU" in capsys.readouterr().out
    assert not target.exists()


def test_cli_verification_reports_a_defect(
    workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ein beschädigter Sicherungsstand endet mit Exit-Code 1 und benennt die Datei."""
    target = tmp_path / "sicherung"
    create_backup(workspace, target)
    (target / "data" / "manifest.json").write_bytes(b"kaputt")
    monkeypatch.setattr(sys, "argv", ["backup", "--ziel", str(target), "--pruefen"])

    assert cli_main() == 1

    assert "data/manifest.json" in capsys.readouterr().out


def test_cli_reports_domain_errors_without_traceback(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ein fachlicher Fehler endet mit einer Meldung nach dem Fehlermodell, nicht mit Exit 2."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["backup", "--ziel", str(workspace / "innen"), "--root", str(workspace)],
    )

    assert cli_main() == 1

    assert "invalid_input" in capsys.readouterr().out


def test_cli_survives_cp1252_stdout(workspace: Path, tmp_path: Path) -> None:
    """Auch bei enger Konsolen-Codepage läuft die CLI durch (Dateinamen mit Umlauten)."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.backup",
            "--ziel",
            str(tmp_path / "sicherung"),
            "--root",
            str(workspace),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert b"UnicodeEncodeError" not in completed.stderr
