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
| `get_paper_file` | Katalog / lokaler Dateipfad | [specs/get_paper_file.md](specs/get_paper_file.md) |
| `get_citations` | Graph / Zitationsnetz | [specs/get_citations.md](specs/get_citations.md) |
| `get_reference` | Zitation / Literaturangabe | [specs/get_reference.md](specs/get_reference.md) |
| `list_topics` | Übersicht / Katalog | [specs/list_topics.md](specs/list_topics.md) |
| `answer_question` | Antwort / Synthese | [specs/answer_question.md](specs/answer_question.md) |
| `correct_paper_metadata` | Korrektur / Zitation (**schreibend**) | [specs/correct_paper_metadata.md](specs/correct_paper_metadata.md) |
| `search_authors` | Personen – Name → Personenschlüssel | [specs/search_authors.md](specs/search_authors.md) |
| `get_author` | Personen – Profil | [specs/get_author.md](specs/get_author.md) |
| `search_author_papers` | Personen / Retrieval – Suche in den Papern einer Person | [specs/search_author_papers.md](specs/search_author_papers.md) |
| `get_author_citations` | Personen / Zitationsnetz | [specs/get_author_citations.md](specs/get_author_citations.md) |

> **Sampling nur opt-in:** Alle Evidenz-Tools sind modellfrei. Ausschließlich `answer_question`
> kann mit `synthesize = true` über **MCP-Sampling** eine Antwort vom **Client-Modell**
> formulieren lassen; ohne Sampling-Fähigkeit bleibt `generated = false` und die Evidenz
> vollständig ([ADR 0012](../../../docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md)).

> **Modus-Wahl ist nachvollziehbar:** Wählt `answer_question` den Modus selbst (`mode = "auto"`,
> Default), liefert die Antwort unter `routing` die Begründung mit – Konfidenzstufe
> (`strong`/`weak`/`none`) und auslösende Signale. Bei explizit gewähltem Modus ist das Feld
> `null` ([ADR 0017](../../../docs/adr/0017-router-hardening-phase7.md)).

> **Antworten bleiben unter der 1-MB-Transportgrenze:** Alle Trefferzahl-Parameter (`k`, `n`,
> `fan_out`, `communities`, `limit`) teilen eine Obergrenze `MAX_RESULT_COUNT = 50`
> (`research_graphrag.limits`) und werden bei Überschreitung mit `invalid_input` abgelehnt statt
> still gekürzt. `list_topics` liefert standardmäßig eine gefilterte, membergelöste Übersicht
> (`min_size`/`limit`); die volle Mitgliederliste einer Community liefert `community_id`.
> `_guard` prüft zusätzlich als letzte Absicherung die serialisierte Antwortgröße und meldet
> `constraint_violation`, statt eine übergroße Antwort jemals mitten im Inhalt abzuschneiden
> ([ADR 0037](../../../docs/adr/0037-mcp-tool-response-size-ceiling.md)).

> **`get_paper_file` überträgt keinen Dateiinhalt:** Nur den nativen lokalen Pfad des
> Original-PDFs (kein Datei-Pfad als Eingabe, nur `paper_id`) – konsistent mit der 1-MB-Grenze
> aus ADR 0037. Der Agent liest die Datei selbst weiter. Referenz-Einträge und lokal fehlende
> PDFs sind sichtbar `available = false`, kein Fehler.
>
> **`correct_paper_metadata` ist das erste schreibende Tool** dieser Oberfläche: Es schreibt
> ausschließlich die `manual`-Herkunft nach `metadata/paper_metadata.json` (git-versioniert,
> append-only protokolliert in `data/corrections_log.md`). Die Korrektur wirkt **nicht sofort**
> in den übrigen Tools – erst nach dem nächsten `python -m scripts.ingest`-Lauf, ausgewiesen als
> `effective_after` in der Antwort ([ADR 0039](../../../docs/adr/0039-correction-tool-and-pdf-file-access.md)).
> Über `clear_fields` kann ein Feld **explizit als leer bestätigt** werden, statt nur "nie
> gesetzt" zu sein – so scheint eine niedrigerrangige, falsche Herkunft (z. B. ein
> Regex-Fehltreffer) nicht mehr durch die Auflösungskette durch
> ([ADR 0040](../../../docs/adr/0040-explicit-field-clearing.md)).

> **Personen-Tools weisen ihre Abdeckung aus:** Die Personenebene kennt nur die Autoren belegter
> (`strong`) Zitierdaten. Jede Antwort von `search_authors`, `get_author`, `search_author_papers`
> und `get_author_citations` trägt deshalb `coverage` (Volltexte mit Autoren / Volltexte gesamt,
> Klartext in `note`). Ein mehrdeutiger Name ist kein Fehler, sondern eine Kandidatenliste mit
> `ambiguous = true` ([ADR 0043](../../../docs/adr/0043-author-index-and-person-tools.md)).

