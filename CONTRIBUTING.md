# Contributing zu Research-GraphRAG

Dieses Dokument ist das zentrale Regelwerk für die Arbeit am Repository **Research-GraphRAG**. Es beschreibt, *wie* im Repo gearbeitet wird und *welche Anforderungen* an Code, Dokumentation und den künftigen MCP-Server gestellt werden.

> Research-GraphRAG ist ein **persönliches Forschungswerkzeug** (siehe [README.md](README.md)). Der Anspruch an Nachvollziehbarkeit und Reproduzierbarkeit ist bewusst hoch – die Prozessschärfe ist aber **right-sized**: schwergewichtige Formalien (z. B. ein hartes Coverage-Gate) werden nur dort verlangt, wo sie realen Nutzen stiften. Vorbild für Struktur und Disziplin ist das Repo `mcs-copilot-tools`.

---

## 1. Leitprinzipien

1. **Provenienz zuerst.** Jede abgeleitete Antwort ist auf Paper/Abschnitt/Seite rückführbar.
2. **Nachvollziehbarkeit vor Tempo.** Nicht-triviale Entscheidungen werden dokumentiert (ADR, Docstring, Commit).
3. **Reproduzierbarkeit.** Versionen werden über ein Lockfile fixiert; Seeds/Läufe werden festgehalten, wo Ergebnisse variieren.
4. **Offline-bewusst.** Die Entwicklung erfolgt in einem Umfeld ohne PyPI-Zugang; es werden nur beschaffbare Werkzeuge vorausgesetzt (siehe [ADR 0002](docs/adr/0002-venv-and-offline-dependency-strategy.md) und [ADR 0003](docs/adr/0003-offline-test-and-coverage-tooling.md)).
5. **Lokal zuerst.** Der MCP-Server wird lokal per `stdio` in VS Code eingebunden und von Copilot genutzt.
6. **Klein, aber wachstumsfähig.** Optimiert für ≤ 500 Paper mit klaren Erweiterungspfaden (siehe [Roadmap.md](Roadmap.md)).

---

## 2. Weiterführende Dokumente

| Dokument | Inhalt |
| --- | --- |
| [docs/vscode-integration.md](docs/vscode-integration.md) | Einbindung des MCP-Servers in VS Code + Copilot (mit venv-Interpreter) |
| [docs/repository-structure.md](docs/repository-structure.md) | Verbindliche Ordnerstruktur und Definition of Done |
| [docs/testing.md](docs/testing.md) | Teststrategie (offline-tauglich) |
| [docs/documentation-standards.md](docs/documentation-standards.md) | Docstrings, Typing, Spezifikation, Provenienz, Reproduzierbarkeit, Secrets, Logging |
| [docs/error-model.md](docs/error-model.md) | Fehler-/Error-Modell (Fehlertaxonomie) |
| [docs/glossary.md](docs/glossary.md) | Glossar zentraler Fachbegriffe |
| [docs/adr/README.md](docs/adr/README.md) | Prozess für Architecture Decision Records |
| [templates/tool-spec.md](templates/tool-spec.md) | Vorlage Pro-Tool-Spezifikation |
| [templates/tool-code-walkthrough.md](templates/tool-code-walkthrough.md) | Vorlage Code-Walkthrough |
| [templates/server-README.md](templates/server-README.md) | Vorlage Server-README |
| [templates/adr-template.md](templates/adr-template.md) | Vorlage ADR |

---

## 3. Technischer Stack

- **Primärsprache: Python** (WinPython-Basis: 3.13; Mindestversion 3.11, daher `requires-python = ">=3.11"`).
- **MCP-Server** mit dem offiziellen **MCP Python SDK** (`mcp`, inkl. FastMCP), Transport `stdio`.
- **PDF-Extraktion:** `pypdf` (Offline-Hybrid, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)); Docling/Marker als späterer Ausbau, falls offline beschaffbar.
- **Index & Retrieval:** Offline-Hybrid – TF-IDF (`scikit-learn`) + handimplementiertes BM25 mit Rang-Fusion (`numpy`, [ADR 0014](docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)) + `networkx`/Louvain + SQLite ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)).
- **Tests:** `pytest`; asynchrone Tests über das `anyio`-Plugin (offline, siehe [ADR 0003](docs/adr/0003-offline-test-and-coverage-tooling.md)).
- **Statische Qualität:** `ruff` (Lint + Format) und `mypy` (Typen).
- **Dependencies/Lockfile:** `pip` + `requirements.lock` (Offline-Kompromiss, [ADR 0002](docs/adr/0002-venv-and-offline-dependency-strategy.md)). `uv` ist das bevorzugte Ziel, sobald ein Mirror verfügbar ist.
- **LLM/Embeddings:** LLM-Bridge über MCP-Sampling (Client-Modell) zur Abfragezeit; Index-Backend als Offline-Hybrid entschieden ([ADR 0004](docs/adr/0004-llm-bridge-via-mcp-sampling.md), [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)).

