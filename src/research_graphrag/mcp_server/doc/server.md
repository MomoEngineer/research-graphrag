# Modul-Doku: `server.py`

| Feld | Wert |
| --- | --- |
| **Modul** | `src/research_graphrag/mcp_server/server.py` |
| **Paket** | `mcp_server` – MCP-Server über `stdio` |
| **Phase** | 5 (eingeführt), 7 / A1 + A2 (zwei Werkzeuge ergänzt), 12 / K1 (`get_reference` ergänzt), ADR 0037 (Größen-Sicherheitsnetz, `list_topics`-Neuschnitt), ADR 0039 (`get_paper_file` + erstes schreibendes Werkzeug `correct_paper_metadata`), 17 / A4 (vier Personen-Werkzeuge) |
| **Grundlagen** | [ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md), [ADR 0012](../../../../docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md), [ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md), [ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md), [ADR 0039](../../../../docs/adr/0039-correction-tool-and-pdf-file-access.md), [ADR 0043](../../../../docs/adr/0043-author-index-and-person-tools.md) |

---

## 1. Zweck

Die **Außengrenze** des Systems: Hier werden fünfzehn Werkzeuge für GitHub Copilot registriert, hier
werden Fehler in eine strukturierte Ausgabe übersetzt, und hier wird der `stdio`-Transport
gestartet.

Der Server enthält **keine** Fachlogik. Jedes Werkzeug ist ein dünner Wrapper um eine Funktion aus
`retrieval/` oder `generation/` – ein eigenes Werkzeug-Verzeichnis gibt es bewusst nicht.

## 2. Öffentliche Schnittstelle

| Symbol | Art | Aufgabe |
| --- | --- | --- |
| `mcp` | Objekt | Die FastMCP-Instanz mit den registrierten Werkzeugen |
| `main` | Funktion | Startet den `stdio`-Transport |

Die fünfzehn Werkzeuge: `search_basic`, `search_local`, `search_global`, `search_drift`,
`get_paper`, `get_paper_file`, `get_citations`, `get_reference`, `answer_question`, `list_topics`,
`correct_paper_metadata` sowie die Personen-Werkzeuge `search_authors`, `get_author`,
`search_author_papers` und `get_author_citations` (Wrapper um
[`retrieval/authors`](../../retrieval/doc/authors.md),
[ADR 0043](../../../../docs/adr/0043-author-index-and-person-tools.md)). Die Beschreibungen der
Personen-Werkzeuge grenzen sich ausdrücklich gegen die Suchwerkzeuge und `get_citations` ab, damit
die wachsende Werkzeugliste die Tool-Wahl nicht verschlechtert. Ihre Verträge stehen in [`specs/`](../specs); die Werkzeugnamen werden
explizit gesetzt und weichen daher von den Python-Funktionsnamen ab.

`get_paper_file` (Wrapper um [`retrieval/paper_file.get_paper_file`](../../retrieval/doc/paper_file.md))
und `correct_paper_metadata` (Wrapper um
[`bibliography/corrections.apply_manual_correction`](../../bibliography/doc/corrections.md)) sind
die einzigen Werkzeuge, die nicht ausschließlich den Index lesen – Ersteres liest zusätzlich vom
Dateisystem (nur Existenz/Größe, nie Inhalt), Letzteres schreibt nach
`metadata/paper_metadata.json` und protokolliert append-only
([ADR 0039](../../../../docs/adr/0039-correction-tool-and-pdf-file-access.md)).

Seit [ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md) hat `list_topics`
eigene Fachlogik in [`retrieval/topics.py`](../../retrieval/doc/topics.md) statt einer direkten
Weiterreichung von `graph_index.load_communities`: Der Wrapper entscheidet anhand des Parameters
`community_id`, ob er die gefilterte Übersicht (`topics.list_topics`) oder den Einzelabruf
(`topics.get_topic`) ruft.

Der Einstiegspunkt `python -m research_graphrag.mcp_server` liegt in `__main__.py` und ruft
lediglich `main()` auf.

## 3. Ablauf

