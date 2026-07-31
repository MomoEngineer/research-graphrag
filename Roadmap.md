# Roadmap – Research-GraphRAG

Phasenweiser Umsetzungsplan für den persönlichen Scientific-GraphRAG-Assistenten. Der Plan ist **iterativ**: erst ein dünner, lauffähiger Durchstich, dann gezielte Ausbaustufen. **Bewusst ohne Zeitschätzungen** – Fortschritt wird über die „Definition of Done" (DoD) je Phase und über Meilensteine gemessen.

> Ergänzt die [README](README.md). Änderungen an Entscheidungen werden hier fortgeschrieben.

---

## Leitprinzipien

- **Lean & container-frei:** reine Python-Umgebung, kein Docker-/DB-Server im MVP.
- **Provenienz zuerst:** jede Antwort ist auf Paper/Abschnitt/Seite rückführbar.
- **Inkrementell nutzbar:** neue PDFs per Drop-in-Ordner + Skript, ohne alles neu aufzusetzen.
- **Klein, aber wachstumsfähig:** optimiert für ≤ 500 Paper, mit klaren Erweiterungspfaden.
- **Wiederverwenden statt neu bauen:** MCP-SDK sowie `scikit-learn`/`networkx`/`pypdf` als Fundament der Offline-Variante (Option B, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)); Microsoft GraphRAG/Docling bleiben Zielbild, falls beschaffbar.
- **Konsolidierte Forschungsbasis:** ersetzt den bisherigen `Recherche`-Ordner und vereint PDFs, kuratierte Literaturübersicht (`Übersicht.md`) und GraphRAG-Index in einem Repo.

## Offene Entscheidungen (mit Empfehlung)

| Entscheidung | Optionen | Empfehlung |
|---|---|---|
| **Index-LLM / Embeddings** | Cloud-API (Azure OpenAI/OpenAI) · lokal via Ollama · hybrid | **Entschieden: Offline-Hybrid (Option B)** – Cloud/Ollama offline nicht beschaffbar; **TF-IDF** im Index, LLM nur zur Abfragezeit via Bridge ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)). |
| **Primär-Extraktor** | Docling · Marker | **Entschieden: `pypdf` (Option B)** – Docling/Marker offline nicht beschaffbar; `pypdf` liefert Text + Seiten-Provenienz, Docling/Marker als späterer Ausbau ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)). |
| **Index-Aktualisierung** | voller Re-Index · inkrementelles `graphrag update` | **Voller Re-Index** als Standard (bei ≤ 500 günstig & konsistent); inkrementelles Update als spätere Optimierung. |
| **Ingestion-Trigger** | manuelles Skript · Auto-Watcher | **Manuelles Skript** zuerst (vorhersehbar); Auto-Watcher als Ausbaustufe. |
| **`papers/`-Layout bei Migration** | flach · Cluster-Unterordner beibehalten | **Flach** (eine Ebene) für einfache Dedup/Links; Themencluster leben in `Übersicht.md`, nicht im Dateisystem. |
| **Übersicht-Pflege** | rein manuell · Pipeline-Entwurf + Kuratierung | **Pipeline-Entwurf** (Auto-Spalten) + **menschliche Kuratierung** der wertenden Spalten (Relevanz, SRQ). |

Diese Punkte werden spätestens in der jeweiligen Phase final entschieden und hier aktualisiert.

---

## Phasen

### Phase 0 – Fundament & Setup
**Ziel:** reproduzierbares, leeres Grundgerüst.

- Repo-Struktur (src-Layout), `pyproject.toml`, virtuelle Umgebung.
- LLM-/Embedding-Backend auswählen und anbinden (siehe offene Entscheidungen).
- Pragmatisches **Prüf-Fragen-Set** anlegen (über alle 5 Fragetypen).

**DoD:** `pip install -e .` läuft; Backend erreichbar; Dummy-Durchlauf über 1 Dokument erzeugt Artefakte.

> **Status:** ✅ umgesetzt – 0a (Gerüst) und 0b (Offline-Hybrid-Durchstich) fertig; **M1 erreicht** (1 PDF → Index → belegte Antwort). Umsetzung als Option B ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)); Backend = TF-IDF offline + LLM-Bridge zur Abfragezeit. Kernmodule 100 % Zeilenabdeckung.

### Phase 1 – Migration der bestehenden Recherche
**Ziel:** bestehende Literatur & Recherche vollständig ins Repo übernommen.

