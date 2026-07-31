# Repository-Struktur und Definition of Done

Dieses Dokument legt die **verbindliche Ordnerstruktur** fest und fasst die **Definition of Done** zusammen. Struktur und Disziplin orientieren sich an `mcs-copilot-tools`, sind aber auf **ein** src-Layout-Paket mit **einem** MCP-Server zugeschnitten.

---

## 1. Verbindliche Ordnerstruktur

```
research-graphrag/
├─ README.md                     # Zielbild & Kontext
├─ Roadmap.md                    # Phasenplan (0–7)
├─ Übersicht.md                  # Kuratierte Literaturübersicht (Quellen-Tabelle)
├─ CONTRIBUTING.md               # Zentrales Regelwerk
├─ pyproject.toml                # src-Layout, Kern-Deps + Extras [pipeline]/[dev]
├─ requirements.lock             # eingefrorene Gesamtauflösung (pip freeze, ADR 0002)
├─ .env.example                  # Beispiel-Umgebungsvariablen (keine Secrets)
├─ docs/
│  ├─ vscode-integration.md
│  ├─ repository-structure.md    # dieses Dokument
│  ├─ documentation-standards.md
│  ├─ testing.md
│  ├─ error-model.md
│  ├─ glossary.md
│  └─ adr/
│     ├─ README.md
│     └─ 0001-*.md … 0005-*.md
├─ templates/
│  ├─ tool-spec.md
│  ├─ tool-code-walkthrough.md
│  ├─ server-README.md
│  └─ adr-template.md
├─ scripts/
│  ├─ __init__.py
│  ├─ README.md
│  ├─ coverage_offline.py        # Offline-Coverage-Gate (ADR 0003)
│  ├─ ingest.py                  # (Phase 2/6, noch nicht vorhanden)
│  └─ update_overview.py         # (Phase 2, noch nicht vorhanden)
├─ src/research_graphrag/
│  ├─ __init__.py                # Paket-Version
│  ├─ extraction/                # (Phase 2) Docling/Marker → Canonical JSON
│  ├─ indexing/                  # (Phase 3) GraphRAG-Orchestrierung
│  ├─ retrieval/                 # (Phase 4) Query-Router (Local/Global/DRIFT/Basic)
│  └─ mcp_server/                # (Phase 5) MCP-Server (stdio) mit Tools + specs/
├─ eval/
│  └─ pruef-fragen.md            # Prüf-Fragen über alle 5 Fragetypen
├─ recherche/                    # (Phase 1) migrierte Rechercheartefakte (noch nicht vorhanden)
├─ papers/                       # PDF-Korpus (nicht versioniert)
├─ data/                         # Canonical JSON, manifest.json, graphrag/ (nicht versioniert)
└─ tests/                        # gespiegelt zu src/research_graphrag/
   ├─ conftest.py
   └─ test_smoke.py
```

> **Phasen-Hinweis:** Einträge mit „(Phase n)" sind der jeweiligen Roadmap-Phase zugeordnet. In Phase 0 existieren die Unterpakete unter `src/research_graphrag/` als **importierbare Platzhalter**; `scripts/ingest.py`, `scripts/update_overview.py` und der Ordner `recherche/` werden erst in ihrer Phase angelegt.

### Zuordnung zu den Roadmap-Phasen

| Ordner | Verantwortung | Phase |
| --- | --- | --- |
| `src/research_graphrag/extraction/` | PDF → Canonical Paper JSON (Docling/Marker) | 2 |
| `src/research_graphrag/indexing/` | Canonical JSON → GraphRAG-Index | 3 |
| `src/research_graphrag/retrieval/` | Query-Router (Local/Global/DRIFT/Basic) | 4 |
| `src/research_graphrag/mcp_server/` | MCP-Server (stdio) mit Tools + Provenienz | 5 |

---

## 2. Konventionen

- **Ein Tool = ein Modul** unter `src/research_graphrag/mcp_server/tools/` (ab Phase 5).
- **Ein Tool = ein Test-Skript** unter `tests/mcp_server/test_<tool>.py`.
- **Ein Tool = eine Spezifikation** unter `src/research_graphrag/mcp_server/specs/<tool>.md`.
- **Ein nicht-triviales Tool = ein Code-Walkthrough** unter `src/research_graphrag/mcp_server/specs/<tool>.code.md` (siehe [documentation-standards.md](documentation-standards.md)).
- Der Server-Einstiegspunkt (`python -m research_graphrag.mcp_server`) registriert die Tools und startet den `stdio`-Transport.
- **Tool-Namen** sind sprechend und domänenbezogen: `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper`, `list_topics` (siehe [README.md](../README.md)).

---

## 3. Definition of Done (pro Beitrag)

Identisch zu [CONTRIBUTING.md](../CONTRIBUTING.md), hier als Checkliste (right-sized):

- [ ] Vollständige Type-Hints; `mypy` ohne Fehler.
- [ ] `ruff` (Lint + Format) ohne Befunde.
- [ ] Docstrings für alle öffentlichen Funktionen/Tools.
- [ ] Tests vorhanden und grün.
- [ ] Für MCP-Tools: Tool-Spezifikation (+ Code-Walkthrough bei nicht-trivialen Tools).
- [ ] Zeilenabdeckung als Richtwert ≥ 80 % pro Kernmodul.
- [ ] Provenienz-Angaben, wo Ergebnisse abgeleitet werden.
- [ ] Reproduzierbarkeit sichergestellt (Seeds/Versionen).
- [ ] Bei Architekturentscheidungen: ADR angelegt.

---

## 4. Definition of Done (Server, ab Phase 5)

- [ ] Der Server startet fehlerfrei über `stdio` (`python -m research_graphrag.mcp_server`).
- [ ] Alle enthaltenen Tools erfüllen ihre Definition of Done.
- [ ] Server-README ([templates/server-README.md](../templates/server-README.md)) vollständig.
- [ ] Einbindungsbeispiel in [docs/vscode-integration.md](vscode-integration.md) nachvollziehbar.
- [ ] Integrationstests vorhanden, wo Tools zusammenwirken (Extraktion → Index → Retrieval).
