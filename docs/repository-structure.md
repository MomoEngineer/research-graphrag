# Repository-Struktur und Definition of Done

Dieses Dokument legt die **verbindliche Ordnerstruktur** fest und fasst die **Definition of Done** zusammen. Struktur und Disziplin orientieren sich an `mcs-copilot-tools`, sind aber auf **ein** src-Layout-Paket mit **einem** MCP-Server zugeschnitten.

---

## 1. Verbindliche Ordnerstruktur

```
research-graphrag/
├─ README.md                     # Zielbild & Kontext
├─ Roadmap.md                    # aktiver Phasenplan (8–11)
├─ Übersicht.md                  # Kuratierte Literaturübersicht (Quellen-Tabelle)
├─ CONTRIBUTING.md               # Zentrales Regelwerk
├─ pyproject.toml                # src-Layout, Kern-Deps (Offline-Hybrid) + Extra [dev]
├─ requirements.lock             # eingefrorene Gesamtauflösung (pip freeze, ADR 0002)
├─ .env.example                  # Beispiel-Umgebungsvariablen (keine Secrets)
├─ docs/
│  ├─ features.md                # funktionale Landkarte (Feature → Einstiegspunkt → Modul → ADR)
│  ├─ funktionsweise.md          # Konzept & Abläufe (Mermaid), Einstieg in die Modul-Dokus
│  ├─ roadmap-historie.md        # Archiv der abgeschlossenen Phasen 0–7 (nicht fortgeschrieben)
│  ├─ vscode-integration.md
│  ├─ repository-structure.md    # dieses Dokument
│  ├─ documentation-standards.md
│  ├─ testing.md
│  ├─ error-model.md
│  ├─ glossary.md
│  └─ adr/
│     ├─ README.md
│     └─ 0001-*.md … 0020-*.md
├─ templates/
│  ├─ tool-spec.md
│  ├─ module-doc.md              # Vorlage Modul-Doku (ADR 0018)
│  ├─ tool-code-walkthrough.md   # abgelöst durch module-doc.md (ADR 0018)
│  ├─ server-README.md
│  └─ adr-template.md
├─ scripts/
│  ├─ __init__.py
│  ├─ README.md
│  ├─ coverage_offline.py        # Offline-Coverage-Gate (ADR 0003)
│  ├─ ingest.py                  # Drop-in → Canonical JSON → Index (Option B)
│  ├─ ask.py                     # Frage → Retrieval-Modi (Basic/Local/Global/DRIFT + Router)
│  ├─ intake.py                  # Korpus-Zufluss: new_papers/ → papers/ → Ingest → Übersicht (Phase 8)
│  ├─ update_overview.py         # Entwurfszeilen → Übersicht.md (append-only, Option B)
│  ├─ graph_info.py              # Community-Übersicht (read-only, Phase 3)
│  ├─ citations.py               # Zitationen eines Papers (read-only, Phase 7 / A2)
│  ├─ discover.py                # Online-Kandidatensuche ohne Download (separat startbar, Phase 9 / S1)
│  ├─ status.py                  # Read-only Index-/Korpus-Status + Konsistenz (Phase 6)
│  ├─ qa.py                      # Prüf-Fragen je Modus durchspielen (QS-Harness, Phase 6; `--quantitativ` seit Phase 7 / A6)
│  └─ eval_retrieval.py          # Evaluation: Primitive/Modi, Baseline, Regressions-Check, Router (Phase 7 / A4 + A6 + A7)
├─ src/research_graphrag/
│  ├─ __init__.py                # Paket-Version
│  ├─ doc/                       # Modul-Dokus der Top-Level-Module (ADR 0018)
│  ├─ errors.py                  # gemeinsame Fehlertaxonomie (docs/error-model.md)
│  ├─ intake.py                  # Korpus-Zufluss mit Duplikatprüfung (Phase 8)
│  ├─ keywords.py                # kuratierte Keyword-Politik (Stopwords/Token-Filter, Phase 7 / A5)
│  ├─ pipeline.py                # Drop-in-Ingestion (papers/ → Canonical → Index)
│  ├─ extraction/                # pypdf → Canonical Paper JSON 0.4.0 (Option B)
│  │  ├─ doc/                    #   Modul-Dokus (eine je Modul, ADR 0018)
│  │  ├─ model.py                #   Datenmodell (Section/Chunk/CanonicalPaper)
│  │  ├─ normalization.py        #   Textnormalisierung (Ligaturen/Glyph-Artefakte, Phase 7 / A5)
│  │  ├─ structure.py            #   Section-/Identifier-Heuristik
│  │  ├─ chunking.py             #   größenbasiertes Chunking
│  │  ├─ quality.py              #   Qualitäts-Gates (Flags)
│  │  └─ pdf.py                  #   Orchestrator extract_pdf
│  ├─ indexing/                  # Canonical JSON → Offline-Hybrid-Index (Option B)
│  │  ├─ doc/                    #   Modul-Dokus
│  │  ├─ tfidf_index.py          #   Chunk-Index über SQLite (TF-IDF + BM25, Hybrid-Wertung)
│  │  ├─ bm25.py                 #   BM25-Gewichte, handimplementiert (Phase 7 / A4)
│  │  ├─ fusion.py               #   Reciprocal Rank Fusion (Phase 7 / A4)
│  │  ├─ graph_index.py          #   Paper-Ähnlichkeitsgraph + Louvain-Communities (Phase 3)
│  │  └─ citation_graph.py       #   Intra-Korpus-Zitationsgraph (CITES, Phase 7 / A2)
│  ├─ retrieval/                 # Query-Router: Basic/Local/Global/DRIFT (Phase 4)
│  │  ├─ doc/                    #   Modul-Dokus
│  │  ├─ basic.py                #   search_basic (Top-k über die Hybrid-Wertung)
│  │  ├─ local.py                #   search_local (Chunk-Nachbarschaft + Paper-Fan-out)
│  │  ├─ global_search.py        #   search_global (Community-Ranking)
│  │  ├─ drift.py                #   search_drift (Global→Local-Hybrid)
│  │  ├─ router.py               #   Heuristik-Router (Fragetyp → Modus)
│  │  ├─ provenance.py           #   Citation/PaperRef + Provenienz-Assembler
│  │  ├─ paper.py                #   get_paper (Paper-Metadaten aus dem Index, Phase 5)
│  │  └─ citations.py            #   get_citations (Zitationen + Provenienz, Phase 7 / A2)
│  ├─ overview/drafts.py         # Übersicht-Entwürfe (Staging, Phase 2) + overview/doc/
│  ├─ generation/                # LLM-Bridge & Antwort-Synthese (Phase 7 / A1)
│  │  ├─ doc/                    #   Modul-Dokus
│  │  ├─ provider.py             #   Generierungs-Port (Noop/Sampling) + Antwort-Contract
│  │  ├─ synthesis.py            #   Evidenz (nummeriert) + synthesize_answer (retrieval-frei)
│  │  ├─ evidence.py             #   Adapter: Basic/Local/Global/DRIFT → Evidenz
│  │  └─ answer.py               #   Router → Retrieval → Evidenz → optionale Synthese
│  ├─ evaluation/                # Quantitative Evaluation von Retrieval und Router (Phase 7 / A4 + A6 + A7)
│  │  ├─ doc/                    #   Modul-Dokus
│  │  ├─ gold.py                 #   Gold-Set + mechanische Label-Regel
│  │  ├─ metrics.py              #   Hit@k/MRR/Coverage/Lift (retrieval-frei)
│  │  ├─ runner.py               #   Primitive + Modi gegen den realen Index
│  │  ├─ baseline.py             #   Fingerprint, Einfrieren, qid-genauer Vergleich
│  │  ├─ routing.py              #   Router-Gold-Set + Contract-Treue (Phase 7 / A7)
│  │  └─ report.py               #   Textausgabe
│  ├─ online/                    # Online-Kandidatensuche, separat startbar (Phase 9 / S1)
│  │  ├─ doc/                    #   Modul-Dokus
│  │  ├─ transport.py            #   HttpClient-Port + Proxy-Transport (einzige Netzstelle)
│  │  ├─ sources.py              #   Adapter arXiv + OpenAlex
│  │  ├─ candidates.py           #   Kandidaten-Modell + Dedup (nutzt die Intake-Logik)
│  │  ├─ search.py               #   Anfragen aus dem Bestand + Laufsteuerung
│  │  └─ report.py               #   append-only Bericht + Ablage der Rohantworten
│  └─ mcp_server/                # MCP-Server (stdio), Phase 5
│     ├─ doc/                    #   Modul-Dokus (server.py, sampling.py)
│     ├─ server.py               #   FastMCP: 8 Tools + Fehlerübersetzung an der Grenze
│     ├─ sampling.py             #   Async-Brücke zum Client-Modell (opt-in, Phase 7 / A1)
│     ├─ __main__.py             #   Einstiegspunkt (python -m research_graphrag.mcp_server)
│     ├─ README.md               #   Server-README
│     └─ specs/                  #   Pro-Tool-Spezifikationen (8 Tools)
├─ eval/
│  ├─ pruef-fragen.md            # Prüf-Fragen über alle 5 Fragetypen
│  ├─ retrieval-gold.json        # versioniertes Gold-Set für Hit@k/MRR (Phase 7 / A4)
│  ├─ retrieval-baseline.json    # eingefrorene Ränge je Frage/Ebene (Phase 7 / A6)
│  └─ router-gold.json           # versioniertes Router-Gold-Set (Contract-Labels, Phase 7 / A7)
├─ recherche/                    # (Phase 1) migrierte Rechercheartefakte (noch nicht vorhanden)
├─ new_papers/                   # Eingangsordner des Intake (nicht versioniert, außer README.md)
│  └─ _duplikate/                #   Quarantäne der Identifikator-Duplikate (vom Intake angelegt)
├─ papers/                       # PDF-Korpus (nicht versioniert)
├─ data/                         # Canonical JSON 0.4.0, manifest.json, index/, quality_report.*, intake_log.md, online_candidates.md, online_raw/ (nicht versioniert)
└─ tests/                        # gespiegelt zu src/research_graphrag/
   ├─ conftest.py                # anyio-Backend + make_pdf-Fixture
   ├─ test_smoke.py
   ├─ test_errors.py
   ├─ test_intake.py
   ├─ test_keywords.py
   ├─ test_pipeline.py
   ├─ extraction/                # PDF-Extraktion + Struktur/Chunking/Qualität (Phase 2)
   ├─ indexing/                  # TF-IDF/SQLite-Index (0b) + BM25/Fusion (Phase 7 / A4) + Graph (Phase 3) + Zitationen (Phase 7)
   ├─ retrieval/                 # Basic/Local/Global/DRIFT + Router + Provenienz + get_paper/get_citations + QS-Harness + Eval-Harness (Phase 4/5/6/7)
   ├─ overview/                  # Übersicht-Entwürfe (Phase 2)
   ├─ generation/                # LLM-Bridge: Port, Evidenz, Synthese, CLI-Pfad (Phase 7 / A1)
   ├─ evaluation/                # Gold-Set, Kennzahlen, Modus-Lauf, Baseline, Ausgabe (Phase 7 / A6) + Router-Messung (A7)
   ├─ online/                   # Transport-Port, Quellen-Adapter, Dedup, Bericht, CLI (Phase 9 / S1)
   ├─ mcp_server/                # Server-Contract via In-Memory-Client (Phase 5) + Sampling (Phase 7)
   └─ integration/               # End-to-End-Durchstich (M1) + Drop-in-Freshness/atomarer Swap + Status (Phase 6/7)
```

