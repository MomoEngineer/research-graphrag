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
├─ pyproject.toml                # src-Layout, Kern-Deps (Offline-Hybrid) + Extra [dev]
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
│  ├─ ingest.py                  # Drop-in → Canonical JSON → Index (Option B)
│  ├─ ask.py                     # Frage → Basic Search (Provenienz)
│  └─ update_overview.py         # Übersicht-Entwürfe → data/overview_drafts.md (Option B)
├─ src/research_graphrag/
│  ├─ __init__.py                # Paket-Version
│  ├─ errors.py                  # gemeinsame Fehlertaxonomie (docs/error-model.md)
│  ├─ pipeline.py                # Drop-in-Ingestion (papers/ → Canonical → Index)
│  ├─ extraction/                # pypdf → Canonical Paper JSON 0.2.0 (Option B)
│  │  ├─ model.py                #   Datenmodell (Section/Chunk/CanonicalPaper)
│  │  ├─ structure.py            #   Section-/Identifier-Heuristik
│  │  ├─ chunking.py             #   größenbasiertes Chunking
│  │  ├─ quality.py              #   Qualitäts-Gates (Flags)
│  │  └─ pdf.py                  #   Orchestrator extract_pdf
│  ├─ indexing/tfidf_index.py    # TF-IDF-Index über SQLite (Option B)
│  ├─ retrieval/basic.py         # Basic Search (search_basic) mit Provenienz
│  ├─ overview/drafts.py         # Übersicht-Entwürfe (Staging, Phase 2)
│  └─ mcp_server/                # (Phase 5) MCP-Server (stdio) + specs/
├─ eval/
│  └─ pruef-fragen.md            # Prüf-Fragen über alle 5 Fragetypen
├─ recherche/                    # (Phase 1) migrierte Rechercheartefakte (noch nicht vorhanden)
├─ papers/                       # PDF-Korpus (nicht versioniert)
├─ data/                         # Canonical JSON 0.2.0, manifest.json, index/, quality_report.*, overview_drafts.md (nicht versioniert)
└─ tests/                        # gespiegelt zu src/research_graphrag/
   ├─ conftest.py                # anyio-Backend + make_pdf-Fixture
   ├─ test_smoke.py
   ├─ test_errors.py
   ├─ test_pipeline.py
   ├─ extraction/                # PDF-Extraktion + Struktur/Chunking/Qualität (Phase 2)
   ├─ indexing/                  # TF-IDF/SQLite-Index (0b)
   ├─ retrieval/                 # Basic Search (0b)
   ├─ overview/                  # Übersicht-Entwürfe (Phase 2)
   └─ integration/               # End-to-End-Durchstich (M1)
```

> **Phasen-Hinweis:** Einträge mit „(Phase n)" markieren die Phase der **vollen** Ausbaustufe. In **Phase 0b** sind bereits lauffähige Offline-Hybrid-Implementierungen vorhanden (`errors.py`, `pipeline.py`, `extraction/pdf.py`, `indexing/tfidf_index.py`, `retrieval/basic.py`, `scripts/ingest.py`, `scripts/ask.py`). In **Phase 2** kamen die Extraktions-Submodule (`extraction/model.py`, `structure.py`, `chunking.py`, `quality.py`), das Paket `overview/` und `scripts/update_overview.py` hinzu. Der Ordner `recherche/` wird erst in seiner Phase angelegt; `mcp_server/` wird in Phase 5 registriert.

### Zuordnung zu den Roadmap-Phasen

| Ordner | Verantwortung | Phase |
| --- | --- | --- |
| `src/research_graphrag/extraction/` | PDF → Canonical Paper JSON (`pypdf`) | 2 |
| `src/research_graphrag/indexing/` | Canonical JSON → Offline-Hybrid-Index (TF-IDF + networkx/SQLite) | 3 |
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
