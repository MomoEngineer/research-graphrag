# MCP-Server lokal in VS Code einbinden

Diese Anleitung beschreibt, wie der MCP-Server von research-graphrag lokal in VS Code eingebunden und über **GitHub Copilot** (Agent-Modus) genutzt wird. VS Code ist dabei nur der Anwendungsrahmen; die eigentliche Fähigkeit stellt der MCP-Server bereit.

> **Status Phase 0:** Der MCP-Server entsteht in **Phase 5** (siehe [Roadmap.md](../Roadmap.md)). Diese Anleitung ist bereits vollständig, damit die Einbindung ohne Reibung erfolgt, sobald `src/research_graphrag/mcp_server/` einen Einstiegspunkt besitzt. Bis dahin wird bewusst **keine** aktive `.vscode/mcp.json` angelegt – ein Eintrag auf einen noch nicht startbaren Server würde beim Start fehlschlagen.

---

## 1. Voraussetzungen

- **VS Code** (aktuell) mit **GitHub Copilot** + **Copilot Chat** (Agent-Modus).
- Eine eingerichtete virtuelle Umgebung `.venv` (siehe [README.md](../README.md) und [ADR 0002](adr/0002-venv-and-offline-dependency-strategy.md)).

---

## 2. Grundprinzip: Transport `stdio`

- VS Code **startet den Server als lokalen Unterprozess**.
- Kommunikation über Standard-Input/Output – **kein Netzwerk, keine offenen Ports**.
- Copilot entdeckt im Agent-Modus die Tools/Resources und ruft sie selbstständig auf (beim ersten Start ein **Trust-Prompt**).

---

## 3. Einbindung über `.vscode/mcp.json` (mit venv-Interpreter)

Damit der Serverprozess die in der `.venv` verfügbaren Abhängigkeiten (mcp, graphrag, docling …) sieht, zeigt `command` auf den **venv-Interpreter** – **nicht** auf ein globales `python`:

```jsonc
{
  "servers": {
    "research-graphrag": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "research_graphrag.mcp_server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "RESEARCH_GRAPHRAG_WORKSPACE_ROOTS": "${workspaceFolder}",
        "RESEARCH_GRAPHRAG_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

- **Windows:** `.venv/Scripts/python.exe`. Unter Linux/macOS: `.venv/bin/python`.
- **Warum der venv-Pfad?** Das Vorbild-Repo `mcs-copilot-tools` nutzt `"command": "python"`, weil es bewusst gegen das System-WinPython **ohne** venv läuft. research-graphrag nutzt eine venv (Isolation) – daher muss der Interpreterpfad explizit auf die venv zeigen, sonst startet der Server ohne die installierten Pakete (`ModuleNotFoundError`).
- **`cwd`:** Repository-Wurzel, damit der Modul-Import `research_graphrag.mcp_server` auflöst.

> **Secrets:** Keine Tokens/Keys in `mcp.json`. Die Standard-Generierung läuft secret-frei über die LLM-Bridge (MCP-Sampling, [ADR 0004](adr/0004-llm-bridge-via-mcp-sampling.md)). Sensible Werte – falls je nötig – über VS-Code-Inputs oder `.env`, nie committen.

---

## 4. Server aktivieren und prüfen

1. `.vscode/mcp.json` speichern (ab Phase 5).
2. Copilot-Chat öffnen und in den **Agent-Modus** wechseln.
3. In der Werkzeug-/Tools-Auswahl prüfen, ob die Tools gelistet werden: `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper`, `list_topics`.
4. Bei Problemen: `MCP: List Servers` → Server auswählen → `Show Output` (Startfehler des Prozesses prüfen).

Ist der Server korrekt eingebunden, ruft Copilot die Tools im Agent-Modus selbstständig auf und erhält belegte Antworten mit Provenienz.

---

## 5. Optional: Transport HTTP/SSE

Nur relevant, wenn der Server **ausdrücklich** zentral (für mehrere Personen) betrieben wird. Dann statt `command`/`args` eine URL (`"type": "http"`). Ein solcher Betrieb ist **ADR-pflichtig**. Für die normale lokale Arbeit gilt `stdio`.

---

## 6. Fehlerbehebung (Kurzreferenz)

| Symptom | Mögliche Ursache | Prüfen |
| --- | --- | --- |
| Server erscheint nicht in der Tool-Liste | `mcp.json` fehlerhaft oder Prozess startet nicht | JSON-Syntax, `command`/`cwd`, MCP-Output-Log |
| `ModuleNotFoundError` beim Start | Falscher Interpreter (nicht die venv) oder falsches `cwd` | venv-Pfad in `command`, `cwd = ${workspaceFolder}`, lief `pip install -e .`? |
| Tools gelistet, aber Aufruf schlägt fehl | Laufzeitfehler im Tool | Server-Log, zugehöriges Test-Skript ausführen |
| Copilot nutzt die Tools nicht | Agent-Modus/Trust | Agent-Modus aktiv? Server vertraut (`MCP: Reset Trust`)? |