- **PDFs übernehmen:** alle Paper aus `Recherche/` nach `papers/` (flaches Layout, siehe offene Entscheidungen).
- **Rechercheartefakte migrieren:** Prompts, Zusammenfassungen, Gap-Analyse nach `recherche/`.
- **Übersicht portieren:** `Übersicht.md` übernehmen, interne Links auf `papers/` umbiegen und Vollständigkeit gegen den Altbestand prüfen.
- **Pilot-Korpus markieren:** ~20–30 repräsentative Paper (gute/schlechte Scans, Tabellen, Formeln) für die Pipeline-Entwicklung.
- Alten `Recherche`-Ordner erst nach Verifikation als „nicht mehr gepflegt" kennzeichnen.

**DoD:** alle PDFs in `papers/`, Artefakte in `recherche/`, `Übersicht.md` mit funktionierenden internen Links; Umfang entspricht dem Altbestand.

### Phase 2 – PDF-Ingestion, Canonical Model & Übersicht
**Ziel:** robuste PDF → kanonisches JSON, nur neue/geänderte Dateien; Übersicht-Entwürfe.

- `pypdf`-Extraktor integrieren (Option B, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)); Docling/Marker als späterer Ausbau, falls beschaffbar.
- **Canonical Paper JSON** definieren: stabile IDs, Section-Hierarchie (heuristisch), Chunk-IDs, Referenz-Abschnitt, Seiten-/Section-Provenienz, Extraktions-Qualitätsflags. **Bounding-Box-Provenienz** und tiefes Referenz-Parsing sind bewusst zurückgestellt ([ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md), Phase 7).
- **Dedup & Cache:** `manifest.json` (Datei-Hash → Paper-ID); unveränderte PDFs überspringen.
- **Qualitäts-Gates:** fehlender Abstract, kaputte Referenzen, OCR-Rauschen, leere/kopflose Tabellen, zu kurze/lange Chunks.
- **Übersicht-Entwurf:** `scripts/update_overview.py` erzeugt **deterministische, extraktive** Entwurfszeilen (Name, Interner/Externer Link, Keyword, Kurzzusammenfassung) **append-only** nach `data/overview_drafts.md` (Staging, kuratierte `Übersicht.md` bleibt unangetastet); wertende Spalten bleiben manuell.
- Grundgerüst `scripts/ingest.py`.

**DoD:** PDFs in `papers/` + `ingest.py` erzeugen Canonical JSON nur für neue/geänderte Dateien inkl. Qualitätsreport; neue Paper erscheinen als Entwurfszeile in `data/overview_drafts.md`.

> **Status:** ✅ umgesetzt – Canonical-Schema **0.2.0** (Section-Heuristik, größenbasiertes Chunking, DOI/arXiv, Qualitätsflags), Qualitätsreport (`data/quality_report.json`/`.md`) und `scripts/update_overview.py` (Staging-Entwürfe) laufen und sind getestet (84 Tests grün, Kernmodule ≥ 96 % Zeilenabdeckung). Umfangsabgrenzung (keine Bounding-Boxes, kein tiefes Referenz-/Tabellen-Parsing): [ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md).

### Phase 3 – GraphRAG-Index (file-based)
**Ziel:** Wissensgraph + Community-Reports aus Canonical JSON.

> **Umsetzung als Offline-Hybrid (Option B, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)):** statt Microsoft GraphRAG/LanceDB/Leiden → **TF-IDF** (`scikit-learn`), Graph + **Louvain** (`networkx`), Speicher in **SQLite**; Community-Zusammenfassungen extraktiv bzw. on-demand über die LLM-Bridge. Die folgenden MS-GraphRAG-Punkte bleiben das Zielbild (Option C).

- Canonical JSON → GraphRAG-Input (JSON/JSONL bzw. Custom InputReader / BYO-DataFrame).
- `settings.yaml`: Chunking, Entity-/Relationship-/(Claim-)Extraktion, Community-Detection (Leiden), Embeddings.
- **Prompt-Tuning** für die wissenschaftliche Domäne.
- Artefakte als Parquet + LanceDB.

**DoD:** Indexlauf abgeschlossen; Artefakte vorhanden; erste Abfrage per GraphRAG-CLI erfolgreich.

