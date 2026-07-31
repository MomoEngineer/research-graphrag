# Research-GraphRAG

**Ein schlanker, container-freier Scientific-GraphRAG als persönlicher Forschungsassistent für lokale wissenschaftliche PDF-Paper – direkt nutzbar aus GitHub Copilot über einen MCP-Server.**

> **Status:** 🚧 Konzept- & Planungsphase. Dieses Repository beschreibt aktuell das Zielbild und das Vorgehen; die Implementierung folgt der [Roadmap](Roadmap.md). Es ist noch kein lauffähiger Code enthalten.

---

## Ziel & Kontext

Dieses Projekt baut ein **GraphRAG-System** über einer lokalen Sammlung wissenschaftlicher Paper (PDF). Ziel ist ein **persönlicher Forschungsassistent**, der die Inhalte der Paper für einen AI-Agenten (GitHub Copilot) deutlich besser nutzbar macht – von präzisen Detailfragen bis zu corpusweiten Zusammenhängen.

- **Kein Teil einer wissenschaftlichen Arbeit**, sondern ein Werkzeug, das die tägliche Arbeit mit Papern erleichtert (u. a. begleitend zu einer Masterarbeit genutzt).
- **Konsolidierte Forschungsbasis:** ersetzt den bisherigen separaten `Recherche`-Ordner und vereint PDFs, die kuratierte [Literaturübersicht](Übersicht.md) und den GraphRAG-Index an einem Ort.
- **Klein & lokal:** aktuell ~140 Paper, ausgelegt auf max. ~500.
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

Die Paper stammen aus der Literaturrecherche zur Masterarbeit. Dieses Repo wird der **zentrale Ort** dafür und löst den bisherigen `Recherche`-Ordner ab: die PDFs liegen in `papers/`, die zugehörige Recherche (Prompts, Zusammenfassungen, Forschungslücken) unter `recherche/`.

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

> **Warum GraphRAG und nicht nur klassisches Vektor-RAG?** Für reine „finde die Passage"-Fragen genügt hybride Vektor-Suche. Sobald **Zusammenhänge über mehrere Paper** (Methoden, Zitationen, Themen, Widersprüche) gefragt sind, spielt GraphRAG seine Stärken aus. Bei ~140 Papern ist der Nutzen der globalen/Community-Suche noch moderat und wächst mit dem Bestand mit.

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

## Workflow: neue Paper hinzufügen

1. PDF(s) in den Ordner `papers/` legen.
2. Skript ausführen: `python scripts/ingest.py`
3. Das Skript extrahiert **nur neue/geänderte** PDFs, aktualisiert das kanonische JSON und baut den GraphRAG-Index neu (voller Re-Index ist bei diesem Umfang günstig und konsistent).
4. Für neue Paper werden **Entwurfszeilen** in [`Übersicht.md`](Übersicht.md) ergänzt (Titel, Links, Keywords, Kurzzusammenfassung) – Relevanz und SRQ-Zuordnung pflegst du manuell nach.
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

