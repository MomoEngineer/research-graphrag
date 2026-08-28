# Roadmap-Historie – Phasen 0–8, 11 und 12 (Archiv)

**Dies ist das wörtliche Archiv der Roadmap in dem Stand, in dem die Phasen 0–8, 11 und 12
abgeschlossen wurden.** Es enthält die vollständigen Status-Blockquotes mit allen gemessenen Kennzahlen,
korrigierten Annahmen und offen dokumentierten Abweichungen – also die Begründungslage, auf die
sich [ADR 0006](adr/0006-canonical-model-phase2-scope.md) bis
[ADR 0017](adr/0017-router-hardening-phase7.md) mit Formulierungen wie „die Roadmap beschreibt für
Phase 7 / A3 …" beziehen.

> **Fortgeschrieben, wenn eine Phase abgeschlossen wird.** Der aktive Plan steht in [Roadmap.md](../Roadmap.md); dort sind abgeschlossene Phasen nur noch als Ergebnis-Tabelle zusammengefasst. Einzelne Aussagen bleiben datiert und waren zum Zeitpunkt ihrer Entstehung korrekt (dieselbe Regel gilt für ADRs). Der einzige Eingriff gegenüber dem Original ist dieser Kopf sowie die um eine Ebene angepassten relativen Links (`docs/…` → `../docs/…`), weil die Datei aus der Repo-Wurzel nach `docs/` gewandert ist.

---

## Leitprinzipien

- **Lean & container-frei:** reine Python-Umgebung, kein Docker-/DB-Server im MVP.
- **Provenienz zuerst:** jede Antwort ist auf Paper/Abschnitt/Seite rückführbar.
- **Inkrementell nutzbar:** neue PDFs per Drop-in-Ordner + Skript, ohne alles neu aufzusetzen.
- **Klein, aber wachstumsfähig:** optimiert für ≤ 500 Paper, mit klaren Erweiterungspfaden.
- **Wiederverwenden statt neu bauen:** MCP-SDK sowie `scikit-learn`/`networkx`/`pypdf` als Fundament der Offline-Variante (Option B, [ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md)); Microsoft GraphRAG/Docling bleiben Zielbild, falls beschaffbar.
- **Konsolidierte Forschungsbasis:** ersetzt den bisherigen `Recherche`-Ordner und vereint PDFs, kuratierte Literaturübersicht (`Übersicht.md`) und GraphRAG-Index in einem Repo.

## Offene Entscheidungen (mit Empfehlung)

| Entscheidung | Optionen | Empfehlung |
|---|---|---|
| **Index-LLM / Embeddings** | Cloud-API (Azure OpenAI/OpenAI) · lokal via Ollama · hybrid | **Entschieden: Offline-Hybrid (Option B)** – Cloud/Ollama offline nicht beschaffbar; **TF-IDF** im Index, LLM nur zur Abfragezeit via Bridge ([ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md)). |
| **Primär-Extraktor** | Docling · Marker | **Entschieden: `pypdf` (Option B)** – Docling/Marker offline nicht beschaffbar; `pypdf` liefert Text + Seiten-Provenienz, Docling/Marker als späterer Ausbau ([ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md)). |
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

> **Status:** ✅ umgesetzt – 0a (Gerüst) und 0b (Offline-Hybrid-Durchstich) fertig; **M1 erreicht** (1 PDF → Index → belegte Antwort). Umsetzung als Option B ([ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md)); Backend = TF-IDF offline + LLM-Bridge zur Abfragezeit. Kernmodule 100 % Zeilenabdeckung.

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

- `pypdf`-Extraktor integrieren (Option B, [ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md)); Docling/Marker als späterer Ausbau, falls beschaffbar.
- **Canonical Paper JSON** definieren: stabile IDs, Section-Hierarchie (heuristisch), Chunk-IDs, Referenz-Abschnitt, Seiten-/Section-Provenienz, Extraktions-Qualitätsflags. **Bounding-Box-Provenienz** und tiefes Referenz-Parsing sind bewusst zurückgestellt ([ADR 0006](../docs/adr/0006-canonical-model-phase2-scope.md), Phase 7).
- **Dedup & Cache:** `manifest.json` (Datei-Hash → Paper-ID); unveränderte PDFs überspringen.
- **Qualitäts-Gates:** fehlender Abstract, kaputte Referenzen, OCR-Rauschen, leere/kopflose Tabellen, zu kurze/lange Chunks.
- **Übersicht-Entwurf:** `scripts/update_overview.py` erzeugt **deterministische, extraktive** Entwurfszeilen (Name, Interner/Externer Link, Keyword, Kurzzusammenfassung) **append-only** nach `data/overview_drafts.md` (Staging, kuratierte `Übersicht.md` bleibt unangetastet); wertende Spalten bleiben manuell.
- Grundgerüst `scripts/ingest.py`.

**DoD:** PDFs in `papers/` + `ingest.py` erzeugen Canonical JSON nur für neue/geänderte Dateien inkl. Qualitätsreport; neue Paper erscheinen als Entwurfszeile in `data/overview_drafts.md`.

> **Status:** ✅ umgesetzt – Canonical-Schema **0.2.0** (Section-Heuristik, größenbasiertes Chunking, DOI/arXiv, Qualitätsflags), Qualitätsreport (`data/quality_report.json`/`.md`) und `scripts/update_overview.py` (Staging-Entwürfe) laufen und sind getestet (84 Tests grün, Kernmodule ≥ 96 % Zeilenabdeckung). Umfangsabgrenzung (keine Bounding-Boxes, kein tiefes Referenz-/Tabellen-Parsing): [ADR 0006](../docs/adr/0006-canonical-model-phase2-scope.md).

### Phase 3 – GraphRAG-Index (file-based)
**Ziel:** Wissensgraph + Community-Reports aus Canonical JSON.

> **Umsetzung als Offline-Hybrid (Option B, [ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md)):** statt Microsoft GraphRAG/LanceDB/Leiden → **TF-IDF** (`scikit-learn`), Graph + **Louvain** (`networkx`), Speicher in **SQLite**; Community-Zusammenfassungen extraktiv bzw. on-demand über die LLM-Bridge. Die folgenden MS-GraphRAG-Punkte bleiben das Zielbild (Option C).

- Canonical JSON → GraphRAG-Input (JSON/JSONL bzw. Custom InputReader / BYO-DataFrame).
- `settings.yaml`: Chunking, Entity-/Relationship-/(Claim-)Extraktion, Community-Detection (Leiden), Embeddings.
- **Prompt-Tuning** für die wissenschaftliche Domäne.
- Artefakte als Parquet + LanceDB.

**DoD:** Indexlauf abgeschlossen; Artefakte vorhanden; erste Abfrage per GraphRAG-CLI erfolgreich.

> **Status:** ✅ umgesetzt (Option B, [ADR 0007](../docs/adr/0007-graphrag-index-phase3-option-b.md)): deterministischer **Paper-Ähnlichkeitsgraph** (TF-IDF, *mutual top-k*) mit **Louvain-Communities** (fixer Seed) und **extraktiven** Zusammenfassungen (repräsentative Paper + Top-TF-IDF-Keywords), additiv in `data/index/index.sqlite` (`graph_nodes`/`graph_edges`/`communities`/`community_members`). Der Graph-Bau ist in `python -m scripts.ingest` integriert; `IngestReport` zählt Knoten/Kanten/Communities, `python -m scripts.graph_info` zeigt sie. **DoD-Anpassung:** mangels „GraphRAG-CLI“ (offline nicht vorhanden) erfolgt der Nachweis über Tests, die `IngestReport`-Kennzahlen und `scripts/graph_info`. Realer Korpuslauf: **145 Knoten, 216 Kanten, 42 Communities**; Chunk-/Entitäts-Ebene bleibt zurückgestellt (Phase 4/7). 97 Tests grün, Kernmodule ≥ 96 % (graph_index 98,7 %).

### Phase 4 – Retrieval & Query-Router
**Ziel:** passender Suchmodus je Fragetyp, mit Provenienz.

- Local / Global / DRIFT / Basic Search kapseln.
- Leichtgewichtiger **Router** (heuristisch oder explizite Werkzeug-Wahl) gemäß Fragetyp-Mapping.
- Provenienz-Assembler (Paper-ID, Abschnitt, Seite/Chunk).

**DoD:** alle 5 Fragetypen per CLI beantwortbar, jeweils mit Quellenangaben.

