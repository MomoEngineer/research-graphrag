# 0008 – Retrieval & Query-Router Phase 4: Offline-Modi (Basic/Local/Global/DRIFT) & Router

- **Status:** Akzeptiert
- **Datum:** 2026-07-31

> **Nachtrag (2026-08-02, [ADR 0017](0017-router-hardening-phase7.md)):** Die unten festgelegte
> **Präzedenz** `drift > global > local > basic` ist **abgelöst**. Der gehärtete Router behandelt
> `basic` als Rückfallebene statt als gleichrangigen Modus, entscheidet zwischen den strukturellen
> Modi über die Signalzahl und fällt bei Gleichstand sichtbar auf `basic` zurück. Ebenfalls
> abgelöst ist das rohe **Substring-Matching**: Die Match-Art ist seither je Signal deklariert.
> Unverändert gilt alles Übrige dieses ADR – insbesondere die Offline-Semantik der vier Modi, der
> Provenienz-Assembler und die Gleichwertigkeit der expliziten Modus-Wahl.

> **Nachtrag (2026-08-03, [ADR 0021](0021-local-multi-seed-phase10.md)):** Die unten für **Local**
> festgelegte Verankerung an **einem** Seed-Chunk ist **abgelöst**. Local nutzt die Top-*m* der
> Hybrid-Wertung als Seeds (Default 5), bildet die Chunk-Nachbarschaft je Seed und führt die
> Teilranglisten per Reciprocal Rank Fusion zusammen; `LocalSearchResult.seed` heißt seither
> `seeds` und ist eine Liste. Unverändert bleiben die drei Bausteine als solche, der Fan-out über
> den Paper-Ähnlichkeitsgraphen (weiterhin am Paper des ersten Seeds) und die Provenienz.

> **Nachtrag (2026-08-03, [ADR 0022](0022-drift-community-union-and-fallback-phase10.md)):** Die
> unten für **DRIFT** festgelegte Beschränkung auf die **beste** Community ist **abgelöst**. Die
> lokale Verfeinerung läuft über die **Vereinigung der Top-5** Communities, und liefert dieser
> Pfad keine Belege, fällt DRIFT sichtbar auf die Chunk-Suche ohne Paper-Filter zurück
> (`DriftSearchResult.fallback`). `DriftSearchResult.community` heißt seither `communities` und
> ist eine Liste. Unverändert bleiben die Global→Local-Grundidee, die Community-Provenienz und
> das Fehlerverhalten bei fehlendem Graphen.

## Kontext

[Roadmap.md](../../Roadmap.md) beschreibt für **Phase 4** einen „Query-Router" mit den
Microsoft-GraphRAG-Suchmodi **Local / Global / DRIFT / Basic**, einen **leichtgewichtigen Router**
gemäß Fragetyp-Mapping ([README.md](../../README.md)) und einen **Provenienz-Assembler**
(Paper-ID, Abschnitt, Seite/Chunk). Das Fragetyp-Mapping der README ordnet zu:

| Fragetyp | Primärmodus (README) |
| --- | --- |
| Detailfrage zu einem Paper | Local + Basic |
| Cross-Paper-Synthese / Themen | Global |
| Zitations-/Methodennetze (Multi-Hop) | Local (Fan-out) |
| Exakte Fakten (DOI, Metrik) | Basic |
| Widersprüche / Vergleiche | DRIFT |

Die MS-GraphRAG-Semantik dieser Modi (Entitäts-/Community-Graph, LLM-Community-Reports,
iteratives DRIFT) stammt aus der Zeit *vor* [ADR 0005](0005-graphrag-index-backend-open.md) und ist
im Offline-Umfeld ([ADR 0002](0002-venv-and-offline-dependency-strategy.md)) **nicht** bedienbar.
Phase 4 muss die Modi daher – wie Phase 2/3 ([ADR 0006](0006-canonical-model-phase2-scope.md),
[ADR 0007](0007-graphrag-index-phase3-option-b.md)) – **deterministisch offline approximieren**.

Rahmenbedingungen (Option B):

