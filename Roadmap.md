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

> **Status:** ✅ umgesetzt ([ADR 0010](docs/adr/0010-drop-in-workflow-and-qa-phase6.md)): Die Bausteine „ein Befehl“ (`python -m scripts.ingest`, seit Phase 2/3) und „On-Read“ (der MCP-Server lädt Index/Communities **pro Anfrage** frisch, seit Phase 5) waren bereits erfüllt und wurden **verifiziert + gehärtet**: Der Index-Neuaufbau erfolgt jetzt **atomar** (Build nach `*.sqlite.tmp` + `os.replace`; ein Fehler lässt den Alt-Index intakt), sodass On-Read nie einen halbfertigen Index sieht. Neu für die **pragmatische QS**: `python -m scripts.status` (read-only Index-/Korpus-Status + Konsistenz-Check `papers/ ↔ manifest ↔ canonical`) und `python -m scripts.qa` (feste Prüf-Fragen je Modus durchspielen, Provenienz zeigen; Single Source of Truth). **DoD-Nachweis** – wie in Phasen 3–5 über Tests (kein steuerbarer Copilot-Client): ein **Freshness-/Atomaritäts-Regressionstest** plus die **QS-Harness-Regression**; realer Korpuslauf unverändert **145 Paper / 14 397 Chunks / 42 Communities**, `scripts.qa` liefert **10/10** Fragen mit belegter Provenienz. **170 Tests grün**, Kernmodule ≥ 92 %. Inkrementelles Update bleibt dokumentiert/optional (Phase 7).

### Phase 7 – Ausblick & Erweiterungen (optional, nach Bedarf)
**Ziel:** gezielte, bedarfsgetriebene Vertiefung entlang der in den Phasen 2–6 **beobachteten** Lücken – **offline-first** (Option B) priorisiert, mit klar abgegrenztem, beschaffungsabhängigem **Zielbild** (Option C, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)). Wie im gesamten Plan: **keine Zeitschätzungen**; Auswahl und Reihenfolge richten sich nach Nutzen und tatsächlichem Bedarf, jeder Punkt bleibt einzeln zieh- und weglassbar. Die Akzeptanzkriterien sind bewusst „right-sized“ (Nachweis über Tests/Stichproben, kein Over-Engineering).

**Gruppe A – offline umsetzbar (Option B), nach beobachtetem Nutzen priorisiert.** Reihenfolge = Vorschlag; höher = größerer erwarteter Mehrwert bei der täglichen Nutzung.

1. **LLM-Bridge / optionale Antwort-Synthese tatsächlich implementieren** ([ADR 0004](docs/adr/0004-llm-bridge-via-mcp-sampling.md)). *Lücke:* Der injizierbare Generierungs-Port ist in ADR 0004 beschrieben, im Code aber **nicht vorhanden**; Antworten sind heute reine Evidenz + Provenienz – der größte Hebel für die tägliche Nutzbarkeit (aus Belegen wird eine belegte Fließtext-Antwort). *Akzeptanz:* `GenerationProvider`-Protokoll mit `SamplingGenerationProvider` (Client-Modell via MCP-Sampling) und `NoopGenerationProvider` (Fallback → `generated = false`); optionaler Synthese-Pfad (Flag `--synthese` in `python -m scripts.ask` bzw. ein dediziertes Tool); ohne Sampling bleibt die **volle Evidenz** erhalten und die Pipeline degradiert **sichtbar** statt zu scheitern; Determinismus der Evidenz unberührt; Noop-Fallback getestet.

