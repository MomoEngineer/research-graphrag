# Research-GraphRAG

**Ein schlanker, container-freier Scientific-GraphRAG als persönlicher Forschungsassistent für lokale wissenschaftliche PDF-Paper – direkt nutzbar aus GitHub Copilot über einen MCP-Server.**

> **Status:** **Phase 0–5 umgesetzt.** Phase 0: Fundament + **Offline-Hybrid-Durchstich** (Roadmap-M1) – `pip install -e .`, Ingestion (`pypdf` → TF-IDF/SQLite) und belegte Basic-Search-Antworten laufen und sind getestet. Phase 1: **145 Paper** aus dem bisherigen `Recherche`-Ordner nach `papers/` migriert und [`Übersicht.md`](Übersicht.md) portiert (reduzierter Umfang – `recherche/`-Artefakte bewusst ausgelassen). Phase 2: **robuste Extraktion** (Canonical-Schema **0.2.0** mit Section-Heuristik, größenbasiertem Chunking, DOI/arXiv, Qualitätsflags), **Qualitätsreport** und **Übersicht-Entwürfe** (`scripts/update_overview.py` → `data/overview_drafts.md`) – Umfangsabgrenzung in [ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md). Phase 3: **GraphRAG-Index (Offline-Hybrid)** – deterministischer **Paper-Ähnlichkeitsgraph** (TF-IDF) mit **Louvain-Communities** und extraktiven Zusammenfassungen, integriert in `python -m scripts.ingest` und einsehbar über `python -m scripts.graph_info` ([ADR 0007](docs/adr/0007-graphrag-index-phase3-option-b.md)). Phase 4: **Retrieval & Query-Router** – **Basic/Local/Global/DRIFT** als deterministische, belegbare Offline-Modi plus schlanker Heuristik-Router (`python -m scripts.ask [--mode …]`); der **Provenienz-Assembler** liefert Paper · Abschnitt · Seite/Chunk (Index-Schema **0.2.0**) ([ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md)). Phase 5: **MCP-Server (stdio)** – die vier Retrieval-Modi sowie `get_paper` und `list_topics` sind als **MCP-Tools** für GitHub Copilot registriert (FastMCP; Fehlerübersetzung an der Server-Grenze; **kein** serverseitiges LLM-Sampling), eingebunden über [`.vscode/mcp.json`](.vscode/mcp.json); der Index wurde additiv auf Schema **0.3.0** (Identifikatoren für `get_paper`) erweitert ([ADR 0009](docs/adr/0009-mcp-server-stdio-phase5.md)). Die weiteren Phasen folgen der [Roadmap](Roadmap.md); die Umsetzung ist die **Offline-Variante (Option B, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md))**.

---

## Ziel & Kontext

Dieses Projekt baut ein **GraphRAG-System** über einer lokalen Sammlung wissenschaftlicher Paper (PDF). Ziel ist ein **persönlicher Forschungsassistent**, der die Inhalte der Paper für einen AI-Agenten (GitHub Copilot) deutlich besser nutzbar macht – von präzisen Detailfragen bis zu corpusweiten Zusammenhängen.

- **Kein Teil einer wissenschaftlichen Arbeit**, sondern ein Werkzeug, das die tägliche Arbeit mit Papern erleichtert (u. a. begleitend zu einer Masterarbeit genutzt).
- **Konsolidierte Forschungsbasis:** ersetzt den bisherigen separaten `Recherche`-Ordner und vereint PDFs, die kuratierte [Literaturübersicht](Übersicht.md) und den GraphRAG-Index an einem Ort.
- **Klein & lokal:** aktuell ~145 Paper, ausgelegt auf max. ~500.
- **Container-frei:** reine Python-Umgebung, kein Docker- oder Datenbank-Server nötig.
- **Drop-in-Workflow:** neue PDFs in einen Ordner legen, kurz ein Skript ausführen – fertig.

### Welche Fragen soll der Assistent beantworten?

| Fragetyp                          | Beispiel                                                       |
| --------------------------------- | -------------------------------------------------------------- |
| Präzise Detailfragen             | „Welche Methode verwendet Paper X in Abschnitt 4?"            |
| Cross-Paper-Synthese              | „Welche Forschungsrichtungen zeichnen sich im Korpus ab?"     |
| Zitations-/Autoren-/Methodennetze | „Welche Paper bauen auf Methode Y auf?"                       |
| Exakte Fakten                     | „Wie lautet die DOI bzw. der berichtete F1-Score in Paper Z?" |
| Widersprüche & Vergleiche        | „Wo widersprechen sich die Ergebnisse zu Thema T?"            |