> **Phasen-Hinweis:** Einträge mit „(Phase n)" markieren die Phase der **vollen** Ausbaustufe. In **Phase 0b** sind bereits lauffähige Offline-Hybrid-Implementierungen vorhanden (`errors.py`, `pipeline.py`, `extraction/pdf.py`, `indexing/tfidf_index.py`, `retrieval/basic.py`, `scripts/ingest.py`, `scripts/ask.py`). In **Phase 2** kamen die Extraktions-Submodule (`extraction/model.py`, `structure.py`, `chunking.py`, `quality.py`), das Paket `overview/` und `scripts/update_overview.py` hinzu. In **Phase 3** kamen `indexing/graph_index.py` (Paper-Ähnlichkeitsgraph + Louvain-Communities) und `scripts/graph_info.py` hinzu. In **Phase 4** kamen die Retrieval-Module (`retrieval/local.py`, `global_search.py`, `drift.py`, `router.py`, `provenance.py`) hinzu; der Index wurde additiv um `section_title` erweitert (Schema 0.2.0, [ADR 0008](adr/0008-retrieval-and-query-router-phase4.md)). In **Phase 5** kamen der MCP-Server (`mcp_server/server.py`, `__main__.py`, `README.md`) und `retrieval/paper.py` (`get_paper`) hinzu; der Index wurde additiv um `identifiers` (DOI/arXiv) erweitert (Schema 0.3.0, [ADR 0009](adr/0009-mcp-server-stdio-phase5.md)). In **Phase 6** kamen `scripts/status.py` (read-only Status/Konsistenz) und `scripts/qa.py` (QS-Harness) sowie der **atomare Index-Swap** in `pipeline.py` hinzu (On-Read gehärtet, [ADR 0010](adr/0010-drop-in-workflow-and-qa-phase6.md)); Index-/Canonical-Schema bleiben unverändert. In **Phase 7 / A2** kamen `indexing/citation_graph.py`, `retrieval/citations.py` und `scripts/citations.py` hinzu; der Index wurde additiv um das Zitations-Teilschema (`citation_edges`, `meta.citation_schema_version`) erweitert, das im selben atomaren Swap gebaut wird ([ADR 0011](adr/0011-intra-corpus-citation-graph-phase7.md)). In **Phase 7 / A1** kam das Paket `generation/` (Generierungs-Port, Evidenz, Synthese, Orchestrierung) samt `mcp_server/sampling.py`, dem Tool `answer_question` und dem CLI-Flag `--synthese` hinzu ([ADR 0012](adr/0012-llm-bridge-and-answer-synthesis-phase7.md)). In **Phase 7 / A3** wurde die Extraktion verfeinert – `extraction/structure.py` erhielt Reject-Regeln und die **Section-Absorption**, `extraction/chunking.py` gibt die Seitengrenze zugunsten einer **Seiten-Range** auf; Canonical-Schema `0.3.0`, Index-Schema `0.4.0` (`chunks.page_end`), `Citation` additiv um `page_end` erweitert ([ADR 0013](adr/0013-chunking-refinement-phase7.md)). In **Phase 7 / A4** kamen `indexing/bm25.py` und `indexing/fusion.py` hinzu; `indexing/tfidf_index.py` baut beide Wertungen über **einer** Tokenisierung und liefert per Default die Rang-Fusion, `Citation` trägt additiv `score_tfidf`/`score_bm25` (Laufzeit-Schema; **Index-Schema unverändert** `0.4.0`), dazu `scripts/eval_retrieval.py` und `eval/retrieval-gold.json` ([ADR 0014](adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)). Der Ordner `recherche/` wird erst in seiner Phase angelegt.

