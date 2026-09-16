# Tool-Spezifikation: `search_drift`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/drift.py`; als MCP-Tool registriert in **Phase 5**
> ([ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md)).

> **Änderung `0.1.0` → `0.2.0` (Phase 10 / V2, [ADR 0022](../../../../docs/adr/0022-drift-community-union-and-fallback-phase10.md)):**
> Das Feld `community` (ein Objekt oder `null`) ist durch die Liste **`communities`** ersetzt, neu
> hinzu kommt **`fallback`**. Das ist ein **bewusster Bruch** des Output-Schemas; das
> Input-Schema bleibt unverändert.

> **Änderung `0.3.0` → `0.4.0` ([ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md)):**
> `k` hat jetzt eine Obergrenze (`50`, geteilt mit den übrigen Retrieval-Werkzeugen); ebenso die
> Python-API-Option `communities`. Abwärtskompatibel für jeden bestehenden Aufruf innerhalb dieser
> Grenze.

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `search_drift` (generisch) |
| **Version** | `0.4.0` |
| **Capability-Schicht** | Retrieval – DRIFT Search (siehe README.md) |
| **Status** | Implementiert (Phase 4; Community-Vereinigung und Fallback seit Phase 10 / V2) |

---

## 1. Zweck

Beantwortet **Widerspruchs-/Vergleichsfragen** über einen **pragmatischen Global→Local-Hybrid** ([ADR 0008](../../../../docs/adr/0008-retrieval-and-query-router-phase4.md)): zuerst die thematisch passendsten **Communities** bestimmen (Global-Ranking, Default die Top-5), dann **innerhalb der Vereinigung** ihrer Mitglieds-Paper die query-relevantesten Chunks suchen (lokale Verfeinerung). So verbindet DRIFT den corpusweiten Kontext mit belegten Einzelpassagen. Bewusst **kein** echtes iteratives Multi-Step-DRIFT (right-sized).

Liefert dieser Pfad **keine** Belege, fällt das Werkzeug sichtbar auf die Chunk-Suche **ohne** Paper-Filter zurück (`fallback = true`) – die leere Antwort entfällt damit ([ADR 0022](../../../../docs/adr/0022-drift-community-union-and-fallback-phase10.md)).

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `query` | `str` | ja | Natürlichsprachige Anfrage; nicht leer. |
| `k` | `int` | nein | Maximale Zahl der lokal verfeinerten Chunk-Belege (`0 < k <= 50`); Default `6`. |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).
>
> Die Obergrenze `50` ist die geteilte `MAX_RESULT_COUNT` aller Retrieval-Werkzeuge ([ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md), Modul `research_graphrag.limits`) – sie gilt auch für die Python-API-Option `communities`.
>
> Die Zahl der berücksichtigten Communities ist **bewusst kein** Tool-Parameter: Sie beschreibt die interne Auswahl, nicht die gewünschte Ergebnisgröße, und ist – wie die Zahl der Local-Seeds – gemessen statt wählbar ([ADR 0022](../../../../docs/adr/0022-drift-community-union-and-fallback-phase10.md)). Die Python-API bietet sie als `communities`; eine CLI-Option gibt es bewusst **noch nicht** (Begründung im ADR).

## 3. Output-Schema

```json
{
  "query": "…",
  "communities": [
    {
      "community_id": 0,
      "score": 0.21,
      "size": 27,
      "keywords": ["graph", "graphrag", "retrieval", "…"],
      "representatives": [ { "paper_id": "…", "document_kind": "full", "source_uri": "file:///…", "snippet": "…", "identifiers": { "arxiv": "…" }, "citation_key": "…" } ]
    }
  ],
  "fallback": false,
  "citations": [
    { "paper_id": "…", "document_kind": "full", "section_title": "…", "page_number": 6, "page_end": 6, "chunk_id": "…", "score": 0.0325, "score_tfidf": 0.3, "score_bm25": 14.2, "source_uri": "file:///…", "snippet": "…", "identifiers": { "doi": "10.…", "arxiv": "2503.06689", "url": "https://…" }, "citation_key": "Beispiel2023" }
  ]
}
```

`communities` ist absteigend nach Score sortiert und **leer**, wenn keine Community zur Anfrage passt. In diesem Fall ist `fallback` **`true`**, und die `citations` stammen aus der corpusweiten Chunk-Suche – sie sind dann **nicht** auf Community-Mitglieder beschränkt. `fallback` ist ebenfalls `true`, wenn Communities gefunden wurden, ihre Mitglieder aber keinen passenden Chunk enthalten. Sind auch corpusweit keine Belege zu finden, bleibt `citations` leer.