> Code-Walkthroughs werden – wie in Phase 4 – nur für nicht-triviale Tools verlangt; die hier
> registrierten Tools sind dünne Wrapper um die getestete Kernlogik und daher **spec-only**
> (right-sized, siehe [CONTRIBUTING.md](../../../CONTRIBUTING.md)). Das gilt auch für
> `answer_question`: Die Orchestrierung liegt in `research_graphrag.generation`, der Wrapper
> reicht lediglich den Generierungs-Port durch; die Sampling-Brücke ist in `sampling.py`
> dokumentiert und durch einen Client-Roundtrip-Test abgedeckt.

## Abhängigkeiten

- Python ≥ 3.11 (WinPython-Basis: 3.13), `mcp` (SDK, inkl. FastMCP).
- Offline-Hybrid-Stack als Kern: `pypdf`, `scikit-learn` (TF-IDF), `numpy` (BM25-Wertung), `networkx`, SQLite (stdlib) –
  Option B, [ADR 0005](../../../docs/adr/0005-graphrag-index-backend-open.md).

## Start (Transport `stdio`)

```pwsh
python -m research_graphrag.mcp_server
```

## Einbindung in VS Code

Siehe [docs/vscode-integration.md](../../../docs/vscode-integration.md) – `command` zeigt auf den
**venv-Interpreter** (`${workspaceFolder}/.venv/Scripts/python.exe`), `cwd` auf die
Repository-Wurzel.

## Einbindung in Claude Code

Über [`.mcp.json`](../../../.mcp.json) im Repository-Wurzelverzeichnis. `command` zeigt auf den
**venv-Interpreter** (`${CLAUDE_PROJECT_DIR}/.venv/Scripts/python.exe`).

> **Kein `cwd` im stdio-Server-Schema von Claude Code.** Anders als `.vscode/mcp.json` kennt das
> `mcpServers`-Format von Claude Code kein `cwd`-Feld – ohne weitere Vorkehrung würde der
> Serverprozess das Arbeitsverzeichnis des aufrufenden Claude-Code-Prozesses erben, das **nicht**
> notwendig die Repository-Wurzel ist. `RESEARCH_GRAPHRAG_INDEX`/`_METADATA`/`_DATA` werden in
> `.mcp.json` deshalb **alle drei** explizit auf absolute, `${CLAUDE_PROJECT_DIR}`-basierte Pfade
> gesetzt statt sich auf die cwd-relativen Defaults zu verlassen – sonst würde insbesondere
> `correct_paper_metadata` still in ein falsches Verzeichnis schreiben (beobachtet als
> nicht-diagnostizierbarer `internal_error`, seit ADR 0039 (Nachtrag 2026-09-19) mit
> Exception-Typ/-Meldung im Antworttext).

## Konfiguration (Umgebungsvariablen)

| Variable | Zweck | Pflicht | Default |
| --- | --- | --- | --- |
| `RESEARCH_GRAPHRAG_INDEX` | Pfad zur SQLite-Index-Datei | nein | `data/index/index.sqlite` |
| `RESEARCH_GRAPHRAG_METADATA` | Pfad zu `metadata/paper_metadata.json` (Ziel von `correct_paper_metadata`) | nein | `metadata/paper_metadata.json` |
| `RESEARCH_GRAPHRAG_DATA` | Datenverzeichnis für append-only Protokolle (`data/corrections_log.md`) | nein | `data` |
| `RESEARCH_GRAPHRAG_LOG_LEVEL` | Log-Niveau (stderr) | nein | `INFO` |

> **Keine** Pfad-Root-Grenze (`RESEARCH_GRAPHRAG_WORKSPACE_ROOTS`) nötig: kein Tool nimmt einen
> nutzergesteuerten Datei-Pfad entgegen (nur `query`/`paper_id`, plus benannte
> Korrekturfelder bei `correct_paper_metadata`), siehe
> [ADR 0009](../../../docs/adr/0009-mcp-server-stdio-phase5.md).
>
> **Secrets:** keine – die Tools liefern nur Evidenz + Provenienz; ein LLM kommt allein zur
> Abfragezeit über den Client (Copilot) ins Spiel ([ADR 0004](../../../docs/adr/0004-llm-bridge-via-mcp-sampling.md)).
> Auch der opt-in Synthese-Pfad bindet **kein** Modell im Server: Er fragt das Modell des
> aufrufenden Clients per Sampling an.

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
  [ADR 0005](../../../docs/adr/0005-graphrag-index-backend-open.md) (Index-Backend),
  [ADR 0037](../../../docs/adr/0037-mcp-tool-response-size-ceiling.md) (Antwort-Größen-Obergrenze),
  [ADR 0039](../../../docs/adr/0039-correction-tool-and-pdf-file-access.md) (Korrektur-Tool &
  PDF-Datei-Zugriff), [ADR 0040](../../../docs/adr/0040-explicit-field-clearing.md) (explizites
  Leeren eines `manual`-Feldes).