> **Phase 7 / A5:** Neu sind `extraction/normalization.py` (Ligatur-Reparatur, Entfernen der
> `/uniXXXXXXXX`-Glyphen) und das Querschnittsmodul `keywords.py` (kuratierte Stopwords +
> Token-Filter für `indexing/graph_index.py` und `overview/drafts.py`). `extraction/structure.py`
> verwirft zusätzlich Bibliografie-Zeilen und schaltet im Referenzabschnitt den
> Numerierungs-Zweig ab. Das **Canonical-Schema** steigt auf **0.4.0** (Inhalts-Contract, zugleich
> Re-Extraktions-Trigger); Index- und Graph-Teilschema bleiben unverändert
> ([ADR 0015](adr/0015-noise-reduction-keywords-and-sections-phase7.md)).

> **Phase 7 / A6:** Die Evaluationslogik zieht von `scripts/eval_retrieval.py` in das neue Paket
> `evaluation/` (fünf Module) – sie unterliegt damit `mypy src`, dem Coverage-Richtwert und ist
> aus `scripts/qa.py` wiederverwendbar. Gemessen werden jetzt auch die **Modi als Ganzes**
> (Local-Baustein-Beitrag, Community-Auswahl mit Trivial-Baselines, DRIFT-Deckelung); neu ist das
> eingefrorene Artefakt `eval/retrieval-baseline.json` mit qid-genauem Regressions-Check.
> Schemata und Index bleiben unberührt – **kein Re-Ingest**
> ([ADR 0016](adr/0016-quantitative-retrieval-evaluation-phase7.md)).

