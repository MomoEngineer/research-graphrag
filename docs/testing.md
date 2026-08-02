# Teststrategie

Dieses Dokument definiert, wie Code und – ab Phase 5 – MCP-Tools getestet werden. Offline-tauglich und right-sized (siehe [CONTRIBUTING.md](../CONTRIBUTING.md)).

> **Grundregel:** Pro (nicht-trivialem) MCP-Tool ein eigenes Test-Skript mit mehreren Tests. Kein Tool gilt ohne Tests als fertig (siehe Definition of Done).

---

## 1. Testbereich im Repo

Alle Tests liegen unter `tests/`, gespiegelt zur Paketstruktur:

```
tests/
├─ conftest.py            # anyio-Backend + make_pdf-Fixture
├─ test_smoke.py          # Paket-Smoke-Test
├─ test_errors.py         # Fehlertaxonomie
├─ test_keywords.py       # kuratierte Keyword-Politik (Phase 7 / A5)
├─ test_pipeline.py       # Drop-in-Ingestion
├─ extraction/            # Extraktion: pdf/normalization/structure/chunking/quality (Phase 2, 7 / A5)
├─ indexing/              # Index (0b) + BM25/Fusion (Phase 7 / A4) + Graph/Communities (Phase 3) + Zitationsgraph (Phase 7)
├─ retrieval/            # Basic/Local/Global/DRIFT + Router + Provenienz + get_paper/get_citations + QS-Harness (Phase 4/5/6/7)
├─ overview/              # Übersicht-Entwürfe (Phase 2)
├─ generation/            # LLM-Bridge: Port, Evidenz, Synthese, CLI-Pfad (Phase 7 / A1)
├─ evaluation/            # Gold-Set, Kennzahlen, Modus-Lauf, Baseline, Ausgabe (Phase 7 / A4 + A6) + Router-Contract (A7)
├─ integration/           # End-to-End-Durchstich (M1) + Drop-in-Freshness/atomarer Swap (Phase 6) + Status (Phase 7)
└─ mcp_server/            # (Phase 5) Server-Contract via In-Memory-Client (test_server.py)
```

> **Aktueller Stand (Phase 7 / A1 + A2 + A3 + A4 + A5 + A6 + A7):** Die Kernmodule (`errors`, `extraction/*` inkl. `model`/`structure`/`chunking`/`quality`, `indexing` inkl. `bm25`/`fusion`/`graph_index`/`citation_graph`, `retrieval/*` inkl. `basic`/`local`/`global_search`/`drift`/`router`/`provenance`/`paper`/`citations`, `generation/*` inkl. `provider`/`synthesis`/`evidence`/`answer`, `evaluation/*` inkl. `gold`/`metrics`/`runner`/`baseline`/`routing`/`report`, `overview`, `pipeline`, `mcp_server/server`/`sampling`) sind mit Funktions-, Fehler-, Contract- und Property-Tests abgedeckt (Kernmodule ≥ 85 % Zeilenabdeckung, retrieval- und evaluation-Module 100 %; **404 Tests**). Der **Contract-Test** (Abschnitt 2.1) ist umgesetzt: ein **In-Memory-Client-Roundtrip** (`tests/mcp_server/test_server.py`) prüft alle acht Tools über das echte MCP-Protokoll (Erfolg + strukturierte Fehlerausgabe) – inklusive eines **echten Sampling-Roundtrips** für `answer_question` (Sampling-Callback als Client-Modell-Attrappe) und der sichtbaren Degradation ohne Sampling-Fähigkeit. **Phase 6** ergänzt einen **Freshness-/Atomaritäts-Regressionstest** (`tests/integration/test_phase6_freshness.py`: neue PDF → `ingest` → On-Read liefert sie sofort; unveränderte übersprungen; ein fehlgeschlagener Re-Index lässt den Alt-Index intakt) und eine **QS-Harness-Regression** (`tests/retrieval/test_qa.py`: das feste Prüf-Fragen-Set liefert wohlgeformte Provenienz). **Phase 7** ergänzt die Zitationsgraph-Tests (`tests/indexing/test_citation_graph.py`, `tests/retrieval/test_citations.py`), eine Status-Regression (`tests/integration/test_status.py`), die Synthese-Tests (`tests/generation/`), eine **Konsolen-Encoding-Regression** (`tests/integration/test_cli_encoding.py`: die CLI-Skripte laufen auch bei cp1252-Ausgabe durch) sowie die **Chunking-Verfeinerung** (`tests/extraction/test_structure.py`: Reject-Regeln und Section-Absorption inkl. Schutz des Referenzabschnitts; `tests/extraction/test_chunking.py`: Seiten-Range statt Seitengrenze). **Phase 7 / A4** ergänzt die Wertungs-Tests (`tests/indexing/test_bm25.py`: Term-Sättigung, Längennormalisierung, positive IDF; `tests/indexing/test_fusion.py`: RRF-Formel und Fusionsverhalten; `tests/indexing/test_tfidf_index.py`: **Äquivalenz des TF-IDF-Raums zum früheren `TfidfVectorizer`**, Wertungs-Varianten, Determinismus) und den Eval-Harness (`tests/retrieval/test_eval_retrieval.py`: mechanische Label-Ableitung, Hit@k/MRR, Gold-Set-Integrität).

> **Phase 7 / A5** ergänzt die Rausch-Reduktion: `tests/extraction/test_normalization.py`
> (Ligatur-Reparatur, Entfernen der Glyph-Artefakte, Erhalt der mathematischen Alphanumerics und
> der Zeilenstruktur, Idempotenz), `tests/test_keywords.py` (kuratierte Stopwords, numerische
> Token, Auffüllen bis zum Limit) sowie zusätzliche Fälle in
> `tests/extraction/test_structure.py` (Bibliografie-Rejects und der Referenzkontext, in dem
> numerierte Zeilen Literatureinträge sind).