- **Kein LLM zur Index-/Retrieval-Zeit.** Die natürlichsprachige Antwort formuliert der aufrufende
  Agent (Copilot) über die **LLM-Bridge** ([ADR 0004](0004-llm-bridge-via-mcp-sampling.md)) aus der
  hier gelieferten, **belegten Evidenz**. Die Modi liefern nur strukturierte Treffer + Provenienz.
- **Vorhandene Artefakte:** rekonstruierbarer **TF-IDF-Raum** über Chunks ([ADR 0005](0005-graphrag-index-backend-open.md))
  und der **Paper-Ähnlichkeitsgraph** mit **Louvain-Communities** ([ADR 0007](0007-graphrag-index-phase3-option-b.md))
  in `data/index/index.sqlite`.
- **Right-sizing** ([CONTRIBUTING.md](../../CONTRIBUTING.md)): Bei ~145 Papern ist der Nutzen von
  Global/DRIFT „noch moderat". In **Phase 5** wird zudem **Copilot selbst zum Router** (explizite
  Tool-Wahl je Modus); ein schwergewichtiger Klassifikator wäre teilweise Wegwerf-Code.

## Entscheidung

Phase 4 kapselt **vier deterministische, belegbare Retrieval-Modi**, einen **schlanken Router** und
einen **Provenienz-Assembler**. Der Index-/Graph-Contract bleibt bis auf eine **additive
Schema-Erweiterung** (Abschnitts-Provenienz) unverändert; die MCP-Registrierung folgt in Phase 5.

| Modus | Offline-Umsetzung (Option B) | Provenienz |
| --- | --- | --- |
| **Basic** (`search_basic`, existiert) | TF-IDF-Top-k über alle Chunks (Kosinus). | Chunk-Zitate. |
| **Local** (`search_local`) | **Beides kombiniert:** (a) **Chunk-Nachbarschaft** – nächste Chunks zum besten Treffer-Chunk (Chunk↔Chunk-Kosinus zur Abfragezeit aus der TF-IDF-Matrix, wie in [ADR 0007](0007-graphrag-index-phase3-option-b.md) vorgesehen); (b) **Paper-Fan-out** – Nachbarpaper des Seed-Papers über die persistierten `graph_edges`, je Nachbar der query-relevanteste Chunk. Deckt „Local + Basic" **und** „Local (Fan-out)" ab. | Seed-Chunk + Nachbar-Chunks + Fan-out-Chunks (je mit Kantengewicht). |
| **Global** (`search_global`) | **Community-Ranking:** frischer `TfidfVectorizer` über je Community aggregierte **Keywords + Summary**; Query dagegen scoren; Top-N Communities zurückgeben. Offline-Analog zum Map-Reduce über Community-Reports. | Repräsentative Paper je Community (`paper_id`, `source_uri`, Leit-Snippet). |
| **DRIFT** (`search_drift`) | **Pragmatischer Global→Local-Hybrid:** Top-Community bestimmen (Global-Ranking), dann **fokussierte Chunk-Suche innerhalb der Community-Mitglieder**. Bewusst **kein** iteratives Multi-Step-DRIFT (right-sized). | Gewählte Community (Kontext) + Chunk-Zitate innerhalb der Community. |

**Router:** Ein reiner, DB-freier **Heuristik-Klassifikator** `route(query) → (mode, rationale)`
auf Basis deutscher/englischer Schlüsselwörter (Präzedenz `drift > global > local > basic`, Default
`basic` als präzisester Modus). Er dient dem **CLI-Komfort** (`--mode auto`); die **explizite
Modus-Wahl** (`--mode {basic,local,global,drift}`) bleibt gleichwertig. Der Klassifikator ist
absichtlich dünn und liefert eine kurze **Begründung** (Transparenz/Logging).

**Provenienz-Assembler:** `retrieval/provenance.py` stellt das **gemeinsame** `Citation`-Modell
(Chunk-Ebene, inkl. **`section_title`**) und `PaperRef` (Paper-Ebene: `source_uri` + Leit-Snippet)
bereit sowie den `ProvenanceAssembler`, der Paper-Provenienz **direkt aus dem Index** (ohne
`sklearn`) zusammenstellt. Alle Modi nutzen dieselben Provenienz-Typen.