> **Phase 7 / A7:** Der Query-Router in `retrieval/router.py` wird gehärtet: Signale tragen eine
> **deklarierte Match-Art** (Wortgrenze/Wortanfang für Englisch, Teilwort nur für deutsche
> Stämme), `basic` ist Rückfallebene statt gleichrangiger Modus, und die Entscheidung trägt
> Konfidenzstufe plus auslösende Signale – ausgewiesen in der CLI und additiv als `routing` in
> `answer_question`. Neu sind `evaluation/routing.py` und `eval/router-gold.json`; die feste
> Präzedenz aus [ADR 0008](adr/0008-retrieval-and-query-router-phase4.md) ist abgelöst. Kein
> Schema-Eingriff, **kein Re-Ingest**
> ([ADR 0017](adr/0017-router-hardening-phase7.md)).

> **Phase 8:** Neu sind `intake.py` (Top-Level, Korpus-Zufluss) und das dünne `scripts/intake.py`
> samt Eingangsordner `new_papers/`. Die Duplikatprüfung ist dreistufig mit **abgestufter**
> Konsequenz; `overview/drafts.py` hängt Entwurfszeilen jetzt an die kuratierte `Übersicht.md` an
> (byte-erhaltend, atomar, eigene ID-Reihe) – die Staging-Datei `data/overview_drafts.md` ist
> abgelöst und wird nur noch gelesen. Der Flag-Katalog erhält `no_chunks`. Kein Schema-Eingriff,
> **kein Re-Ingest** ([ADR 0019](adr/0019-corpus-intake-new-papers-phase8.md)).

