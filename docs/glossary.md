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
| **Local / Global / DRIFT / Basic Search** | GraphRAG-Suchmodi: Detail an Entitäten (Local), corpusweit über Community-Reports (Global), global + lokal verfeinert (DRIFT), Top-k-Vektorsuche auf Chunks (Basic). |
| **Community-Report** | Von GraphRAG erzeugte Zusammenfassung einer Graph-Community; Grundlage der Global Search. |
| **Leiden** | Community-Detection-Algorithmus zur Partitionierung des Graphen. |
| **Canonical Paper JSON** | Kanonisches Zwischenformat je Paper: Struktur, Section-Hierarchie, Chunk-IDs, Referenzen, Seiten-/Bounding-Box-Provenienz, Qualitätsflags. |
| **Chunk / TextUnit** | Kleinste retrievbare Texteinheit mit Provenienz. |
| **Provenienz** | Herkunftsnachweis einer abgeleiteten Aussage: Paper-ID, Abschnitt, Seite/Chunk (ggf. Bounding-Box), Score (siehe [documentation-standards.md](documentation-standards.md), Abschnitt 5). |
| **Docling / Marker** | PDF-Extraktoren: Docling (Standard, pure Python), Marker (Fallback für formel-/layoutlastige PDFs). |
| **LanceDB / Parquet** | Eingebetteter Vektor-/Spaltenspeicher der GraphRAG-Artefakte (file-based, kein Server). |
| **manifest.json / Dedup** | Datei-Hash → Paper-ID; unveränderte PDFs werden bei der Ingestion übersprungen. |
| **TF-IDF** | Deterministische, offline-taugliche Vektorisierung als Fallback, wo neuronale Embeddings nicht verfügbar sind (vgl. offener [ADR 0005](adr/0005-graphrag-index-backend-open.md)). |
| **Query-Router** | Leichtgewichtige Auswahl des passenden Suchmodus je Fragetyp (Phase 4). |
| **ADR (Architecture Decision Record)** | Dokumentierte Architektur-/Grundsatzentscheidung mit Kontext, Entscheidung und Konsequenzen (siehe [adr/README.md](adr/README.md)). |
| **Definition of Done (DoD)** | Verbindliche Checkliste, ab wann ein Beitrag/Server als fertig gilt (siehe [repository-structure.md](repository-structure.md)). |
| **Reproduzierbarkeit** | Wiederholbarkeit von Ergebnissen durch fixierte Versionen (Lockfile), Seeds und Lauf-Metadaten. |
| **Offline-Firmenumfeld** | Entwicklungsumfeld ohne PyPI-Zugang; prägt die Tooling-Kompromisse (siehe [ADR 0002](adr/0002-venv-and-offline-dependency-strategy.md), [ADR 0003](adr/0003-offline-test-and-coverage-tooling.md)). |
| **SRQ (Sub-Forschungsfrage)** | Zuordnungsdimension der kuratierten `Übersicht.md`. |