```mermaid
flowchart TD
    A["Client ruft ein Werkzeug"] --> B["Wrapper: Parameter durchreichen"]
    B --> C["_guard"]
    C --> D["Kernfunktion in retrieval/ bzw. generation/"]
    D -- Erfolg --> E["to_dict → dict"]
    E --> SZ{"serialisierte Größe<br/>> _MAX_RESPONSE_BYTES?"}
    SZ -- nein --> OK["Antwort ausliefern"]
    SZ -- ja --> TOOBIG["constraint_violation<br/>Protokoll: Warnung"]
    D -- DomainError --> F["Fehler-Envelope, isError = true<br/>Protokoll: Info"]
    D -- unerwartet --> G["internal_error<br/>Protokoll: mit Stacktrace"]
```

### Die Fehlerübersetzung

`_guard` ist die einzige Stelle, an der Fehler die Systemgrenze überschreiten:

| Fehlerart | Behandlung |
| --- | --- |
| fachlicher Fehler | in den Envelope übersetzt, als Information protokolliert |
| unerwartete Ausnahme | in `internal_error` übersetzt, mit Stacktrace protokolliert |
| Antwort über `_MAX_RESPONSE_BYTES` (ADR 0037) | in `constraint_violation` übersetzt, als Warnung protokolliert – **nie** ausgeliefert |

Der Envelope wird **doppelt** ausgeliefert – als JSON-Text und als strukturierter Inhalt –, weil
Clients unterschiedlich darauf zugreifen.

Wichtig ist die letzte Sicherung: Eine unerwartete Ausnahme darf **nie** ungefiltert nach außen
gelangen. Ihr Text könnte Pfade oder interne Details preisgeben; nach außen geht nur eine
allgemeine Meldung, die Einzelheiten bleiben im Protokoll.

### Das Byte-Sicherheitsnetz (ADR 0037)

Seit [ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md) prüft `_guard` nach
einem erfolgreichen `produce()` **zusätzlich** die serialisierte Größe der Antwort gegen
`_MAX_RESPONSE_BYTES` (900.000 Byte, Marge unter der 1-MB-MCP-Transportgrenze). Bei Überschreitung
wird die bereits serialisierte Antwort **verworfen** und stattdessen ein strukturierter
`constraint_violation`-Fehler gemeldet – nie wird eine Antwort mitten im Inhalt abgeschnitten
ausgeliefert.

Dieses Netz soll im Normalfall **nie greifen**: Die eigentliche Größenbegrenzung liegt in der
geteilten Obergrenze `research_graphrag.limits.MAX_RESULT_COUNT`, die jeder Trefferzahl-Parameter
(`k`/`n`/`fan_out`/`communities`/`limit`) bereits an seiner eigenen Validierungsstelle durchsetzt
(deutlich unter dieser Schwelle, siehe ADR 0037 für die Messtabelle). `_guard` fängt ausschließlich
Unvorhergesehenes ab.

### On-Read: der Index wird pro Anfrage geladen

Kein Werkzeug hält einen geladenen Index. Jeder Aufruf liest die Index-Datei neu.

Das ist die Voraussetzung für den Drop-in-Workflow: Neue Paper werden sofort sichtbar, ohne den
Server neu zu starten. Der Preis ist Ladezeit je Aufruf – bewusst akzeptiert, weil ein Cache die
Freshness-Garantie bräche. Zusammen mit dem atomaren Index-Swap kann eine Anfrage auch während
eines laufenden Neuaufbaus keinen halbfertigen Zustand sehen.

### Der Index-Pfad

Der Pfad kommt aus einer Umgebungsvariablen, sonst aus einem Standardwert. Es gibt **keinen**
Pfad-Parameter an den Werkzeugen: Ein Client soll nicht bestimmen können, welche Datei gelesen
wird.

### Nur ein asynchrones Werkzeug

Zehn Werkzeuge sind synchron. Nur `answer_question` ist asynchron – und auch das nur, weil
optionales Sampling einen laufenden Event-Loop braucht:

```mermaid
sequenceDiagram
    participant C as Client
    participant T as answer_question (async)
    participant W as Worker-Thread
    participant S as Sampling-Brücke
    C->>T: query, synthesize=true
    T->>W: Kernlogik synchron ausführen
    W->>S: Sampler aufrufen
    S-->>T: zurück in den Event-Loop
    S-->>W: Completion
    W-->>T: Ergebnis-dict
    T-->>C: Antwort + Evidenz
```

Die Kernlogik bleibt dadurch synchron und offline testbar – die Asynchronität existiert
ausschließlich an dieser Grenze.

