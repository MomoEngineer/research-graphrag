# scripts/

Entwickler-Hilfsskripte (kein MCP-Server). Aufruf stets über `python -m scripts.<name>`
vom Repository-Wurzelverzeichnis (WinPython-Konsolenskripte liegen nicht im `PATH`).

| Skript | Zweck |
| --- | --- |
| `coverage_offline.py` | Offline-Coverage-Gate: Zeilenabdeckung je Kernmodul via stdlib `trace` ([ADR 0003](../docs/adr/0003-offline-test-and-coverage-tooling.md)). Aufruf: `python -m scripts.coverage_offline`. |
| `ingest.py` | (Phase 2/6, **noch nicht vorhanden**) Drop-in → Extraktion → Canonical JSON → Index-Update. |
| `update_overview.py` | (Phase 2, **noch nicht vorhanden**) Entwurfszeilen für `Übersicht.md` erzeugen. |

Damit `python -m scripts.…` funktioniert, enthält der Ordner ein `__init__.py`.
