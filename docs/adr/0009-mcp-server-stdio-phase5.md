# 0009 – MCP-Server (stdio) Phase 5: Retrieval-Tools & Copilot-Integration

- **Status:** Akzeptiert
- **Datum:** 2026-07-31

## Kontext

[Roadmap.md](../../Roadmap.md) beschreibt für **Phase 5** einen **MCP-Server (Transport `stdio`)**,
der die in Phase 4 ([ADR 0008](0008-retrieval-and-query-router-phase4.md)) fertiggestellten,
deterministischen Retrieval-Modi als **Werkzeuge für GitHub Copilot** bereitstellt – jede Antwort
mit strukturierter Provenienz. Zugesagt sind sechs Tools: `search_local`, `search_global`,
`search_drift`, `search_basic`, `get_paper`, `list_topics` ([README.md](../../README.md),
[docs/vscode-integration.md](../vscode-integration.md)). Die DoD lautet: *Copilot ruft die Werkzeuge
auf und erhält belegte Antworten mit Quellen.*

Rahmenbedingungen:

- **Offline-Firmenumfeld** ([ADR 0002](0002-venv-and-offline-dependency-strategy.md)); nur das
  offline vorhandene **MCP Python SDK** (`mcp`, inkl. FastMCP) ist verfügbar.
- **Secret-Freiheit & Modell-Agnostik** ([documentation-standards.md](../documentation-standards.md),
  Abschnitt 8): kein gebundenes Modell/Key im Server.
- **Vorbild** `mcs-copilot-tools` (FastMCP + `stdio`, strukturierte Fehlerausgabe an der
  Server-Grenze).
- Vier der sechs Tools sind bereits als getestete, serialisierbare Funktionen in
  `src/research_graphrag/retrieval/` vorhanden (`to_dict()`); nur `get_paper` benötigt neuen
  Backend-Code, `list_topics` ist ein dünner Wrapper um `load_communities`
  ([ADR 0007](0007-graphrag-index-phase3-option-b.md)).

## Entscheidung

Phase 5 registriert die sechs Tools über **FastMCP** (`stdio`) in **einem** Server
`research_graphrag.mcp_server` (Start: `python -m research_graphrag.mcp_server`). Die Tools sind
**dünne Wrapper** um die bestehende, offline-deterministische Kernlogik.

1. **Kein serverseitiges LLM-Sampling (Abgrenzung zu [ADR 0004](0004-llm-bridge-via-mcp-sampling.md)).**
   Die Tools liefern **ausschließlich strukturierte Evidenz + Provenienz**; die natürlichsprachige
   Antwort formuliert der aufrufende Agent (Copilot) selbst. Ein serverseitiger Sampling-Aufruf
   (`create_message`) würde dasselbe Client-Modell mit **weniger Kontext** (nur Server-Prompt statt
   voller Konversation) anfragen und ein „Telefonspiel" (Evidenz → Zwischen-Zusammenfassung mit
   Kontext-/Provenienzverlust → Endantwort) erzeugen. Der Verzicht ist damit die Variante mit den
   **besseren Antworten** und wahrt Determinismus/Testbarkeit. Die LLM-Bridge aus
   [ADR 0004](0004-llm-bridge-via-mcp-sampling.md) bleibt für einen späteren, echten
   Synthese-Bedarf reserviert, wird in Phase 5 aber **nicht** gebaut (YAGNI, right-sized).

2. **`get_paper` liest aus dem Index (Single Source of Truth), `paper_id`-basiert.** Eingabe ist
   eine **`paper_id`** (kein Datei-Pfad) → kein Pfad-Traversal-Vektor, unbekannte IDs ergeben
   `not_found` statt `permission_denied`. Rückgabe (AI-freundlich, stabil): `paper_id`,
   `source_uri`, `identifiers` (`doi`/`arxiv`), `n_pages`, `n_chunks`, `sections` (eindeutige
   Abschnittstitel in Reihenfolge), `snippet` (Leit-Snippet des ersten Chunks). Der Abruf koppelt
   **nicht** an den gitignorierten Canonical-Cache.

3. **Additive Index-Erweiterung `identifiers` (Index-Schema `0.2.0 → 0.3.0`).** DOI/arXiv liegen
   bereits im Canonical (Schema 0.2.0), waren aber nicht im Index. Sie werden als
   **JSON-Spalte** `papers.identifiers TEXT NOT NULL DEFAULT '{}'` additiv aufgenommen (gleiches
   Muster wie `communities.keywords`), damit `get_paper` zitierfähige Identifikatoren aus der
   Source of Truth liefert. Da `build_index` stets **voll** neu baut, genügt ein **Re-Ingest**
   (Extraktion wird übersprungen, Canonical unverändert); eine Migrationslogik ist nicht nötig.

