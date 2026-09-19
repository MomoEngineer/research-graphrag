"""Atomares Schreiben einer Datei (Temporärdatei + ``os.replace``, mit Windows-Retry).

Geteilte Grundlage für :func:`research_graphrag.bibliography.store.save_records` und
:func:`research_graphrag.online.report.append_section`: Beide schreiben eine Datei
deterministisch und dürfen nichts Halbfertiges hinterlassen, wenn ein Lauf abbricht.

Für **konkurrierende** Schreibversuche auf **dieselbe** Zieldatei (z. B. zwei
``correct_paper_metadata``-Aufrufe, die ein MCP-Client ohne Warten auf die erste Antwort
abschickt) reicht eine eindeutige Temporärdatei je Aufruf allein nicht: Gemessen mit acht
parallelen Schreibversuchen auf dieselbe Zieldatei scheitert ``os.replace`` unter Windows auch
bei eindeutiger Quelle gelegentlich transient mit ``PermissionError`` (``[WinError 5]``), weil ein
anderer, ebenfalls gerade ersetzender Aufruf die Zieldatei im selben Moment kurz hält. Ein
knapper Retry ausschließlich auf diesen einen, gemessenen Fehlertyp macht den in der Praxis
seltenen, aber realen Regelfall robust – **ohne** eine echte Sperre über den ganzen
Lade-Merge-Schreib-Zyklus einzuführen, die für ein persönliches Werkzeug mit typischerweise
sequenziellen Aufrufen unverhältnismäßig wäre (ADR 0039, Nachtrag 2026-09-19).
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

_REPLACE_ATTEMPTS = 5
"""Höchstzahl der Versuche für den abschließenden ``os.replace`` (erster Versuch + Retries)."""

_REPLACE_RETRY_SECONDS = 0.05
"""Wartezeit zwischen zwei Retry-Versuchen – knapp bemessen, weil die Konkurrenz-Fenster, die
diesen Fehler auslösen, im Millisekundenbereich liegen (siehe Testsuite)."""


def atomic_write_bytes(target: Path, data: bytes) -> None:
    """Schreibt ``data`` deterministisch/atomar nach ``target``.

    Args:
        target: Zieldatei; der Elternordner muss bereits existieren.
        data: Vollständiger, neuer Dateiinhalt (ersetzt den bisherigen Inhalt ganz).

    Raises:
        OSError: wenn weder das Schreiben der Temporärdatei noch – nach den Retry-Versuchen aus
            :func:`_replace_with_retry` – das abschließende ``os.replace`` gelingt (z. B.
            gesperrte Zieldatei, fehlende Schreibrechte, nicht existierendes Verzeichnis).
    """
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f"{target.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        _replace_with_retry(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)


def _replace_with_retry(tmp_path: Path, target: Path) -> None:
    """``os.replace`` mit kurzem Retry gegen den oben beschriebenen, gemessenen Windows-Fehler.

    Der letzte Versuch reicht eine fortbestehende ``PermissionError`` unverändert weiter – jede
    andere ``OSError``-Unterklasse (z. B. eine dauerhaft fehlende Berechtigung) wird nicht
    wiederholt, weil ein Retry dort nichts ändern würde.
    """
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp_path, target)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_SECONDS)
