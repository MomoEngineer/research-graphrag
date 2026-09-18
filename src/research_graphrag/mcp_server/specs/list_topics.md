# Tool-Spezifikation: `list_topics`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/topics.py` (über `indexing/graph_index.py`); als MCP-Tool
> registriert in **Phase 5** ([ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md)).

> **Änderung `0.1.0` → `0.2.0` ([ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md)):**
> Gemessen am realen Korpus (3.461 Paper, 1.170 Communities) liefert die alte, parameterlose
> Fassung **555 KB** – mehr als die Hälfte der MCP-Transportgrenze von 1 MB, unbedingt und ohne
> jedes Zutun des Aufrufers. Die Standardantwort verliert deshalb das Feld `members`, blendet
> Singleton-Communities aus (`min_size`) und deckelt die Trefferzahl (`limit`); ein neuer
> Parameter `community_id` liefert bei Bedarf **eine** Community mit voller Mitgliederliste. Das
> ist ein **bewusster Bruch** des Output-Schemas (Präzedenzfall: `search_local` `0.1.0` →
> `0.2.0`) sowie der Sortierreihenfolge (aufsteigend `community_id` → absteigend `size`).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `list_topics` |
| **Version** | `0.2.0` |
| **Capability-Schicht** | Übersicht / Katalog (siehe README.md) |
| **Status** | Implementiert (Phase 5; Filter/Limit/Einzelabruf seit [ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md)) |

---

## 1. Zweck

Listet die **Themencluster des Korpus** – die Louvain-Communities des Paper-Ähnlichkeitsgraphen ([ADR 0007](../../../../docs/adr/0007-graphrag-index-phase3-option-b.md)) – mit Größe, Keywords und Vertreter-Papern. Gibt einem Agenten einen corpusweiten Überblick und hilft, eine Community für `search_global`/`search_drift` auszuwählen. Mit `community_id` liefert dasselbe Werkzeug stattdessen die **volle Mitgliederliste** genau einer Community – der Weg, um nach der Auswahl aus der Übersicht ins Detail zu gehen.

> Die `keywords` durchlaufen die kuratierte **Keyword-Politik** (`research_graphrag.keywords`): Bibliografie-Vokabular, rein numerische Token und Glyph-Artefakte werden **vor** dem Top-10-Anschnitt entfernt, sodass die frei werdenden Plätze mit Themenbegriffen aufgefüllt werden ([ADR 0015](../../../../docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)).

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `min_size` | `int` | nein | Blendet Communities mit weniger Mitgliedern aus (>= 1); Default `2` – Singleton-Communities sind keine cross-paper-Themen. Ohne Wirkung, wenn `community_id` gesetzt ist. |
| `limit` | `int` | nein | Maximale Zahl der Communities in der Übersicht (1 ≤ `limit` ≤ 50); Default `50`. Ohne Wirkung, wenn `community_id` gesetzt ist. |
| `community_id` | `int` | nein | Liefert **nur** diese Community, dafür mit voller `members`-Liste; ignoriert `min_size`/`limit`. Default: keine (Übersichts-Modus). |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).
>
> `MAX_RESULT_COUNT = 50` ist dieselbe geteilte Obergrenze, die auch `k`/`n`/`fan_out`/`communities` der übrigen Retrieval-Werkzeuge begrenzt ([ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md), Modul `research_graphrag.limits`).

## 3. Output-Schema

**Übersichts-Modus** (`community_id` nicht gesetzt):

```json
{
  "topics": [
    {
      "community_id": 0,
      "size": 12,
      "keywords": ["…"],
      "summary": "…",
      "representatives": ["…"]
    }
  ],
  "total_matching": 219,
  "truncated": true
}
```

