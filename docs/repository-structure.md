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
│     └─ 0001-*.md … 0010-*.md
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
│  ├─ ask.py                     # Frage → Retrieval-Modi (Basic/Local/Global/DRIFT + Router)
│  ├─ update_overview.py         # Übersicht-Entwürfe → data/overview_drafts.md (Option B)
│  ├─ graph_info.py              # Community-Übersicht (read-only, Phase 3)
│  ├─ status.py                  # Read-only Index-/Korpus-Status + Konsistenz (Phase 6)
│  └─ qa.py                      # Prüf-Fragen je Modus durchspielen (QS-Harness, Phase 6)
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
│  ├─ indexing/                  # Canonical JSON → Offline-Hybrid-Index (Option B)
│  │  ├─ tfidf_index.py          #   TF-IDF-Index über SQLite
│  │  └─ graph_index.py          #   Paper-Ähnlichkeitsgraph + Louvain-Communities (Phase 3)
│  ├─ retrieval/                 # Query-Router: Basic/Local/Global/DRIFT (Phase 4)
│  │  ├─ basic.py                #   search_basic (TF-IDF-Top-k)
│  │  ├─ local.py                #   search_local (Chunk-Nachbarschaft + Paper-Fan-out)
│  │  ├─ global_search.py        #   search_global (Community-Ranking)
│  │  ├─ drift.py                #   search_drift (Global→Local-Hybrid)
│  │  ├─ router.py               #   Heuristik-Router (Fragetyp → Modus)
│  │  ├─ provenance.py           #   Citation/PaperRef + Provenienz-Assembler
│  │  └─ paper.py                #   get_paper (Paper-Metadaten aus dem Index, Phase 5)
│  ├─ overview/drafts.py         # Übersicht-Entwürfe (Staging, Phase 2)
│  └─ mcp_server/                # MCP-Server (stdio), Phase 5
│     ├─ server.py               #   FastMCP: 6 Tools + Fehlerübersetzung an der Grenze
│     ├─ __main__.py             #   Einstiegspunkt (python -m research_graphrag.mcp_server)
│     ├─ README.md               #   Server-README
│     └─ specs/                  #   Pro-Tool-Spezifikationen (6 Tools)
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
   ├─ retrieval/                 # Basic/Local/Global/DRIFT + Router + Provenienz + get_paper + QS-Harness (Phase 4/5/6)
   ├─ overview/                  # Übersicht-Entwürfe (Phase 2)
   ├─ mcp_server/                # Server-Contract via In-Memory-Client (Phase 5)
   └─ integration/               # End-to-End-Durchstich (M1) + Drop-in-Freshness/atomarer Swap (Phase 6)
```

> **Phasen-Hinweis:** Einträge mit „(Phase n)" markieren die Phase der **vollen** Ausbaustufe. In **Phase 0b** sind bereits lauffähige Offline-Hybrid-Implementierungen vorhanden (`errors.py`, `pipeline.py`, `extraction/pdf.py`, `indexing/tfidf_index.py`, `retrieval/basic.py`, `scripts/ingest.py`, `scripts/ask.py`). In **Phase 2** kamen die Extraktions-Submodule (`extraction/model.py`, `structure.py`, `chunking.py`, `quality.py`), das Paket `overview/` und `scripts/update_overview.py` hinzu. In **Phase 3** kamen `indexing/graph_index.py` (Paper-Ähnlichkeitsgraph + Louvain-Communities) und `scripts/graph_info.py` hinzu. In **Phase 4** kamen die Retrieval-Module (`retrieval/local.py`, `global_search.py`, `drift.py`, `router.py`, `provenance.py`) hinzu; der Index wurde additiv um `section_title` erweitert (Schema 0.2.0, [ADR 0008](adr/0008-retrieval-and-query-router-phase4.md)). In **Phase 5** kamen der MCP-Server (`mcp_server/server.py`, `__main__.py`, `README.md`) und `retrieval/paper.py` (`get_paper`) hinzu; der Index wurde additiv um `identifiers` (DOI/arXiv) erweitert (Schema 0.3.0, [ADR 0009](adr/0009-mcp-server-stdio-phase5.md)). In **Phase 6** kamen `scripts/status.py` (read-only Status/Konsistenz) und `scripts/qa.py` (QS-Harness) sowie der **atomare Index-Swap** in `pipeline.py` hinzu (On-Read gehärtet, [ADR 0010](adr/0010-drop-in-workflow-and-qa-phase6.md)); Index-/Canonical-Schema bleiben unverändert. Der Ordner `recherche/` wird erst in seiner Phase angelegt.

### Zuordnung zu den Roadmap-Phasen

| Ordner | Verantwortung | Phase |
| --- | --- | --- |
| `src/research_graphrag/extraction/` | PDF → Canonical Paper JSON (`pypdf`) | 2 |
| `src/research_graphrag/indexing/` | Canonical JSON → Offline-Hybrid-Index (TF-IDF + networkx/SQLite) | 3 |
| `src/research_graphrag/retrieval/` | Query-Router (Local/Global/DRIFT/Basic) | 4 |
| `src/research_graphrag/mcp_server/` | MCP-Server (stdio) mit Tools + Provenienz | 5 |

---

## 2. Konventionen

- **Tool-Logik = ein Modul** unter `src/research_graphrag/retrieval/` (bzw. ein dediziertes Read-Modul wie `retrieval/paper.py`); `server.py` registriert die Tools als **dünne Wrapper**. Ein separates `mcp_server/tools/`-Verzeichnis ist bei diesem Zuschnitt bewusst nicht nötig (right-sized, [ADR 0009](adr/0009-mcp-server-stdio-phase5.md)).
- **Tool-Contracts** werden in `tests/mcp_server/` über einen In-Memory-Client geprüft; die Backend-Funktionen zusätzlich in `tests/retrieval/`.
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
