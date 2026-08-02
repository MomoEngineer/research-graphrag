# Research-GraphRAG

**Ein schlanker, container-freier Scientific-GraphRAG als persönlicher Forschungsassistent für lokale wissenschaftliche PDF-Paper – direkt nutzbar aus GitHub Copilot über einen MCP-Server.**

> **Status:** **Phase 0–6 umgesetzt**, dazu die Phase-7-Ausbaupunkte **A2 (Zitationsgraph)** und **A1 (LLM-Bridge & Antwort-Synthese)**. Phase 0: Fundament + **Offline-Hybrid-Durchstich** (Roadmap-M1) – `pip install -e .`, Ingestion (`pypdf` → TF-IDF/SQLite) und belegte Basic-Search-Antworten laufen und sind getestet. Phase 1: **145 Paper** aus dem bisherigen `Recherche`-Ordner nach `papers/` migriert und [`Übersicht.md`](Übersicht.md) portiert (reduzierter Umfang – `recherche/`-Artefakte bewusst ausgelassen). Phase 2: **robuste Extraktion** (Canonical-Schema **0.2.0** mit Section-Heuristik, größenbasiertem Chunking, DOI/arXiv, Qualitätsflags), **Qualitätsreport** und **Übersicht-Entwürfe** (`scripts/update_overview.py` → `data/overview_drafts.md`) – Umfangsabgrenzung in [ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md). Phase 3: **GraphRAG-Index (Offline-Hybrid)** – deterministischer **Paper-Ähnlichkeitsgraph** (TF-IDF) mit **Louvain-Communities** und extraktiven Zusammenfassungen, integriert in `python -m scripts.ingest` und einsehbar über `python -m scripts.graph_info` ([ADR 0007](docs/adr/0007-graphrag-index-phase3-option-b.md)). Phase 4: **Retrieval & Query-Router** – **Basic/Local/Global/DRIFT** als deterministische, belegbare Offline-Modi plus schlanker Heuristik-Router (`python -m scripts.ask [--mode …]`); der **Provenienz-Assembler** liefert Paper · Abschnitt · Seite/Chunk (Index-Schema **0.2.0**) ([ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md)). Phase 5: **MCP-Server (stdio)** – die vier Retrieval-Modi sowie `get_paper` und `list_topics` sind als **MCP-Tools** für GitHub Copilot registriert (FastMCP; Fehlerübersetzung an der Server-Grenze; **kein** serverseitiges LLM-Sampling), eingebunden über [`.vscode/mcp.json`](.vscode/mcp.json); der Index wurde additiv auf Schema **0.3.0** (Identifikatoren für `get_paper`) erweitert ([ADR 0009](docs/adr/0009-mcp-server-stdio-phase5.md)). Phase 6: **Drop-in-Workflow & Qualitätssicherung** – der `ingest`→On-Read-Kreislauf ist verifiziert und **gehärtet** (atomarer Index-Swap: Build nach `*.sqlite.tmp` + `os.replace`, ein Fehler lässt den Alt-Index intakt); neu sind `python -m scripts.status` (read-only Index-/Korpus-Status + Konsistenz-Check) und `python -m scripts.qa` (Prüf-Fragen je Modus durchspielen), Nachweis über einen Freshness-/Atomaritäts-Regressionstest und die QS-Harness ([ADR 0010](docs/adr/0010-drop-in-workflow-and-qa-phase6.md)). Die weiteren Phasen folgen der [Roadmap](Roadmap.md); die Umsetzung ist die **Offline-Variante (Option B, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md))**. Phase 7 / A2: **Intra-Korpus-Zitationsgraph** – aus dem Referenzabschnitt entstehen deterministische, gerichtete `CITES`-Kanten (DOI/arXiv/Titel-Match gegen den eigenen Korpus, Präzision vor Recall), additiv im Index (`citation_edges`) und abfragbar über `python -m scripts.citations` sowie das MCP-Tool `get_citations` ([ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)). Phase 7 / A1: **LLM-Bridge & Antwort-Synthese** – das Paket `generation/` realisiert den injizierbaren Generierungs-Port aus [ADR 0004](docs/adr/0004-llm-bridge-via-mcp-sampling.md) und bildet alle vier Modi auf **eine** nummerierte Evidenz mit Zitier-Contract ab; das Tool `answer_question` liefert sie in einem Aufruf und formuliert auf Wunsch (`synthesize = true`) per **MCP-Sampling** über das Client-Modell – ohne Sampling degradiert es sichtbar (`generated = false`) bei voller Evidenz ([ADR 0012](docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md)). Phase 7 / A3: **Chunking-Verfeinerung** – die Messung widerlegte die vermutete Ursache (nicht die Seitengrenze, sondern die **übersegmentierende Überschriften-Heuristik**), deshalb wirken jetzt **Reject-Regeln** und eine **Section-Absorption**; die Seite ist kein Segmentierungskriterium mehr, sondern eine **Provenienz-Range** (`page_number` … `page_end`, Canonical **0.3.0**, Index **0.4.0**). Ergebnis am realen Korpus: `short_chunk`-Anteil **20,1 % → 3,7 %**, Chunks **14 397 → 11 339**, Qualitäts-Flags **3074 → 320** ([ADR 0013](docs/adr/0013-chunking-refinement-phase7.md)). Phase 7 / A4: **Hybrid-Retrieval** – über **einer** Tokenisierung stehen jetzt der TF-IDF-Kosinus und ein **handimplementiertes BM25** (Term-Sättigung + Längennormalisierung), verbunden per **Reciprocal Rank Fusion**; das ist der neue Default aller Chunk-Modi, umschaltbar per `--scoring`. Belegt wird der Nutzen mit einem versionierten Gold-Set und dem Harness `python -m scripts.eval_retrieval` (Hit@5 **0,735 → 0,882**, bei Fakt-Fragen **0,773 → 0,955**); der Index bleibt unverändert (**kein Re-Ingest**), `Citation` weist die Teil-Scores `score_tfidf`/`score_bm25` aus ([ADR 0014](docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)). Phase 7 / A5: **Rausch-Reduktion** – der extrahierte Seitentext wird jetzt **normalisiert** (Ligaturen wie `conﬁguration` repariert, nicht dekodierbare `/uniXXXXXXXX`-Glyphen entfernt), die Überschriften-Erkennung verwirft **Bibliografie-Zeilen** (URL/DOI, `et al`, Code-Zeichen, Satzpunkt-Ende sowie kleingeschriebene Fließtextreste wie `methods.`) und schaltet im Referenzabschnitt den Numerierungs-Zweig ab, und eine kuratierte **Keyword-Politik** (`keywords.py`) filtert Rausch-Terme aus Community-Keywords und Übersicht-Entwürfen – als **Nachfilter**, damit der Ähnlichkeitsgraph unberührt bleibt. Ergebnis am realen Korpus: verrauschte Abschnittstitel **267 → 0**, Rausch-Anteil der Keywords **6,0 % → 0 %**, Ligaturen **3628 → 0**, `CITES`-Kanten **256 → 382**, MRR@5 **0,641 → 0,650** bei unverändertem Hit@5 (Canonical-Schema **0.4.0**, [ADR 0015](docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)). Phase 7 / A6: **Quantitative Retrieval-Evaluation** – die Messung reicht jetzt über die geteilte Chunk-Primitive hinaus auf die **Modi als Ganzes**, mit zwei Diagnosen, die **Auswahl- von Rankingfehlern trennen**; Global wird nie ohne **Selektivität und Trivial-Baselines** ausgewiesen (das Vergleichsinstrument ist der **Lift**, denn die nackte Coverage hätte die triviale Strategie „größte Communities" gekürt: 0,567 vs. 0,248). Neu sind das Paket `evaluation/`, das eingefrorene [`eval/retrieval-baseline.json`](eval/retrieval-baseline.json) und ein **qid-genauer** Regressions-Check (`--check`) mit Fingerprint-Guard ([ADR 0016](docs/adr/0016-quantitative-retrieval-evaluation-phase7.md)). Phase 7 / A7: **Router-Härtung** – auch hier korrigierte die Messung die Erwartung: Signal-Konflikte sind mit **1 von 44** Fragen praktisch inexistent, der Schaden lag im **rohen Substring-Matching** (15 von 26 korpus-häufigen Teilwörtern leiteten fehl) und in **einem** Signal (`which papers` schickte 16 von 22 Fakt-Fragen in den schwächeren Modus). Der Router deklariert die Match-Art jetzt **je Signal** (Wortgrenze/Wortanfang für Englisch, Teilwort nur für deutsche Stämme), behandelt `basic` als **Rückfallebene** statt als gleichrangigen Modus, fällt bei Gleichstand sichtbar dorthin zurück (Konfidenz `weak`) und **weist die Entscheidung aus** – in der CLI und additiv als `routing` in `answer_question`. Gemessen wird gegen ein **Router-Gold-Set** mit aus dieser README abgeleiteten Contract-Labels: Contract-Treue der Prüf-Fragen **6/10 → 10/10**, Gold-Set **83/84**, Signal-Abdeckung **69/69**, end-to-end Hit@5 **0,765 → 0,882** ([ADR 0017](docs/adr/0017-router-hardening-phase7.md)).

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

### Vertiefung

Diese README beschreibt Ziel und Stand. Wer wissen will, **welche Features** es gibt und wo sie
verbaut sind, liest [docs/features.md](docs/features.md); **wie** sie zusammenarbeiten, erklärt
[docs/funktionsweise.md](docs/funktionsweise.md) mit Diagrammen; die Funktionsweise **eines
Moduls** steht jeweils in dessen Modul-Doku unter `src/research_graphrag/<paket>/doc/`. Die
Aufgabenteilung dieser Dokumente regelt [ADR 0018](docs/adr/0018-code-documentation-architecture.md).

## Workflow: neue Paper hinzufügen

1. PDF(s) in den Ordner `papers/` legen.
2. Skript ausführen: `python scripts/ingest.py`
3. Das Skript extrahiert **nur neue/geänderte** PDFs, aktualisiert das kanonische JSON und baut Index, Ähnlichkeitsgraph und Zitationskanten neu (voller Re-Index ist bei diesem Umfang günstig und konsistent).
4. Für neue Paper erzeugt `python -m scripts.update_overview` **Entwurfszeilen** (Titel, Links, Keywords, Kurzzusammenfassung) append-only in `data/overview_drafts.md` – die kuratierte [`Übersicht.md`](Übersicht.md) bleibt unangetastet; Relevanz und SRQ-Zuordnung pflegst du dort manuell nach.
5. Der MCP-Server nutzt die aktualisierten Artefakte (**On-Read**: er lädt den Index pro Anfrage frisch, **kein Server-Neustart** nötig; der Index-Neuaufbau erfolgt atomar) – die neuen Paper sind in Copilot sofort verfügbar.

## Fragetypen → Suchmodus

> Diese Tabelle ist der **Contract des Query-Routers**: Aus ihr leitet das Router-Gold-Set seine
> Labels ab, und gegen sie wird die Router-Treue gemessen ([ADR 0017](docs/adr/0017-router-hardening-phase7.md)).

| Fragetyp                             | Primärer Suchmodus | Warum                                                                                      |
| ------------------------------------ | ------------------- | ------------------------------------------------------------------------------------------ |
| Detailfrage zu einem Paper           | Local + Basic       | Startet an relevanten Entitäten, zieht TextUnits/Beziehungen; Basic für exakte Passagen. |
| Cross-Paper-Synthese / Themen        | Global              | Nutzt Community-Reports (Map-Reduce) für corpusweite Fragen.                              |
| Zitations-/Methodennetze (Multi-Hop) | Local (Fan-out) + `get_citations`     | Folgt Ähnlichkeitskanten im Graphen; **echte Zitationen** liefert `get_citations` (Intra-Korpus, [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)); Text2Cypher siehe Roadmap. |
| Exakte Fakten (DOI, Metrik, Abk.)    | Basic               | Top-k auf Chunks über die **Hybrid-Wertung** (BM25 + TF-IDF, Rang-Fusion; [ADR 0014](docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)).       |
| Widersprüche / Vergleiche           | DRIFT               | Verbindet globale Community-Info mit lokaler Verfeinerung.                                 |

## Datenmodell (Überblick)

Zwei komplementäre Graph-Sichten:

- **Lexical/Document Graph:** `Paper` → `Section` → `Chunk` (+ `Figure`, `Table`, `Reference`) – erhält Struktur & Provenienz.
- **Domain Graph:** `Concept`, `Method`, `Dataset`, `Metric`, `Result`, `Claim`, `Author` und Beziehungen wie `CITES`, `USES_METHOD`, `EVALUATES_ON`, `SUPPORTED_BY`. Davon ist **`CITES` umgesetzt** (Intra-Korpus, deterministisch aus dem Referenzabschnitt, [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)); die übrigen Kantentypen brauchen LLM-/Entitätsextraktion und bleiben Zielbild.

Details und Ausbaustufen siehe [Roadmap](Roadmap.md).

## Tech-Stack

> **Offline-Variante (Option B, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)):** In der aktuellen Offline-Umgebung sind **Microsoft GraphRAG, Docling und LanceDB nicht beschaffbar** (empirisch geprüft). Die **implementierte** Variante nutzt daher `pypdf` (Extraktion), **TF-IDF + handimplementiertes BM25** (`scikit-learn`/`numpy`, Rang-Fusion – [ADR 0014](docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)), `networkx`/**Louvain** und **SQLite**; ein LLM kommt nur zur Abfragezeit über die **LLM-Bridge** (MCP-Sampling, [ADR 0004](docs/adr/0004-llm-bridge-via-mcp-sampling.md)). Die folgende Tabelle bleibt das **Zielbild** (Option C), falls Wheels/Modelle verfügbar werden.

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
│  ├─ citations.py             # Zitationen eines Papers (read-only, Phase 7 / A2)
│  ├─ eval_retrieval.py        # Hit@k/MRR, Modus-Ebene, Regressions-Check (Phase 7 / A4 + A6)
│  └─ update_overview.py       # Entwurfszeilen → data/overview_drafts.md (Staging)
├─ src/research_graphrag/
│  ├─ extraction/              # pypdf → Canonical JSON (Option B, inkl. Textnormalisierung)
│  ├─ indexing/               # Index-Orchestrierung (TF-IDF + BM25 + networkx/SQLite)
│  ├─ retrieval/               # Query-Router (Local/Global/DRIFT/Basic)
│  ├─ overview/                # Übersicht-Entwürfe (Staging, Phase 2)
│  ├─ generation/              # LLM-Bridge: Evidenz + optionale Antwort-Synthese (Phase 7)
│  ├─ evaluation/             # Gold-Set, Kennzahlen, Modus-Lauf, Baseline (Phase 7 / A6) + Router-Messung (A7)
│  ├─ keywords.py             # kuratierte Keyword-Politik (Phase 7 / A5)
│  └─ mcp_server/             # MCP-Server (stdio) mit Tools
├─ eval/                      # Prüf-Fragen & Stichproben (pragmatische QS) + Gold-Set und Baseline (Hit@k/MRR) + Router-Gold-Set
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

# 2c. (optional) Status/Konsistenz prüfen und Prüf-Fragen als QS durchspielen
python -m scripts.status
python -m scripts.qa

# 2d. (optional) Retrieval quantitativ messen (Hit@k/MRR gegen das Gold-Set)
python -m scripts.eval_retrieval
python -m scripts.eval_retrieval --scoring tfidf   # Vergleich gegen die reine TF-IDF-Wertung
python -m scripts.eval_retrieval --modi           # Modi als Ganzes (Local/Global/DRIFT), dauert einige Minuten
python -m scripts.eval_retrieval --check          # Regressions-Check gegen die eingefrorene Baseline
python -m scripts.eval_retrieval --router         # Contract-Treue des Query-Routers (ohne Index, sofort)

# 3. Frage mit belegter Quelle stellen (Basic/Local/Global/DRIFT; ohne --mode = Heuristik-Router)
python -m scripts.ask "Welcher F1-Score wird berichtet?"
python -m scripts.ask "Welche Forschungsrichtungen zeichnen sich ab?" --mode global
python -m scripts.ask "Which papers use FAISS?" --scoring bm25   # Wertung explizit wählen

# 3b. (optional) Zitationen eines Papers innerhalb des Korpus ansehen
python -m scripts.citations <paper_id>

# 3c. (optional) Belege nummeriert über die LLM-Bridge aufbereiten
#     (CLI hat offline kein Modell → sichtbarer Noop-Fallback, Belege bleiben vollständig)
python -m scripts.ask "Welche Datensätze werden genutzt?" --synthese

# 4. MCP-Server nutzen: .vscode/mcp.json ist eingerichtet – in Copilot Chat
#    (Agent-Modus) die bereitgestellten Werkzeuge aufrufen
```

Der MCP-Server stellt u. a. Werkzeuge bereit wie `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper`, `get_citations` und `list_topics` – jeweils mit Quellenangaben. Dazu kommt `answer_question`: ein Aufruf, der den Modus selbst wählt und **nummerierte Belege** mit Zitier-Contract liefert (optional per `synthesize = true` vom Client-Modell formuliert). Wählt der Router den Modus (`mode = "auto"`, Default), weist die Antwort unter `routing` aus, **warum** – mit Konfidenzstufe und auslösenden Signalen ([ADR 0017](docs/adr/0017-router-hardening-phase7.md)).

## Qualitätssicherung (pragmatisch)

Da dies ein persönliches Werkzeug ist: keine formale Evaluation, aber gezielte Prüfungen.

- Kleines, festes **Prüf-Fragen-Set** über alle Fragetypen.
- **Stichproben** der Provenienz (stimmen Quelle/Seite?).
- **Qualitäts-Gates** in der Ingestion (fehlender Abstract, kaputte Referenzen, OCR-Rauschen, leere Tabellen).
- **Quantitativ** ergänzt seit A4: ein versioniertes Gold-Set mit mechanisch abgeleiteten Labels und der Harness `python -m scripts.eval_retrieval` (Hit@k/MRR) machen Retrieval-Änderungen messbar statt nur plausibel ([ADR 0014](docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)).
- **Seit A6** reicht die Messung über die geteilte Chunk-Primitive hinaus auf die **Modi als Ganzes** (`--modi`), und `--check` meldet Regressionen **qid-genau** gegen eine eingefrorene Baseline; ein Fingerprint-Guard verweigert den Vergleich, sobald der Korpus nicht mehr passt ([ADR 0016](docs/adr/0016-quantitative-retrieval-evaluation-phase7.md)).
- **Seit A7** ist auch der **Query-Router** messbar: `--router` prüft seine Treue zum Fragetyp-Contract dieser README gegen ein versioniertes Gold-Set – ohne Index und in Sekunden, mit einer Label-Regel, die sich aus der Tabelle „Fragetypen → Suchmodus" ableiten lässt ([ADR 0017](docs/adr/0017-router-hardening-phase7.md)).

## Projektstatus & Roadmap

**Phase 0 ist umgesetzt** (Fundament + Offline-Hybrid-Durchstich, Roadmap-M1: 1 PDF → Index → belegte Antwort). **Phase 1 (Migration) ist im reduzierten Umfang umgesetzt:** 145 Paper aus dem bisherigen `Recherche`-Ordner nach `papers/` übernommen und [`Übersicht.md`](Übersicht.md) portiert (mit funktionierenden internen Links); die `recherche/`-Artefakte wurden bewusst ausgelassen, der Pilot-Korpus liegt als Vorschlag in [`eval/pilot-korpus.md`](eval/pilot-korpus.md). **Phase 2 ist umgesetzt:** robuste PDF-Extraktion (Canonical-Schema 0.2.0), Qualitätsreport und Übersicht-Entwürfe ([ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md)). **Phase 3 ist umgesetzt:** Offline-Hybrid-**GraphRAG-Index** – Paper-Ähnlichkeitsgraph (TF-IDF) mit Louvain-Communities und extraktiven Zusammenfassungen in `data/index/index.sqlite` ([ADR 0007](docs/adr/0007-graphrag-index-phase3-option-b.md)). **Phase 4 ist umgesetzt:** Basic/Local/Global/DRIFT-Suchmodi, ein schlanker Heuristik-Router und der Provenienz-Assembler (Paper · Abschnitt · Seite/Chunk; Index-Schema 0.2.0, [ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md)) – alle 5 Fragetypen sind per `python -m scripts.ask` belegbar ([eval/pruef-fragen.md](eval/pruef-fragen.md)). **Phase 5 ist umgesetzt:** der **stdio-MCP-Server** registriert `search_basic`/`search_local`/`search_global`/`search_drift` sowie `get_paper` und `list_topics` als Copilot-Werkzeuge (FastMCP, strukturierte Fehlerausgabe an der Grenze, Index-Schema **0.3.0** mit Identifikatoren) und ist über [`.vscode/mcp.json`](.vscode/mcp.json) eingebunden ([ADR 0009](docs/adr/0009-mcp-server-stdio-phase5.md)). **Phase 6 ist umgesetzt:** der Drop-in-Kreislauf ist verifiziert und **gehärtet** (atomarer Index-Swap), ergänzt um `scripts.status` (read-only Status/Konsistenz) und `scripts.qa` (Prüf-Fragen-Harness); die DoD ist testgestützt (Freshness-/Atomaritäts-Regression + QS-Harness), realer Korpus 145/14 397/42, 10/10 Prüf-Fragen belegt ([ADR 0010](docs/adr/0010-drop-in-workflow-and-qa-phase6.md)). Der weitere phasenweise Umsetzungsplan mit „Definition of Done" steht in der [Roadmap](Roadmap.md); aus **Phase 7** ist **A2 (Intra-Korpus-Zitationsgraph)** umgesetzt: deterministische `CITES`-Kanten aus dem Referenzabschnitt (DOI/arXiv/Titel-Match, Präzision vor Recall), additiv als `citation_edges` im Index und abfragbar über `python -m scripts.citations` bzw. das MCP-Tool `get_citations`; realer Korpus **158 Kanten** aus 143/145 Papern mit erkanntem Referenzabschnitt ([ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)). Ebenfalls umgesetzt ist **A1 (LLM-Bridge & Antwort-Synthese)**: injizierbarer Generierungs-Port, mode-agnostische nummerierte Evidenz und das Tool `answer_question` mit **opt-in** Sampling; der Nachweis erfolgt über einen echten Sampling-Roundtrip im In-Memory-Client-Test ([ADR 0012](docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md)). Ebenfalls umgesetzt ist **A3 (Chunking-Verfeinerung)**: Die Ursachenannahme der Roadmap wurde gemessen und **korrigiert** – 85,4 % der `short_chunk`-Fälle entstanden am Abschnittswechsel (Übersegmentierung), nur 12,2 % am Seitenschnitt. Umgesetzt sind daher Reject-Regeln in der Überschriften-Erkennung, eine evidenzbasierte Section-Absorption und die **Seiten-Range** statt der harten Seitengrenze; realer Korpus: `short_chunk` **20,1 % → 3,7 %**, Chunks **14 397 → 11 339**, Sections **9367 → 4406**, Flags **3074 → 320**, `CITES`-Kanten **158 → 256** (vollständiger Referenzabschnitt), Extraktion **145/145** deterministisch ([ADR 0013](docs/adr/0013-chunking-refinement-phase7.md)). Ebenfalls umgesetzt ist **A4 (Hybrid-Retrieval)**: BM25 ist über der bestehenden Tokenisierung **handimplementiert** und wird per **Reciprocal Rank Fusion** mit TF-IDF verbunden – Default aller Chunk-Modi, umschaltbar per `--scoring`. Der Nachweis erfolgt erstmals **quantitativ** (Gold-Set mit mechanisch abgeleiteten Labels + `scripts.eval_retrieval`): Hit@5 **0,735 → 0,882**, Fakt-Fragen **0,773 → 0,955**. Offen dokumentiert: **reines BM25** liegt aggregiert leicht vor der Fusion, der Vorsprung kehrt sich aber auf einem unabhängigen Validierungsset um – der Default bleibt `hybrid`, weil nur er in keiner Fragenklasse einbricht ([ADR 0014](docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)). Ebenfalls umgesetzt ist **A5 (Rausch-Reduktion)**: Auch hier hat die Messung die Roadmap-Annahme präzisiert – das Keyword-Rauschen sitzt in der **Auswahlpolitik** (die Terme haben eine Dokumentfrequenz nahe *N* und damit IDF ≈ 0, erst die Summe über eine Community hebt sie hoch), und die „Ligatur-Artefakte" sind zwei Dinge: nicht dekodierbare Glyph-Indizes (entfernen) und echte Ligaturen, die **Inhalt tragen** und deshalb **repariert** werden. Umgesetzt sind daher Textnormalisierung, vier Bibliografie-Reject-Regeln plus Referenzkontext und ein Keyword-Nachfilter; realer Korpus: verrauschte Titel **267 → 0**, Keyword-Rauschen **6,0 % → 0 %**, Ligaturen **3628 → 0**, Sections **4406 → 3948** (Median 27 → 25), `CITES` **256 → 382** (382/382 belegt), Hit@5 unverändert 0,882 bei MRR **0,641 → 0,650** ([ADR 0015](docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)). Ebenfalls umgesetzt ist **A6 (quantitative Retrieval-Evaluation)** – im vereinbarten Umfang: Die Evaluationslogik wurde zum Paket `src/research_graphrag/evaluation/` (fünf Module, 100 % Zeilenabdeckung) und misst jetzt die **Modi als Ganzes**. Der Erkenntnisgewinn liegt in den Diagnosen, nicht in der Aggregatzahl: **Local ist bei Fakt-Fragen schwächer als Basic** (0,618 vs. 0,882), weil das ganze Bündel an einem Top-1-Seed hängt und der Fan-out nur **1 von 34** Fragen rettet; **DRIFTs lokale Verfeinerung ist dagegen fehlerfrei** – Treffer und erreichbare Deckelung sind identisch (8/34), *alle* Fehlschläge entstehen in der Community-Wahl (12× keine, 14× die falsche). Für Global gilt: Coverage nie ohne Selektivität und Trivial-Baselines – der **Lift** ordnet (echte Auswahl **3,55**, größte-5 **1,01**, zufällig **1,05**), die nackte Coverage nicht. Ein `--check` direkt nach dem Einfrieren meldet über alle fünf Ebenen keine Abweichung (Determinismus). Bewusst zurückgestellt bleiben **inhaltliche Labels** und ein **breiteres Fragenset**: Die Roadmap forderte inhaltliche Labels „statt" der lexikalischen – das wurde abgelehnt, weil die mechanische Regel als einzige nachrechenbar ist und genau dadurch in A5 den Re-Ingest abgesichert hat ([ADR 0016](docs/adr/0016-quantitative-retrieval-evaluation-phase7.md)). Ebenfalls umgesetzt ist **A7 (Router-Härtung)**: Der Router entscheidet nicht mehr „erster Substring gewinnt", sondern über Signale mit **deklarierter Match-Art**, mit `basic` als **Rückfallebene** (Fakt-Signale bestätigen nur, Gleichstand fällt sichtbar zurück) – die feste Präzedenz aus [ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md) ist damit abgelöst. Jede Entscheidung trägt jetzt **Konfidenzstufe und auslösende Signale** und wird in `answer_question` additiv als `routing` ausgewiesen. Auch hier lieferte die Vorabmessung die Richtung: Signal-Konflikte sind mit 1 von 44 Fragen praktisch inexistent (ein Score-Modell wäre Wegwerf-Mechanik gewesen), während Substring-Treffer und das Signal `which papers` messbar schadeten. Ergebnis: Prüf-Fragen **6/10 → 10/10**, Router-Gold-Set **83/84**, Signal-Abdeckung **9/51 → 69/69**, end-to-end Hit@5 **0,765 → 0,882** (Fakt-Fragen 0,773 → 0,955) – wobei das End-to-End-Maß bewusst nur als **Veto** dient und nie als Optimierungsziel ([ADR 0017](docs/adr/0017-router-hardening-phase7.md)). Die übrigen Phase-7-Punkte folgen nach Bedarf.

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