`topics` ist absteigend nach `size` sortiert (Tie-Break: kleinere `community_id`) und enthält höchstens `limit` Einträge aus allen Communities mit `size >= min_size`. `total_matching` ist die Zahl **aller** Communities, die `min_size` erfüllen (vor `limit`); `truncated` ist `true`, wenn `total_matching > limit` – die Kürzung ist damit immer sichtbar, nie stillschweigend. `summary` ist ein **extraktives** Leit-Snippet (repräsentatives Paper); `representatives` sind die zentralsten Paper der Community. Das Feld `members` ist in diesem Modus **nicht** enthalten (siehe `community_id`).

**Einzelabruf** (`community_id` gesetzt):

```json
{
  "community_id": 0,
  "size": 105,
  "keywords": ["…"],
  "summary": "…",
  "members": ["…"],
  "representatives": ["…"]
}
```

Hier trägt die Antwort zusätzlich die vollständige `members`-Liste; `min_size`/`limit`/`total_matching`/`truncated` entfallen, weil sie sich auf die Übersicht beziehen.

## 4. Annahmen und Vorbedingungen

- Ein Index **und** der Paper-Ähnlichkeitsgraph wurden gebaut (`python -m scripts.ingest`, Phase 3).

## 5. Grenzen (Nicht-Ziele)

- **Keine** Query/Relevanz-Filterung (dafür `search_global`) und **keine** Chunk-Provenienz.
- Keine LLM-Formulierung im Tool – nur strukturierte Community-Sichten.
- **Kein Mehrfachabruf** in einem Aufruf: `community_id` liefert genau eine Community; mehrere Community-Details erfordern mehrere Aufrufe.

## 6. Fehlerverhalten

- `invalid_input`: `min_size < 1`, `limit` außerhalb `[1, 50]`.
- `not_found`: Index-Datei fehlt **oder** `community_id` ist unbekannt.
- `constraint_violation`: kein Graph/keine Communities gebaut (Phase 3 nicht ausgeführt).

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- Übersicht: Vertreter-Paper-IDs (`representatives`) je Community.
- Einzelabruf: zusätzlich die vollständigen Mitglieds-Paper-IDs (`members`).

## 8. Reproduzierbarkeit

- Deterministisch: persistierte Communities mit fixem Louvain-Seed aus Phase 3 ([ADR 0007](../../../../docs/adr/0007-graphrag-index-phase3-option-b.md)); die Sortierung nach `size` mit Tie-Break über `community_id` ist stabil.

## 9. Testabdeckung

- `tests/indexing/test_graph_index.py`: `CommunityView.to_dict()` (Serialisierung).
- `tests/retrieval/test_topics.py`: Filterung (`min_size`), Deckelung (`limit`, `truncated`/`total_matching`), Einzelabruf (`community_id`), Fehler-/Edge-Cases (`invalid_input`, `not_found`).
- `tests/mcp_server/test_server.py`: Tool-Contract über einen In-Memory-Client (Erfolg + Fehler-Envelope, beide Modi).

## 10. Beispiel

Real erzeugt gegen den Testindex aus `tests/mcp_server/conftest.py` (zwei Communities: Attention/Transformer und Graph/Community-Detection); geprüft in `tests/mcp_server/test_spec_examples.py`.

Anfrage (Übersichts-Modus):

```json
{}
```

Antwort:

```json
{
  "topics": [
    {
      "community_id": 0,
      "size": 2,
      "keywords": ["attention", "transformer", "encoder", "self", "architecture", "aufmerksamkeit", "heads", "language", "pretraining", "vorarbeit"],
      "summary": "transformer attention mechanism self attention encoder doi:10.1145/1234",
      "representatives": ["aaaa0001", "aaaa0002"]
    },
    {
      "community_id": 1,
      "size": 2,
      "keywords": ["graph", "dataset", "community", "detection", "louvain", "message", "modularity", "network", "neural", "nodes"],
      "summary": "graph neural network message passing nodes",
      "representatives": ["bbbb0001", "bbbb0002"]
    }
  ],
  "total_matching": 2,
  "truncated": false
}
```