## Literaturbasis & Übersicht

Die Paper stammen aus der Literaturrecherche zur Masterarbeit. Dieses Repo wird der **zentrale Ort** dafür und löst den bisherigen `Recherche`-Ordner ab: die PDFs liegen in `papers/`. Die zugehörige Recherche (Prompts, Zusammenfassungen, Forschungslücken) ist für `recherche/` vorgesehen, in Phase 1 aber bewusst noch nicht migriert.

Ergänzend zum GraphRAG-Index bleibt die **kuratierte Quellen-Tabelle** [`Übersicht.md`](Übersicht.md) erhalten – eine menschlich gepflegte Landkarte der Literatur nach **Themenclustern** und **Sub-Forschungsfragen (SRQ)**. Sie beantwortet, *welche* Quellen es gibt und wie relevant sie sind; der GraphRAG-Index beantwortet, *was inhaltlich* in ihnen steht.

| Aspekt | `Übersicht.md` (kuratiert) | GraphRAG-Index (automatisch) |
|---|---|---|
| Zweck | Quellen einordnen, bewerten, SRQ zuordnen | Inhalte durchsuchbar/fragbar machen |
| Pflege | menschlich, mit Pipeline-Entwurf | vollautomatisch bei Ingestion |
| Stärke | Relevanz, Struktur, Nachvollziehbarkeit | Detail-, Synthese- und Multi-Hop-Fragen |

Die Ingestion kann für neue PDFs **Entwurfszeilen** der Übersicht vorbefüllen (Titel, Links, Keywords, Kurzzusammenfassung); die wertenden Spalten (Relevanz, SRQ-Zuordnung) bleiben in deiner Hand.

## Kernidee: Lean Scientific GraphRAG

Statt Roh-PDFs „blind" in ein RAG zu werfen, trennen wir sauber in zwei Schichten:

1. **PDF-Verstehen zuerst:** hochwertige Extraktion in ein **kanonisches Paper-Modell** (Struktur, Metadaten, Referenzen, Provenienz).
2. **GraphRAG darüber:** Microsoft GraphRAG erzeugt aus diesem sauberen Zwischenformat einen Wissensgraphen mit Entitäten, Beziehungen, Communities und Community-Reports und beantwortet Fragen über **Local / Global / DRIFT / Basic Search**.

Der Zugriff erfolgt über einen **MCP-Server** (stdio), den GitHub Copilot in VS Code als Werkzeugquelle einbindet. Jede Antwort liefert **Provenienz** (Paper, Abschnitt, Seite/Chunk) zurück, damit Aussagen überprüfbar bleiben.

> **Warum GraphRAG und nicht nur klassisches Vektor-RAG?** Für reine „finde die Passage"-Fragen genügt hybride Vektor-Suche. Sobald **Zusammenhänge über mehrere Paper** (Methoden, Zitationen, Themen, Widersprüche) gefragt sind, spielt GraphRAG seine Stärken aus. Bei ~145 Papern ist der Nutzen der globalen/Community-Suche noch moderat und wächst mit dem Bestand mit.

## Architektur-Überblick

- ```mermaid
  flowchart LR
      A[papers/*.pdf<br/>Drop-in-Ordner]
      subgraph Ingestion["Ingestion · scripts/ingest.py"]
          B[Extraktion<br/>Docling / Marker]
          C[Canonical Paper JSON<br/>Struktur · Referenzen · Provenienz]
          D[Microsoft GraphRAG<br/>Entities · Relationships<br/>Communities · Reports]
      end
      E[(File-based Store<br/>Parquet + LanceDB)]
      subgraph Retrieval["Retrieval · MCP"]
          F[Query-Router<br/>Local · Global · DRIFT · Basic]
          G[MCP-Server<br/>stdio · Tools + Provenienz]
      end
      H[GitHub Copilot<br/>in VS Code]

      A --> B --> C --> D --> E --> F --> G --> H
  ```