> **Status:** ✅ umgesetzt ([ADR 0012](docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md)): Das neue Paket `generation/` realisiert den Port (`GenerationProvider` mit `NoopGenerationProvider`/`SamplingGenerationProvider`), eine **mode-agnostische, deterministisch nummerierte** Evidenz (`Evidence`, `[1] … [n]` mit Paper · Abschnitt · Seite · Quelle), die Adapter für alle vier Modi und die Orchestrierung `answer_question` (Router → Retrieval → Evidenz → optionale Synthese). Der **Antwort-Contract** ist strikt: nur aus den Belegen, `[n]`-Zitatmarken, „nicht belegt" statt Vermutung, Deutsch, `temperature = 0`.
>
> **Bewusste Scope-Schärfung gegenüber der ursprünglichen Akzeptanz:** Ein reiner CLI-Pfad wäre offline dauerhaft im Noop-Fallback geblieben (kein Modell) – und Copilot formuliert die Antwort ohnehin selbst, ein serverseitiges Sampling *per Default* wäre also **doppelte Generierung**. Deshalb gibt es **beides**: `python -m scripts.ask --synthese` (Noop, macht den Fallback beobachtbar) **und** genau ein neues MCP-Tool **`answer_question`** – mit `synthesize = false` als Default (deterministisches Evidenz-Bündel in *einem* Aufruf, einheitliches Schema über alle Modi) und `synthesize = true` als **opt-in** Sampling über das Client-Modell. Die sechs bestehenden Evidenz-Tools bleiben unverändert modellfrei; [ADR 0009](docs/adr/0009-mcp-server-stdio-phase5.md) gilt für sie unverändert weiter.
>
> Die Async-Brücke (`anyio`) beschränkt sich auf die Servergrenze (Tool-Wrapper `to_thread`, Sampler `from_thread` in `mcp_server/sampling.py`); die Kernlogik bleibt synchron und offline testbar. **Nachweis:** ein **echter Sampling-Roundtrip** über den In-Memory-Client (Sampling-Callback als Modell-Attrappe, prüft Contract und Belege in der Anfrage), die sichtbare Degradation ohne Sampling-Fähigkeit sowie der reale CLI-Lauf (`--synthese` → „keine generierte Antwort" + vollständige Belege). **244 Tests grün**, Kernmodule ≥ 85 % (`synthesis`/`evidence`/`answer` 100 %). Nicht deterministisch ist ausschließlich der opt-in Synthese-Pfad – die Evidenz bleibt es immer.

2. **Echter Intra-Korpus-Zitationsgraph** – ohne Kuzu/GROBID. *Lücke:* Der Phase-3-Graph modelliert nur **Paper-Ähnlichkeit** (TF-IDF); der in der [README](README.md) skizzierte Domain-/Zitationsgraph (`CITES`, `USES_METHOD`, …) fehlt, Multi-Hop-Zitationsfragen sind offline faktisch unbeantwortbar. *Akzeptanz:* eine deterministische, leichte Extraktion (Referenz-Sektion über die bestehende Heuristik + DOI-/arXiv-/Titel-Matching **gegen den eigenen Korpus**) erzeugt **additive** `CITES`-Kanten in `data/index/index.sqlite` (Graph-Teilschema versioniert); die Frage „welche Paper bauen auf X auf?“ ist über ein read-only Skript/Tool belegbar; die Kanten-Precision wird stichprobenhaft geprüft. (GROBID/externe Referenzen bleiben Zielbild, Gruppe B.)

> **Status:** ✅ umgesetzt ([ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)): `indexing/citation_graph.py` erzeugt aus dem Referenzabschnitt (Phase-2-Heuristik) deterministische, gerichtete **`CITES`**-Kanten gegen den eigenen Korpus (Präzedenz **DOI > arXiv > Titel**, Selbstzitate ausgeschlossen) und persistiert sie **additiv** als `citation_edges` (Teilschema **0.1.0**) – gebaut im **selben atomaren Swap** wie Index und Ähnlichkeitsgraph. Belegbar über `python -m scripts.citations <paper_id>` und das MCP-Tool **`get_citations`** (`retrieval/citations.py` reichert um `source_uri` + Leit-Snippet und das Match-Kriterium an); `python -m scripts.status` und der `IngestReport` weisen die Kennzahlen aus. **Präzisions-Befund:** Ein erster Lauf ergab 192 Kanten, davon hingen **37 (19 %)** an Identifikatoren, die die Extraktion fälschlich aus dem Fließtext übernommen hatte (zitierte fremde IDs) – sie erzeugten einen falschen Zitations-Hub. Konsequenz: DOI/arXiv zählen nur noch, wenn sie im **Frontmatter** des Zielpapers belegt sind. Realer Korpuslauf danach: **158 Kanten** (98 arXiv, 58 Titel, 2 DOI) aus **143/145** Papern mit erkanntem Referenzabschnitt; die Stichprobe (14 Kanten über alle drei Methoden) war **14/14 korrekt**, die Top-Zitierten sind plausibel (GraphRAG „From Local to Global“ 19×, SWE-bench 13×). **200 Tests grün**, `citation_graph`/`retrieval/citations` 100 % Zeilenabdeckung. Zitationskontexte, externe Referenzen und Multi-Hop-Cypher bleiben Gruppe B.

3. **Chunking-Verfeinerung gegen die `short_chunk`-Flut.** *Lücke:* **2894 von 3074** Qualitätsflags sind `short_chunk` (harte Seiten-Chunk-Grenze, [ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md)); das verwässert Provenienz-Signal und Report-Aussagekraft. *Akzeptanz:* seitenübergreifendes Zusammenführen kurzer Rest-Chunks **mit erhaltener Seiten-Provenienz-Range** oder aggregierte statt per-Chunk-Flags; Canonical-/Index-Schema additiv/versioniert; Re-Ingest bleibt **deterministisch**; der `short_chunk`-Anteil sinkt messbar; Retrieval-Contract stabil.
4. **Hybrid-Retrieval (BM25 + TF-IDF), offline handimplementiert.** *Lücke:* Reine Kosinus-TF-IDF ist bei **exakten Fakten** (DOI, Metriken, Abkürzungen) schwächer; ein Fremd-Wheel ist nicht nötig, BM25 ist über die vorhandenen SQLite-Token deterministisch nachbaubar. *Akzeptanz:* deterministische BM25-Wertung + transparente, rangbasierte Score-Fusion mit TF-IDF; Basic/Local profitieren nachweislich bei Fakt-/Abkürzungsfragen (Stichprobe aus [eval/pruef-fragen.md](eval/pruef-fragen.md)); bestehende Modi-Contracts bleiben rückwärtskompatibel.
5. **Rausch-Reduktion bei Keywords & Section-Provenienz.** *Lücke:* Community-Keywords enthalten Rauschen (et/al/arxiv/Jahreszahlen/OCR-Ligaturen wie `uni00000013`); die Section-Heuristik übersegmentiert (bis **652** Sections auf einzelnen Papern, [ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md)). *Akzeptanz:* kuratierte Domänen-Stopwords + Token-Filter (rein numerische Token/Ligatur-Artefakte) und optional eine Section-Merge-Heuristik gegen Übersegmentierung; eine Vorher/Nachher-Stichprobe zeigt sauberere Keywords/Abschnitte; deterministisch; Schema additiv versioniert, falls nötig.
6. **Quantitative, offline Retrieval-Evaluation.** *Lücke:* Die QS (`python -m scripts.qa`) ist **rein qualitativ** (10 feste Fragen, Provenienz-Sichtprüfung); ein reproduzierbares Maß für Retrieval-Güte/Regressionen fehlt. *Akzeptanz:* ein versioniertes Gold-Set (Frage → erwartete Paper/Chunks) + Harness berechnet Kennzahlen (z. B. Hit@k, MRR) **deterministisch offline**; die Baseline ist dokumentiert; integriert als optionaler QS-Lauf.
7. **Router-Härtung.** *Lücke:* Der Router ([ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md)) ist eine naive DE/EN-Substring-Heuristik ohne Konfidenz/Fallback; eine Fehlklassifikation führt **still** in den falschen Modus. *Akzeptanz:* konfidenz-/score-basierte Entscheidung mit definiertem Fallback (z. B. Basic bei Unsicherheit) und **erklärbarer** Begründung (welches Signal, warum); erweiterte Router-Tests inkl. Grenzfällen; Verhalten bleibt deterministisch.
8. **Betriebs-Ausbaustufen (kleiner, optional).** *Lücke:* Voller Re-Index ist bei ~145 Papern günstig, wird bei wachsendem Bestand aber teurer; der Drop-in-Kreislauf ist noch manuell. *Akzeptanz:* (a) **inkrementelles Update** – nur neue/geänderte Paper extrahieren/indizieren, dann den Graphen neu bauen; das Ergebnis ist **nachweislich identisch** zum vollen Re-Index (Determinismus-Vergleich); voller Re-Index bleibt Standard. (b) **Auto-Watcher** für `papers/` als optionaler Komfort; der manuelle Anstoß bleibt möglich.

**Gruppe B – Zielbild (Option C, beschaffungsabhängig).** Diese Punkte bleiben das **Zielbild** und werden erst umgesetzt, wenn die nötigen Wheels/Modelle/Runtimes offline verfügbar werden ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)); sie sind aktuell **empirisch nicht beschaffbar**.

