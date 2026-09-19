# Tool-Spezifikation: `correct_paper_metadata`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/bibliography/corrections.py`; als MCP-Tool registriert
> ([ADR 0039](../../../../docs/adr/0039-correction-tool-and-pdf-file-access.md),
> [ADR 0040](../../../../docs/adr/0040-explicit-field-clearing.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `correct_paper_metadata` |
| **Version** | `0.2.0` |
| **Capability-Schicht** | Korrektur / Zitation (siehe README.md) |
| **Status** | Implementiert (ADR 0039, ADR 0040) |

---

## 1. Zweck

Korrigiert **bibliografische Metadaten** eines Papers (Titel, Autoren, Jahr, Venue, DOI/arXiv,
URL) mit der höchsten Herkunfts-Priorität `manual`
([ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md)). Das erste **schreibende**
Werkzeug der MCP-Oberfläche: Ein Agent kann einen erkannten Fehler direkt beheben, statt die
versionierte Metadatendatei von Hand zu editieren. Neben dem Setzen eines Wertes kann ein Feld
seit [ADR 0040](../../../../docs/adr/0040-explicit-field-clearing.md) auch **explizit als leer
bestätigt** werden (`clear_fields`) – notwendig, wenn eine niedrigerrangige Herkunft (typisch:
ein per Regex extrahierter Fehltreffer) sonst weiter durchscheinen würde, weil „kein Wert" und
„nie geprüft" für die Auflösungskette sonst ununterscheidbar sind.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `paper_id` | `str` | ja | Stabile Paper-ID (kein Datei-Pfad); muss im Index existieren. |
| `evidence` | `str` | ja | Nicht-leerer, handlungsleitender Beleg für die Korrektur (z. B. „laut Publisher-Landingpage doi.org/…"). |
| `title` | `str` \| `null` | nein | Neuer Titel; nach `strip()` nicht leer, wenn gesetzt. |
| `authors` | `list[str]` \| `null` | nein | Neue Autorenliste in Nennreihenfolge; nicht leer, wenn gesetzt. |
| `year` | `int` \| `null` | nein | Erscheinungsjahr; `1000 <= year <= aktuelles Jahr + 1`. |
| `venue` | `str` \| `null` | nein | Journal/Konferenz/Verlag; nicht leer, wenn gesetzt. |
| `doi` | `str` \| `null` | nein | DOI ohne URL-Präfix (z. B. `10.1145/…`); nicht leer, wenn gesetzt. |
| `arxiv_id` | `str` \| `null` | nein | arXiv-ID ohne Version; nicht leer, wenn gesetzt. |
| `url` | `str` \| `null` | nein | Landing- oder Volltext-Link; nicht leer, wenn gesetzt. |
| `clear_fields` | `list[str]` \| `null` | nein | Feldnamen aus `title`…`url`, die **explizit als leer bestätigt** werden sollen (ADR 0040). Ein Feld darf nicht gleichzeitig hier **und** als Set-Parameter oben stehen. |

**Mindestens einer** der beiden Kanäle muss nicht-leer sein: ein Feld-Parameter (`title` … `url`)
**oder** `clear_fields`.

> Der Metadatendatei-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard:
> `metadata/paper_metadata.json` relativ zum Repository-Wurzelverzeichnis).

## 3. Output-Schema

```json
{
  "paper_id": "…",
  "applied_fields": ["doi", "venue"],
  "previous": { "doi": "", "venue": "arXiv (Cornell University)" },
  "record": {
    "origin": "manual",
    "title": "",
    "authors": [],
    "year": 0,
    "venue": "ACM SIGCOMM",
    "doi": "10.1145/3696410",
    "arxiv_id": "",
    "url": "",
    "confidence": "strong",
    "evidence": "laut Publisher-Landingpage doi.org/10.1145/3696410",
    "cleared_fields": []
  },
  "log_path": "data/corrections_log.md",
  "effective_after": "python -m scripts.ingest"
}
```

- `applied_fields` nennt genau die in diesem Aufruf geänderten Felder – gesetzt **oder** über
  `clear_fields` geleert (nicht alle Felder des `manual`-Records).
- `previous` zeigt die vorherigen Werte **nur** der geänderten Felder (leer, wenn zuvor kein
  `manual`-Record existierte) – Transparenz über die tatsächliche Änderung. Für ein geleertes
  Feld ist das der vorherige `manual`-Wert (nicht der zuvor über eine niedrigerrangige Herkunft
  aufgelöste Wert).
- `record` ist der vollständige, jetzt gespeicherte `manual`-Record dieses Papers (alle Felder,
  auch aus früheren Korrekturen unverändert übernommene). `record.cleared_fields` (seit
  [ADR 0040](../../../../docs/adr/0040-explicit-field-clearing.md)) nennt **alle** je Aufruf
  akkumulierten, explizit geleerten Felder dieses Papers (nicht nur die des aktuellen Aufrufs) –
  leer, wenn keines geleert wurde.
- `effective_after` ist immer der feste Wert `"python -m scripts.ingest"` – der Hinweis, dass die
  Korrektur `get_paper`/`get_reference`/`answer_question` erst nach dem nächsten Ingest erreicht
  (dieselbe Verzögerung wie bei `python -m scripts.resolve_metadata`,
  [ADR 0026](../../../../docs/adr/0026-online-metadata-resolution.md)).

## 4. Annahmen und Vorbedingungen

- Ein Index wurde gebaut (`python -m scripts.ingest`); `paper_id` muss darin bekannt sein.
- Das Repository-Wurzelverzeichnis ist beschreibbar (`metadata/paper_metadata.json`,
  `data/corrections_log.md`).

## 5. Grenzen (Nicht-Ziele)

- **Keine** Korrektur von extrahiertem Volltext, Chunk-Text oder Abschnittstiteln – nur die
  sieben bibliografischen Felder aus `bibliography.model.METADATA_FIELDS`.
- **Keine** Korrektur des Kuratierungsurteils (`metadata/curation.json`, seit
  [ADR 0034](../../../../docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md)
  bewusst eingefroren).
- **Keine** sofortige Wirkung auf andere Werkzeuge – siehe `effective_after`.
- **Kein** vollständiges Entfernen eines `manual`-Records oder eines Feldes aus der
  Speicherform; ein Feld kann überschrieben oder (seit ADR 0040) über `clear_fields` explizit
  auf leer gesetzt werden, aber nicht aus dem Record selbst getilgt werden. Ein vollständiger
  Rückbau bleibt der Handbearbeitung von `metadata/paper_metadata.json` vorbehalten
  (git-versioniert, jederzeit revidierbar).

## 6. Fehlerverhalten

- `invalid_input`: leere `paper_id`; leeres/fehlendes `evidence`; weder ein Feld-Parameter noch
  `clear_fields` gesetzt; ein gesetztes Feld ist nach `strip()` leer; `authors` ist eine leere
  Liste; `year` außerhalb `1000..aktuelles Jahr + 1`; ein unbekannter Feldname in `clear_fields`;
  ein Feld gleichzeitig als Set-Parameter **und** in `clear_fields` angegeben.
- `not_found`: Index-Datei fehlt **oder** `paper_id` ist im Index unbekannt.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- `record.evidence` trägt den kumulierten Beleg aller bisherigen `manual`-Korrekturen dieses
  Papers (neue Belege werden angehängt, getrennt durch `; `).
- `data/corrections_log.md` protokolliert **jeden** Aufruf einzeln mit Zeitstempel, geänderten
  Feldern (alt → neu) und Beleg – die granulare Audit-Spur, die der zusammengefasste
  `evidence`-Text im Live-Record nicht mehr trägt.
- `metadata/paper_metadata.json` ist git-versioniert; jede Korrektur erscheint als Diff.

## 8. Reproduzierbarkeit

- Deterministisch: atomares Schreiben (Temporärdatei + `os.replace`), feste Feldreihenfolge,
  sortierte Schlüssel (siehe `bibliography.store.save_records`). Kein Netz, kein Zufall.
- Der einzige nicht-deterministische Anteil ist der Zeitstempel im Protokoll
  (`data/corrections_log.md`), analog zu den bestehenden append-only Protokollen.

## 9. Testabdeckung

- `tests/bibliography/test_corrections.py`: Merge-Logik (neues Feld, überschreibendes Feld,
  Erhalt unveränderter Felder), explizites Leeren (`clear_fields`: markiert das Feld, wird durch
  ein späteres Setzen wieder verlassen, Protokoll-Vermerk `(explizit geleert)`), Validierung je
  Feldtyp (inkl. Widerspruch „gleichzeitig gesetzt und geleert"), Protokoll-Eintrag,
  Determinismus eines zweiten identischen Aufrufs.
- `tests/bibliography/test_resolve.py`: Ein `manual`-Record mit `cleared_fields` gewinnt mit
  leerem Wert gegen eine niedrigerrangige Herkunft mit echtem (falschem) Wert.
- `tests/mcp_server/test_server.py`: Tool-Contract über einen In-Memory-Client (Erfolg +
  Fehler-Envelope je Fehlerfall, inkl. `clear_fields`-Widerspruch).

## 10. Beispiele

Real erzeugt gegen den Testindex aus `tests/mcp_server/conftest.py`; geprüft in `tests/mcp_server/test_spec_examples.py`. **Hinweis:** `record` trägt anders als früher hier dokumentiert **kein** eigenes `paper_id`-Feld (die `MetadataRecord.to_dict()`-Speicherform lässt es bewusst weg – der Aufruf-Envelope trägt `paper_id` bereits auf oberster Ebene); Abschnitt 3 wurde entsprechend korrigiert.

### 10.1 Feld setzen

Anfrage:

```json
{
  "paper_id": "aaaa0001",
  "authors": ["Anna Beispiel", "Bert Muster"],
  "venue": "ACM SIGCOMM",
  "evidence": "laut Publisher-Landingpage doi.org/10.1145/1234"
}
```

Antwort:

```json
{
  "paper_id": "aaaa0001",
  "applied_fields": ["authors", "venue"],
  "previous": { "authors": [], "venue": "" },
  "record": {
    "origin": "manual",
    "title": "",
    "authors": ["Anna Beispiel", "Bert Muster"],
    "year": 0,
    "venue": "ACM SIGCOMM",
    "doi": "",
    "arxiv_id": "",
    "url": "",
    "confidence": "strong",
    "evidence": "laut Publisher-Landingpage doi.org/10.1145/1234",
    "cleared_fields": []
  },
  "log_path": "data/corrections_log.md",
  "effective_after": "python -m scripts.ingest"
}
```

### 10.2 Feld explizit leeren (ADR 0040)

Anfrage:

```json
{
  "paper_id": "aaaa0001",
  "clear_fields": ["arxiv_id"],
  "evidence": "arXiv-ID gehoert zu einem im Volltext zitierten Fremdpaper, nicht zu diesem Buch"
}
```

Antwort:

```json
{
  "paper_id": "aaaa0001",
  "applied_fields": ["arxiv_id"],
  "previous": { "arxiv_id": "" },
  "record": {
    "origin": "manual",
    "title": "",
    "authors": [],
    "year": 0,
    "venue": "",
    "doi": "",
    "arxiv_id": "",
    "url": "",
    "confidence": "strong",
    "evidence": "arXiv-ID gehoert zu einem im Volltext zitierten Fremdpaper, nicht zu diesem Buch",
    "cleared_fields": ["arxiv_id"]
  },
  "log_path": "data/corrections_log.md",
  "effective_after": "python -m scripts.ingest"
}
```

`arxiv_id` bleibt leer, gewinnt aber jetzt in der Präzedenzauflösung gegen einen niedrigerrangigen
(z. B. `extracted`) Wert – `get_reference`/`python -m scripts.cite` weisen `arxiv_id=manual` statt
`arxiv_id=extracted` aus, sobald der nächste Ingest gelaufen ist.
