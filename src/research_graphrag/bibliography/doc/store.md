# Modul-Doku: `store.py`

| Feld | Wert |
| --- | --- |
| **Modul** | `src/research_graphrag/bibliography/store.py` |
| **Paket** | `bibliography` – zitierfähige Metadaten |
| **Phase** | 12 / K1, erweitert in 17 / A1 |
| **Grundlagen** | [ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md) · [ADR 0026](../../../../docs/adr/0026-online-metadata-resolution.md) · [ADR 0042](../../../../docs/adr/0042-title-page-evidence-and-rejections.md) |

---

## 1. Zweck

Verwaltet die **versionierte** Datei `metadata/paper_metadata.json` – die einzige Stelle, an der
extern aufgelöste (`resolved`) und von Hand gepflegte (`manual`) Zitationsdaten dauerhaft liegen.
Die Kernidee ist ein Format, das gleichzeitig maschinell geschrieben und von Hand bearbeitet
werden kann.

## 2. Öffentliche Schnittstelle

| Symbol | Art | Aufgabe |
| --- | --- | --- |
| `load_records` | Funktion | Datei → Datensätze (fehlende Datei ⇒ leer) |
| `save_records` | Funktion | Datensätze → Datei (deterministisch, atomar); `reviews=None` **behält** den Prüfstand der Datei |
| `load_reviews` | Funktion | Prüfstand je Paper (Ablehnungsvermerke, Status) – fehlend ⇒ leer |
| `add_rejection` / `set_review_status` | Funktionen | Vermerk ergänzen (ohne Dublette) bzw. Status setzen/aufheben (mit Pflicht-Grund) |
| `REVIEWS_KEY` | Konstante | Schlüssel `reviews` in der Datei (additiv, Phase 17 / A1) |
| `upsert_records` | Funktion | je `(paper_id, origin)` ersetzen, Rest behalten |
| `metadata_path` | Funktion | Pfad unterhalb eines Wurzelverzeichnisses |
| `SCHEMA_VERSION` / `METADATA_DIR` / `METADATA_FILENAME` / `WRITABLE_ORIGINS` | Konstanten | Format und Ablageort |

## 3. Ablauf

```mermaid
flowchart TD
    A["save_records"] --> B["nach paper_id und Herkunfts-Vorrang sortieren"]
    B --> C["je paper_id gruppieren"]
    C --> D["json.dumps mit sort_keys + indent"]
    D --> E["eindeutige *.tmp-Datei anlegen (tempfile.mkstemp)"]
    E --> F["os.replace auf das Ziel"]
    F --> G["finally: *.tmp entfernen"]
```

### `write_bytes` statt `write_text`

Unter Windows würde `write_text` jedes `\n` zu `\r\n` machen. Die Datei wäre dann je nach
Plattform verschieden – ein Byte-Vergleich zwischen zwei Läufen würde scheitern, und in der
Versionsverwaltung erschiene sie bei jedem Wechsel als vollständig geändert. Deshalb wird der
fertige Text als **Bytes** geschrieben.

### Warum nur zwei Herkünfte gespeichert werden

`extracted` und `curated` werden bei **jedem** Index-Bau neu abgeleitet – aus den Canonical-Papern
bzw. der Übersicht. Sie hier zusätzlich zu speichern, hieße zwei Wahrheiten zu pflegen: Eine
Korrektur in der Übersicht würde von einer veralteten Kopie überstimmt. `WRITABLE_ORIGINS`
dokumentiert diese Festlegung.

### Der Schlüssel des Upsert

`upsert_records` ersetzt je **Paar** aus Paper und Herkunft. Damit überschreibt ein erneuter
Auflösungslauf ausschließlich seine eigenen früheren Ergebnisse; ein `manual`-Eintrag zum selben
Paper bleibt unangetastet.

### Der Prüfstand in derselben Datei (Phase 17 / A1)