- **Domain-/Zitationsgraph mit Kuzu (embedded) + Text2Cypher** für deterministische Cypher-Graphfragen und Multi-Hop-Netze (baut auf A2 auf).
- **GROBID** für präzises Parsing **externer** Referenzen/Zitationskontexte (benötigt Docker/Java).
- **Microsoft GraphRAG / Docling / LanceDB** als vollwertiges Zielbild (LLM-gestützte Entitäts-/Community-Reports, Bounding-Box-Provenienz).
- **Hybrid-Suche mit dedizierten Vektor-/Suchmaschinen** und **Skalierung Richtung Qdrant/Weaviate/Neo4j**, falls der Bestand deutlich über die ~500-Paper-Auslegung hinauswächst.

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
- **M3 – Drop & Use:** ✅ erreicht – Drop-in-Kreislauf (neue PDF → `python -m scripts.ingest` → sofort per On-Read abfragbar, unveränderte übersprungen) mit **atomarem Index-Swap** und pragmatischer QS (`scripts.status`/`scripts.qa`); voller Re-Index als Standard, inkrementell dokumentiert/optional (Phase 6, [ADR 0010](docs/adr/0010-drop-in-workflow-and-qa-phase6.md)).
- **M4 – Erweiterungen:** Graph-/Zitationsfunktionen nach Bedarf (Phase 7).
