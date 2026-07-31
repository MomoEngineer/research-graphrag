# 0007 – GraphRAG-Index Phase 3: Paper-Ähnlichkeitsgraph & Louvain-Communities (Option B)

- **Status:** Akzeptiert
- **Datum:** 2026-07-31

## Kontext

[Roadmap.md](../../Roadmap.md) beschreibt für **Phase 3** einen „GraphRAG-Index (file-based)" mit
**Wissensgraph + Community-Reports**. Der Roadmap-Text nennt den Microsoft-GraphRAG-Stack
(LanceDB/Parquet, Leiden, Entity-/Relationship-/Claim-Extraktion, Embeddings) – dieser stammt aus
der Zeit *vor* [ADR 0005](0005-graphrag-index-backend-open.md) und ist im Offline-Umfeld
([ADR 0002](0002-venv-and-offline-dependency-strategy.md)) **nicht** bedienbar.

Rahmenbedingungen der tatsächlichen Umsetzung (Option B, [ADR 0005](0005-graphrag-index-backend-open.md)):

- **Kein LLM/NLP zur Index-Zeit.** Ein semantischer **Domänen-Entitätsgraph** (`Concept`, `Method`,
  `Author`, `CITES`, `USES_METHOD` …) wie in [README.md](../../README.md) skizziert braucht LLM-/
  NLP-Extraktion und ist in [ADR 0006](0006-canonical-model-phase2-scope.md) explizit **Phase 7**
  zugeordnet. Was Phase 3 offline **deterministisch** liefern kann, ist ein **lexikalisch-
  thematischer Ähnlichkeitsgraph** auf Basis der bereits genutzten **TF-IDF**-Repräsentation.
- **Leiden fehlt offline** (`leidenalg`/`python-igraph` nicht beschaffbar); der Offline-Hybrid nutzt
  **Louvain** (`networkx`), bereits Kern-Dependency.
- **Korpusgröße ≤ 500 Paper** (aktuell ~145). Der Nutzen corpusweiter Community-Suche ist laut
  [README.md](../../README.md) „noch moderat" und wächst mit dem Bestand – das Vorgehen soll
  **right-sized** sein ([CONTRIBUTING.md](../../CONTRIBUTING.md)).

## Entscheidung

Phase 3 baut einen **deterministischen Paper-Ähnlichkeitsgraphen mit Louvain-Communities** und
**extraktiven** Community-Zusammenfassungen; die Artefakte werden in die bestehende
`data/index/index.sqlite` geschrieben. Der **Retrieval-Contract bleibt unverändert** (Local/Global/
DRIFT sind Phase 4, MCP-Tools Phase 5).

| Aspekt | Phase-3-Umsetzung (Option B) |
| --- | --- |
| Graph-Ebene | **Paper-Ebene** (Knoten = Paper). Beste Signalqualität für corpusweite Fragen; die feinkörnige **Chunk-Nachbarschaft** (Local Search) wird in Phase 4 **zur Abfragezeit** aus der ohnehin rekonstruierten TF-IDF-Matrix berechnet – kein persistierter ~14k-Knoten-Chunk-Graph. |
| Knoten-Repräsentation | Frischer `TfidfVectorizer` (mit englischer Stopwortliste) über den **pro Paper konkatenierten Chunk-Text**; dieser TF-IDF-Raum ist die Basis für die Kanten-Ähnlichkeit und die **pro Community aggregierten** Keywords (deterministisch). |
| Kanten | **Mutual Top-k** (Default `k = 8`) mit **Mindest-Kosinus** (Default `0.10`); Gewicht = Kosinus; ungerichtet einmal gespeichert (`source_paper_id < target_paper_id`). Verhindert einen fast vollständigen Graphen und Hubs. |
| Community-Detection | `networkx.algorithms.community.louvain_communities(weight="weight", seed=42, resolution=1.0)`. **Fixer Seed** für Reproduzierbarkeit; isolierte Paper werden **Singleton-Communities**. |
| Community-IDs | Deterministisch vergeben: sortiere Communities nach **Größe absteigend**, dann nach **kleinster Mitglieds-`paper_id`**; nummeriere `0…n-1`. |
| Community-Zusammenfassung | **Extraktiv & deterministisch:** aggregierte Top-TF-IDF-**Keywords**, **repräsentative Paper** (höchste gewichtete Zentralität, Tie-Break `paper_id`) und ein extraktiver Kurztext aus dem Leit-Snippet des Top-Papers. **Kein LLM** zur Index-Zeit. |
| Persistenz | Neue Tabellen `graph_nodes`, `graph_edges`, `communities`, `community_members` in `index.sqlite` (Source of Truth) + `meta.graph_schema_version`. |
| Nachweis (DoD) | Kennzahlen im `IngestReport` (`n_nodes`/`n_edges`/`n_communities`), read-only `scripts/graph_info.py` (Community-Übersicht) und Integrationstests – **statt** der offline nicht existierenden „GraphRAG-CLI-Abfrage". |

