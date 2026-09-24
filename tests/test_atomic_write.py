"""Tests für das atomare Schreiben mit Windows-Retry (ADR 0039, Nachträge 2026-09-19/-23)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from research_graphrag import atomic_write as atomic_write_module
from research_graphrag.atomic_write import atomic_write_bytes


def test_writes_bytes_to_a_new_file(tmp_path: Path) -> None:
    """Eine neue Datei entsteht mit exakt den übergebenen Bytes."""
    target = tmp_path / "datei.txt"

    atomic_write_bytes(target, b"Inhalt")

    assert target.read_bytes() == b"Inhalt"


def test_replaces_existing_content_fully(tmp_path: Path) -> None:
    """Ein erneuter Aufruf ersetzt den bisherigen Inhalt vollständig, kein Anhängen."""
    target = tmp_path / "datei.txt"
    atomic_write_bytes(target, b"alt genug, um laenger zu sein")

    atomic_write_bytes(target, b"neu")

    assert target.read_bytes() == b"neu"


def test_leaves_no_temporary_file(tmp_path: Path) -> None:
    """Nach dem Schreiben bleibt keine Temporärdatei zurück."""
    atomic_write_bytes(tmp_path / "datei.txt", b"Inhalt")

    assert list(tmp_path.glob("*.tmp")) == []


def test_creates_missing_parent_directories(tmp_path: Path) -> None:
    """Ein noch nicht existierender (auch mehrstufiger) Elternordner wird selbst angelegt."""
    target = tmp_path / "a" / "b" / "datei.txt"

    atomic_write_bytes(target, b"Inhalt")

    assert target.read_bytes() == b"Inhalt"


def test_retries_mkdir_on_permission_error_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eine transiente ``PermissionError`` beim Anlegen des Zielordners wird wiederholt.

    Reproduziert den Fehler aus ADR 0039 (Nachtrag 2026-09-23): ein frisch eingerichteter
    Zielordner (z. B. eine NTFS-Junction wie ``metadata/``) kann ``os.makedirs`` trotz
    ``exist_ok=True`` transient mit ``PermissionError`` scheitern lassen.
    """
    target = tmp_path / "ordner" / "datei.txt"
    real_makedirs = os.makedirs
    calls: list[int] = []

    def flaky_makedirs(name: object, exist_ok: bool = False) -> None:
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("transient (Test)")
        real_makedirs(name, exist_ok=exist_ok)

    monkeypatch.setattr(atomic_write_module.os, "makedirs", flaky_makedirs)
    monkeypatch.setattr(atomic_write_module.time, "sleep", lambda _seconds: None)

    atomic_write_bytes(target, b"Inhalt")

    assert len(calls) == 3
    assert target.read_bytes() == b"Inhalt"


def test_raises_after_exhausting_mkdir_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bleibt das Anlegen des Zielordners dauerhaft gestört, wird die ``PermissionError``
    weitergereicht, statt eine Temporärdatei anzulegen."""
    target = tmp_path / "ordner" / "datei.txt"
    calls: list[int] = []

    def always_fails(_name: object, exist_ok: bool = False) -> None:
        calls.append(1)
        raise PermissionError("dauerhaft gesperrt (Test)")

    monkeypatch.setattr(atomic_write_module.os, "makedirs", always_fails)
    monkeypatch.setattr(atomic_write_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError, match="dauerhaft gesperrt"):
        atomic_write_bytes(target, b"Inhalt")

    assert len(calls) == atomic_write_module._PERMISSION_RETRY_ATTEMPTS
    assert not target.exists()


def test_retries_on_permission_error_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eine transiente ``PermissionError`` bei ``os.replace`` wird bis zum Erfolg wiederholt."""
    target = tmp_path / "datei.txt"
    real_replace = os.replace
    calls: list[int] = []

    def flaky_replace(src: object, dst: object) -> None:
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("transient (Test)")
        real_replace(src, dst)

    monkeypatch.setattr(atomic_write_module.os, "replace", flaky_replace)
    monkeypatch.setattr(atomic_write_module.time, "sleep", lambda _seconds: None)

    atomic_write_bytes(target, b"Inhalt")

    assert len(calls) == 3
    assert target.read_bytes() == b"Inhalt"
    assert list(tmp_path.glob("*.tmp")) == []


def test_raises_after_exhausting_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bleibt ``os.replace`` dauerhaft gestört, wird die letzte ``PermissionError`` weitergereicht."""
    target = tmp_path / "datei.txt"
    calls: list[int] = []

    def always_fails(_src: object, _dst: object) -> None:
        calls.append(1)
        raise PermissionError("dauerhaft gesperrt (Test)")

    monkeypatch.setattr(atomic_write_module.os, "replace", always_fails)
    monkeypatch.setattr(atomic_write_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError, match="dauerhaft gesperrt"):
        atomic_write_bytes(target, b"Inhalt")

    assert len(calls) == atomic_write_module._PERMISSION_RETRY_ATTEMPTS
    assert not target.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_other_os_errors_are_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Eine nicht-transiente ``OSError`` (kein ``PermissionError``) wird sofort weitergereicht."""
    target = tmp_path / "datei.txt"
    calls: list[int] = []

    def fails_once(_src: object, _dst: object) -> None:
        calls.append(1)
        raise OSError("kein Konkurrenzproblem (Test)")

    monkeypatch.setattr(atomic_write_module.os, "replace", fails_once)

    with pytest.raises(OSError, match="kein Konkurrenzproblem"):
        atomic_write_bytes(target, b"Inhalt")

    assert len(calls) == 1
