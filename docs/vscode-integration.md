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

> **Antwort-Synthese (opt-in):** `answer_question` kann mit `synthesize = true` die Antwort über **MCP-Sampling** vom Modell des Clients formulieren lassen. VS Code fragt dafür um Zustimmung und lässt die Modellwahl zu; unterstützt der Client kein Sampling, liefert das Tool weiterhin die vollständige Evidenz mit `generated = false` ([ADR 0012](adr/0012-llm-bridge-and-answer-synthesis-phase7.md)). Für Copilot ist der Default (`synthesize = false`) der empfohlene Weg – er vermeidet eine doppelte Generierung.

> **Nachvollziehbare Modus-Wahl:** Läuft `answer_question` mit `mode = "auto"` (Default), enthält die Antwort das Feld `routing` mit Konfidenzstufe und auslösenden Signalen. Bei `weak` (Gleichstand → Fallback `basic`) oder `none` (kein Signal) lohnt sich häufig ein **expliziter** Modus ([ADR 0017](adr/0017-router-hardening-phase7.md)).

> **Zitieren aus einem Treffer:** Jeder Beleg trägt `identifiers` (DOI/arXiv/URL) und einen `citation_key`; die fertige Angabe in **Harvard** und **APA** liefert `get_reference` bzw. der `references`-Block von `answer_question`. Ist ein Datensatz unvollständig, weisen `missing` und `note` das aus – fehlende Angaben werden nie geraten ([ADR 0025](adr/0025-citable-paper-metadata.md)).

> **Personen recherchieren:** Fragen nach einer Person beginnen mit `search_authors` (Name → Personenschlüssel). Meldet die Antwort `ambiguous = true`, den passenden Kandidaten wählen – gleichnamige Personen werden nie still zusammengeführt. Mit dem Schlüssel liefern `get_author`, `search_author_papers` und `get_author_citations` Profil, Suche und Zitationsnetz. Der Block `coverage` sagt, wie viele Volltexte belegte Autoren tragen; „nicht gefunden“ heißt deshalb nicht „nicht im Korpus“ ([ADR 0043](adr/0043-author-index-and-person-tools.md)).

---

## 4. Server aktivieren und prüfen

1. `.vscode/mcp.json` speichern (bereits angelegt).
2. Copilot-Chat öffnen und in den **Agent-Modus** wechseln.
3. In der Werkzeug-/Tools-Auswahl prüfen, ob die fünfzehn Tools gelistet werden: `search_local`, `search_global`, `search_drift`, `search_basic`, `get_paper`, `get_paper_file`, `get_citations`, `get_reference`, `list_topics`, `answer_question`, `correct_paper_metadata`, `search_authors`, `get_author`, `search_author_papers`, `get_author_citations`.
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