`document_kind` ist `full` (Volltext) oder `reference` (**Referenz-Eintrag ohne Volltext**). In den `citations` sind Referenz-Einträge **nachrangig** ([ADR 0031](../../../../docs/adr/0031-reference-contract-and-guardrail-phase13.md)); als Community-Vertreter treten sie nicht auf, weil sie keiner Community angehören.

`communities[*].score` ist seit Phase 10 / V4 ([ADR 0036](../../../../docs/adr/0036-global-community-ranking-over-member-chunks-phase10.md)) das Mittel der fünf höchsten Hybrid-Chunk-Scores der Mitgliederpaper (zuvor ein separater TF-IDF-Score über Keywords + Summary); in den `citations` ist `score` der **Fusionswert** derselben Hybrid-Wertung mit den Rohwerten `score_tfidf`/`score_bm25` ([ADR 0014](../../../../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)). Beide Werte entstehen jetzt aus derselben Quelle, sind aber durch die Aggregation weiterhin **nicht** direkt miteinander vergleichbar.

Jeder Beleg – Community-Vertreter wie Chunk-Zitat – trägt zusätzlich `identifiers` und `citation_key` und ist damit **extern auflösbar**; beide stammen aus dem aufgelösten Metadatensatz des Papers und können leer sein ([ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md)).

## 4. Annahmen und Vorbedingungen

- Ein Index **inklusive Graph/Communities** wurde gebaut (`python -m scripts.ingest`, Phase 3).

## 5. Grenzen (Nicht-Ziele)

- Kein echtes iteratives DRIFT; nur **eine** Community-Auswahl plus lokale Verfeinerung.
- Die Community-Rangfolge wirkt **nur über die Zugehörigkeit**: In der Vereinigung entscheidet allein die Chunk-Wertung, nicht der Rang der Community.
- Der Fallback ist die **Basic-Suche**, keine DRIFT-Leistung – er verhindert eine leere Antwort, verbessert aber kein Retrieval. Seit Phase 10 / V4 tritt der Fall „Community-Pfad ohne jeden Beleg trotz echtem Basic-Treffer" am realen Korpus nicht mehr auf, weil beide Pfade dieselbe Chunk-Wertung teilen; die Garantie bleibt als Auffangnetz bestehen ([ADR 0036](../../../../docs/adr/0036-global-community-ranking-over-member-chunks-phase10.md)).
- Die Kandidatenmenge der Vereinigung kann bei breit gestreuten Fragen groß werden und die lokale Verfeinerung verdünnen – seit V4 tendenziell öfter, weil mehr Communities positiv scoren (ADR 0036).
- Keine LLM-Formulierung im Tool – nur strukturierte Evidenz + Provenienz.

## 6. Fehlerverhalten

- `invalid_input`: leere `query`, `k <= 0` oder `k > 50`, `communities <= 0` oder `communities > 50` (Grenzen für `communities` nur über CLI/API erreichbar).
- `not_found`: Index-Datei fehlt.
- `constraint_violation`: kein Graph gebaut bzw. keine Communities vorhanden. Ein **defekter** Index wird bewusst **nicht** vom Fallback aufgefangen.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- **Community-Kontext**: je Community `community_id`, `score`, `size`, `keywords`, repräsentative Paper.
- **Lokale Belege**: Chunk-Zitate (`paper_id`, `section_title`, `page_number`, `page_end`, `chunk_id`, `score`, `score_tfidf`, `score_bm25`, `source_uri`, `snippet`), beschränkt auf die Mitglieds-Paper der gewählten Communities – **außer** im Fallback (`fallback = true`), wo sie aus dem gesamten Korpus stammen.

## 8. Reproduzierbarkeit

- Deterministisch: Community-Auswahl über das Global-Ranking (Phase-3-Communities, fixer Seed, Tie-Break über `community_id`); lokale Verfeinerung und Fallback über die Hybrid-Wertung (BM25 + TF-IDF, Reciprocal Rank Fusion, [ADR 0014](../../../../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)) mit Tie-Break über `chunk_id`.

## 9. Testabdeckung

- `tests/retrieval/test_drift.py`: Community-Vereinigung + lokale Verfeinerung (auf Mitglieder beschränkt), Fallback bei fehlender Übereinstimmung (Belege identisch zur Basic-Suche), die seit V4 geschlossene alte Fallback-Lücke (`test_drift_finds_the_orphans_own_community_instead_of_falling_back`), `communities`-Grenzen, Determinismus, Fehler-/Edge-Cases (`invalid_input`, `not_found`, `constraint_violation`), Output-Schema.
