# 0003 – Offline-Test- und Coverage-Tooling

- **Status:** Akzeptiert
- **Datum:** 2026-07-31

## Kontext

Die Teststrategie ([testing.md](../testing.md)) sieht `pytest` und eine Zeilenabdeckung als Richtwert vor. Im Offline-Umfeld ([ADR 0002](0002-venv-and-offline-dependency-strategy.md)) sind **`pytest-asyncio`**, **`pytest-cov`** und **`coverage`** nicht installierbar; vorhanden sind `pytest` und `anyio` (inkl. Pytest-Plugin).

## Entscheidung

1. **Asynchrone Tests** werden über das **`anyio`-Pytest-Plugin** ausgeführt (`@pytest.mark.anyio`), Backend `asyncio` (Fixture `anyio_backend` in `tests/conftest.py`). `anyio` ist ohnehin transitive Abhängigkeit von `mcp`.
2. **Coverage-Messung** erfolgt über das stdlib-Modul `trace`: `scripts/coverage_offline.py` misst die **Zeilenabdeckung** je Kernmodul (`src/research_graphrag/**` ohne `__init__.py`) und meldet Unterschreitungen mit Exit-Code ≠ 0. Die 80-%-Schwelle ist ein **Richtwert** (right-sized), kein hartes CI-Gate.
3. **Aufruf über `python -m <tool>`** (WinPython-Konsolenskripte liegen nicht im `PATH`; `python -m` legt das Arbeitsverzeichnis auf `sys.path`, sodass `research_graphrag` und `scripts` importierbar sind).

## Alternativen

- **`pytest-asyncio`:** offline nicht installierbar → durch `anyio`-Plugin ersetzt (funktional gleichwertig).
- **`pytest-cov` / `coverage.py`:** offline nicht installierbar → Zeilenabdeckung über stdlib `trace`.

## Konsequenzen

- **Positiv:** Tests und Abdeckungsmessung laufen sofort mit vorhandenen Mitteln; keine unbeschaffbaren Werkzeuge nötig.
- **Negativ / Aufwand:** `trace` misst nur **Zeilen-**, keine **Zweigabdeckung**; letztere bleibt späterem `coverage.py` vorbehalten. Der `pyproject.toml`-Coverage-Block ist für diesen späteren Moment bereits hinterlegt.
- **Aufruf-Konvention (venv + Offline):** Werkzeuge werden über `python -m <tool>` aus der venv gestartet. Da die `--system-site-packages`-venv die WinPython-Toolchain wiederverwendet, aber deren Konsolen-Launcher **nicht** erbt, wird der `ruff`-Launcher (`ruff.exe`) einmalig nach `.venv\Scripts\` kopiert (Bootstrap nach jeder venv-Neuanlage). `mypy`, `pytest` und `scripts.coverage_offline` benötigen dies nicht; `pytest`/Coverage laufen bewusst über die venv, weil sie das editierbar installierte Paket importieren.
- **Bezug:** entspricht inhaltlich `mcs-copilot-tools`, ADR 0003 + 0020.
