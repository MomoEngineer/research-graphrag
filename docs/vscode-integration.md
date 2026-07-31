# MCP-Server lokal in VS Code einbinden

Diese Anleitung beschreibt, wie der MCP-Server von research-graphrag lokal in VS Code eingebunden und über **GitHub Copilot** (Agent-Modus) genutzt wird. VS Code ist dabei nur der Anwendungsrahmen; die eigentliche Fähigkeit stellt der MCP-Server bereit.

> **Status:** ✅ **Phase 5 umgesetzt** – der MCP-Server ist lauffähig (`python -m research_graphrag.mcp_server`) und die aktive [`.vscode/mcp.json`](../.vscode/mcp.json) ist angelegt ([ADR 0009](adr/0009-mcp-server-stdio-phase5.md)). **Phase 6** härtet den On-Read-Zugriff (atomarer Index-Swap) und ergänzt read-only Status-/QS-Skripte ([ADR 0010](adr/0010-drop-in-workflow-and-qa-phase6.md)). Diese Anleitung beschreibt die Einbindung; folge ihr, um die Werkzeuge im Copilot-Agent-Modus zu nutzen.

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

Damit der Serverprozess die in der `.venv` verfügbaren Abhängigkeiten (mcp, scikit-learn, networkx, pypdf …) sieht, zeigt `command` auf den **venv-Interpreter** – **nicht** auf ein globales `python`:

```jsonc
{
  "servers": {
    "research-graphrag": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "research_graphrag.mcp_server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "RESEARCH_GRAPHRAG_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

- **Windows:** `.venv/Scripts/python.exe`. Unter Linux/macOS: `.venv/bin/python`.
- **Warum der venv-Pfad?** Das Vorbild-Repo `mcs-copilot-tools` nutzt `"command": "python"`, weil es bewusst gegen das System-WinPython **ohne** venv läuft. research-graphrag nutzt eine venv (Isolation) – daher muss der Interpreterpfad explizit auf die venv zeigen, sonst startet der Server ohne die installierten Pakete (`ModuleNotFoundError`).
- **`cwd`:** Repository-Wurzel, damit der Modul-Import `research_graphrag.mcp_server` auflöst.
- **Umgebungsvariablen (optional):** `RESEARCH_GRAPHRAG_INDEX` setzt den Index-Pfad (Default `data/index/index.sqlite` relativ zu `cwd`), `RESEARCH_GRAPHRAG_LOG_LEVEL` das stderr-Log-Niveau (Default `INFO`) – vollständige Liste im [Server-README](../src/research_graphrag/mcp_server/README.md).

> **Secrets:** Keine Tokens/Keys in `mcp.json`. Die Tools liefern nur strukturierte Evidenz + Provenienz; ein LLM kommt allein clientseitig (Copilot) ins Spiel ([ADR 0009](adr/0009-mcp-server-stdio-phase5.md), [ADR 0004](adr/0004-llm-bridge-via-mcp-sampling.md)). Sensible Werte – falls je nötig – über VS-Code-Inputs oder `.env`, nie committen.

---

## 4. Server aktivieren und prüfen

1. `.vscode/mcp.json` speichern (bereits angelegt).
2. Copilot-Chat öffnen und in den **Agent-Modus** wechseln.
3. In der Werkzeug-/Tools-Auswahl prüfen, ob die Tools gelistet werden: `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper`, `list_topics`.
4. Bei Problemen: `MCP: List Servers` → Server auswählen → `Show Output` (Startfehler des Prozesses prüfen).

Ist der Server korrekt eingebunden, ruft Copilot die Tools im Agent-Modus selbstständig auf und erhält belegte Antworten mit Provenienz.

> **Frische Artefakte (On-Read):** Der Server hält keinen Index im Speicher, sondern lädt ihn **pro Anfrage** frisch aus `data/index/index.sqlite`. Nach `python -m scripts.ingest` sind neue Paper daher **ohne Server-Neustart** sofort verfügbar; der Index-Neuaufbau erfolgt **atomar** (Build nach `*.sqlite.tmp` + `os.replace`), sodass ein laufender Aufruf nie einen halbfertigen Index sieht ([ADR 0010](adr/0010-drop-in-workflow-and-qa-phase6.md)). Ein schneller Status-/Konsistenz-Überblick: `python -m scripts.status`.

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
