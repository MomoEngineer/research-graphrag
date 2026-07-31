# scripts/

Entwickler-Hilfsskripte (kein MCP-Server). Aufruf stets über `python -m scripts.<name>`
vom Repository-Wurzelverzeichnis (WinPython-Konsolenskripte liegen nicht im `PATH`).

| Skript | Zweck |
| --- | --- |
| `coverage_offline.py` | Offline-Coverage-Gate: Zeilenabdeckung je Kernmodul via stdlib `trace` ([ADR 0003](../docs/adr/0003-offline-test-and-coverage-tooling.md)). Aufruf: `python -m scripts.coverage_offline`. |
| `ingest.py` | Drop-in-Ingestion: `papers/*.pdf` → Canonical JSON → TF-IDF/SQLite-Index (Option B). Aufruf: `python -m scripts.ingest`. |
| `ask.py` | Frage über Basic Search mit Provenienz beantworten. Aufruf: `python -m scripts.ask "<Frage>"`. |
| `update_overview.py` | (Phase 2, **noch nicht vorhanden**) Entwurfszeilen für `Übersicht.md` erzeugen. |

Damit `python -m scripts.…` funktioniert, enthält der Ordner ein `__init__.py`.
