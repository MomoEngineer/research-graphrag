# Dokumentationsstandards

Dieses Dokument definiert die Anforderungen an die Dokumentation von Code und Ergebnissen. Ziel ist durchgängige **Nachvollziehbarkeit, Wartbarkeit und Provenienz**. Right-sized für ein persönliches Werkzeug (siehe [CONTRIBUTING.md](../CONTRIBUTING.md)).

---

## 1. Docstrings und Typing

- **Type-Hints sind Pflicht** für alle öffentlichen Funktionen, Tools und Rückgabewerte. `python -m mypy src` muss ohne Fehler durchlaufen.
- **Docstrings sind Pflicht** für jedes öffentlich bereitgestellte MCP-Tool sowie für öffentliche Funktionen und Klassen.
- Ein Tool-Docstring enthält mindestens: **Zweck** (ein Satz, dient zugleich als MCP-Tool-Beschreibung), **Parameter**, **Rückgabe**, **Fehler/Grenzen**.
- Stil: einheitlich (empfohlen: Google-Stil), konsistent über das Repo.

```python
def search_local(
    db_path: str | Path, query: str, *, k: int = 5, fan_out: int = 5
) -> LocalSearchResult:
    """Beantwortet eine Detail-/Netz-Frage über Local Search mit Provenienz.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        query: Natürlichsprachige Frage zu einem Paper/Abschnitt (nicht leer).
        k: Maximale Zahl der Chunk-Nachbarn (> 0).
        fan_out: Maximale Zahl der Graph-Nachbarpaper (>= 0).

    Returns:
        LocalSearchResult mit Seed, Chunk-Nachbarschaft und Paper-Fan-out (je mit
        Provenienz: Paper-ID, Abschnitt, Seite/Chunk).

    Raises:
        DomainError: `invalid_input` bei leerer Frage/`k <= 0`/`fan_out < 0`;
            `not_found`, wenn kein Index existiert; `constraint_violation` ohne Chunks/Graph.
    """
```

---

## 2. Pro-Tool-Spezifikation und Modul-Dokumentation

- Jedes **nicht-triviale** MCP-Tool besitzt eine Spezifikation nach [templates/tool-spec.md](../templates/tool-spec.md) unter `src/research_graphrag/mcp_server/specs/<tool>.md`. Das Input-/Output-Schema ist die Single Source of Truth für Tests und Contract-Checks; die Spezifikation entsteht **vor** dem Code.
- Ergänzend erklärt eine **Modul-Doku** ([templates/module-doc.md](../templates/module-doc.md)) die **Funktionsweise** des Codes (das *Wie*), abgelegt als `src/research_graphrag/<paket>/doc/<modul>.md` (Top-Level-Module unter `src/research_graphrag/doc/`). Sie tritt an die Stelle des früheren Code-Walkthroughs `<tool>.code.md`, weil die Logik in Modulen liegt und der Server nur dünne Wrapper registriert ([ADR 0018](adr/0018-code-documentation-architecture.md)).
- **Diagramme:** bevorzugt **Mermaid** (rendern ohne Zusatzwerkzeuge in der Markdown-Vorschau). Pflicht bei mehrstufigem Ablauf; reine Datentyp-/Konstanten-Module dokumentieren ihre Schnittstelle tabellarisch.
- Bei Abweichung zwischen Spec und Code gilt die **Spec als verbindlicher Contract**; die Modul-Doku ist **beschreibend** und wird im Konfliktfall korrigiert.
- Die funktionale Landkarte [docs/features.md](features.md) und das Konzeptdokument [docs/funktionsweise.md](funktionsweise.md) ergänzen die Modul-Ebene; ihre Abgrenzung regelt [ADR 0018](adr/0018-code-documentation-architecture.md).

---

## 3. Architecture Decision Records (ADRs)

Architektur- und Grundsatzentscheidungen werden als ADR festgehalten (Prozess/Vorlage: [docs/adr/README.md](adr/README.md), [templates/adr-template.md](../templates/adr-template.md)).

