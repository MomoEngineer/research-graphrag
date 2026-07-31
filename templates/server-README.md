# MCP-Server: research-graphrag

> Vorlage für die README des MCP-Servers. Die endgültige Fassung entsteht in **Phase 5**
> unter `src/research_graphrag/mcp_server/README.md`.

## Zweck

Stellt Retrieval über den GraphRAG-Index als MCP-Tools bereit – jede Antwort mit
Provenienz (Paper, Abschnitt, Seite/Chunk).

## Enthaltene Tools

| Tool | Schicht | Spezifikation | Code-Walkthrough |
| --- | --- | --- | --- |
| `search_local` | Retrieval | specs/search_local.md | specs/search_local.code.md |
| `search_global` | Retrieval | specs/search_global.md | specs/search_global.code.md |
| `search_drift` | Retrieval | specs/search_drift.md | specs/search_drift.code.md |
| `search_basic` | Retrieval | specs/search_basic.md | specs/search_basic.code.md |
| `get_paper` | Ingestion / Provenienz | specs/get_paper.md | specs/get_paper.code.md |
| `list_topics` | Übersicht | specs/list_topics.md | specs/list_topics.code.md |

## Abhängigkeiten

- Python ≥ 3.11 (WinPython-Basis: 3.13), `mcp` (SDK).
- Pipeline-Stack (`graphrag`, `docling`, `lancedb`) über das Extra `[pipeline]`.

## Start (Transport `stdio`)

```pwsh
python -m research_graphrag.mcp_server
```

## Einbindung in VS Code

Siehe [docs/vscode-integration.md](../docs/vscode-integration.md) – `command` zeigt auf den
**venv-Interpreter** (`${workspaceFolder}/.venv/Scripts/python.exe`).

## Konfiguration (Umgebungsvariablen)

| Variable | Zweck | Pflicht | Default |
| --- | --- | --- | --- |
| `RESEARCH_GRAPHRAG_WORKSPACE_ROOTS` | Erlaubte Datei-Roots (Sicherheitsgrenze) | ja (für Datei-Zugriff) | – |
| `RESEARCH_GRAPHRAG_LOG_LEVEL` | Log-Niveau (stderr) | nein | `INFO` |

## Tests

```pwsh
python -m pytest tests/mcp_server
```

## Zugehörige ADRs

- [ADR 0004](../docs/adr/0004-llm-bridge-via-mcp-sampling.md) (LLM-Bridge),
  [ADR 0005](../docs/adr/0005-graphrag-index-backend-open.md) (Index-Backend, offen).
