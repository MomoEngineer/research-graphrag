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
├─ test_intake.py         # Korpus-Intake: Prüfstufen, --dry-run, Idempotenz (Phase 8)
├─ test_keywords.py       # kuratierte Keyword-Politik (Phase 7 / A5)
├─ test_pipeline.py       # Drop-in-Ingestion
├─ extraction/            # Extraktion: pdf/normalization/structure/chunking/quality (Phase 2, 7 / A5)
├─ indexing/              # Index (0b) + BM25/Fusion (Phase 7 / A4) + Graph/Communities (Phase 3) + Zitationsgraph (Phase 7)
├─ retrieval/            # Basic/Local/Global/DRIFT + Router + Provenienz + get_paper/get_citations + QS-Harness (Phase 4/5/6/7)
├─ overview/              # Übersicht-Entwürfe (Phase 2, 8)
├─ generation/            # LLM-Bridge: Port, Evidenz, Synthese, CLI-Pfad (Phase 7 / A1)
├─ evaluation/            # Gold-Set, Kennzahlen, Modus-Lauf, Baseline, Ausgabe (Phase 7 / A4 + A6) + Router-Contract (A7)
├─ online/               # Transport-Port, Quellen-Adapter, Dedup, Bericht, CLI (Phase 9 / S1)
├─ integration/           # End-to-End-Durchstich (M1) + Drop-in-Freshness/atomarer Swap (Phase 6) + Status (Phase 7)
└─ mcp_server/            # (Phase 5) Server-Contract via In-Memory-Client (test_server.py)
```

> **Aktueller Stand (Phase 9 / S1):** Die Kernmodule (`errors`, `extraction/*` inkl. `model`/`structure`/`chunking`/`quality`, `indexing` inkl. `bm25`/`fusion`/`graph_index`/`citation_graph`, `retrieval/*` inkl. `basic`/`local`/`global_search`/`drift`/`router`/`provenance`/`paper`/`citations`, `generation/*` inkl. `provider`/`synthesis`/`evidence`/`answer`, `evaluation/*` inkl. `gold`/`metrics`/`runner`/`baseline`/`routing`/`report`, `online/*` inkl. `transport`/`sources`/`candidates`/`search`/`report`, `intake`, `overview`, `pipeline`, `mcp_server/server`/`sampling`) sind mit Funktions-, Fehler-, Contract- und Property-Tests abgedeckt (Kernmodule ≥ 85 % Zeilenabdeckung, retrieval- und evaluation-Module 100 %; **567 Tests**). Der **Contract-Test** (Abschnitt 2.1) ist umgesetzt: ein **In-Memory-Client-Roundtrip** (`tests/mcp_server/test_server.py`) prüft alle acht Tools über das echte MCP-Protokoll (Erfolg + strukturierte Fehlerausgabe) – inklusive eines **echten Sampling-Roundtrips** für `answer_question` (Sampling-Callback als Client-Modell-Attrappe) und der sichtbaren Degradation ohne Sampling-Fähigkeit. **Phase 6** ergänzt einen **Freshness-/Atomaritäts-Regressionstest** (`tests/integration/test_phase6_freshness.py`: neue PDF → `ingest` → On-Read liefert sie sofort; unveränderte übersprungen; ein fehlgeschlagener Re-Index lässt den Alt-Index intakt) und eine **QS-Harness-Regression** (`tests/retrieval/test_qa.py`: das feste Prüf-Fragen-Set liefert wohlgeformte Provenienz). **Phase 7** ergänzt die Zitationsgraph-Tests (`tests/indexing/test_citation_graph.py`, `tests/retrieval/test_citations.py`), eine Status-Regression (`tests/integration/test_status.py`), die Synthese-Tests (`tests/generation/`), eine **Konsolen-Encoding-Regression** (`tests/integration/test_cli_encoding.py`: die CLI-Skripte laufen auch bei cp1252-Ausgabe durch) sowie die **Chunking-Verfeinerung** (`tests/extraction/test_structure.py`: Reject-Regeln und Section-Absorption inkl. Schutz des Referenzabschnitts; `tests/extraction/test_chunking.py`: Seiten-Range statt Seitengrenze). **Phase 7 / A4** ergänzt die Wertungs-Tests (`tests/indexing/test_bm25.py`: Term-Sättigung, Längennormalisierung, positive IDF; `tests/indexing/test_fusion.py`: RRF-Formel und Fusionsverhalten; `tests/indexing/test_tfidf_index.py`: **Äquivalenz des TF-IDF-Raums zum früheren `TfidfVectorizer`**, Wertungs-Varianten, Determinismus) und den Eval-Harness (`tests/retrieval/test_eval_retrieval.py`: mechanische Label-Ableitung, Hit@k/MRR, Gold-Set-Integrität).

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

> **Phase 8** ergänzt `tests/test_intake.py` (Korpus-Zufluss) und erweitert
> `tests/overview/test_drafts.py`. Zwei Zusicherungen sind hier wichtiger als die Abdeckung:
> **`--dry-run` verändert nichts** – belegt über ein Hash-Abbild des gesamten Arbeitsbaums vor und
> nach dem Lauf – und die **kuratierten Übersicht-Zeilen bleiben byte-identisch**, geprüft über
> `read_bytes()` und nicht über den Textinhalt (unter Windows würde ein textbasiertes Schreiben
> alle Zeilenenden austauschen). Dazu kommen die drei Prüfstufen mit ihren **unterschiedlichen**
> Konsequenzen (der Titel-Verdacht darf nachweislich **nicht** löschen), die Idempotenz eines
> zweiten Laufs, die beiden Härtungen des Identifikator-Vergleichs (nicht belegter und
> mehrdeutiger Wert) sowie das Robustheits-Gate für Dateien ohne PDF-Signatur und für nicht
> parsebare PDFs ([ADR 0019](adr/0019-corpus-intake-new-papers-phase8.md)).

> **Phase 9 / S1** ergänzt den Testbaum `tests/online/`. Die Leitidee ist, dass **kein Test das
> Netz berührt**: Der Transport liegt hinter einem Port, den die Tests durch einen Fake ersetzen,
> und die Quellen-Antworten sind Fixtures, die die **Struktur** der realen APIs nachbilden
> (Namensräume, invertierter Abstract-Index) – mit erfundenen Inhalten, denn fremde Abstracts
> gehören nicht in ein Repository. Besonderes Gewicht liegt auf zwei Punkten: der
> **quellenübergreifenden Dublettenerkennung** (dasselbe Paper aus arXiv und OpenAlex unter
> verschiedenen Identifikatoren) und der **Entschärfung fremder Inhalte** – ein als Titel
> geschmuggelter Markdown-Link, Tabellen-Pipes, Zeilenumbrüche und Steuerzeichen dürfen die
> Berichtstruktur nicht verändern. Dazu kommen die Grenzen des Transports (fremdes URL-Schema,
> Größenlimit, defektes Chunking) und der Nachweis, dass ein Fehler **sauber** endet: klare
> Meldung mit Fehlerkategorie statt Stacktrace.
>
> **Bewusste Ausnahme beim Coverage-Richtwert:** `online/transport.py` liegt darunter, weil der
> Socket-, TLS- und SSPI-Pfad plattform- und netzgebunden ist. Getestet ist alles, was ohne
> Verbindung prüfbar ist; der Rest wäre nur mit echtem Netz messbar und damit kein Offline-Test
> ([ADR 0020](adr/0020-online-candidate-search-phase9.md)).

> **Phase 10 / V1** erweitert `tests/retrieval/test_local.py` um die Multi-Seed-Semantik. Zwei
> Zusicherungen tragen dabei mehr als die reine Abdeckung: dass die Seeds **exakt** die Top-*m*
> der Chunk-Wertung sind (der Modus erfindet keinen eigenen Anker) und dass `seeds = 1` die
> Nachbarschaft von **vor** der Umstellung reproduziert – die Rang-Fusion über eine einzelne
> Teilrangliste darf deren Reihenfolge nicht verändern. Dazu kommen der Ausschluss der Seeds aus
> der Nachbarschaft (kein Beleg doppelt), die Deckelung durch `k` **über alle** Seeds hinweg und
> die Verankerung des Fan-outs am ersten Seed. Der Schema-Bruch `seed` → `seeds` ist zusätzlich
> am MCP-Werkzeug abgesichert ([ADR 0021](adr/0021-local-multi-seed-phase10.md)).

> **Phase 10 / V2** erweitert `tests/retrieval/test_drift.py`. Der aufwendigste Teil ist das
> **Fixture für den Fallback**: Gebraucht wird ein Term, der im Chunk-Text steht, aber in **keinem**
> Community-Dokument – sonst lässt sich der Rückfall gar nicht auslösen. Er entsteht
> deterministisch aus zwei bekannten Regeln (Keywords sind auf die zehn bestbewerteten Terme
> begrenzt mit alphabetischem Tie-Break; die Summary ist der Auszug des **ersten** Chunks) und ist
> im Testmodul begründet. Abgesichert werden außerdem: die Belege des Fallbacks sind **identisch**
> zu denen der Basic-Suche, die Auswahl entspricht **exakt** dem Global-Ranking, ein fehlender
> Graph führt weiterhin zu `constraint_violation` (der Fallback verdeckt keinen defekten Index),
> und `communities = 1` reproduziert das Verhalten von vor V2
> ([ADR 0022](adr/0022-drift-community-union-and-fallback-phase10.md)).

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
