# MCP-Server: research-graphrag

Stellt das Retrieval über den Offline-Hybrid-Index als **MCP-Tools** (Transport `stdio`) für
GitHub Copilot bereit – jede Antwort mit **Provenienz** (Paper · Abschnitt · Seite/Chunk).
Die Tools liefern **strukturierte Evidenz**; die natürlichsprachige Antwort formuliert der
aufrufende Agent selbst (kein serverseitiges LLM-Sampling, siehe
[ADR 0009](../../../docs/adr/0009-mcp-server-stdio-phase5.md)).

## Enthaltene Tools

| Tool | Schicht | Spezifikation |
| --- | --- | --- |
| `search_basic` | Retrieval – exakte Fakten | [specs/search_basic.md](specs/search_basic.md) |
| `search_local` | Retrieval – Detailfrage & Multi-Hop | [specs/search_local.md](specs/search_local.md) |
| `search_global` | Retrieval – Cross-Paper-Synthese | [specs/search_global.md](specs/search_global.md) |
| `search_drift` | Retrieval – Widersprüche & Vergleiche | [specs/search_drift.md](specs/search_drift.md) |
| `get_paper` | Katalog / Provenienz | [specs/get_paper.md](specs/get_paper.md) |
| `list_topics` | Übersicht / Katalog | [specs/list_topics.md](specs/list_topics.md) |

> Code-Walkthroughs werden – wie in Phase 4 – nur für nicht-triviale Tools verlangt; die hier
> registrierten Tools sind dünne Wrapper um die getestete Kernlogik und daher **spec-only**
> (right-sized, siehe [CONTRIBUTING.md](../../../CONTRIBUTING.md)).

## Abhängigkeiten

- Python ≥ 3.11 (WinPython-Basis: 3.13), `mcp` (SDK, inkl. FastMCP).
- Offline-Hybrid-Stack als Kern: `pypdf`, `scikit-learn` (TF-IDF), `networkx`, SQLite (stdlib) –
  Option B, [ADR 0005](../../../docs/adr/0005-graphrag-index-backend-open.md).

## Start (Transport `stdio`)

```pwsh
python -m research_graphrag.mcp_server
```

## Einbindung in VS Code

Siehe [docs/vscode-integration.md](../../../docs/vscode-integration.md) – `command` zeigt auf den
**venv-Interpreter** (`${workspaceFolder}/.venv/Scripts/python.exe`), `cwd` auf die
Repository-Wurzel.

## Konfiguration (Umgebungsvariablen)

| Variable | Zweck | Pflicht | Default |
| --- | --- | --- | --- |
| `RESEARCH_GRAPHRAG_INDEX` | Pfad zur SQLite-Index-Datei | nein | `data/index/index.sqlite` |
| `RESEARCH_GRAPHRAG_LOG_LEVEL` | Log-Niveau (stderr) | nein | `INFO` |

> **Keine** Pfad-Root-Grenze (`RESEARCH_GRAPHRAG_WORKSPACE_ROOTS`) nötig: kein Tool nimmt einen
> nutzergesteuerten Datei-Pfad entgegen (nur `query`/`paper_id`), siehe
> [ADR 0009](../../../docs/adr/0009-mcp-server-stdio-phase5.md).
>
> **Secrets:** keine – die Tools liefern nur Evidenz + Provenienz; ein LLM kommt allein zur
> Abfragezeit über den Client (Copilot) ins Spiel ([ADR 0004](../../../docs/adr/0004-llm-bridge-via-mcp-sampling.md)).

## Fehlerverhalten

Fachliche Fehler werden an der Server-Grenze in eine strukturierte Ausgabe mit `isError = true`
übersetzt (`content` = JSON-Text, `structuredContent` = `{"error": {code, message[, details]}}`),
siehe [docs/error-model.md](../../../docs/error-model.md).

## Tests

```pwsh
python -m pytest tests/mcp_server
```

## Zugehörige ADRs

- [ADR 0009](../../../docs/adr/0009-mcp-server-stdio-phase5.md) (MCP-Server Phase 5),
  [ADR 0008](../../../docs/adr/0008-retrieval-and-query-router-phase4.md) (Retrieval-Modi),
  [ADR 0004](../../../docs/adr/0004-llm-bridge-via-mcp-sampling.md) (LLM-Bridge),
  [ADR 0005](../../../docs/adr/0005-graphrag-index-backend-open.md) (Index-Backend).