> **Status:** ✅ umgesetzt (Option B, [ADR 0007](docs/adr/0007-graphrag-index-phase3-option-b.md)): deterministischer **Paper-Ähnlichkeitsgraph** (TF-IDF, *mutual top-k*) mit **Louvain-Communities** (fixer Seed) und **extraktiven** Zusammenfassungen (repräsentative Paper + Top-TF-IDF-Keywords), additiv in `data/index/index.sqlite` (`graph_nodes`/`graph_edges`/`communities`/`community_members`). Der Graph-Bau ist in `python -m scripts.ingest` integriert; `IngestReport` zählt Knoten/Kanten/Communities, `python -m scripts.graph_info` zeigt sie. **DoD-Anpassung:** mangels „GraphRAG-CLI“ (offline nicht vorhanden) erfolgt der Nachweis über Tests, die `IngestReport`-Kennzahlen und `scripts/graph_info`. Realer Korpuslauf: **145 Knoten, 216 Kanten, 42 Communities**; Chunk-/Entitäts-Ebene bleibt zurückgestellt (Phase 4/7). 97 Tests grün, Kernmodule ≥ 96 % (graph_index 98,7 %).

### Phase 4 – Retrieval & Query-Router
**Ziel:** passender Suchmodus je Fragetyp, mit Provenienz.

- Local / Global / DRIFT / Basic Search kapseln.
- Leichtgewichtiger **Router** (heuristisch oder explizite Werkzeug-Wahl) gemäß Fragetyp-Mapping.
- Provenienz-Assembler (Paper-ID, Abschnitt, Seite/Chunk).

**DoD:** alle 5 Fragetypen per CLI beantwortbar, jeweils mit Quellenangaben.

> **Status:** ✅ umgesetzt (Option B, [ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md)): **Basic** (TF-IDF-Top-k), **Local** (Chunk-Nachbarschaft zur Abfragezeit **+** Paper-Fan-out über den Phase-3-Graphen), **Global** (Query→Community-Ranking mit repräsentativer Paper-Provenienz) und **DRIFT** (pragmatischer Global→Local-Hybrid) sind in `src/research_graphrag/retrieval/` gekapselt. Ein schlanker Heuristik-**Router** (`--mode auto`) plus **explizite** Modus-Wahl decken das Fragetyp-Mapping ab; der **Provenienz-Assembler** liefert Paper · Abschnitt · Seite/Chunk – dazu wurde der Index additiv um `section_title` erweitert (Schema **0.2.0**, voller Re-Ingest). **DoD-Nachweis:** alle 5 Fragetypen per `python -m scripts.ask "<frage>" [--mode …]` belegt beantwortet (siehe [eval/pruef-fragen.md](eval/pruef-fragen.md)). **145 Tests grün**, Kernmodule ≥ 96 % (retrieval-Module 100 %). Realer Korpuslauf: **145 Paper / 14 397 Chunks / 42 Communities**; echtes iteratives DRIFT und ein semantischer Entitäts-/Zitationsgraph bleiben zurückgestellt (Phase 7).

### Phase 5 – MCP-Server (stdio) & Copilot-Integration
**Ziel:** Retrieval als Werkzeuge in Copilot.

- Python-MCP-Server (stdio) mit Werkzeugen: `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper`, `list_topics`.
- Jede Werkzeug-Antwort mit strukturierter Provenienz.
- Registrierung in VS Code (`.vscode/mcp.json`), Kurzdoku.

**DoD:** Copilot ruft die Werkzeuge auf und erhält belegte Antworten mit Quellen.

> **Status:** ✅ umgesetzt ([ADR 0009](docs/adr/0009-mcp-server-stdio-phase5.md)): Der **stdio-MCP-Server** (`python -m research_graphrag.mcp_server`, FastMCP) registriert alle sechs Werkzeuge (`search_basic`/`search_local`/`search_global`/`search_drift`/`get_paper`/`list_topics`); jede Antwort trägt strukturierte Provenienz, fachliche Fehler werden an der Server-Grenze in `isError`-Ausgaben (`{"error": …}`) übersetzt. **Kein** serverseitiges LLM-Sampling – die Tools liefern Evidenz, Copilot formuliert (Abgrenzung zu [ADR 0004](docs/adr/0004-llm-bridge-via-mcp-sampling.md)). Einbindung über [`.vscode/mcp.json`](.vscode/mcp.json) (venv-Interpreter). Für zitierfähige `get_paper`-Metadaten wurde der Index additiv auf **Schema 0.3.0** (Identifikatoren) erweitert; Re-Ingest bestätigt (**145 Paper / 14 397 Chunks / 42 Communities**, 142/145 mit DOI/arXiv). **DoD-Anpassung:** mangels steuerbarem Copilot-Client erfolgt der Nachweis – wie in Phase 3/4 – über Tests, insbesondere einen **In-Memory-Client-Roundtrip** über alle sechs Tools (Erfolg + Fehler-Envelope). Tests grün; Chunk-/Entitäts-Ebene und ein LLM-Synthese-Pfad bleiben zurückgestellt (Phase 7).