Die Startwerte (`k = 8`, Schwelle `0.10`, `seed = 42`, `resolution = 1.0`) sind bewusste,
begründete Defaults und leicht justierbar; sie sind hier als Single Source of Truth dokumentiert.

## Alternativen

- **Chunk-Ebenen-Graph jetzt (GraphRAG-näher).** Zurückgestellt: ~14.400 Knoten, deutlich mehr
  Rauschen (der Korpus-Stresstest zeigte 2894 `short_chunk`-Chunks), höherer Rechen-/Speicheraufwand
  – ohne Mehrwert für Phase 3. Die Chunk-Nachbarschaft ist in Phase 4 zur Abfragezeit aus der
  TF-IDF-Matrix rekonstruierbar; ein persistierter Chunk-Graph würde dort ohnehin neu bewertet.
- **Semantischer Domänen-Entitätsgraph (LLM/NLP).** Verworfen für Phase 3: widerspricht
  [ADR 0005](0005-graphrag-index-backend-open.md) (kein Index-LLM) und ist in
  [ADR 0006](0006-canonical-model-phase2-scope.md) **Phase 7** zugeordnet.
- **LLM-erzeugte Community-Reports im Ingest.** Verworfen: kein Batch-LLM offline; LLM bleibt der
  Abfragezeit vorbehalten ([ADR 0004](0004-llm-bridge-via-mcp-sampling.md)). Phase-3-Summaries sind
  extraktiv; eine LLM-Veredelung erfolgt optional später on-demand über die Bridge.
- **Separate `graph.sqlite`-Datei.** Verworfen: eine Index-Datei bleibt die Source of Truth und
  vermeidet Konsistenz-/Reload-Fragen; die Graph-Tabellen sind additiv.

## Konsequenzen

- **Positiv:** Voll offline-tauglich, **deterministisch/reproduzierbar** (fixer Seed, stabile
  Tie-Breaks), nutzt ausschließlich vorhandene Bausteine (TF-IDF, `networkx`, SQLite); scharfe
  Phasengrenze (Retrieval-Contract unverändert); interpretierbare Themencluster für die spätere
  Global Search.
- **Negativ / Aufwand:** Communities sind **lexikalisch-thematisch** (TF-IDF), **kein** semantischer
  Entitätsgraph; **Louvain statt Leiden**; „Community-Reports" sind extraktiv, nicht LLM-generiert;
  eine spätere Chunk-Ebene/Entity-Ebene ist bewusst nicht vorbereitet (bei Bedarf Folge-ADR).
- **Folgeentscheidungen:** Local/Global/DRIFT-Retrieval (Phase 4) konsumiert diese Artefakte;
  Domänen-Entitätsgraph, tiefes Zitations-Parsing und ggf. Chunk-Ebene bleiben **Phase 7**
  (Option C, [ADR 0005](0005-graphrag-index-backend-open.md)).