> **Status:** ✅ umgesetzt (Option B, [ADR 0008](../docs/adr/0008-retrieval-and-query-router-phase4.md)): **Basic** (TF-IDF-Top-k), **Local** (Chunk-Nachbarschaft zur Abfragezeit **+** Paper-Fan-out über den Phase-3-Graphen), **Global** (Query→Community-Ranking mit repräsentativer Paper-Provenienz) und **DRIFT** (pragmatischer Global→Local-Hybrid) sind in `src/research_graphrag/retrieval/` gekapselt. Ein schlanker Heuristik-**Router** (`--mode auto`) plus **explizite** Modus-Wahl decken das Fragetyp-Mapping ab; der **Provenienz-Assembler** liefert Paper · Abschnitt · Seite/Chunk – dazu wurde der Index additiv um `section_title` erweitert (Schema **0.2.0**, voller Re-Ingest). **DoD-Nachweis:** alle 5 Fragetypen per `python -m scripts.ask "<frage>" [--mode …]` belegt beantwortet (siehe [eval/pruef-fragen.md](../eval/pruef-fragen.md)). **145 Tests grün**, Kernmodule ≥ 96 % (retrieval-Module 100 %). Realer Korpuslauf: **145 Paper / 14 397 Chunks / 42 Communities**; echtes iteratives DRIFT und ein semantischer Entitäts-/Zitationsgraph bleiben zurückgestellt (Phase 7).

### Phase 5 – MCP-Server (stdio) & Copilot-Integration
**Ziel:** Retrieval als Werkzeuge in Copilot.

- Python-MCP-Server (stdio) mit Werkzeugen: `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper`, `list_topics`.
- Jede Werkzeug-Antwort mit strukturierter Provenienz.
- Registrierung in VS Code (`.vscode/mcp.json`), Kurzdoku.

**DoD:** Copilot ruft die Werkzeuge auf und erhält belegte Antworten mit Quellen.

> **Status:** ✅ umgesetzt ([ADR 0009](../docs/adr/0009-mcp-server-stdio-phase5.md)): Der **stdio-MCP-Server** (`python -m research_graphrag.mcp_server`, FastMCP) registriert alle sechs Werkzeuge (`search_basic`/`search_local`/`search_global`/`search_drift`/`get_paper`/`list_topics`); jede Antwort trägt strukturierte Provenienz, fachliche Fehler werden an der Server-Grenze in `isError`-Ausgaben (`{"error": …}`) übersetzt. **Kein** serverseitiges LLM-Sampling – die Tools liefern Evidenz, Copilot formuliert (Abgrenzung zu [ADR 0004](../docs/adr/0004-llm-bridge-via-mcp-sampling.md)). Einbindung über [`.vscode/mcp.json`](../.vscode/mcp.json) (venv-Interpreter). Für zitierfähige `get_paper`-Metadaten wurde der Index additiv auf **Schema 0.3.0** (Identifikatoren) erweitert; Re-Ingest bestätigt (**145 Paper / 14 397 Chunks / 42 Communities**, 142/145 mit DOI/arXiv). **DoD-Anpassung:** mangels steuerbarem Copilot-Client erfolgt der Nachweis – wie in Phase 3/4 – über Tests, insbesondere einen **In-Memory-Client-Roundtrip** über alle sechs Tools (Erfolg + Fehler-Envelope). Tests grün; Chunk-/Entitäts-Ebene und ein LLM-Synthese-Pfad bleiben zurückgestellt (Phase 7).

### Phase 6 – Drop-in-Workflow & Qualitätssicherung
**Ziel:** reibungsloser „ablegen → nutzen"-Kreislauf.

- `ingest.py` bindet Extraktion-Dedup + Index-Aktualisierung zu einem Befehl zusammen (voller Re-Index Standard; inkrementelles Update dokumentiert).
- MCP-Server liest stets die **aktuellen** Artefakte (Reload/On-Read).
- Pragmatische QS: Prüf-Fragen durchspielen, Provenienz-Stichproben, einfaches Logging/Status.

**DoD:** neue PDF ablegen → `ingest.py` → sofort in Copilot abfragbar; unveränderte PDFs übersprungen.

> **Status:** ✅ umgesetzt ([ADR 0010](../docs/adr/0010-drop-in-workflow-and-qa-phase6.md)): Die Bausteine „ein Befehl“ (`python -m scripts.ingest`, seit Phase 2/3) und „On-Read“ (der MCP-Server lädt Index/Communities **pro Anfrage** frisch, seit Phase 5) waren bereits erfüllt und wurden **verifiziert + gehärtet**: Der Index-Neuaufbau erfolgt jetzt **atomar** (Build nach `*.sqlite.tmp` + `os.replace`; ein Fehler lässt den Alt-Index intakt), sodass On-Read nie einen halbfertigen Index sieht. Neu für die **pragmatische QS**: `python -m scripts.status` (read-only Index-/Korpus-Status + Konsistenz-Check `papers/ ↔ manifest ↔ canonical`) und `python -m scripts.qa` (feste Prüf-Fragen je Modus durchspielen, Provenienz zeigen; Single Source of Truth). **DoD-Nachweis** – wie in Phasen 3–5 über Tests (kein steuerbarer Copilot-Client): ein **Freshness-/Atomaritäts-Regressionstest** plus die **QS-Harness-Regression**; realer Korpuslauf unverändert **145 Paper / 14 397 Chunks / 42 Communities**, `scripts.qa` liefert **10/10** Fragen mit belegter Provenienz. **170 Tests grün**, Kernmodule ≥ 92 %. Inkrementelles Update bleibt dokumentiert/optional (Phase 7).

### Phase 7 – Ausblick & Erweiterungen (optional, nach Bedarf)
**Ziel:** gezielte, bedarfsgetriebene Vertiefung entlang der in den Phasen 2–6 **beobachteten** Lücken – **offline-first** (Option B) priorisiert, mit klar abgegrenztem, beschaffungsabhängigem **Zielbild** (Option C, [ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md)). Wie im gesamten Plan: **keine Zeitschätzungen**; Auswahl und Reihenfolge richten sich nach Nutzen und tatsächlichem Bedarf, jeder Punkt bleibt einzeln zieh- und weglassbar. Die Akzeptanzkriterien sind bewusst „right-sized“ (Nachweis über Tests/Stichproben, kein Over-Engineering).

**Gruppe A – offline umsetzbar (Option B), nach beobachtetem Nutzen priorisiert.** Reihenfolge = Vorschlag; höher = größerer erwarteter Mehrwert bei der täglichen Nutzung.

1. **LLM-Bridge / optionale Antwort-Synthese tatsächlich implementieren** ([ADR 0004](../docs/adr/0004-llm-bridge-via-mcp-sampling.md)). *Lücke:* Der injizierbare Generierungs-Port ist in ADR 0004 beschrieben, im Code aber **nicht vorhanden**; Antworten sind heute reine Evidenz + Provenienz – der größte Hebel für die tägliche Nutzbarkeit (aus Belegen wird eine belegte Fließtext-Antwort). *Akzeptanz:* `GenerationProvider`-Protokoll mit `SamplingGenerationProvider` (Client-Modell via MCP-Sampling) und `NoopGenerationProvider` (Fallback → `generated = false`); optionaler Synthese-Pfad (Flag `--synthese` in `python -m scripts.ask` bzw. ein dediziertes Tool); ohne Sampling bleibt die **volle Evidenz** erhalten und die Pipeline degradiert **sichtbar** statt zu scheitern; Determinismus der Evidenz unberührt; Noop-Fallback getestet.

