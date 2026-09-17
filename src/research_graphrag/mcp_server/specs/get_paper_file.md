# Tool-Spezifikation: `get_paper_file`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/paper_file.py`; als MCP-Tool registriert
> ([ADR 0039](../../../../docs/adr/0039-correction-tool-and-pdf-file-access.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `get_paper_file` |
| **Version** | `0.1.0` |
| **Capability-Schicht** | Katalog / Provenienz (siehe README.md) |
| **Status** | Implementiert (ADR 0039) |

---

## 1. Zweck

Liefert den **lokalen Dateisystem-Pfad** des Original-PDFs eines Papers, sofern lokal vorhanden –
für einen Zugriff **über das vollständige Dokument** hinaus, das die Chunk-/Snippet-Auszüge der
übrigen Werkzeuge bieten. Das Werkzeug überträgt **keine** Datei-Bytes; der aufrufende Agent
(GitHub Copilot in VS Code) liest die Datei über sein eigenes Dateisystem-Werkzeug weiter, sobald
er den Pfad kennt.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `paper_id` | `str` | ja | Stabile Paper-ID (kein Datei-Pfad); nicht leer. |

## 3. Output-Schema

```json
{
  "paper_id": "…",
  "document_kind": "full",
  "available": true,
  "path": "C:\\Users\\…\\research-graphrag-data\\papers\\Beispiel.pdf",
  "source_uri": "file:///C:/Users/…/research-graphrag-data/papers/Beispiel.pdf",
  "size_bytes": 1048576,
  "reason": "",
  "note": ""
}
```

Ein Referenz-Eintrag (kein lokales PDF):

```json
{
  "paper_id": "…",
  "document_kind": "reference",
  "available": false,
  "path": "",
  "source_uri": "file:///…/referenzen/Beispiel.refjson",
  "size_bytes": 0,
  "reason": "reference_only",
  "note": "Referenz-Eintrag ohne Volltext – kein lokales PDF vorhanden."
}
```

- `available = false` ist **kein Fehler** – beide Fälle (`reference_only`,
  `file_missing`) liefern `isError = false`. Das Werkzeug meldet eine Abweichung sichtbar
  im Ergebnis, statt zwei unterschiedliche Antwortformen (Erfolg/Fehler) für denselben
  Sachverhalt „kein Zugriff auf den Inhalt möglich" zu erzeugen.
- `path` ist ein **nativer** Dateisystem-Pfad (aus `source_uri` über
  `urllib.request.url2pathname` aufgelöst), keine `file://`-URI – direkt für ein
  Dateisystem-Werkzeug nutzbar.
- `reason` ist `""` (verfügbar), `"reference_only"` oder `"file_missing"`.

## 4. Annahmen und Vorbedingungen

- Ein Index wurde gebaut (`python -m scripts.ingest`); `paper_id` muss darin bekannt sein.
- Der Prozess, der den MCP-Server ausführt, hat Lesezugriff auf `papers/` (lokaler Symlink auf
  ein externes, nicht versioniertes Datenverzeichnis).

## 5. Grenzen (Nicht-Ziele)

- **Keine** Übertragung von Datei-Inhalten/Bytes – kollidiert mit der gemessenen 1-MB-Grenze
  ([ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md)) bei den meisten
  realen Papern.
- **Kein** Datei-Pfad als Eingabe – ausschließlich `paper_id`
  ([ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md): kein
  Pfad-Traversal-Vektor).
- **Keine** Existenzgarantie über den Aufruf hinaus: `papers/` liegt außerhalb der
  Versionskontrolle und kann sich zwischen zwei Aufrufen ändern.

## 6. Fehlerverhalten

- `invalid_input`: leere `paper_id`.
- `not_found`: Index-Datei fehlt **oder** `paper_id` ist im Index unbekannt.
- **Kein** eigener Fehlerfall für ein fehlendes PDF oder einen Referenz-Eintrag – siehe
  Abschnitt 3 (`available = false`).

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- `source_uri` (identisch zur Quelle, die `get_paper` bereits ausweist), `document_kind`.

## 8. Reproduzierbarkeit

- Deterministisch bis auf den Dateisystem-Zustand: Zwei Aufrufe mit unverändertem `papers/`-Ordner
  liefern identische Ergebnisse. Kein Netz, kein Zufall.

## 9. Testabdeckung

- `tests/retrieval/test_paper_file.py`: vorhandenes PDF, Referenz-Eintrag
  (`reason = "reference_only"`), im Index verzeichnetes, aber lokal fehlendes PDF
  (`reason = "file_missing"`), unbekannte `paper_id`, leere `paper_id`, fehlender Index.
- `tests/mcp_server/test_server.py`: Tool-Contract über einen In-Memory-Client (Erfolg +
  Fehler-Envelope).