> **Phase 9 / S1:** Neu ist das Paket `online/` (fünf Module) samt `scripts/discover.py`. Der
> gesamte Netzzugang liegt in `online/transport.py` hinter einem **injizierbaren Port**; alles
> übrige ist netzfrei und offline getestet. Die Duplikatprüfung wird aus `intake.py`
> **wiederverwendet** (`load_corpus`, `CorpusView`, `best_title_match` sind dafür öffentlich
> geworden, ebenso `citation_graph.title_from_uri`). `certifi` und `pywin32` sind jetzt explizit
> gepinnt – beide waren transitiv vorhanden und werden nun direkt importiert. Geschrieben wird
> ausschließlich `data/online_candidates.md` (append-only) und `data/online_raw/`; kein
> Schema-Eingriff, **kein Re-Ingest**, **kein** MCP-Werkzeug
> ([ADR 0020](adr/0020-online-candidate-search-phase9.md)).

> **Geplant (Phasen 9–11, [Roadmap.md](../Roadmap.md)):** Aus **Phase 9** sind S0 (Machbarkeit)
> und S1 (Kandidatensuche) erledigt; **S2** (Volltext-Download) bleibt zurückgestellt, weil die
> Lizenzangaben der Quellen keine belastbare Whitelist tragen. Die Phasen 10 und 11
> arbeiten die in [ADR 0016](adr/0016-quantitative-retrieval-evaluation-phase7.md) belegten
> Retrieval-Befunde sowie Betriebsthemen ab. Die abgeschlossenen Phasen 0–7 sind in der
> [Roadmap-Historie](roadmap-historie.md) archiviert.

### Zuordnung zu den Roadmap-Phasen