> **Status:** ✅ umgesetzt ([ADR 0012](../docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md)): Das neue Paket `generation/` realisiert den Port (`GenerationProvider` mit `NoopGenerationProvider`/`SamplingGenerationProvider`), eine **mode-agnostische, deterministisch nummerierte** Evidenz (`Evidence`, `[1] … [n]` mit Paper · Abschnitt · Seite · Quelle), die Adapter für alle vier Modi und die Orchestrierung `answer_question` (Router → Retrieval → Evidenz → optionale Synthese). Der **Antwort-Contract** ist strikt: nur aus den Belegen, `[n]`-Zitatmarken, „nicht belegt" statt Vermutung, Deutsch, `temperature = 0`.
>
> **Bewusste Scope-Schärfung gegenüber der ursprünglichen Akzeptanz:** Ein reiner CLI-Pfad wäre offline dauerhaft im Noop-Fallback geblieben (kein Modell) – und Copilot formuliert die Antwort ohnehin selbst, ein serverseitiges Sampling *per Default* wäre also **doppelte Generierung**. Deshalb gibt es **beides**: `python -m scripts.ask --synthese` (Noop, macht den Fallback beobachtbar) **und** genau ein neues MCP-Tool **`answer_question`** – mit `synthesize = false` als Default (deterministisches Evidenz-Bündel in *einem* Aufruf, einheitliches Schema über alle Modi) und `synthesize = true` als **opt-in** Sampling über das Client-Modell. Die sechs bestehenden Evidenz-Tools bleiben unverändert modellfrei; [ADR 0009](../docs/adr/0009-mcp-server-stdio-phase5.md) gilt für sie unverändert weiter.
>
> Die Async-Brücke (`anyio`) beschränkt sich auf die Servergrenze (Tool-Wrapper `to_thread`, Sampler `from_thread` in `mcp_server/sampling.py`); die Kernlogik bleibt synchron und offline testbar. **Nachweis:** ein **echter Sampling-Roundtrip** über den In-Memory-Client (Sampling-Callback als Modell-Attrappe, prüft Contract und Belege in der Anfrage), die sichtbare Degradation ohne Sampling-Fähigkeit sowie der reale CLI-Lauf (`--synthese` → „keine generierte Antwort" + vollständige Belege). **244 Tests grün**, Kernmodule ≥ 85 % (`synthesis`/`evidence`/`answer` 100 %). Nicht deterministisch ist ausschließlich der opt-in Synthese-Pfad – die Evidenz bleibt es immer.

2. **Echter Intra-Korpus-Zitationsgraph** – ohne Kuzu/GROBID. *Lücke:* Der Phase-3-Graph modelliert nur **Paper-Ähnlichkeit** (TF-IDF); der in der [README](../README.md) skizzierte Domain-/Zitationsgraph (`CITES`, `USES_METHOD`, …) fehlt, Multi-Hop-Zitationsfragen sind offline faktisch unbeantwortbar. *Akzeptanz:* eine deterministische, leichte Extraktion (Referenz-Sektion über die bestehende Heuristik + DOI-/arXiv-/Titel-Matching **gegen den eigenen Korpus**) erzeugt **additive** `CITES`-Kanten in `data/index/index.sqlite` (Graph-Teilschema versioniert); die Frage „welche Paper bauen auf X auf?“ ist über ein read-only Skript/Tool belegbar; die Kanten-Precision wird stichprobenhaft geprüft. (GROBID/externe Referenzen bleiben Zielbild, Gruppe B.)

> **Status:** ✅ umgesetzt ([ADR 0011](../docs/adr/0011-intra-corpus-citation-graph-phase7.md)): `indexing/citation_graph.py` erzeugt aus dem Referenzabschnitt (Phase-2-Heuristik) deterministische, gerichtete **`CITES`**-Kanten gegen den eigenen Korpus (Präzedenz **DOI > arXiv > Titel**, Selbstzitate ausgeschlossen) und persistiert sie **additiv** als `citation_edges` (Teilschema **0.1.0**) – gebaut im **selben atomaren Swap** wie Index und Ähnlichkeitsgraph. Belegbar über `python -m scripts.citations <paper_id>` und das MCP-Tool **`get_citations`** (`retrieval/citations.py` reichert um `source_uri` + Leit-Snippet und das Match-Kriterium an); `python -m scripts.status` und der `IngestReport` weisen die Kennzahlen aus. **Präzisions-Befund:** Ein erster Lauf ergab 192 Kanten, davon hingen **37 (19 %)** an Identifikatoren, die die Extraktion fälschlich aus dem Fließtext übernommen hatte (zitierte fremde IDs) – sie erzeugten einen falschen Zitations-Hub. Konsequenz: DOI/arXiv zählen nur noch, wenn sie im **Frontmatter** des Zielpapers belegt sind. Realer Korpuslauf danach: **158 Kanten** (98 arXiv, 58 Titel, 2 DOI) aus **143/145** Papern mit erkanntem Referenzabschnitt; die Stichprobe (14 Kanten über alle drei Methoden) war **14/14 korrekt**, die Top-Zitierten sind plausibel (GraphRAG „From Local to Global“ 19×, SWE-bench 13×). **200 Tests grün**, `citation_graph`/`retrieval/citations` 100 % Zeilenabdeckung. Zitationskontexte, externe Referenzen und Multi-Hop-Cypher bleiben Gruppe B.

3. **Chunking-Verfeinerung gegen die `short_chunk`-Flut.** *Lücke:* **2894 von 3074** Qualitätsflags sind `short_chunk` (harte Seiten-Chunk-Grenze, [ADR 0006](../docs/adr/0006-canonical-model-phase2-scope.md)); das verwässert Provenienz-Signal und Report-Aussagekraft. *Akzeptanz:* seitenübergreifendes Zusammenführen kurzer Rest-Chunks **mit erhaltener Seiten-Provenienz-Range** oder aggregierte statt per-Chunk-Flags; Canonical-/Index-Schema additiv/versioniert; Re-Ingest bleibt **deterministisch**; der `short_chunk`-Anteil sinkt messbar; Retrieval-Contract stabil.

> **Status:** ✅ umgesetzt ([ADR 0013](../docs/adr/0013-chunking-refinement-phase7.md)) – **mit korrigierter Ursachenannahme.** Eine Messung am realen Korpus widerlegte die oben unterstellte Ursache: Nur **12,2 %** der `short_chunk`-Fälle hingen am Seitenschnitt, **85,4 %** entstanden an einem *Abschnittswechsel* – die eigentliche Wurzel war die **übersegmentierende Überschriften-Heuristik** (9367 Sections auf 145 Papern, Median 50, Maximum 652; als „Überschrift" gelesene Pseudocode-Zeilen, Tabellenzellen und Silbentrennungsreste). Umgesetzt wurde deshalb die Ursache statt des Symptoms: **Reject-Regeln** in `detect_heading` (Mathematik-/Pseudocode-Symbole, tabellarische Zeilen, ziffernlastige Zellen – *nach* dem Schlüsselwort-Zweig, damit `Abstract`/`References` nie verworfen werden) plus eine evidenzbasierte **Section-Absorption** (inhaltsarme Abschnitte gehen an ihren Vorgänger; `front`/`abstract`/`references` bleiben geschützt, und es wird nie **in** einen Referenzabschnitt hinein absorbiert).
>
> Zweiter Befund: **2779** Seitenumbrüche lagen innerhalb einer Section, **79,6 % davon mitten im Satz**. Die Seite ist ein Layout-Artefakt und **kein Segmentierungskriterium** mehr, sondern eine **Provenienz-Range** – `page_number` bleibt die Startseite (Contract rückwärtskompatibel), `page_end` kommt additiv hinzu (Canonical **0.3.0**, Index **0.4.0**, `Citation` mit 8 Feldern). Der Frontmatter-Guard des Zitationsgraphen prüft entsprechend **strenger** (`page_end <= 2`). Zu kurze Chunks werden als aggregiertes `short_chunks:<n>` je Paper geführt; `long_chunk` bleibt pro Chunk.
>
> **Realer Korpuslauf (145 Paper):** Chunks **14 397 → 11 339** (−21,2 %), `short_chunk`-Anteil **20,1 % → 3,7 %**, Chunk-Median **840 → 1245** Zeichen, Sections **9367 → 4406** (Median/Paper 50 → 27, Maximum 652 → 85), Qualitäts-Flags **3074 → 320** (geflaggte Paper 145 → 136). Mehrseitig sind **862 Chunks (7,6 %)**, maximale Spanne 4 Seiten. **Nachweis der Seiten-Wirkung:** von 1963 Chunk-Grenzen, die auf einen Seitenwechsel fallen, sind **1963 durch `MAX_CHARS` erzwungen – keine einzige ist seitenbedingt**. Der Zitationsgraph profitiert unerwartet: der Referenzabschnitt wird nicht mehr von Pseudo-Überschriften abgeschnitten, daher **158 → 256 `CITES`-Kanten** (arXiv 149, Titel 104, DOI 3) bei unverändert **143/145** erkannten Referenzabschnitten; alle **256/256** Kanten sind mechanisch im Referenztext der Quelle belegt, die Kontext-Stichprobe war **12/12** korrekt und die Top-Zitierten bleiben plausibel. **Determinismus:** erneute Extraktion **145/145** textidentisch, Rebuild von Index, Ähnlichkeitsgraph und Zitationskanten byte-identisch. **258 Tests grün**, Kernmodule ≥ 85 %, `python -m scripts.qa` weiterhin **10/10** mit belegter Provenienz.
>
> **Abweichung vom Zielkriterium (transparent):** Der angestrebte Sections-Median von ≤ 25 wird mit **27** knapp verfehlt (Mittelwert 64,6 → 30,4, Maximum 652 → 85). Verbleibende verrauschte Abschnittstitel und Community-Keywords sind bewusst **A5** zugeordnet.

4. **Hybrid-Retrieval (BM25 + TF-IDF), offline handimplementiert.** *Lücke:* Reine Kosinus-TF-IDF ist bei **exakten Fakten** (DOI, Metriken, Abkürzungen) schwächer; ein Fremd-Wheel ist nicht nötig, BM25 ist über die vorhandenen SQLite-Token deterministisch nachbaubar. *Akzeptanz:* deterministische BM25-Wertung + transparente, rangbasierte Score-Fusion mit TF-IDF; Basic/Local profitieren nachweislich bei Fakt-/Abkürzungsfragen (Stichprobe aus [eval/pruef-fragen.md](../eval/pruef-fragen.md)); bestehende Modi-Contracts bleiben rückwärtskompatibel.

> **Status:** ✅ umgesetzt ([ADR 0014](../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)): Über **einer** Tokenisierung (`CountVectorizer`) stehen jetzt zwei Wertungen – der bisherige TF-IDF-Kosinus (via `TfidfTransformer`, **nachweislich identisch** zum früheren `TfidfVectorizer`) und ein handimplementiertes **BM25** (`indexing/bm25.py`, `k1 = 1.5`, `b = 0.75`, stets positive Lucene-IDF). Verbunden werden sie per **Reciprocal Rank Fusion** (`indexing/fusion.py`, `K = 60`), die seit A4 der **Default** aller Chunk-Modi ist (Basic, Local-Seed, Local-Fan-out, DRIFT); `neighbors_of_chunk`, das Global-Community-Ranking, der Paper-Graph und das Zitations-Matching bleiben bewusst unberührt. `score` ist damit ein **Fusionswert statt einer Ähnlichkeit**; transparent gemacht wird das durch die additiven Felder `score_tfidf`/`score_bm25` (`Citation` 8 → 10 Schlüssel – reines **Laufzeit**-Schema, Index-Schema bleibt `0.4.0`, **kein Re-Ingest**). Umschaltbar per `--scoring hybrid|tfidf|bm25`; die MCP-Tools bekommen bewusst keinen Schalter.
>
> **Nachweis – und eine korrigierte Annahme.** Vor der ersten Code-Zeile entstand ein Messapparat: ein Gold-Set mit **mechanisch aus dem Chunk-Text abgeleiteten** Labels ([eval/retrieval-gold.json](../eval/retrieval-gold.json)) und der Harness [scripts/eval_retrieval.py](../scripts/eval_retrieval.py) (Hit@k/MRR, `--verify-labels`). Am realen Korpus (34 Fragen, 145 Paper, 11 339 Chunks) steigt **Hit@5 von 0,735 auf 0,882** und bei **Fakt-Fragen von 0,773 auf 0,955** (MRR 0,596 → 0,680); fünf zuvor unbeantwortete Fakt-Fragen sind es jetzt. **Nicht bestätigt** hat sich dagegen die Annahme, die Fusion sei dem Einzelverfahren überlegen: **`bm25` allein liegt aggregiert vor `hybrid`** (MRR@5 0,691 vs. 0,641) – auf dem Entwicklungsset deutlich, auf einem eigens ergänzten **unabhängigen Validierungsset kehrte sich der Vorsprung jedoch um**. Der Unterschied ist damit nicht belastbar; belastbar ist nur, dass **beide** die TF-IDF-Baseline klar schlagen. Der Default bleibt `hybrid`, weil er als Einziger in **keiner** Fragenklasse einbricht (`bm25` fällt bei konzeptuellen Fragen auf MRR 0,567, `tfidf` bei Paraphrasen auf 0,333) – ein Nachziehen von `K` oder Fusionsgewichten wäre Tuning auf 34 Fragen und wurde bewusst unterlassen. **Kosten:** +3,6 % Aufbauzeit (1845 → 1911 ms), BM25-Matrix mit gleicher Besetzung (~13 MB). **291 Tests grün** (+33), Determinismus bestätigt. Gold-Set und Harness sind ein **Teil-Vorgriff auf A6**.
5. **Rausch-Reduktion bei Keywords & Section-Provenienz.** *Lücke:* Community-Keywords enthalten Rauschen (et/al/arxiv/Jahreszahlen/OCR-Ligaturen wie `uni00000013`); die Section-Heuristik übersegmentiert (bis **652** Sections auf einzelnen Papern, [ADR 0006](../docs/adr/0006-canonical-model-phase2-scope.md)). **Teilweise erledigt:** Die Übersegmentierung wurde in **A3** adressiert (Reject-Regeln + Section-Absorption, Maximum 652 → 85, [ADR 0013](../docs/adr/0013-chunking-refinement-phase7.md)); offen bleiben die **Keyword-Bereinigung** und die verbleibenden verrauschten Abschnittstitel. *Akzeptanz:* kuratierte Domänen-Stopwords + Token-Filter (rein numerische Token/Ligatur-Artefakte); eine Vorher/Nachher-Stichprobe zeigt sauberere Keywords/Abschnitte; deterministisch; Schema additiv versioniert, falls nötig.

> **Status:** ✅ umgesetzt ([ADR 0015](../docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)) – **mit zwei gemessenen Präzisierungen der Roadmap-Annahme.** Erstens sitzt das Keyword-Rauschen nicht im Vektorraum, sondern in der **Auswahlpolitik**: `et`/`al`/`arxiv` stehen in 139–143 von 145 Papern, ihre IDF ist damit ≈ 0 und für die Ähnlichkeit bedeutungslos – erst die Summenbildung über eine Community hebt sie in die Top-10. Der Filter greift deshalb als **Nachfilter vor dem Anschnitt** (verdrängte Slots werden aufgefüllt) in einem gemeinsamen Modul `keywords.py` für Community-Keywords **und** Übersicht-Entwürfe; das Retrieval bleibt bewusst stopword-frei, damit Fakt-Anfragen nach Jahreszahlen oder DOIs weiter treffen. Zweitens sind die „Ligatur-Artefakte" **zwei** Phänomene: `/uniXXXXXXXX` sind nicht dekodierbare Glyph-Indizes (1615 Vorkommen → **entfernen**), die typografischen Ligaturen `ﬁ ﬂ ﬀ ﬃ` dagegen tragen Inhalt (**3628** Zeichen in 533 Wörtern) und sind ein **Retrieval-Defekt**: `conﬁguration` war für die Anfrage `configuration` unauffindbar. Sie werden daher **repariert** statt gefiltert – über eine explizite Zeichen-Map, bewusst **kein** pauschales NFKC (das würde `𝑥 → x` abbilden und die Pseudocode-Reject-Regel aus A3 aushebeln).
>
> Für die Abschnittstitel kamen **fünf Zeilenregeln** hinzu – vier nach dem Schlüsselwort-Zweig (Satzpunkt-Ende, URL-/DOI-Marker, `et al`, JSON-/Code-Zeichen) und eine **davor**, die kleingeschriebene Fließtextreste wie `methods.` abweist (sie würden sonst als bekannter Abschnitt gelesen und zogen bis zu 6166 Zeichen fremden Text an sich) – plus eine **Kontextregel**: innerhalb der Bibliografie ist der Numerierungs-Zweig abgeschaltet, weil er die laufende Nummer eines Literatureintrags als Abschnittsnummer las. Eine sechste geplante Regel (Seitenbereiche `104–115`) wurde nach Simulation **verworfen** – 4 von 6 Treffern wären echte Überschriften gewesen.
>
> **Realer Korpus (voller Re-Ingest):** verrauschte Abschnittstitel **267 → 0** (distinct 2838 → 2455), Rausch-Anteil der Keyword-Slots **6,0 % → 0 %**, Ligaturen **3628 → 0**, Glyph-Artefakte **1615 → 0**, Sections **4406 → 3948** (Median 27 → **25**, womit der in [ADR 0013](../docs/adr/0013-chunking-refinement-phase7.md) offen gebliebene Zielwert erreicht ist), Chunks 11 339 → 11 181, Communities 43 → 44. **Nachweis über das Gold-Set** (Abbruchkriterium war ein Rückgang): Hit@5 bleibt **0,882**, MRR@5 steigt **0,641 → 0,650**, bei Fakt-Fragen **0,680 → 0,695**; die Ligatur-Reparatur macht u. a. `configuration` in 133 zusätzlichen Chunks auffindbar. **Unerwartet:** Eine als Überschrift gelesene Zeile landet **nicht** im Chunk-Text – verrauschte Titel kosteten also Retrieval-Treffer; zwei Gold-Labels ändern sich genau deshalb (Gold-Set **1.2.0**, `--verify-labels` 34/34). Der Zitationsgraph wächst **256 → 382** Kanten, **382/382** mechanisch im Referenztext belegt. Determinismus bestätigt (Extraktion 37/37 identisch, Rebuild von Index/Graph/Zitationen identisch). **319 Tests grün**, `scripts.qa` **10/10**. Offen dokumentiert: bei Papern ohne erkennbare Anhang-Überschrift zählt der Anhang jetzt zum Referenzabschnitt (genau **eine** zuvor erkannte Anhang-Überschrift geht verloren, ein Kapitälchen-Artefakt), und numerierte Fließtextreste ohne Rauschmerkmal bleiben als Titel bestehen.
6. **Quantitative, offline Retrieval-Evaluation.** *Lücke:* Die QS (`python -m scripts.qa`) ist **rein qualitativ** (10 feste Fragen, Provenienz-Sichtprüfung); ein reproduzierbares Maß für Retrieval-Güte/Regressionen fehlt. **Teilweise erledigt:** In **A4** entstanden bereits ein versioniertes Gold-Set ([eval/retrieval-gold.json](../eval/retrieval-gold.json), 34 Fragen mit mechanisch abgeleiteten, nachrechenbaren Labels) und ein Harness ([scripts/eval_retrieval.py](../scripts/eval_retrieval.py)) mit **Hit@k/MRR**; die Baseline ist in [ADR 0014](../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md) dokumentiert. *Offene Akzeptanz:* Ausweitung auf die **Modi als Ganzes** (Local-Fan-out, Community-Auswahl statt nur der geteilten Chunk-Primitive), inhaltlich statt nur lexikalisch abgeleitete Labels, breiteres Fragenset und die Integration als optionaler QS-Lauf.

> **Status:** ✅ umgesetzt, soweit ohne neue Label-Quellen möglich ([ADR 0016](../docs/adr/0016-quantitative-retrieval-evaluation-phase7.md)) – **zwei der vier offenen Punkte bleiben begründet zurückgestellt.** Die Evaluationslogik ist ein Paket (`src/research_graphrag/evaluation/`, fünf Module, 100 % Zeilenabdeckung); die CLI ist auf Argumentbehandlung zusammengeschrumpft, `python -m scripts.qa --quantitativ` ruft denselben Code. Gemessen werden jetzt die **Modi als Ganzes**: die Bündel-Reihenfolge jedes Modus gegen die Gold-Labels plus zwei Diagnosen, die **Auswahl- von Rankingfehlern trennen** (welcher Local-Baustein trug bei; enthält die gewählte Community überhaupt ein erwartetes Paper). Neu ist ein eingefrorenes Baseline-Artefakt ([eval/retrieval-baseline.json](../eval/retrieval-baseline.json)) mit **qid-genauem** Regressions-Check: `Treffer → kein Treffer` ist eine Regression (Exit 1), reine Rangbewegung nur ein Bericht, und ein **Fingerprint-Guard** lehnt den Vergleich ab (Exit 2), sobald der Korpus nicht mehr zur Baseline passt. Aggregat-Schwellen wurden bewusst verworfen – bei 34 Fragen entspricht eine Frage 2,9 Prozentpunkten Hit@5.
>
> **Erst messen, dann bauen – und die Messung hat sich selbst korrigiert.** Vor der ersten Code-Zeile lief eine Wegwerf-Messung über alle vier Modi. Sie zeigte, dass eine nackte Coverage-Kennzahl die **triviale** Strategie „gib die größten Communities zurück" zur Siegerin gekürt hätte (0,567 vs. 0,248 der echten Auswahl). Ausgewiesen wird deshalb nie Coverage allein, sondern immer zusammen mit der **Selektivität** und zwei Trivial-Baselines; das Vergleichsinstrument ist der **Lift** (Coverage ÷ Selektivität). Korrigiert wurde dabei die Vorabmessung selbst: Ihre zufällige Baseline stammte aus **einer** Ziehung (Lift 0,39) – über 100 Ziehungen gemittelt liegt sie bei **1,05**. Damit sitzen **beide** trivialen Strategien auf Zufallsniveau (≈ 1,0) und der Lift bekommt eine klare Ablesevorschrift; die echte Community-Auswahl erreicht **3,55**.
>
> **Realer Korpus (145 Paper, 11 181 Chunks, 44 Communities, Gold-Set 1.2.0):** `primitive` **0,882 / 0,650** (unverändert zu A5 – das Messgerät selbst hat sich nicht bewegt), `basic` **identisch** dazu (die Gleichheit ist als Contract-Test gesichert, statt sie als zweite Kennzahl zu pflegen), `local` **0,618 / 0,532**, `global` **0,353 / 0,269**, `drift` **0,235 / 0,235**. Drei Befunde wären ohne die Modus-Ebene unsichtbar geblieben: (1) **Local ist bei Fakt-Fragen schwächer als Basic** – kein Ranking-, sondern ein Strukturproblem, weil Nachbarschaft und Fan-out Ähnlichkeit *zum Seed* messen; der Fan-out rettet genau **1 von 34** Fragen. (2) **DRIFTs lokale Verfeinerung ist fehlerfrei** – Treffer (8) und erreichbare Deckelung (8) sind identisch, **alle** Fehlschläge entstehen davor (12× keine Community, 14× die falsche). (3) Die Beschränkung auf die Top-1-Community kostet DRIFT ein Drittel (Global erreicht mit fünf Communities 12 Fragen). Diese Befunde werden **belegt, nicht behoben** – sie sind Kandidaten für eigene Punkte. **Determinismus:** ein `--check` unmittelbar nach dem Einfrieren meldet über alle fünf Ebenen **keine einzige Abweichung**. **352 Tests grün**, kein Schema-Eingriff, **kein Re-Ingest**.
>
> **Bewusst zurückgestellt (transparent):** *inhaltlich abgeleitete Labels* und ein *breiteres Fragenset*. Die Roadmap forderte inhaltliche Labels „**statt**" der lexikalischen – das wurde abgelehnt: Die mechanische Regel ist über `--verify-labels` nachrechenbar und hat genau dadurch in A5 den Re-Ingest abgesichert; geurteilte Labels wären semantisch stärker, aber nicht mehr verifizierbar. Die Architektur weist deshalb die **Label-Quelle** aus, sodass weitere Quellen additiv danebentreten können. Der naheliegendste nächste Schritt ohne Subjektivität sind Multi-Hop-Fragen gegen den **Zitationsgraphen** aus [ADR 0011](../docs/adr/0011-intra-corpus-citation-graph-phase7.md) (382 `CITES`-Kanten; 44 Paper mit ≥ 3 zitierenden) – „welche Paper bauen auf X auf?" ist damit objektiv und nicht-lexikalisch labelbar. Mehr Fragen desselben lexikalisch verankerten Typs würden dagegen nur die statistische Stabilität erhöhen, nicht den Erkenntnisgewinn.

7. **Router-Härtung.** *Lücke:* Der Router ([ADR 0008](../docs/adr/0008-retrieval-and-query-router-phase4.md)) ist eine naive DE/EN-Substring-Heuristik ohne Konfidenz/Fallback; eine Fehlklassifikation führt **still** in den falschen Modus. *Akzeptanz:* konfidenz-/score-basierte Entscheidung mit definiertem Fallback (z. B. Basic bei Unsicherheit) und **erklärbarer** Begründung (welches Signal, warum); erweiterte Router-Tests inkl. Grenzfällen; Verhalten bleibt deterministisch.

> **Status:** ✅ umgesetzt ([ADR 0017](../docs/adr/0017-router-hardening-phase7.md)) – **mit zwei gemessenen Korrekturen der eigenen Erwartung.** Die Vorabmessung (Wegwerf-Skript, wie in A3–A6) zeigte erstens, dass **Signal-Konflikte praktisch nicht existieren**: Nur **1 von 44** realen Fragen trug Signale aus mehr als einem Modus, und die Präzedenz hat **nie** eine Signal-Mehrheit überstimmt – ein aufwändiges Score-Modell wäre Wegwerf-Mechanik gewesen. Zweitens saß der Schaden woanders: Das rohe Substring-Matching leitete **15 von 26** korpus-häufigen Teilwort-Trägern in einen fremden Modus (`different` → drift, `contextcite` → local), und **ein einzelnes** Signal (`which papers`) schickte **16 von 22** Fakt-Fragen des Gold-Sets nach `local` – also in den Modus, für den A6 **0,618** gegen basic **0,882** gemessen hatte.
>
> Umgesetzt sind daher: eine **je Signal deklarierte Match-Art** (Wortgrenze bzw. Wortanfang für Englisch, Teilwort **nur** für deutsche Stämme – dort ist die gemessene Fehlalarm-Fläche praktisch null; die einzige Ausnahme `metrik` in `Biometrika` fand die abschließende QA und ist als Wortform korrigiert), eine Lexikon-Revision entlang der Frage *„markiert der Term die Frageform oder nur einen Gegenstand?"* (`which papers` und der Singular `trend` entfallen, `corpus`/`korpus` zählen nur noch als Reichweiten-Formulierung, Beziehungs- und Cluster-Marker kommen hinzu), und eine Entscheidungsregel, in der `basic` **Rückfallebene statt gleichrangiger Kandidat** ist: Fakt-Signale bestätigen nur, Gleichstand fällt sichtbar auf `basic` zurück (Konfidenz `weak`, Konkurrenten benannt). Die **feste Präzedenz** aus [ADR 0008](../docs/adr/0008-retrieval-and-query-router-phase4.md) ist damit abgelöst (dort als Nachtrag vermerkt). Die Entscheidung wird ausgewiesen statt still getroffen: `RouteDecision` trägt **Konfidenzstufe und auslösende Signale**, `python -m scripts.ask` zeigt sie, und `answer_question` liefert sie **additiv** als `routing` (nur bei `mode = "auto"`, sonst `null`).
>
> **Messbar** wird der Router durch ein **Router-Gold-Set** ([eval/router-gold.json](../eval/router-gold.json), 84 Fragen, DE + EN) mit einer Label-Regel ohne Urteil: Die zulässigen Modi werden aus dem Fragetyp über die README-Tabelle abgeleitet und sind so nachrechenbar wie die mechanischen Labels aus [ADR 0016](../docs/adr/0016-quantitative-retrieval-evaluation-phase7.md); zusätzlich prüft die Messung, dass **jedes** Signal von mindestens einer Frage berührt wird (vorher: 9 von 51). Ausgewertet über `python -m scripts.eval_retrieval --router`. Bewusst **kein** Baseline-Artefakt: Der Router ist korpus-unabhängig, die Regression ist deshalb ein deterministischer Test statt einer eingefrorenen Datei.
>
> **Ergebnis am realen Korpus:** Contract-Treue der Prüf-Fragen **6/10 → 10/10**, Router-Gold-Set **83/84 (0,988)**, Signal-Abdeckung **69/69**, sachlich falsche Fehlleitungen **15 → 0**. Das **Veto** (Gold-Set end-to-end über `mode = auto`) steigt von **Hit@5 0,765 / MRR 0,618** auf **0,882 / 0,650**, bei Fakt-Fragen von **0,773** auf **0,955**. Ehrlich dazu: Der neue Router schickt alle 34 Gold-Fragen nach `basic` (korrekt – es sind Fakt-Fragen ohne strukturellen Marker), weshalb das Veto dort **nur Nicht-Verschlechterung** belegen kann; unterscheidbar ist gutes Routing allein auf dem Router-Gold-Set. Der einzige Fehlgriff (R83) ist ein **absichtlich konstruierter Gleichstand** und als bekannte Grenze eingefroren. **404 Tests grün** (+52), kein Schema-Eingriff, **kein Re-Ingest**.
8. **Betriebs-Ausbaustufen (kleiner, optional).** *Lücke:* Voller Re-Index ist bei ~145 Papern günstig, wird bei wachsendem Bestand aber teurer; der Drop-in-Kreislauf ist noch manuell. *Akzeptanz:* (a) **inkrementelles Update** – nur neue/geänderte Paper extrahieren/indizieren, dann den Graphen neu bauen; das Ergebnis ist **nachweislich identisch** zum vollen Re-Index (Determinismus-Vergleich); voller Re-Index bleibt Standard. (b) **Auto-Watcher** für `papers/` als optionaler Komfort; der manuelle Anstoß bleibt möglich.

**Gruppe B – Zielbild (Option C, beschaffungsabhängig).** Diese Punkte bleiben das **Zielbild** und werden erst umgesetzt, wenn die nötigen Wheels/Modelle/Runtimes offline verfügbar werden ([ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md)); sie sind aktuell **empirisch nicht beschaffbar**.

- **Domain-/Zitationsgraph mit Kuzu (embedded) + Text2Cypher** für deterministische Cypher-Graphfragen und Multi-Hop-Netze (baut auf A2 auf).
- **GROBID** für präzises Parsing **externer** Referenzen/Zitationskontexte (benötigt Docker/Java).
- **Microsoft GraphRAG / Docling / LanceDB** als vollwertiges Zielbild (LLM-gestützte Entitäts-/Community-Reports, Bounding-Box-Provenienz).
- **Hybrid-Suche mit dedizierten Vektor-/Suchmaschinen** und **Skalierung Richtung Qdrant/Weaviate/Neo4j**, falls der Bestand deutlich über die ~500-Paper-Auslegung hinauswächst.

---

### Phase 8 – Korpus-Zufluss: `new_papers/` + Intake
**Ziel:** Ein einziger Befehl übernimmt neue PDFs aus einem Eingangsordner in den Korpus, verhindert dabei **Doppelbestand**, stößt die vollständige Pipeline an und pflegt die Literaturübersicht nach.

> **Status: umgesetzt** ([ADR 0019](../docs/adr/0019-corpus-intake-new-papers-phase8.md)) – mit
> **einer begründeten Abweichung** von der Vorgabe unten. Die Vorabmessung hat das Kriterium der
> Stufe 2 widerlegt: Im eigenen Korpus würden **17 von 155** Identifikatoren fehlleiten – der
> unausgefüllte ACM-Vorlagen-Platzhalter `10.1145/nnnnnnn.nnnnnnn` steht bei **drei** Papern, und
> **14** Werte stammen aus dem Volltext-Fallback der Extraktion und zeigen auf ein *zitiertes*
> fremdes Paper (darunter der Falsch-Hub aus [ADR 0011](../docs/adr/0011-intra-corpus-citation-graph-phase7.md)).
> Ein Intake, der darauf hin löscht, vernichtet unter realistischen Bedingungen legitime Dateien.
>
> Umgesetzt ist daher eine **abgestufte** Konsequenz: Stufe 1 (sha256) löscht wie geplant – dort
> ist bitgenau bewiesen, dass die Datei bereits im Korpus liegt. Stufe 2 verschiebt nach
> `new_papers/_duplikate/` (hartes Löschen nur per `--delete-identifier-duplicates`) und
> vergleicht nur noch **gehärtete** Schlüssel: belegt auf der eigenen Titelseite (Guard aus
> ADR 0011) **und** im Korpus eindeutig – von 155 Identifikatoren überleben **138**. Stufe 3
> (Schwelle **0,85**, am Korpus **ohne** Fehlalarm) bleibt folgenlos und erkennt **22 von 25**
> künstlich umbenannten Realpapern, keines davon falsch zugeordnet.
>
> Ebenfalls umgesetzt: das **Robustheits-Gate** (`no_chunks`-Flag – schließt die bekannte Grenze
> aus [ADR 0013](../docs/adr/0013-chunking-refinement-phase7.md) – plus `%PDF-`-Signaturprüfung), die
> **Übersicht als einzige Senke** (append-only, byte-erhaltend, atomar, ID-Reihe `Z1`, `Z2`, …;
> löst eine Phase-2-Festlegung ab) und ein append-only **Protokoll** `data/intake_log.md` mit Hash
> je gelöschter Datei. Der Nachweis erfolgte end-to-end an einer **vollständigen Kopie** des
> 145-Paper-Korpus: alle fünf Wege einmal durchlaufen, `--dry-run` nachweislich wirkungslos
> (Hash-Abbild identisch), kuratierte Zeilen byte-identisch, zweiter Lauf idempotent. **436 Tests**
> grün, kein Schema-Eingriff, **kein Re-Ingest**.

**Warum das nötig war:** Der bestehende Drop-in-Workflow (PDF nach `papers/` legen, `python -m scripts.ingest`) deduplizierte über `data/manifest.json` nur **Dateiname → sha256**. Ein inhaltsgleiches PDF unter anderem Dateinamen wurde als neues Paper indiziert: eigene `paper_id`, doppelte Belege in jeder Antwort, zweite Übersicht-Zeile. Sobald PDFs aus dem Netz mit fremd vergebenen Dateinamen kamen, wurde das zum Regelfall.

**Drei Prüfstufen mit fallender Sicherheit:**

| Stufe | Kriterium | Grundlage | Konsequenz |
| --- | --- | --- | --- |
| 1 | **sha256** identisch | `data/manifest.json` | sicheres Duplikat → **löschen** |
| 2 | **DOI oder arXiv-ID** identisch | `extract_identifiers` gegen `papers.identifiers` im Index | **abweichend umgesetzt:** Quarantäne `new_papers/_duplikate/`, hartes Löschen nur per Flag |
| 3 | **Titel-Ähnlichkeit** (≥ 0,85) | normalisierter Titel/Dateiname-Stamm | **unsicher** → keine Löschung, Befund im Bericht |

**Kein Treffer** → Datei wird nach `papers/` verschoben. **Namenskollision mit abweichendem Hash** → Datei bleibt liegen, erscheint als Befund.

**Zwei bewusste Härten:** (1) `--dry-run` ist Pflichtbestandteil – Löschen ist endgültig. (2) Eine neuere arXiv-Version zählt als Duplikat – **wer ersetzen will, löscht zuerst die alte Datei in `papers/`**.

**Übersicht-Pflege:** Der Intake hängt Entwurfszeilen append-only direkt an [`../Übersicht.md`](../Übersicht.md) (ID-Reihe `Z1`, `Z2`, …; wertende Spalten `(manuell)`; idempotent). Löst die Phase-2-Festlegung (`data/overview_drafts.md`) ab.

**Robustheits-Gate:** `no_chunks`-Flag für Dokumente ohne Fließtext (Scans, HTML-Fehlerseiten) sichtbar im Intake-Bericht – Datei wird übernommen, Befund aber ausgewiesen.

**DoD:** PDF nach `new_papers/` legen → **ein** Befehl → Duplikate entfernt, neue Paper in `papers/`, Index/Graph/Zitationskanten aktualisiert, Übersicht erweitert, Bericht vollständig; `--dry-run` nachweislich wirkungslos; kuratierte Zeilen byte-identisch.

---

### Phase 12 – Zitierfähigkeit: vom Identifikator zur Literaturangabe

> **Status: umgesetzt.** Beide Punkte sind erledigt – **K1** (netzfrei) und **K2** (Auflösung).
> Belegt am realen Korpus (341 Paper): **vollständig zitierfähig 0 → 336**, Paper mit
> Identifikator 329 → **339**, und die kuratierte Übersicht steuert erstmals maschinell
> **265 Feldwerte** bei (131 Titel, 91 arXiv-IDs, 35 DOIs, 8 Links), die zuvor ungenutzt in einer
> Markdown-Tabelle lagen ([ADR 0025](../docs/adr/0025-citable-paper-metadata.md) ·
> [ADR 0026](../docs/adr/0026-online-metadata-resolution.md)).

**Warum das nötig war:** Bis Phase 11 lieferte **eines von acht** Werkzeugen (`get_paper`) überhaupt einen extern auflösbaren Identifikator. Alle Suchtreffer und Belege in `answer_question` trugen ausschließlich eine interne `paper_id` und einen lokalen Dateipfad. Der Zitier-Contract aus [ADR 0012](../docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md) verlangte Marken `[1]`, `[2]` …, die auf nichts Zitierbares zeigten.

Vorabmessung (341 Paper):

| Befund | Wert |
| --- | --- |
| Paper mit mind. einem extrahierten Identifikator | 329 (96,5 %) |
| davon **nicht** auf der eigenen Titelseite belegt | ≈ 45 |
| Identifikatoren mit mehr als einem Träger | 9 (u. a. ACM-Platzhalter, MBPP-Falsch-Hub) |
| kuratierte Übersichtszeilen mit externer Angabe | 129 von 131 |
| davon **abweichend** von der Extraktion | **29** |

#### K1 – Zitierfähige Metadaten, netzfrei

*Umgesetzt:* eigene **versionierte** Quelle `metadata/paper_metadata.json` (außerhalb des regenerierbaren `data/`), **feldweise** Auflösung nach `manual > curated > resolved > extracted` mit ausgewiesener Herkunft je Feld, additive Index-Tabelle `paper_metadata`, Durchreichung von `identifiers` und `citation_key` bis in jeden Beleg, vollständige Literaturangaben (Harvard und APA) in `answer_question`, `get_paper`, dem neunten Werkzeug `get_reference` und `python -m scripts.cite`.

*Bewusst nicht:* die vollständige Angabe in **jedem** Chunk-Zitat (fünf Belege desselben Papers trügen sie fünfmal) und ein Zugriffsdatum in der Literaturangabe (es wäre vom Ausführungstag abhängig und bräche jeden Byte-Vergleich).

#### K2 – Online-Auflösung der fehlenden Felder

*Umgesetzt:* `python -m scripts.resolve_metadata` löst Autoren, Venue und Publikationsjahrgang über OpenAlex auf (Rückfall: arXiv-Feed), **automatisch** übernommen, aber mit ausgewiesener Belegstärke: Identifikator-Treffer `strong`, nicht belegter Identifikator oder Titel-Ähnlichkeit `weak`, unterhalb der Schwelle verworfen. Protokoll append-only in `data/metadata_log.md`.

*Bewusst nicht:* eine Auflösung **im Ingest** – der Kern bleibt netzfrei und deterministisch – und **kein** MCP-Werkzeug, weil der Lauf schreibt und Netz benötigt.

#### Ergebnis am realen Korpus

| Kennzahl | vorher | nachher |
| --- | --- | --- |
| vollständig zitierfähige Paper | 0 | **336** von 341 |
| Paper mit Identifikator | 329 | **339** |
| schwach belegte Datensätze | – | 66 (ausgewiesen) |
| Werkzeuge mit Identifikator in der Antwort | 1 von 8 | **9 von 9** |

Offen bleiben **5** Paper, für die keine Quelle einen Treffer liefert; sie sind über einen `manual`-Eintrag zu pflegen.

---

### Phase 11 – Betrieb, Robustheit & Datensicherheit

> **Status: aufgelöst am 2026-08-28.** Von den sechs Punkten sind **B1** und **B5** umgesetzt,
> **B4** bewusst gestrichen und **B6** geprüft und verworfen – diese vier stehen unverändert
> unten. Die beiden **offenen** Punkte **B2** (inkrementelles Update) und **B3** (Messung ohne
> Wartezeit) sind in die Phase 15 (Skalierung) der aktiven [Roadmap](../Roadmap.md) übergegangen,
> weil sie dort keine Kür mehr sind, sondern an einer bezifferten Wachstumsgrenze hängen. Die
> Phase existiert damit nicht mehr als eigener Abschnitt des aktiven Plans.

#### B1 – Sicherung des Korpus

*Lücke:* `papers/` und `data/` sind **nicht versioniert**. Der gesamte Bestand hängt damit an einem Ordner auf einer Maschine – während der Index jederzeit aus den PDFs reproduzierbar wäre. Phase 8 verschärft das gleich doppelt: Der Intake **löscht** Dateien unwiderruflich, und Phase 9 fügt automatisiert neue hinzu.

*Akzeptanz:* ein dokumentierter, einfacher Sicherungsweg – gesichert werden müssen nur `papers/`, [`Übersicht.md`](../Übersicht.md) und `data/manifest.json`; alles Übrige ist rekonstruierbar. Dazu ein `--dry-run` überall dort, wo gelöscht wird. Bewusst **kein** eigenes Backup-Framework – das wäre für ein persönliches Werkzeug überzogen.

> **Status: umgesetzt** (2026-08-06, [ADR 0027](../docs/adr/0027-corpus-backup-phase11.md)). Neu sind `backup.py` (Top-Level) und das dünne `scripts/backup.py` mit `--dry-run`, `--pruefen` und einem Fortschrittsbalken.
>
> **Der Umfang wurde gegenüber dieser Akzeptanz präzisiert**, weil sie aus der Zeit vor Phase 9 und Phase 12 stammt: Neben `papers/`, [`Übersicht.md`](../Übersicht.md) und `data/manifest.json` sind auch `metadata/paper_metadata.json` (Herkunft `manual` ist aus **keiner** Quelle reproduzierbar) sowie die drei append-only Protokolle `data/intake_log.md`, `data/metadata_log.md` und `data/online_candidates.md` nicht rekonstruierbar. **Nicht** gesichert werden `data/canonical/`, `data/index/` und die Qualitätsberichte – und zwar aus **Korrektheits-, nicht aus Platzgründen**: Sie machen nur 8,7 % aus (68,7 MB von 788 MB), ein mitgesicherter Index verleitet aber dazu, ihn zurückzuspielen, obwohl er zum wiederhergestellten Korpus nicht passen muss. Der Weg zurück ist deshalb genau einer: zurückkopieren, dann `python -m scripts.ingest`.
>
> **Die zweite Hälfte der Akzeptanz war bereits erfüllt** – belegt statt gebaut: Ein Scan aller löschenden Aufrufe unter `src/research_graphrag/` ergab genau vier Stellen mit Nutzerwirkung, alle vier in `intake.py`, und `scripts.intake` besitzt `--dry-run` seit Phase 8. Die übrigen Treffer sind Temporärdateien atomarer Schreibvorgänge und das Verwerfen **abgeleiteter** Artefakte.
>
> **Realer Nachweis** (341 Paper): Vorschau und Lauf treffen dieselben Entscheidungen für **348 Dateien / 680,9 MiB**; der zweite Lauf kopiert **0** und ist nach 15 s fertig (Idempotenz über sha256); `--pruefen` bestätigt 348/348 mit Exit `0`, nach einer gezielten Manipulation meldet es die Datei namentlich mit Exit `1`. Der Sicherungsstand enthält nachweislich **kein** `canonical/` und **kein** `index/`. Kein Schema-Eingriff, kein Contract, kein neues MCP-Werkzeug (der Server bleibt bei **neun**).
>
> *Nachtrag Phase 13 / R1:* `new_papers/referenzen.txt` und `data/references_log.md` sind in den Sicherungsumfang aufgenommen.

#### B4 – Auto-Watcher: bewusst gestrichen

Der frühere Punkt A8b entfällt. `watchdog` ist offline **vorhanden** – technisch scheitert es also nicht. Die Entscheidung ist fachlich: Der Intake **löscht Dateien** und verändert den Korpus; beides soll beobachtet und angestoßen werden, nicht im Hintergrund passieren. Ein Watcher würde die einzige Stelle automatisieren, an der ein Mensch hinsehen soll.

#### B5 – Messgrundlage nachführbar halten

*Lücke (2026-08-06 aufgefallen, nachträglich aufgenommen):* Die Gold-Sets und Baselines waren auf den Stand von **145** Papern eingefroren, der Korpus ist auf **341** gewachsen. `--verify-labels` reproduzierte nur noch **1 von 34** Fragen, beide `--check`-Läufe verweigerten den Vergleich mit Exit `2`. Der Fingerprint-Guard hat damit korrekt gearbeitet – der quantitative Regressionsschutz war trotzdem faktisch außer Betrieb. Ursache war eine Werkzeuglücke: Für das Multi-Hop-Gold gab es einen reproduzierbaren Neuableitungs-Weg (`--zitationen --write-gold`), für das **Retrieval**-Gold nicht.

*Akzeptanz:* Ein Befehl leitet die mechanischen Labels aus dem aktuellen Index neu ab, ohne die Fragen anzufassen; das Ergebnis ist über `--verify-labels` vollständig nachrechenbar, und eine Frage ohne Ziel wird als Befund gemeldet statt still geschrieben.

> **Status: umgesetzt** (2026-08-06, Nachtrag in [ADR 0016](../docs/adr/0016-quantitative-retrieval-evaluation-phase7.md)). Neu sind `relabel_gold_set`, `unlabelled_questions` und `save_gold_set` im Paket `evaluation` sowie `python -m scripts.eval_retrieval --write-gold` (mit `--gold-version` und `--notiz`).
>
> **Warum ein Gold-Set einen Korpuswechsel nicht überlebt:** Die Labels sind Paper-IDs, und eine `paper_id` ist der sha256-Hash der Datei. Ein durch eine neuere Fassung **ersetztes** PDF bekommt eine neue ID – das eingefrorene Label zeigt danach ins Leere, unabhängig davon, ob der Inhalt noch im Korpus steht. Genau das erklärt die 6 weggefallenen Alt-Ziele restlos: Sie gehören zu **4 Papern, die nicht mehr im Bestand sind**.
>
> **Gemessene Drift vor der Neuableitung:** 32 der 34 Fragen gewinnen Ziele hinzu, 2 bleiben gleich, keine verliert unterm Strich. Die Zielmenge wächst von **141 auf 355** (Faktor 2,52) bei einem Korpus-Faktor von 2,35 – die Label-Regel skaliert also proportional. Die breiteste Frage deckt **7,9 %** des Korpus ab, eine zufällige Fünferauswahl erreicht Hit@5 = **0,146**: Die Trennschärfe bleibt erhalten. Keine Frage steht ohne Ziel da.
>
> **Neuer Stand** (Gold-Set **1.3.0**, Fragen wortgleich, **34/34** Labels reproduzierbar; Multi-Hop-Gold **44 → 113** Anker, 113/113 geprüft): primitive/basic/local **0,824 / 0,736**, global **0,559 / 0,412**, drift **0,588 / 0,472**; Community-Auswahl Lift **5,80** gegen größte-5 1,04 und zufällig-5 0,94. Multi-Hop: graph **0,593 / 0,452**, basic_title **0,673 / 0,634**, local_title **0,858 / 0,768**, basic_topic **0,142 / 0,133**, local_topic **0,628 / 0,464**; strukturelle Auswahl Lift **15,09** gegen 1,03. Beide Baselines sind neu eingefroren, beide `--check`-Läufe melden 0 Abweichungen.
>
> **Ehrlich dazu:** Diese Zahlen sind mit den alten **nicht** vergleichbar – Korpus *und* Labels haben sich geändert. Belastbar ist allein das Verhältnis der Ebenen innerhalb eines Laufs. Global hat deutlich zugelegt (Lift 3,55 → 5,80), und auf dem fakt-orientierten Set liefert **Local exakt dasselbe wie Basic** – alle 28 Treffer aus den Seeds, null Beitrag von Nachbarschaft und Fan-out.
>
> **Der naheliegende Schluss daraus wäre falsch** und wurde durch die Multi-Hop-Messung desselben Korpus widerlegt: Dort steuert der Fan-out **44 von 71** Treffern der Themen-Anfrage bei, und die strukturelle Auswahl über den Ähnlichkeitsgraphen erreicht **Lift 15,09** (vorher 8,20) – der Graph ist also **besser** geworden, nicht schlechter. Damit bestätigt sich erneut, was schon [ADR 0023](../docs/adr/0023-multihop-citation-evaluation-phase10.md) festgehalten hat: „Der Fan-out trägt kaum bei" ist eine Eigenschaft des **fakt-orientierten Gold-Sets**, dessen Labels mechanisch aus dem Chunk-Text stammen und deshalb die direkte Chunk-Suche strukturell bevorzugen. Die korrekte Aussage lautet: *Auf lexikalisch verankerten Faktfragen ist Local nicht besser als Basic.*

#### B6 – Grad des Ähnlichkeitsgraphen (geprüft, verworfen)

*Lücke (2026-08-06 aufgefallen, nachträglich aufgenommen):* Der Ähnlichkeitsgraph verbindet jedes Paper über *mutual top-k* mit höchstens `DEFAULT_K = 8` Nachbarn – ein Wert aus der Zeit mit 145 Papern. Bei 341 Papern haben **85 Paper (24,9 %) keinen einzigen Nachbarn** und damit keinen Fan-out.

*Akzeptanz (vorab fixiert):* Das kleinste k, das (1) auf **beiden** Gold-Sets keine Kennzahl verschlechtert, (2) die isolierten Paper mindestens halbiert und (3) die größte Community unter 20 % des Korpus hält. Erfüllt kein Kandidat alle drei, wird der Punkt verworfen und der Befund dokumentiert.

> **Status: geprüft und verworfen** (2026-08-06, [ADR 0028](../docs/adr/0028-similarity-graph-degree-phase11.md)). **Keine Code-Änderung**, kein Schema-Eingriff, kein Re-Ingest, keine neue Baseline.
>
> **Die Ursache ist nicht die Schwelle:** 339 von 341 Papern (**99,4 %**) haben einen Nachbarn ≥ 0,10, der Median der besten Ähnlichkeit liegt bei **0,372**. Eine Schwellenänderung von 0,04 auf 0,15 bewegt die Kantenzahl nur von 442 auf 426. Isolation entsteht **allein** durch die Verdrängung im mutual top-k. Damit ist die Schwelle als Stellschraube erledigt.
>
> **Gemessen wurde gegen Index-Kopien** (der Live-Index blieb unberührt), nachdem die Rekonstruktion mit `k = 8` den Live-Stand exakt reproduziert hatte (439 Kanten / 115 Communities / 85 Singletons):
>
> | Ebene | k = 8 | k = 16 | k = 20 |
> | --- | --- | --- | --- |
> | basic / local | 0,824 / 0,736 | 0,824 / 0,736 | 0,824 / 0,736 |
> | global | **0,559** / 0,412 | 0,529 / 0,476 | 0,529 / 0,462 |
> | drift | 0,588 / 0,472 | 0,706 / 0,604 | 0,706 / 0,633 |
> | **Lift der Community-Auswahl** | **5,80** | 3,29 | **2,96** |
> | `no_community` · `fallback` | 2 · 2 | 8 · 8 | 9 · 9 |
>
> **Bedingung 1 ist bei beiden Kandidaten verletzt** – Global verliert Hit@5. Drei Beobachtungen zeigen, dass das kein Rauschen ist: Der **Lift halbiert sich** (die Auswahl wird größer, nicht besser – die Coverage steigt, die Selektivität stärker); der **DRIFT-Gewinn ist erkauft**, weil `fallback` von 2 auf 9 steigt und DRIFT damit häufiger nur das Basic-Ergebnis liefert; und **`no_community` steigt trotz mehr Kanten** von 2 auf 9, weil weniger und größere Communities unschärfere Community-Dokumente ergeben. Der dichtere Graph schadet also genau der Ebene, die von ihm lebt.
>
> **Das ist zugleich ein Argument für V4** (Global-Ranking über die Mitglieds-Chunks, [Roadmap](../Roadmap.md#v4--global-community-ranking-über-die-mitglieds-chunks-erst-messen-dann-entscheiden))**:** Wäre das Community-Dokument nicht nur zehn Keywords plus Auszug, könnte ein dichterer Graph seine Wirkung überhaupt erst entfalten.
>
> **Bewusst getragene Grenze:** 85 Paper bleiben ohne Fan-out. Wer zu einem solchen Paper verwandte Arbeiten sucht, nutzt `get_citations` und die Chunk-Suche.

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
| Kosten/Datenschutz des Index-LLM | Entschärft durch Option B: **kein** Index-LLM (offline, TF-IDF); LLM nur zur Abfragezeit via Bridge ([ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md)). |

## Meilensteine

- **M0 – Migration:** PDFs, Recherche und `Übersicht.md` ins Repo übernommen (Phase 1).
- **M1 – Erster Durchstich:** ✅ erreicht – 1 PDF → Index → 1 Frage mit Quelle beantwortet (Offline-Hybrid, `python -m scripts.ingest` + `python -m scripts.ask`).
- **M2 – Copilot nutzt es:** ✅ erreicht – stdio-MCP-Server registriert ([`.vscode/mcp.json`](../.vscode/mcp.json)), sechs Werkzeuge mit Provenienz; Korpus abfragbar (Nachweis über In-Memory-Client-Roundtrip, produktive Nutzung nach Trust-Prompt im Agent-Modus) (Phase 5).
- **M3 – Drop & Use:** ✅ erreicht – Drop-in-Kreislauf (neue PDF → `python -m scripts.ingest` → sofort per On-Read abfragbar, unveränderte übersprungen) mit **atomarem Index-Swap** und pragmatischer QS (`scripts.status`/`scripts.qa`); voller Re-Index als Standard, inkrementell dokumentiert/optional (Phase 6, [ADR 0010](../docs/adr/0010-drop-in-workflow-and-qa-phase6.md)).
- **M4 – Erweiterungen:** Graph-/Zitationsfunktionen nach Bedarf (Phase 7).
- **M5 – Zufluss ohne Doppelbestand:** ✅ erreicht – neue PDFs gehen über `new_papers/` in den Korpus, Duplikate werden erkannt, die Übersicht wächst mit (Phase 8).
- **M8 – Aus dem Fund wird eine Quelle:** ✅ erreicht – jeder Beleg trägt einen extern auflösbaren Identifikator, und aus einem Suchtreffer entsteht ohne Handarbeit eine korrekte Literaturangabe in Harvard und APA. **336 von 341** Papern sind vollständig zitierfähig (vorher **0**). **Ehrlich dazu:** 66 Datensätze beruhen auf einem nicht eindeutigen Beleg und sind als `weak` markiert; 5 Paper bleiben ohne Auflösung (Phase 12).
