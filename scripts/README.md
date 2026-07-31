# scripts/

Entwickler-Hilfsskripte (kein MCP-Server). Aufruf stets über `python -m scripts.<name>`
vom Repository-Wurzelverzeichnis (WinPython-Konsolenskripte liegen nicht im `PATH`).

| Skript | Zweck |
| --- | --- |
| `coverage_offline.py` | Offline-Coverage-Gate: Zeilenabdeckung je Kernmodul via stdlib `trace` ([ADR 0003](../docs/adr/0003-offline-test-and-coverage-tooling.md)). Aufruf: `python -m scripts.coverage_offline`. |
| `ingest.py` | Drop-in-Ingestion: `papers/*.pdf` → Canonical JSON → TF-IDF/SQLite-Index **+ Paper-Ähnlichkeitsgraph mit Louvain-Communities** (Option B, [ADR 0007](../docs/adr/0007-graphrag-index-phase3-option-b.md)). Aufruf: `python -m scripts.ingest`. |
| `ask.py` | Frage über Basic Search mit Provenienz beantworten. Aufruf: `python -m scripts.ask "<Frage>"`. |
| `graph_info.py` | Read-only-Übersicht der Graph-Communities (Keywords, Vertreter, Auszug); Phase-3-Nachweis ([ADR 0007](../docs/adr/0007-graphrag-index-phase3-option-b.md)). Aufruf: `python -m scripts.graph_info`. |
| `update_overview.py` | Übersicht-Entwürfe: deterministische, extraktive Entwurfszeilen **append-only** nach `data/overview_drafts.md` (kuratierte `Übersicht.md` bleibt unangetastet, [ADR 0006](../docs/adr/0006-canonical-model-phase2-scope.md)). Aufruf: `python -m scripts.update_overview`. |

Damit `python -m scripts.…` funktioniert, enthält der Ordner ein `__init__.py`.