| Schicht                | Wahl (MVP)                                                                                                                         | Später / Optional                                                                  |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| PDF-Extraktion         | **Docling** (pure Python)                                                                                                    | **Marker** (formel-/layoutlastig), GROBID (Referenzen, benötigt Docker/Java) |
| Zwischenformat         | Canonical Paper**JSON/JSONL**                                                                                                | —                                                                                  |
| Index & Retrieval      | **Microsoft GraphRAG** (file-based)                                                                                          | Inkrementelles`graphrag update`                                                   |
| Vektor-/Speicher       | **LanceDB + Parquet** (eingebettet)                                                                                          | Qdrant/Weaviate (bei starkem Wachstum)                                              |
| Graph (Erweiterung)    | —                                                                                                                                 | **Kuzu** (embedded, Cypher, Text2Cypher)                                      |
| Agent-Anbindung        | **MCP-Server (Python, stdio)**                                                                                               | HTTP/SSE (Remote/Multi-User)                                                        |
| Consumer-Agent         | **GitHub Copilot** (VS Code)                                                                                                 | weitere MCP-Clients                                                                 |
| LLM/Embeddings (Index) | **offene Entscheidung** – Cloud-API (empfohlen für Qualität) *oder* lokal via Ollama (kostenlos/privat, kein Container) | —                                                                                  |

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
│  └─ graphrag/                # GraphRAG-Workspace (input/output/cache)
├─ scripts/
│  ├─ ingest.py                # Drop-in → Extraktion → Index-Update
│  └─ update_overview.py       # Entwurfszeilen für Übersicht.md erzeugen
├─ src/research_graphrag/
│  ├─ extraction/              # Docling/Marker → Canonical JSON
│  ├─ indexing/                # GraphRAG-Orchestrierung
│  ├─ retrieval/               # Query-Router (Local/Global/DRIFT/Basic)
│  └─ mcp_server/              # MCP-Server (stdio) mit Tools
├─ eval/                       # Prüf-Fragen & Stichproben (pragmatische QS)
├─ pyproject.toml
├─ README.md
└─ Roadmap.md
```

## Voraussetzungen (geplant)

- **Python** (aktuelle 3.x-Version) in einer virtuellen Umgebung.
- **Kein Docker** für den MVP nötig.
- **LLM-/Embedding-Backend** (eine der Optionen):
  - **Cloud-API** (Azure OpenAI / OpenAI) – beste Extraktionsqualität, geringe Kosten bei kleinem Korpus.
  - **Ollama** (nativer Windows-Installer, kein Container) – lokal, kostenlos, datenschutzfreundlich.
- **VS Code** mit GitHub Copilot für die MCP-Anbindung.

## Nutzung (geplant)

```powershell
# 1. Umgebung einrichten
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e .

# 2. Paper hinzufügen und indexieren
#    (PDFs nach papers/ kopieren)
python scripts/ingest.py

# 3. MCP-Server in VS Code registrieren (.vscode/mcp.json)
#    danach in Copilot Chat die bereitgestellten Werkzeuge nutzen
```

Der MCP-Server stellt u. a. Werkzeuge bereit wie `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper` und `list_topics` – jeweils mit Quellenangaben.

## Qualitätssicherung (pragmatisch)

Da dies ein persönliches Werkzeug ist: keine formale Evaluation, aber gezielte Prüfungen.

- Kleines, festes **Prüf-Fragen-Set** über alle Fragetypen.
- **Stichproben** der Provenienz (stimmen Quelle/Seite?).
- **Qualitäts-Gates** in der Ingestion (fehlender Abstract, kaputte Referenzen, OCR-Rauschen, leere Tabellen).

## Projektstatus & Roadmap

Das Projekt startet in der Konzeptphase. Der konkrete, phasenweise Umsetzungsplan mit „Definition of Done" steht in der [Roadmap](Roadmap.md).

## Wichtigste Risiken

- **PDF-Extraktionsrauschen** (Mehrspaltenlayout, Formeln, Scans) → Qualitäts-Gates, Marker-Fallback, Provenienz zum Original.
- **Entity Resolution** (z. B. „BERT" vs. Langform; gleichnamige Autoren) → leichte Alias-Kuratierung, Stichproben.
- **Scheinsicherheit durch Summaries** → jede Antwort mit Quellenankern / Original-TextUnits.

## Quellen & Inspiration

- Microsoft GraphRAG – Doku & Dataflow: [https://microsoft.github.io/graphrag/](https://microsoft.github.io/graphrag/)
- GraphRAG Pattern Catalog (Neo4j): [https://graphrag.com/concepts/intro-to-graphrag/](https://graphrag.com/concepts/intro-to-graphrag/)
- Model Context Protocol: [https://modelcontextprotocol.io/](https://modelcontextprotocol.io/)
- Docling: [https://www.docling.ai/](https://www.docling.ai/) · Marker: [https://github.com/datalab-to/marker](https://github.com/datalab-to/marker) · Kuzu: [https://kuzudb.github.io/](https://kuzudb.github.io/)

## Lizenz

Noch festzulegen.