Alle Werkzeuge werden über `python -m <tool>` gestartet (WinPython ohne Konsolenskripte im `PATH`).

---

## 4. Arbeitsablauf (phasenorientiert)

Die Umsetzung folgt der [Roadmap.md](Roadmap.md) (Phasen 0–7). Für neuen Code gilt:

1. **Entscheidung dokumentieren**, falls architektonisch relevant (ADR, siehe [docs/adr/README.md](docs/adr/README.md)).
2. **Spezifikation vor Code** für jedes MCP-Tool ([templates/tool-spec.md](templates/tool-spec.md)) – das Input-/Output-Schema ist die Single Source of Truth.
3. **Tests früh** (Contract-/Funktions-/Fehler-Tests, siehe [docs/testing.md](docs/testing.md)), sobald ein Tool-Skeleton existiert.
4. **Implementieren**, bis die Tests grün sind.
5. **Dokumentieren** (Docstrings, Tool-Spec, Code-Walkthrough), siehe [docs/documentation-standards.md](docs/documentation-standards.md).
6. **Definition of Done prüfen** (Abschnitt 5).

---

## 5. Definition of Done (right-sized)

Ein Beitrag gilt als fertig, wenn die **zutreffenden** Punkte erfüllt sind:

- [ ] Vollständige Type-Hints; `python -m mypy src` ohne Fehler.
- [ ] `python -m ruff check .` und `python -m ruff format --check .` ohne Befunde.
- [ ] Docstrings für alle öffentlichen Funktionen/Tools.
- [ ] Tests vorhanden und grün (`python -m pytest tests`).
- [ ] Für MCP-Tools: Tool-Spezifikation + Code-Walkthrough vorhanden und aktuell.
- [ ] Zeilenabdeckung als **Richtwert ≥ 80 %** pro Kernmodul (`python -m scripts.coverage_offline`) – bewusste Unterschreitungen werden kurz begründet.
- [ ] Provenienz-Angaben, wo Ergebnisse abgeleitet werden.
- [ ] Reproduzierbarkeit sichergestellt (Seeds/Versionen dokumentiert, wo relevant).
- [ ] Bei Architekturentscheidungen: ADR angelegt.

> **Right-sizing:** Anders als im Vorbild-Repo ist die 80-%-Abdeckung ein **Richtwert**, kein hartes Gate, und ein Code-Walkthrough wird nur für nicht-triviale Tools verlangt. Das entspricht dem Charakter als persönliches Werkzeug (README, Abschnitt „Qualitätssicherung").

---

## 6. Qualitäts-Checks lokal ausführen

```pwsh
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest tests -q
python -m scripts.coverage_offline
```

> **venv-Aufruf (offline):** Die Befehle laufen über den venv-Interpreter (`.\.venv\Scripts\python.exe -m …`). Da die `--system-site-packages`-venv die Konsolen-Launcher der WinPython-Basis nicht erbt, wird der `ruff`-Launcher einmalig nach `.venv\Scripts\ruff.exe` kopiert (siehe [ADR 0003](docs/adr/0003-offline-test-and-coverage-tooling.md)); `mypy`/`pytest`/Coverage funktionieren ohne diesen Schritt.

---

## 7. Sprache der Dokumentation

Dokumentation und Kommentare werden auf **Deutsch** verfasst (konsistent zu [README.md](README.md) und [Roadmap.md](Roadmap.md)); etablierte englische Fachbegriffe (Transport, Retrieval, Embedding …) bleiben unübersetzt. Code-Bezeichner (Funktions-, Variablennamen) sind englisch.