ADR-pflichtig sind u. a.:

- Einführung/Wechsel eines schweren Backends (Extraktion, Index, Vektor-Store),
- Wechsel der Extraktions-/Index-/Retrieval-Strategie,
- Wahl einer anderen Programmiersprache als Python,
- Betrieb des Servers über HTTP/SSE statt `stdio`,
- bewusst in Kauf genommene Redundanz.

---

## 4. Reproduzierbarkeit

- **Feste Seeds** für alle stochastischen Prozesse.
- **Versionspinning** über Lockfile (`pip` + `requirements.lock`, [ADR 0002](adr/0002-venv-and-offline-dependency-strategy.md)).
- **Lauf-Metadaten** festhalten, wo Ergebnisse variieren: Backend-/Modell-ID, Prompt-/Tool-Version, Seed, Zeitstempel.
- Ergebnisse müssen mit denselben Eingaben und Versionen wiederholbar sein.

### 4.1 Tool-Versionierung

- Jedes MCP-Tool trägt eine **semantische Version** (`MAJOR.MINOR.PATCH`) in seiner Tool-Spezifikation und exponiert sie über MCP.
- **MAJOR** bei nicht abwärtskompatibler Schema-Änderung, **MINOR** bei abwärtskompatibler Erweiterung, **PATCH** bei internen Korrekturen.

---

## 5. Provenienz

Tools, die Ergebnisse ableiten, liefern deren Herkunft mit – das ist das **Kernprinzip** des Projekts (README, „Kernidee"):

- **Paper-ID**, **Abschnitt**, **Seite/Chunk** (ggf. Bounding-Box),
- Quell-URI / Datei-Hash, wo zutreffend,
- **Evidenz-/Score**, sofern vorhanden.

So bleibt jede Aussage bis zur Originalstelle rückführbar; Antworten werden nie ohne Quellenanker geliefert.

---

## 6. Server- und Repo-Dokumentation

- Der MCP-Server hat eine README nach [templates/server-README.md](../templates/server-README.md): enthaltene Tools, Startbefehl, Abhängigkeiten, Einbindung.
- Änderungen an Tools werden in Tool-Spezifikation und Server-README nachgeführt.
- Dokumentation auf **Deutsch**; etablierte englische Fachbegriffe bleiben unübersetzt, Code-Bezeichner sind englisch.

---

## 7. Fehlerverhalten

Das verbindliche Fehler-/Error-Modell (Fehlertaxonomie, strukturierte MCP-Fehlerausgabe) ist in [error-model.md](error-model.md) beschrieben. Jede Tool-Spezifikation verweist auf die dort definierten Fehlerkategorien.

---

## 8. Konfiguration und Secrets

- Server-/Tool-Konfiguration wird über **Umgebungsvariablen** bezogen; sichere Defaults in der Server-README dokumentieren.
- **Keine Secrets** (Tokens, Passwörter, API-Keys) in Code, Tool-Spec, README oder `.vscode/mcp.json`. Die Standard-Generierung ist secret-frei (LLM-Bridge, [ADR 0004](adr/0004-llm-bridge-via-mcp-sampling.md)).
- Ein Tool **darf nicht** auf Ressourcen außerhalb der erlaubten Workspace-Roots zugreifen.

---

## 9. Logging und Beobachtbarkeit (Baseline)

- Logging über das Standard-`logging`-Modul auf **stderr** (nie auf stdout – bei `stdio` ist stdout dem MCP-Protokoll vorbehalten).
- **Keine Secrets und keine sensiblen Nutzdaten** im Log.
- Empfohlenes Standardniveau `INFO`, konfigurierbar über `RESEARCH_GRAPHRAG_LOG_LEVEL`.
- Fehler werden mit der Fehlerkategorie aus [error-model.md](error-model.md) geloggt (konsistent zur MCP-Fehlerausgabe).