- **Ingestion** (links): PDF → kanonisches JSON → GraphRAG-Index. Angestoßen durch ein manuelles Skript; nur neue/geänderte PDFs werden neu verarbeitet (Dedup per Datei-Hash).
- **Retrieval** (rechts): Der Query-Router wählt den passenden Suchmodus; der MCP-Server stellt die Ergebnisse Copilot als Werkzeuge bereit.

> **Hinweis:** Das Diagramm zeigt das **Zielbild**. Die aktuelle Umsetzung folgt der **Offline-Variante (Option B)** – `pypdf` statt Docling, TF-IDF + `networkx`/Louvain + SQLite statt GraphRAG/LanceDB (siehe [Tech-Stack](#tech-stack) und [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)).

## Workflow: neue Paper hinzufügen

1. PDF(s) in den Ordner `papers/` legen.
2. Skript ausführen: `python scripts/ingest.py`
3. Das Skript extrahiert **nur neue/geänderte** PDFs, aktualisiert das kanonische JSON und baut den GraphRAG-Index neu (voller Re-Index ist bei diesem Umfang günstig und konsistent).
4. Für neue Paper erzeugt `python -m scripts.update_overview` **Entwurfszeilen** (Titel, Links, Keywords, Kurzzusammenfassung) append-only in `data/overview_drafts.md` – die kuratierte [`Übersicht.md`](Übersicht.md) bleibt unangetastet; Relevanz und SRQ-Zuordnung pflegst du dort manuell nach.
5. Der MCP-Server nutzt die aktualisierten Artefakte – die neuen Paper sind in Copilot sofort verfügbar.

## Fragetypen → Suchmodus

| Fragetyp                             | Primärer Suchmodus | Warum                                                                                      |
| ------------------------------------ | ------------------- | ------------------------------------------------------------------------------------------ |
| Detailfrage zu einem Paper           | Local + Basic       | Startet an relevanten Entitäten, zieht TextUnits/Beziehungen; Basic für exakte Passagen. |
| Cross-Paper-Synthese / Themen        | Global              | Nutzt Community-Reports (Map-Reduce) für corpusweite Fragen.                              |
| Zitations-/Methodennetze (Multi-Hop) | Local (Fan-out)     | Folgt Beziehungen im Graphen; später ergänzt durch Text2Cypher (siehe Roadmap).          |
| Exakte Fakten (DOI, Metrik, Abk.)    | Basic               | Top-k-Vektorsuche auf Chunks; später Hybrid/BM25.                                         |
| Widersprüche / Vergleiche           | DRIFT               | Verbindet globale Community-Info mit lokaler Verfeinerung.                                 |

## Datenmodell (Überblick)

Zwei komplementäre Graph-Sichten:

- **Lexical/Document Graph:** `Paper` → `Section` → `Chunk` (+ `Figure`, `Table`, `Reference`) – erhält Struktur & Provenienz.
- **Domain Graph:** `Concept`, `Method`, `Dataset`, `Metric`, `Result`, `Claim`, `Author` und Beziehungen wie `CITES`, `USES_METHOD`, `EVALUATES_ON`, `SUPPORTED_BY`.

Details und Ausbaustufen siehe [Roadmap](Roadmap.md).

## Tech-Stack

> **Offline-Variante (Option B, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)):** In der aktuellen Offline-Umgebung sind **Microsoft GraphRAG, Docling und LanceDB nicht beschaffbar** (empirisch geprüft). Die **implementierte** Variante nutzt daher `pypdf` (Extraktion), **TF-IDF** (`scikit-learn`), `networkx`/**Louvain** und **SQLite**; ein LLM kommt nur zur Abfragezeit über die **LLM-Bridge** (MCP-Sampling, [ADR 0004](docs/adr/0004-llm-bridge-via-mcp-sampling.md)). Die folgende Tabelle bleibt das **Zielbild** (Option C), falls Wheels/Modelle verfügbar werden.

| Schicht                | Wahl (MVP)                                                                                                                         | Später / Optional                                                                  |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| PDF-Extraktion         | **Docling** (pure Python)                                                                                                    | **Marker** (formel-/layoutlastig), GROBID (Referenzen, benötigt Docker/Java) |
| Zwischenformat         | Canonical Paper**JSON/JSONL**                                                                                                | —                                                                                  |
| Index & Retrieval      | **Microsoft GraphRAG** (file-based)                                                                                          | Inkrementelles`graphrag update`                                                   |
| Vektor-/Speicher       | **LanceDB + Parquet** (eingebettet)                                                                                          | Qdrant/Weaviate (bei starkem Wachstum)                                              |
| Graph (Erweiterung)    | —                                                                                                                                 | **Kuzu** (embedded, Cypher, Text2Cypher)                                      |
| Agent-Anbindung        | **MCP-Server (Python, stdio)**                                                                                               | HTTP/SSE (Remote/Multi-User)                                                        |
| Consumer-Agent         | **GitHub Copilot** (VS Code)                                                                                                 | weitere MCP-Clients                                                                 |
| LLM/Embeddings (Index) | **entschieden (Option B):** offline **TF-IDF** im Index, LLM nur zur Abfragezeit via Bridge; Cloud-API/Ollama = Zielbild, falls verfügbar ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)) | —                                                                                  |

Alle MVP-Komponenten laufen **ohne Container** unter Windows in einer Python-Umgebung.

## Geplante Projektstruktur

```
research-graphrag/
├─ papers/                     # Alle Paper-PDFs (migriert aus Recherche/, nicht versioniert)
├─ Übersicht.md                # Kuratierte Literaturübersicht (Quellen-Tabelle)
├─ recherche/                  # Migrierte Rechercheartefakte
│  ├─ prompts/                 # Research-Prompts (Suchstrategien)
│  ├─ zusammenfassungen/       # Zusammenfassungen je Recherche-Runde
│  └─ forschungsluecken.md     # Themencluster × SRQ (Gap-Analyse)
├─ data/
│  ├─ canonical/               # extrahiertes Canonical Paper JSON (Cache)
│  ├─ manifest.json            # Datei-Hash → Paper-ID (Dedup)
│  ├─ index/                   # Offline-Hybrid-Index (SQLite + TF-IDF)
│  ├─ quality_report.json      # Qualitätsreport der Ingestion (+ .md)
│  └─ overview_drafts.md       # Übersicht-Entwürfe (Staging, append-only)
├─ scripts/
│  ├─ ingest.py                # Drop-in → Extraktion → Index-Update
│  └─ update_overview.py       # Entwurfszeilen → data/overview_drafts.md (Staging)
├─ src/research_graphrag/
│  ├─ extraction/              # pypdf → Canonical JSON (Option B)
│  ├─ indexing/                # Index-Orchestrierung (TF-IDF + networkx/SQLite)
│  ├─ retrieval/               # Query-Router (Local/Global/DRIFT/Basic)
│  ├─ overview/                # Übersicht-Entwürfe (Staging, Phase 2)
│  └─ mcp_server/              # MCP-Server (stdio) mit Tools
├─ eval/                       # Prüf-Fragen & Stichproben (pragmatische QS)
├─ pyproject.toml
├─ README.md
└─ Roadmap.md
```

## Voraussetzungen

- **Python 3.11+** (WinPython-Basis: 3.13) in einer virtuellen Umgebung (`.venv`).
- **Kein Docker**, kein externer Dienst.
- **LLM/Embeddings (Option B):** Der Index nutzt offline **TF-IDF** (kein externes Backend, keine Secrets); ein LLM kommt nur **zur Abfragezeit** über die **LLM-Bridge** (Copilot via MCP-Sampling, [ADR 0004](docs/adr/0004-llm-bridge-via-mcp-sampling.md)). Cloud-API/Ollama bleiben Zielbild ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)).
- **VS Code** mit GitHub Copilot für die MCP-Anbindung (Phase 5, umgesetzt – siehe [`.vscode/mcp.json`](.vscode/mcp.json)).

## Nutzung

```powershell
# 1. Umgebung einrichten (venv nutzt die WinPython-Toolchain wieder, offline)
python -m venv --system-site-packages .venv; .\.venv\Scripts\Activate.ps1
pip install -e . --no-build-isolation

# 2. Paper hinzufügen und indexieren (PDFs nach papers/ kopieren)
python -m scripts.ingest

# 2b. (optional) Entwurfszeilen für die Übersicht erzeugen (Staging)
python -m scripts.update_overview

# 3. Frage mit belegter Quelle stellen (Basic/Local/Global/DRIFT; ohne --mode = Heuristik-Router)
python -m scripts.ask "Welcher F1-Score wird berichtet?"
python -m scripts.ask "Welche Forschungsrichtungen zeichnen sich ab?" --mode global

# 4. MCP-Server nutzen: .vscode/mcp.json ist eingerichtet – in Copilot Chat
#    (Agent-Modus) die bereitgestellten Werkzeuge aufrufen
```

Der MCP-Server stellt u. a. Werkzeuge bereit wie `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper` und `list_topics` – jeweils mit Quellenangaben.

## Qualitätssicherung (pragmatisch)

Da dies ein persönliches Werkzeug ist: keine formale Evaluation, aber gezielte Prüfungen.

- Kleines, festes **Prüf-Fragen-Set** über alle Fragetypen.
- **Stichproben** der Provenienz (stimmen Quelle/Seite?).
- **Qualitäts-Gates** in der Ingestion (fehlender Abstract, kaputte Referenzen, OCR-Rauschen, leere Tabellen).

## Projektstatus & Roadmap

**Phase 0 ist umgesetzt** (Fundament + Offline-Hybrid-Durchstich, Roadmap-M1: 1 PDF → Index → belegte Antwort). **Phase 1 (Migration) ist im reduzierten Umfang umgesetzt:** 145 Paper aus dem bisherigen `Recherche`-Ordner nach `papers/` übernommen und [`Übersicht.md`](Übersicht.md) portiert (mit funktionierenden internen Links); die `recherche/`-Artefakte wurden bewusst ausgelassen, der Pilot-Korpus liegt als Vorschlag in [`eval/pilot-korpus.md`](eval/pilot-korpus.md). **Phase 2 ist umgesetzt:** robuste PDF-Extraktion (Canonical-Schema 0.2.0), Qualitätsreport und Übersicht-Entwürfe ([ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md)). **Phase 3 ist umgesetzt:** Offline-Hybrid-**GraphRAG-Index** – Paper-Ähnlichkeitsgraph (TF-IDF) mit Louvain-Communities und extraktiven Zusammenfassungen in `data/index/index.sqlite` ([ADR 0007](docs/adr/0007-graphrag-index-phase3-option-b.md)). **Phase 4 ist umgesetzt:** Basic/Local/Global/DRIFT-Suchmodi, ein schlanker Heuristik-Router und der Provenienz-Assembler (Paper · Abschnitt · Seite/Chunk; Index-Schema 0.2.0, [ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md)) – alle 5 Fragetypen sind per `python -m scripts.ask` belegbar ([eval/pruef-fragen.md](eval/pruef-fragen.md)). **Phase 5 ist umgesetzt:** der **stdio-MCP-Server** registriert `search_basic`/`search_local`/`search_global`/`search_drift` sowie `get_paper` und `list_topics` als Copilot-Werkzeuge (FastMCP, strukturierte Fehlerausgabe an der Grenze, Index-Schema **0.3.0** mit Identifikatoren) und ist über [`.vscode/mcp.json`](.vscode/mcp.json) eingebunden ([ADR 0009](docs/adr/0009-mcp-server-stdio-phase5.md)). Der weitere phasenweise Umsetzungsplan mit „Definition of Done" steht in der [Roadmap](Roadmap.md); als Nächstes folgt **Phase 6** (Drop-in-Workflow & Qualitätssicherung).

## Wichtigste Risiken

- **PDF-Extraktionsrauschen** (Mehrspaltenlayout, Formeln, Scans) → Qualitäts-Gates, Provenienz zum Original, Stichproben; Docling/Marker als späterer Ausbau ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)).
- **Entity Resolution** (z. B. „BERT" vs. Langform; gleichnamige Autoren) → leichte Alias-Kuratierung, Stichproben.
- **Scheinsicherheit durch Summaries** → jede Antwort mit Quellenankern / Original-TextUnits.

## Quellen & Inspiration

- Microsoft GraphRAG – Doku & Dataflow: [https://microsoft.github.io/graphrag/](https://microsoft.github.io/graphrag/)
- GraphRAG Pattern Catalog (Neo4j): [https://graphrag.com/concepts/intro-to-graphrag/](https://graphrag.com/concepts/intro-to-graphrag/)
- Model Context Protocol: [https://modelcontextprotocol.io/](https://modelcontextprotocol.io/)
- Docling: [https://www.docling.ai/](https://www.docling.ai/) · Marker: [https://github.com/datalab-to/marker](https://github.com/datalab-to/marker) · Kuzu: [https://kuzudb.github.io/](https://kuzudb.github.io/)

## Lizenz

Noch festzulegen.