### Phase 6 – Drop-in-Workflow & Qualitätssicherung
**Ziel:** reibungsloser „ablegen → nutzen"-Kreislauf.

- `ingest.py` bindet Extraktion-Dedup + Index-Aktualisierung zu einem Befehl zusammen (voller Re-Index Standard; inkrementelles Update dokumentiert).
- MCP-Server liest stets die **aktuellen** Artefakte (Reload/On-Read).
- Pragmatische QS: Prüf-Fragen durchspielen, Provenienz-Stichproben, einfaches Logging/Status.

**DoD:** neue PDF ablegen → `ingest.py` → sofort in Copilot abfragbar; unveränderte PDFs übersprungen.

### Phase 7 – Ausblick & Erweiterungen (optional, nach Bedarf)
**Ziel:** gezielte Vertiefung, wenn der Alltag es verlangt.

- **Domain-/Zitationsgraph** mit **Kuzu** (embedded) + **Text2Cypher** für deterministische Graphfragen und Multi-Hop-Zitationsnetze.
- **GROBID** für präzises Referenz-/Zitationskontext-Parsing (falls Docker/Java verfügbar).
- **Hybrid-Suche** (BM25 + Vektor) für exakte Fakten/Abkürzungen.
- **Inkrementelles** `graphrag update` statt vollem Re-Index bei wachsendem Bestand.
- **Auto-Watcher** für den Drop-in-Ordner.
- Skalierung Richtung Qdrant/Weaviate/Neo4j, falls der Bestand deutlich wächst.

---

## Literaturübersicht & Recherche-Migration

Das Repo übernimmt die Rolle des bisherigen `Recherche`-Ordners:

- **Einmalige Migration (Phase 1):** PDFs → `papers/`, Prompts/Zusammenfassungen/Gap-Analyse → `recherche/`, Tabelle → `Übersicht.md` (interne Links auf `papers/` umgebogen).
- **Laufende Pflege:** Ingestion erzeugt Entwurfszeilen; du kuratierst `Relevanz fuer Expose` und `SRQ-Zuordnung`. `Themenfokus` kann an GraphRAG-Communities ausgerichtet werden.
- **Rollen-Trennung:** `Übersicht.md` = *welche* Quellen und wie relevant; GraphRAG-Index = *was* inhaltlich darin steht.
- **Konsistenz:** `Übersicht.md` ist Single Source of Truth für die kuratierte Einordnung; der alte `Recherche`-Ordner wird nach erfolgreicher Migration nicht mehr gepflegt.

---

## Querschnittsthemen: Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| PDF-Extraktionsrauschen (Layout, Formeln, Scans) | Qualitäts-Gates, Provenienz zum Original, Stichproben; Docling/Marker als späterer Ausbau (ADR 0005). |
| Entity Resolution (Synonyme, gleichnamige Autoren) | Leichte Alias-/Synonym-Kuratierung; bei kleinem Korpus manuell handhabbar. |
| Scheinsicherheit durch Summaries | Antworten immer mit Quellenankern/Original-TextUnits; für Fakten Local/Basic bevorzugen. |
| Inkonsistenz bei inkrementellen Updates | Standard = voller Re-Index (konsistent); inkrementell nur dokumentiert/optional. |
| Kosten/Datenschutz des Index-LLM | Entschärft durch Option B: **kein** Index-LLM (offline, TF-IDF); LLM nur zur Abfragezeit via Bridge ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)). |

## Meilensteine

- **M0 – Migration:** PDFs, Recherche und `Übersicht.md` ins Repo übernommen (Phase 1).
- **M1 – Erster Durchstich:** ✅ erreicht – 1 PDF → Index → 1 Frage mit Quelle beantwortet (Offline-Hybrid, `python -m scripts.ingest` + `python -m scripts.ask`).
- **M2 – Copilot nutzt es:** ✅ erreicht – stdio-MCP-Server registriert ([`.vscode/mcp.json`](.vscode/mcp.json)), sechs Werkzeuge mit Provenienz; Korpus abfragbar (Nachweis über In-Memory-Client-Roundtrip, produktive Nutzung nach Trust-Prompt im Agent-Modus) (Phase 5).
- **M3 – Drop & Use:** nahtlose inkrementelle Ingestion + pragmatische QS (Phase 6).
- **M4 – Erweiterungen:** Graph-/Zitationsfunktionen nach Bedarf (Phase 7).
