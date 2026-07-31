# 0002 – venv- und Offline-Dependency-Strategie

- **Status:** Akzeptiert
- **Datum:** 2026-07-31

## Kontext

Reproduzierbarkeit ist ein Kernprinzip (siehe [CONTRIBUTING.md](../../CONTRIBUTING.md)) und verlangt **fixierte Versionen über ein Lockfile**. Rahmenbedingung: dieselbe Umgebung wie beim Vorbild-Repo – ein **verwalteter Firmen-Laptop ohne PyPI-Zugang** (vgl. `mcs-copilot-tools`, ADR 0002). Vorhanden ist eine **WinPython-Distribution** mit u. a. `mcp`, `ruff`, `mypy`, `pytest`, `anyio`. Gewünscht ist eine **virtuelle Umgebung** zur Isolation (Nutzer-Vorgabe), um nicht – wie im Vorbild-Repo – direkt gegen das System-Python arbeiten zu müssen.

Zusätzlich: Der fachliche Kern (Microsoft GraphRAG, Docling, LanceDB) ist **schwergewichtig** und offline evtl. **nicht beschaffbar**.

## Entscheidung

1. **venv mit Zugriff auf die System-Toolchain:** `python -m venv --system-site-packages .venv`. So bleibt die Isolation für lokal ergänzte Pakete erhalten, während die offline **nicht** nachinstallierbare Toolchain (`mcp`, `ruff`, `mypy`, `pytest`, `anyio`) aus der WinPython-Basis wiederverwendet wird.
2. **Kern-Deps minimal + exakt gepinnt** in `pyproject.toml`; damit läuft `pip install -e .` auch offline durch (bei Bedarf `--no-build-isolation`, um die PEP-517-Build-Isolation nicht auf PyPI zugreifen zu lassen).
3. **Schwerer Stack als Extra `[pipeline]`** (`docling`, `graphrag`, `lancedb`): wird erst in Phase 0b/2 beschafft (Wheelhouse oder einmaliges Online-Fenster) und dann final gepinnt.
4. **Lockfile** über das vorhandene `pip`: `requirements.lock` via `pip freeze` als eingefrorene Gesamtauflösung.
5. **Zielbild:** Sobald ein Mirror/Netz verfügbar ist, Umstieg auf **`uv`** (Ablösung dieses ADR durch einen Folge-ADR).

## Alternativen

- **Voll isolierte venv (ohne System-Pakete):** kann offline keine Werkzeuge nachladen → nicht arbeitsfähig.
- **`uv` / Poetry / pip-tools:** offline nicht installierbar → aktuell nicht umsetzbar.
- **Kein venv (wie Vorbild-Repo):** widerspricht der Isolations-Vorgabe des Nutzers.
- **Schweren Stack als Kern-Dependency:** `pip install -e .` würde offline scheitern → daher als Extra ausgelagert.

## Konsequenzen

- **Positiv:** `pip install -e .` läuft offline (Kern); Isolation gewahrt; keine unbeschaffbaren Werkzeuge nötig.
- **Negativ / Aufwand:** `requirements.lock` spiegelt die WinPython-Basis wider (keine Hashes, keine strikte Trennung direkt/transitiv); der Pipeline-Stack bleibt bis zur Beschaffung offen.
- **Folgeentscheidungen:** [ADR 0005](0005-graphrag-index-backend-open.md) (Index-Backend); späterer `uv`-Umstieg.
