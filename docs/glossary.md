# Glossar

Zentrale Fachbegriffe dieses Repositories. Etablierte englische Fachbegriffe bleiben unübersetzt (siehe [documentation-standards.md](documentation-standards.md)). Bei Erweiterungen der Domäne wird dieses Glossar mitgepflegt.

| Begriff | Bedeutung |
| --- | --- |
| **GraphRAG** | Retrieval-Augmented Generation über einem aus dem Korpus gebauten Wissensgraphen (Entitäten, Beziehungen, Communities, Community-Reports). |
| **MCP (Model Context Protocol)** | Offenes Protokoll, über das Tools/Resources/Prompts standardisiert für LLM-Clients (z. B. GitHub Copilot) bereitstehen. |
| **MCP-Server** | Prozess, der zusammengehörige MCP-Fähigkeiten bündelt und über einen Transport (hier `stdio`) bereitstellt. research-graphrag hat **einen** Server. |
| **MCP-Tool** | Aufrufbare Fähigkeit mit definiertem Input-/Output-Schema (z. B. `search_local`, `get_paper`). |
| **Transport `stdio`** | Standard-Transport: VS Code startet den Server als lokalen Unterprozess, Kommunikation über Standard-Input/Output, kein Netzwerk. |
| **LLM-Bridge / MCP-Sampling** | Der Server bindet **kein** Modell; benötigte Completions werden zur Abfragezeit per `session.create_message` vom Client (Copilot) angefordert (siehe [ADR 0004](adr/0004-llm-bridge-via-mcp-sampling.md)). |
| **Local / Global / DRIFT / Basic Search** | GraphRAG-Suchmodi: Detail an Entitäten (Local), corpusweit über Community-Reports (Global), global + lokal verfeinert (DRIFT), Top-k-Vektorsuche auf Chunks (Basic). Im Offline-Hybrid **implementiert** (Phase 4): Basic = TF-IDF-Top-k, Local = Chunk-Nachbarschaft + Paper-Fan-out, Global = Query→Community-Ranking, DRIFT = Global→Local-Hybrid ([ADR 0008](adr/0008-retrieval-and-query-router-phase4.md)). |
| **Community-Report** | Von GraphRAG erzeugte Zusammenfassung einer Graph-Community; Grundlage der Global Search. Im Offline-Hybrid **extraktiv** erzeugt (repräsentative Paper + Top-TF-IDF-Keywords), LLM-Veredelung optional zur Abfragezeit ([ADR 0007](adr/0007-graphrag-index-phase3-option-b.md)). |
| **Leiden** | Community-Detection-Algorithmus. Offline nicht verfügbar (`leidenalg`/`igraph` fehlen); der Offline-Hybrid nutzt **Louvain** (`networkx`). |
| **Louvain** | Community-Detection über `networkx`; Ersatz für Leiden im Offline-Hybrid ([ADR 0005](adr/0005-graphrag-index-backend-open.md)). |
| **Canonical Paper JSON** | Kanonisches Zwischenformat je Paper (Schema 0.2.0): heuristische Section-Hierarchie, Chunk-IDs, Referenz-Abschnitt, DOI/arXiv-Identifikatoren, Seiten-/Section-Provenienz, Qualitätsflags. Bounding-Box-Provenienz ist zurückgestellt ([ADR 0006](adr/0006-canonical-model-phase2-scope.md)). |
| **Chunk / TextUnit** | Kleinste retrievbare Texteinheit mit Provenienz; in Phase 2 abschnitts-/größenbasiert gebildet (Seite = harte Grenze). |
| **Qualitäts-Gate / -Flag** | Heuristisches Signal der Extraktion (z. B. `missing_abstract`, `ocr_noise`, `short_chunk`); aggregiert im `data/quality_report.*` ([ADR 0006](adr/0006-canonical-model-phase2-scope.md)). |
| **Provenienz** | Herkunftsnachweis einer abgeleiteten Aussage: Paper-ID, Abschnitt, Seite/Chunk (ggf. Bounding-Box), Score (siehe [documentation-standards.md](documentation-standards.md), Abschnitt 5). |
| **Docling / Marker** | PDF-Extraktoren (Docling pure Python, Marker für formel-/layoutlastige PDFs). Offline **nicht beschaffbar**; der Offline-Hybrid nutzt `pypdf` (Text). Docling/Marker sind späterer Ausbau ([ADR 0005](adr/0005-graphrag-index-backend-open.md)). |
| **LanceDB / Parquet** | Eingebetteter Vektor-/Spaltenspeicher der MS-GraphRAG-Artefakte. Offline **nicht beschaffbar**; der Offline-Hybrid nutzt **SQLite** (stdlib) + TF-IDF-Matrix ([ADR 0005](adr/0005-graphrag-index-backend-open.md)). |
| **manifest.json / Dedup** | Datei-Hash → Paper-ID; unveränderte PDFs werden bei der Ingestion übersprungen. |
| **TF-IDF** | Gewähltes, deterministisches Embedding-Verfahren des Offline-Hybrid (`scikit-learn`); Grundlage von Basic Search und Ähnlichkeit ([ADR 0005](adr/0005-graphrag-index-backend-open.md)). |
| **Query-Router** | Leichtgewichtige Auswahl des passenden Suchmodus je Fragetyp (Phase 4). |
| **ADR (Architecture Decision Record)** | Dokumentierte Architektur-/Grundsatzentscheidung mit Kontext, Entscheidung und Konsequenzen (siehe [adr/README.md](adr/README.md)). |
| **Definition of Done (DoD)** | Verbindliche Checkliste, ab wann ein Beitrag/Server als fertig gilt (siehe [repository-structure.md](repository-structure.md)). |
| **Reproduzierbarkeit** | Wiederholbarkeit von Ergebnissen durch fixierte Versionen (Lockfile), Seeds und Lauf-Metadaten. |
| **Offline-Firmenumfeld** | Entwicklungsumfeld ohne PyPI-Zugang; prägt die Tooling-Kompromisse (siehe [ADR 0002](adr/0002-venv-and-offline-dependency-strategy.md), [ADR 0003](adr/0003-offline-test-and-coverage-tooling.md)). |
| **SRQ (Sub-Forschungsfrage)** | Zuordnungsdimension der kuratierten `Übersicht.md`. |
