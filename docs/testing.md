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
├─ test_pipeline.py       # Drop-in-Ingestion
├─ extraction/            # Extraktion: pdf/structure/chunking/quality (Phase 2)
├─ indexing/              # TF-IDF/SQLite-Index (0b)
├─ retrieval/             # Basic Search (0b)
├─ overview/              # Übersicht-Entwürfe (Phase 2)
├─ integration/           # End-to-End-Durchstich (M1)
└─ mcp_server/            # (Phase 5) je Tool ein test_<tool>.py
```

> **Aktueller Stand (Phase 2):** Die Kernmodule (`errors`, `extraction/*` inkl. `model`/`structure`/`chunking`/`quality`, `indexing`, `retrieval`, `overview`, `pipeline`) sind mit Funktions-, Fehler- und Property-Tests abgedeckt (Kernmodule ≥ 96 % Zeilenabdeckung, Richtwert erfüllt). Der **Contract-Test** (Abschnitt 2.1) greift ab Phase 5, sobald die Tools über MCP registriert sind.

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