Unter `reviews` trägt die Datei je Paper Ablehnungsvermerke und einen optionalen Status
„nicht auflösbar“ ([ADR 0042](../../../../docs/adr/0042-title-page-evidence-and-rejections.md)).
Dass beides in **derselben** Datei liegt wie die Datensätze, ist Absicht. Das Entfernen eines
verworfenen Treffers und sein Vermerk entstehen in einem atomaren Schreibvorgang; zwei Dateien
könnten nach einem Abbruch den Datensatz ohne Vermerk zurücklassen. `save_records` behält den
Prüfstand, solange der Aufrufer keinen neuen übergibt. Auflösungslauf und Korrektur-Tool, die nur
Datensätze schreiben, können deshalb keinen Vermerk verlieren. Der Schlüssel ist additiv und
erscheint nur, wenn es einen Prüfstand gibt.

## 4. Zusammenspiel

```mermaid
flowchart LR
    RM["scripts.resolve_metadata"] --> UP["upsert_records"]
    UP --> SV["save_records"]
    SV --> F[("metadata/paper_metadata.json")]
    F --> LR["load_records"]
    LR --> MI["indexing.metadata_index"]
    HAND["Handpflege im Editor"] --> F
```

Der Weg ist **einseitig gerichtet**: Netz → Datei → Index. Kein Werkzeug schreibt zur Abfragezeit.

## 5. Fehler und Grenzfälle

| Situation | Fehlercode |
| --- | --- |
| Datei fehlt | kein Fehler – leeres Ergebnis |
| defektes JSON | `parse_error` |
| Wurzel ist kein Objekt | `constraint_violation` |
| unbekannte `schema_version` | `constraint_violation` |
| `papers` ist kein Objekt | `constraint_violation` |
| `reviews` ist kein Objekt | `constraint_violation` |
| unbekannter Status in `reviews` | gilt als nicht gesetzt |
| Datensatzliste eines Papers ist keine Liste bzw. enthält kein Objekt | `constraint_violation` |

Die strenge Prüfung ist Absicht: Eine von Hand bearbeitete Datei soll bei einem Tippfehler
**auffallen** und nicht stillschweigend als leer gelten.

## 6. Determinismus

Sortierte Schlüssel, feste Feldreihenfolge, `\n` als Zeilenende. Zwei Läufe mit derselben Menge
schreiben byte-identisch – auch bei umgekehrter Eingabereihenfolge.

## 7. Grenzen

- **Keine Historie.** Ein Upsert überschreibt; wer den Verlauf braucht, findet ihn in
  `data/metadata_log.md` und in der Versionsverwaltung.
- **Keine Sperren.** Zwei gleichzeitige Läufe können sich überschreiben (der letzte gewinnt);
  bei einem persönlichen Werkzeug ist das akzeptabel. Seit ADR 0039 (Nachtrag 2026-09-19)
  delegiert `save_records` das eigentliche Schreiben an
  [`atomic_write.atomic_write_bytes`](../../doc/atomic_write.md), das zwei Absturzursachen
  konkurrierender Schreibversuche schließt: eine **eindeutige** Temporärdatei je Aufruf statt
  eines festen `<name>.tmp` (sonst träfe ein zweiter, fast gleichzeitiger Aufruf mit seinem
  `os.replace` ins Leere, nachdem der erste seine – dann gemeinsame – Temporärdatei bereits
  weggeschoben hätte) **und** einen kurzen Retry gegen eine gemessene, transiente
  `PermissionError`, wenn zwei `os.replace`-Aufrufe **dieselbe Zieldatei** treffen (eindeutige
  Quelle allein reicht dafür nicht). Bemessen für die realistische Gleichzeitigkeit weniger
  Aufrufe eines einzigen MCP-Clients, nicht für beliebig viele (siehe Modul-Doku von
  `atomic_write` für die gemessenen Grenzwerte) – am „letzter gewinnt"-Verhalten selbst ändert
  das nichts.
