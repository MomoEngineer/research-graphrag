# Tool-Spezifikation: `correct_paper_metadata`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/bibliography/corrections.py`; als MCP-Tool registriert
> ([ADR 0039](../../../../docs/adr/0039-correction-tool-and-pdf-file-access.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `correct_paper_metadata` |
| **Version** | `0.1.0` |
| **Capability-Schicht** | Korrektur / Zitation (siehe README.md) |
| **Status** | Implementiert (ADR 0039) |

---

## 1. Zweck

Korrigiert **bibliografische Metadaten** eines Papers (Titel, Autoren, Jahr, Venue, DOI/arXiv,
URL) mit der höchsten Herkunfts-Priorität `manual`
([ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md)). Das erste **schreibende**
Werkzeug der MCP-Oberfläche: Ein Agent kann einen erkannten Fehler direkt beheben, statt die
versionierte Metadatendatei von Hand zu editieren.

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

**Mindestens ein** Feld-Parameter (`title` … `url`) muss gesetzt sein.

> Der Metadatendatei-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard:
> `metadata/paper_metadata.json` relativ zum Repository-Wurzelverzeichnis).

## 3. Output-Schema

```json
{
  "paper_id": "…",
  "applied_fields": ["doi", "venue"],
  "previous": { "doi": "", "venue": "arXiv (Cornell University)" },
  "record": {
    "paper_id": "…",
    "origin": "manual",
    "title": "",
    "authors": [],
    "year": 0,
    "venue": "ACM SIGCOMM",
    "doi": "10.1145/3696410",
    "arxiv_id": "",
    "url": "",
    "confidence": "strong",
    "evidence": "laut Publisher-Landingpage doi.org/10.1145/3696410"
  },
  "log_path": "data/corrections_log.md",
  "effective_after": "python -m scripts.ingest"
}
```

- `applied_fields` nennt genau die in diesem Aufruf geänderten Felder (nicht alle Felder des
  `manual`-Records).
- `previous` zeigt die vorherigen Werte **nur** der geänderten Felder (leer, wenn zuvor kein
  `manual`-Record existierte) – Transparenz über die tatsächliche Änderung.
- `record` ist der vollständige, jetzt gespeicherte `manual`-Record dieses Papers (alle Felder,
  auch aus früheren Korrekturen unverändert übernommene).
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
- **Kein** Zurücksetzen/Löschen eines Feldes auf dieser Schnittstelle; ein bereits gesetztes
  `manual`-Feld lässt sich nur durch eine neue Korrektur überschreiben, nicht entfernen. Ein
  vollständiger Rückbau bleibt der Handbearbeitung von `metadata/paper_metadata.json`
  vorbehalten (git-versioniert, jederzeit revidierbar).

## 6. Fehlerverhalten

- `invalid_input`: leere `paper_id`; leeres/fehlendes `evidence`; kein Feld-Parameter gesetzt;
  ein gesetztes Feld ist nach `strip()` leer; `authors` ist eine leere Liste; `year` außerhalb
  `1000..aktuelles Jahr + 1`.
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
  Erhalt unveränderter Felder), Validierung je Feldtyp, Protokoll-Eintrag, Determinismus eines
  zweiten identischen Aufrufs.
- `tests/mcp_server/test_server.py`: Tool-Contract über einen In-Memory-Client (Erfolg +
  Fehler-Envelope je Fehlerfall).