**Index-Schema-Erweiterung (additiv):** Die Roadmap fordert Abschnitts-Provenienz. Die
Chunk-`section_title` liegt bereits im Canonical (Schema 0.2.0), war aber bewusst **nicht** im Index
([ADR 0006](0006-canonical-model-phase2-scope.md)/[ADR 0007](0007-graphrag-index-phase3-option-b.md)).
Phase 4 nimmt **`section_title`** additiv in die Index-`chunks`-Tabelle auf (Index-Schema
`0.1.0 → 0.2.0`), damit Retrieval die Abschnitts-Provenienz **aus der Source of Truth** liest (nicht
aus dem gitignorierten Canonical-Cache). Da `build_index` stets **voll** neu baut, genügt ein
**Re-Ingest**; eine Migrationslogik ist nicht nötig. `section_title` ist optional (leer, wenn keine
Section erkannt wurde).

## Alternativen

- **Reine Chunk-Nachbarschaft für Local (ohne Paper-Graph).** Verworfen zugunsten „beides
  kombiniert": Der persistierte Paper-Graph ([ADR 0007](0007-graphrag-index-phase3-option-b.md)) ist
  genau das Artefakt für den „Fan-out" (Zitations-/Methodennetze); ihn zu ignorieren, verschenkte
  Phase-3-Arbeit.
- **Persistierter Chunk-Ebenen-Graph.** Bereits in [ADR 0007](0007-graphrag-index-phase3-option-b.md)
  verworfen (~14k Knoten, Rauschen). Die Chunk-Nachbarschaft wird **zur Abfragezeit** aus der
  TF-IDF-Matrix berechnet.
- **Echtes iteratives DRIFT (mehrstufige Verfeinerung).** Verworfen (Over-Engineering bei ~145
  Papern); der Global→Local-Hybrid ist der right-sized Kompromiss und leicht später ausbaubar.
- **Schwergewichtiger Router (ML-/LLM-Klassifikator).** Verworfen: nicht deterministisch/offline
  aufwändig und in Phase 5 redundant (Copilot wählt das Tool). Der dünne Heuristik-Router genügt der
  DoD und bleibt wartungsarm.
- **Abschnitt zur Abfragezeit aus dem Canonical-JSON lesen.** Verworfen: koppelt Retrieval an den
  **gitignorierten Cache** statt an die Index-Source-of-Truth; eine additive Index-Spalte ist
  robuster und billiger (voller Re-Index ohnehin Standard).
- **LLM-veredelte Antworten im Tool.** Verworfen: bleibt der Abfragezeit über die Bridge
  vorbehalten ([ADR 0004](0004-llm-bridge-via-mcp-sampling.md)); die Modi liefern nur Evidenz.

## Konsequenzen

- **Positiv:** Voll offline-tauglich und **deterministisch** (TF-IDF, fixe Tie-Breaks, fixer
  Louvain-Seed aus Phase 3); nutzt ausschließlich vorhandene Bausteine; scharfe Modus-Contracts als
  Single Source of Truth für die Phase-5-Tools; **vollständige Provenienz** inkl. Abschnitt.
- **Negativ / Aufwand:** Modi sind **lexikalisch-thematisch** (TF-IDF/Louvain), kein semantischer
  Entitäts-/Zitationsgraph; DRIFT ist ein **pragmatischer** Hybrid, kein echtes iteratives DRIFT;
  der Heuristik-Router ist bewusst grob; die Index-Schema-Erweiterung erzwingt einen **Re-Ingest**.
- **Folgeentscheidungen:** Phase 5 registriert `search_local`/`search_global`/`search_drift`
  (neben `search_basic`) als MCP-Tools und macht Copilot zum Router; ein echter Domänen-/
  Zitationsgraph, tiefes DRIFT und Hybrid-Suche (BM25) bleiben **Phase 7**
  (Option C, [ADR 0005](0005-graphrag-index-backend-open.md)).
