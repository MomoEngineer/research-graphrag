"""Offline-Coverage-Gate über die Python-Standardbibliothek (``trace``).

Dieses Skript misst die **Zeilenabdeckung pro Kernmodul** ohne externe
Abhängigkeiten (``pytest-cov``/``coverage`` sind im Offline-Firmenumfeld nicht
installierbar). Grundsatzentscheidung:
docs/adr/0003-offline-test-and-coverage-tooling.md.

Vorgehen:

1. Die pytest-Suite wird **einmal in-process unter ``trace.Trace``** ausgeführt.
2. Für jedes Kernmodul (``src/research_graphrag/**/*.py`` ohne ``__init__.py``)
   werden die ausführbaren Zeilen (über ``code.co_lines()`` des kompilierten
   Moduls) den tatsächlich ausgeführten Zeilen gegenübergestellt.
3. Je Modul werden Prozentsatz und fehlende Zeilen berichtet.
4. Liegt ein Kernmodul unter der Schwelle (Richtwert 80 %), endet das Skript mit
   Exit-Code ``1``.

In Phase 0 existieren nur importierbare Platzhalter (``__init__.py``); es gibt noch
keine Kernmodule. Das Skript meldet dann „Abdeckung n/a" und endet mit Code ``0``.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.coverage_offline

Hinweis (subst-Laufwerke, z. B. ``J:``): ``resolve``/``realpath`` lösen den Pfad
auf das reale Ziel auf, während ``trace``/``co_filename`` den subst-Pfad behalten.
Der Abgleich erfolgt daher über ein normalisiertes Pfad-**Suffix** ab
``/research_graphrag/`` und nicht über absolute Pfade.
"""

from __future__ import annotations

import glob
import io
import os
import sys
import trace
from contextlib import redirect_stdout

# Repository-Wurzel = übergeordnetes Verzeichnis von scripts/.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_THIS_DIR)

# Richtwert konsistent zu [tool.coverage.report] fail_under in pyproject.toml.
THRESHOLD = 80.0

_MARKER = "/research_graphrag/"


def _rel_suffix(path: str) -> str:
    """Normalisiert einen Pfad auf ein vergleichbares Suffix ab ``/research_graphrag/``.

    Neutralisiert Laufwerks-/subst-Unterschiede und Trennzeichen, sodass die von
    ``trace`` gelieferten ``co_filename``-Pfade mit den Zieldateien zusammenpassen.
    """
    normalized = os.path.normcase(os.path.abspath(path)).replace("\\", "/")
    index = normalized.find(_MARKER)
    return normalized[index:] if index != -1 else normalized


def _executable_linenos(path: str) -> set[int]:
    """Ermittelt die ausführbaren Zeilennummern einer Datei über ``co_lines()``.

    Der Quelltext wird kompiliert; alle Code-Objekte (inkl. verschachtelter
    Funktionen/Klassen in ``co_consts``) werden rekursiv durchlaufen und ihre
    Zeilennummern eingesammelt.
    """
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    top_code = compile(source, path, "exec")

    linenos: set[int] = set()
    pending = [top_code]
    while pending:
        code = pending.pop()
        for _start, _end, lineno in code.co_lines():
            if lineno is not None and lineno > 0:
                linenos.add(lineno)
        for const in code.co_consts:
            if isinstance(const, type(top_code)):
                pending.append(const)
    return linenos


def _collect_core_modules() -> list[str]:
    """Ermittelt alle Kernmodul-Dateien unter src/research_graphrag (ohne ``__init__.py``)."""
    pattern = os.path.join(REPO_ROOT, "src", "research_graphrag", "**", "*.py")
    modules = [
        path
        for path in glob.glob(pattern, recursive=True)
        if os.path.basename(path) != "__init__.py"
    ]
    return sorted(modules)


def _run_suite_under_trace() -> tuple[int, dict[tuple[str, int], int]]:
    """Führt die pytest-Suite in-process unter ``trace`` aus.

    Returns:
        Tupel aus pytest-Rückgabecode und der ``counts``-Abbildung
        ``{(dateiname, zeilennummer): trefferzahl}``.
    """
    import pytest

    tracer = trace.Trace(count=1, trace=0)
    captured = io.StringIO()
    with redirect_stdout(captured):
        return_code = tracer.runfunc(pytest.main, ["tests", "-q", "-p", "no:cacheprovider"])
    # pytest-Ausgabe zur Nachvollziehbarkeit anzeigen.
    sys.stdout.write(captured.getvalue())
    results = tracer.results()
    return int(return_code), results.counts


def _covered_lines_by_suffix(counts: dict[tuple[str, int], int]) -> dict[str, set[int]]:
    """Gruppiert die ausgeführten Zeilen je Datei-Suffix."""
    covered: dict[str, set[int]] = {}
    for (filename, lineno), hits in counts.items():
        if hits <= 0:
            continue
        suffix = _rel_suffix(filename)
        covered.setdefault(suffix, set()).add(lineno)
    return covered


def main() -> int:
    """Führt die Suite unter ``trace`` aus und prüft die Zeilenabdeckung je Kernmodul."""
    modules = _collect_core_modules()
    return_code, counts = _run_suite_under_trace()
    if return_code != 0:
        print(f"\n[coverage_offline] pytest meldete Fehler (Code {return_code}).")
        return return_code

    if not modules:
        print("\n[coverage_offline] Noch keine Kernmodule (nur Platzhalter) – Abdeckung n/a. OK.")
        return 0

    covered = _covered_lines_by_suffix(counts)
    failed = False
    print("\n[coverage_offline] Zeilenabdeckung je Kernmodul:")
    for path in modules:
        executable = _executable_linenos(path)
        if not executable:
            continue
        suffix = _rel_suffix(path)
        hit = covered.get(suffix, set()) & executable
        pct = 100.0 * len(hit) / len(executable)
        missing = sorted(executable - hit)
        status = "OK " if pct >= THRESHOLD else "LOW"
        print(f"  [{status}] {suffix}: {pct:5.1f}%  fehlend: {missing}")
        if pct < THRESHOLD:
            failed = True

    if failed:
        print(f"\n[coverage_offline] Richtwert {THRESHOLD:.0f}% unterschritten.")
        return 1
    print(f"\n[coverage_offline] Richtwert {THRESHOLD:.0f}% erreicht.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