### Logging auf stderr

Beim `stdio`-Transport ist stdout dem Protokoll vorbehalten. Eine Protokollzeile auf stdout würde
die Verbindung beschädigen. Die Protokollierung geht deshalb ausnahmslos auf stderr; der
Schwellenwert ist über eine Umgebungsvariable einstellbar.

### Modellfrei per Voreinstellung

Alle Evidenz-Werkzeuge liefern ausschließlich Belege und Provenienz; formuliert wird beim Client.
Die einzige Ausnahme ist `answer_question` mit ausdrücklich angefordertem Sampling – die
Voreinstellung ist auch dort „nicht formulieren". Für Copilot ist das richtig: Der Client ist
selbst ein Modell.

## 4. Zusammenspiel

```mermaid
flowchart LR
    VS["VS Code / Copilot"] -->|stdio| SV["server.py"]
    SV --> RB["retrieval/basic"]
    SV --> RL["retrieval/local"]
    SV --> RG["retrieval/global_search"]
    SV --> RD["retrieval/drift"]
    SV --> RP["retrieval/paper"]
    SV --> RPF["retrieval/paper_file"]
    SV --> RC["retrieval/citations"]
    SV --> RT["retrieval/topics"]
    SV --> AN["generation/answer"]
    SV --> SM["mcp_server/sampling"]
    SV --> BC["bibliography/corrections"]
    SV --> ER["errors: Envelope"]
    SV --> LM["limits: MAX_RESULT_COUNT"]
    RT --> GI["indexing/graph_index"]
    BC --> BS["bibliography/store"]
    BC --> LOG["online/report: append_section"]
```

Die Einbindung beschreibt [docs/vscode-integration.md](../../../../docs/vscode-integration.md);
die Werkzeug-Verträge stehen in [`specs/`](../specs).

## 5. Fehler und Grenzfälle

Alle Fehler verlassen den Server als Envelope mit gesetztem Fehler-Flag – nie als Ausnahme.

| Situation | Code im Envelope |
| --- | --- |
| leere Anfrage, unbekannter Modus, ungültige Zahl, Trefferzahl-Parameter über `MAX_RESULT_COUNT` (ADR 0037) | `invalid_input` |
| Index oder Paper nicht vorhanden | `not_found` |
| Index ohne Chunks, Graph oder Zitationskanten | `constraint_violation` |
| serialisierte Antwort über `_MAX_RESPONSE_BYTES` (ADR 0037) | `constraint_violation` |
| unerwarteter Fehler | `internal_error` |
| Sampling schlägt fehl | **kein** Fehler – `generated = false` |
| PDF lokal nicht auffindbar / Referenz-Eintrag ohne Volltext (`get_paper_file`) | **kein** Fehler – `available = false` mit `reason` |

## 6. Determinismus

Der Server fügt kaum Nichtdeterminismus hinzu: Er reicht Parameter durch und serialisiert
Ergebnisse. Variable Anteile sind die optionale Formulierung (`answer_question`) und der
Zeitstempel im Korrektur-Protokoll (`correct_paper_metadata`, analog zu den bestehenden
append-only Protokollen der Skripte).

## 7. Grenzen

- **Nur `stdio`.** Kein HTTP-Transport, kein Mehrbenutzerbetrieb; ein Wechsel wäre
  ADR-pflichtig.
- **Keine Authentifizierung, keine Ratenbegrenzung.** Der Server läuft als lokaler
  Unterprozess des Clients.
- **Keine Wertungs-Umschaltung an den Werkzeugen.** Die Wahl zwischen den Wertungen ist ein
  Analyse-Schalter der Kommandozeile
  ([ADR 0014](../../../../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)).
- **Keine Indexierung/Ingestion.** Der Server baut den Index nicht selbst; das bleibt ein bewusst
  angestoßener Vorgang (`python -m scripts.ingest`).
- **Genau eine Schreiboperation, eng begrenzt.** `correct_paper_metadata` ist seit
  [ADR 0039](../../../../docs/adr/0039-correction-tool-and-pdf-file-access.md) die einzige
  Ausnahme: Es schreibt ausschließlich die `manual`-Herkunft nach
  `metadata/paper_metadata.json` – nie den Index selbst, nie extrahierten Volltext. Die
  Änderung wirkt erst nach dem nächsten Ingest.