> **Phase 7 / A6** ergänzt den Testbaum `tests/evaluation/` (Gold-Set und Label-Regel,
> retrieval-freie Kennzahlen inkl. Lift, Modus-Läufe gegen eine Zwei-Cluster-Fixture, Baseline
> mit Fingerprint-Guard und Schweregraden, Textausgabe). Der wichtigste Test ist ein
> **Contract-Test**: `search_basic` erhält die Reihenfolge der geteilten Chunk-Primitive exakt –
> deshalb wird Basic nicht als zweite Kennzahl gepflegt
> ([ADR 0016](adr/0016-quantitative-retrieval-evaluation-phase7.md)). Die Berichte selbst sind
> **korpusabhängig** und daher bewusst **kein** Gate der Testsuite: Der Regressions-Check
> (`python -m scripts.eval_retrieval --check`) läuft manuell gegen den realen Index, die Logik
> dahinter ist mit synthetischen Fixtures abgedeckt.

> **Phase 7 / A7** ergänzt `tests/evaluation/test_routing.py` und erweitert
> `tests/retrieval/test_router.py` um die Grenzfälle der Härtung (Wortgrenzen gegen die
> gemessenen Fehlalarm-Träger, Wortanfangs-Anker, deutsche Komposita, Gleichstands-Fallback,
> bestätigende statt entscheidende Fakt-Signale). Anders als beim Retrieval **ist** der Router
> ein Gate der Testsuite: Er ist **korpus-unabhängig**, deshalb läuft die Messung gegen
> [eval/router-gold.json](../eval/router-gold.json) direkt im Test – mit **qid-genau**
> eingefrorener Fehlgriff-Menge, geprüften Contract-Labels und der Zusicherung, dass **jedes**
> Signal von mindestens einer Frage berührt wird
> ([ADR 0017](adr/0017-router-hardening-phase7.md)).

---

## 2. Testarten (je MCP-Tool, ab Phase 5)

> **Reihenfolge (Test-first):** Contract- und Fehler-/Edge-Case-Tests werden **aus der Tool-Spezifikation abgeleitet, bevor die Kernlogik entsteht** (rot → grün). Voraussetzung ist ein minimales, registriertes Tool-Skeleton.

### 2.1 Contract-Test (MCP-Protokoll)
- Das Tool wird bei der Discovery (`list_tools`) gefunden.
- Name, Beschreibung, **Input-Schema** und **Tool-Version** entsprechen der Spezifikation.
- Die **Ausgabe** entspricht dem dokumentierten Output-Schema.

### 2.2 Funktions-/Happy-Path-Test
- Repräsentative, gültige Eingaben liefern das erwartete Ergebnis.
- Wo relevant, wird gegen kleine, versionierte **Test-Fixtures** geprüft (z. B. ein Mini-Canonical-JSON).

### 2.3 Fehler-/Edge-Case-Test
- Ungültige Eingaben liefern die erwartete **Fehlerkategorie** (siehe [error-model.md](error-model.md)).
- Sicherheitsgrenzen (Zugriff außerhalb der Workspace-Roots) werden mit `permission_denied` abgewiesen.
- Die **Struktur der Fehlerausgabe** entspricht dem Fehler-Modell.

---

## 3. Integrationstests (werkzeugübergreifend)

Für Ketten (z. B. Extraktion → Index → Retrieval) werden Integrationstests angelegt – entweder eingebettet beim beteiligten Tool oder unter `tests/integration/`.

---

## 4. Werkzeuge und Konfiguration (offline)

- **Test-Runner:** `pytest` (`python -m pytest tests`).
- **Asynchrone Tests:** über das **`anyio`-Pytest-Plugin** (`@pytest.mark.anyio`); Backend `asyncio` fixiert in `tests/conftest.py` ([ADR 0003](adr/0003-offline-test-and-coverage-tooling.md); `pytest-asyncio` ist offline nicht installierbar).
- **Abdeckung:** `python -m scripts.coverage_offline` misst die Zeilenabdeckung je Kernmodul über die stdlib (`trace`); `pytest-cov`/`coverage` sind offline nicht installierbar (ADR 0003).

Verbindlicher Offline-Testlauf:

```pwsh
python -m pytest tests -q
python -m scripts.coverage_offline
```

---

## 5. Abdeckungs-Richtwert

- **≥ 80 % Zeilenabdeckung pro Kernmodul** als **Richtwert** (right-sized: kein hartes Gate).
- `scripts/coverage_offline.py` meldet Unterschreitungen mit Exit-Code ≠ 0; bewusste Ausnahmen werden kurz begründet.
- Die **Zweigabdeckung** bleibt dem späteren `coverage.py` vorbehalten.

---

## 6. Prinzipien für gute Tests

1. **Deterministisch.** Feste Seeds; keine unkontrollierte Abhängigkeit von Netzwerk/Uhrzeit/Zufall.
2. **Isoliert.** Kein hinterlassener Zustand; externe Dienste (Index, LLM) werden gemockt oder über Fixtures bereitgestellt.
3. **Aussagekräftig.** Ein fehlgeschlagener Test benennt die verletzte Erwartung klar.
4. **Reproduzierbar.** Fixtures versioniert; Läufe auf anderen Rechnern wiederholbar.
5. **Nah an der Spezifikation.** Tests prüfen genau die zugesagten Ein-/Ausgaben.