4. **`list_topics`** gibt die persistierten Louvain-Communities
   ([ADR 0007](0007-graphrag-index-phase3-option-b.md)) über `load_communities` zurück
   (`community_id`, `size`, `keywords`, `representatives`, `summary`).

5. **Fehlerübersetzung an der Server-Grenze.** Fachliche `DomainError`
   ([error-model.md](../error-model.md)) werden im Tool abgefangen und als **strukturierte
   Ausgabe** mit `isError = true` geliefert (`content` = JSON-Text des Fehler-Envelopes,
   `structuredContent` = `{"error": {code, message[, details]}}`). Eine letzte `except`-Sicherung
   übersetzt Unerwartetes in `internal_error`. Protokoll-/Schema-Fehler bleiben dem SDK überlassen.

6. **Server-Konfiguration & Sicherheitsgrenze.** Index-Pfad über `RESEARCH_GRAPHRAG_INDEX`
   (Default `data/index/index.sqlite`), Log-Niveau über `RESEARCH_GRAPHRAG_LOG_LEVEL`
   (stderr; stdout ist beim `stdio`-Transport dem MCP-Protokoll vorbehalten). Da **kein** Tool
   nutzergesteuerte Datei-Pfade entgegennimmt (nur `query`/`paper_id`), ist **keine**
   Pfad-Root-Grenze (`RESEARCH_GRAPHRAG_WORKSPACE_ROOTS`) nötig; sie entfällt bewusst.

## Alternativen

- **Serverseitige Antwort-Synthese via MCP-Sampling.** Verworfen (Punkt 1): schlechtere,
  nicht-deterministische Antworten durch Kontextverlust; doppelte Generierung; erschwerte Tests.
- **`get_paper` aus dem Canonical-JSON-Cache.** Verworfen: koppelt ein Tool an einen
  **gitignorierten** Cache statt an die Index-Source-of-Truth und riskiert Divergenz zu den übrigen
  Tools; die Index-Reads sind konsistent und billig.
- **`get_paper` mit Datei-Pfad-Eingabe (+ `WORKSPACE_ROOTS`).** Verworfen: führt einen
  Pfad-Traversal-Vektor ein; `paper_id` als Schlüssel ist sicherer und für einen Agenten stabiler.
- **DOI/arXiv als separate Tabelle bzw. Einzelspalten.** Verworfen zugunsten der JSON-Spalte:
  erweiterbar ohne Schema-Änderung und konsistent mit dem bestehenden `keywords`-Muster.
- **Low-Level-`Server` statt FastMCP.** Verworfen: FastMCP ist im SDK vorhanden, deckt Tool-
  Registrierung/Schema-Ableitung ab und entspricht dem Vorbild `mcs-copilot-tools`.
- **Mehrere Server (je Modus).** Verworfen: Ein Server bündelt das kohärente Retrieval-Portfolio
  (README: „EIN MCP-Server").

## Konsequenzen

- **Positiv:** Voll offline-tauglich, **deterministisch**, secret-frei und modell-agnostisch; die
  Tools sind dünne Wrapper um bereits getestete Kernlogik; vollständige Provenienz inkl. Abschnitt;
  scharfe Fehlerausgabe an der Grenze; `get_paper` liefert zitierfähige Identifikatoren aus einer
  einzigen Quelle.
- **Negativ / Aufwand:** Die additive Index-Spalte erzwingt einen **Re-Ingest**; der Server bringt
  eine schmale FastMCP-Grenzschicht mit (Fehlerübersetzung, Konfiguration). Die DoD wird – wie in
  Phase 3/4 – über **Tests** (inkl. eines In-Memory-Client-Roundtrips) statt über einen manuellen
  Copilot-Lauf nachgewiesen.
- **Folgeentscheidungen:** Ein echter Synthese-Pfad über die LLM-Bridge
  ([ADR 0004](0004-llm-bridge-via-mcp-sampling.md)), ein semantischer Entitäts-/Zitationsgraph und
  Hybrid-Suche bleiben **Phase 7** (Option C, [ADR 0005](0005-graphrag-index-backend-open.md)).