| Ordner | Verantwortung | Phase |
| --- | --- | --- |
| `src/research_graphrag/extraction/` | PDF → Canonical Paper JSON (`pypdf`) | 2 |
| `src/research_graphrag/indexing/` | Canonical JSON → Offline-Hybrid-Index (TF-IDF + BM25 + networkx/SQLite) + Zitationsgraph | 3 / 7 |
| `src/research_graphrag/retrieval/` | Query-Router (Local/Global/DRIFT/Basic) | 4 |
| `src/research_graphrag/mcp_server/` | MCP-Server (stdio) mit Tools + Provenienz | 5 |
| `src/research_graphrag/generation/` | LLM-Bridge: Evidenz-Aufbereitung + optionale Antwort-Synthese | 7 |
| `src/research_graphrag/evaluation/` | Quantitative Evaluation: Retrieval (Gold-Set, Kennzahlen, Baseline) und Router-Contract | 7 |
| `src/research_graphrag/online/` | Online-Kandidatensuche (Transport-Port, arXiv/OpenAlex, Dedup, Bericht) | 9 |
| `src/research_graphrag/keywords.py` | kuratierte Keyword-Politik für extraktive Keyword-Listen | 7 |

---

## 2. Konventionen

- **Tool-Logik = ein Modul** unter `src/research_graphrag/retrieval/` (bzw. ein dediziertes Read-Modul wie `retrieval/paper.py`); `server.py` registriert die Tools als **dünne Wrapper**. Ein separates `mcp_server/tools/`-Verzeichnis ist bei diesem Zuschnitt bewusst nicht nötig (right-sized, [ADR 0009](adr/0009-mcp-server-stdio-phase5.md)).
- **Tool-Contracts** werden in `tests/mcp_server/` über einen In-Memory-Client geprüft; die Backend-Funktionen zusätzlich in `tests/retrieval/`.
- **Ein Tool = eine Spezifikation** unter `src/research_graphrag/mcp_server/specs/<tool>.md`.
- **Ein Modul = eine Modul-Doku** unter `src/research_graphrag/<paket>/doc/<modul>.md` (Top-Level-Module unter `src/research_graphrag/doc/`), nach [templates/module-doc.md](../templates/module-doc.md). Ausgenommen sind `__init__.py` und `__main__.py`. Diese Regel löst den früheren Code-Walkthrough `<tool>.code.md` ab ([ADR 0018](adr/0018-code-documentation-architecture.md), siehe [documentation-standards.md](documentation-standards.md)).
- Der Server-Einstiegspunkt (`python -m research_graphrag.mcp_server`) registriert die Tools und startet den `stdio`-Transport.
- **Tool-Namen** sind sprechend und domänenbezogen: `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper`, `get_citations`, `list_topics`, `answer_question` (siehe [README.md](../README.md)).

---

## 3. Definition of Done (pro Beitrag)

Identisch zu [CONTRIBUTING.md](../CONTRIBUTING.md), hier als Checkliste (right-sized):

- [ ] Vollständige Type-Hints; `mypy` ohne Fehler.
- [ ] `ruff` (Lint + Format) ohne Befunde.
- [ ] Docstrings für alle öffentlichen Funktionen/Tools.
- [ ] Tests vorhanden und grün.
- [ ] Für MCP-Tools: Tool-Spezifikation.
- [ ] Für jedes berührte Modul: Modul-Doku unter `<paket>/doc/<modul>.md` angelegt bzw. nachgezogen; bei neuen Fähigkeiten zusätzlich [features.md](features.md) und ggf. [funktionsweise.md](funktionsweise.md).
- [ ] Zeilenabdeckung als Richtwert ≥ 80 % pro Kernmodul.
- [ ] Provenienz-Angaben, wo Ergebnisse abgeleitet werden.
- [ ] Reproduzierbarkeit sichergestellt (Seeds/Versionen).
- [ ] Bei Architekturentscheidungen: ADR angelegt.

---

## 4. Definition of Done (Server, ab Phase 5)

- [ ] Der Server startet fehlerfrei über `stdio` (`python -m research_graphrag.mcp_server`).
- [ ] Alle enthaltenen Tools erfüllen ihre Definition of Done.
- [ ] Server-README ([templates/server-README.md](../templates/server-README.md)) vollständig.
- [ ] Einbindungsbeispiel in [docs/vscode-integration.md](vscode-integration.md) nachvollziehbar.
- [ ] Integrationstests vorhanden, wo Tools zusammenwirken (Extraktion → Index → Retrieval).
