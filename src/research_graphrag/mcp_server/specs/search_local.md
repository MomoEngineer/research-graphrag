# Tool-Spezifikation: `search_local`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/local.py`; als MCP-Tool registriert in **Phase 5**
> ([ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `search_local` (generisch) |
| **Version** | `0.1.0` |
| **Capability-Schicht** | Retrieval – Local Search (siehe README.md) |
| **Status** | Implementiert (Phase 4) |

---

## 1. Zweck

Beantwortet **Detailfragen zu einem Paper** und **Zitations-/Methodennetz-Fragen** (Multi-Hop), indem beide „Local"-Aspekte kombiniert werden ([ADR 0008](../../../../docs/adr/0008-retrieval-and-query-router-phase4.md)): (1) **Seed** – der zur Anfrage beste Chunk; (2) **Chunk-Nachbarschaft** – die ähnlichsten Chunks zum Seed-Chunk (Chunk↔Chunk-Kosinus zur Abfragezeit); (3) **Paper-Fan-out** – Nachbarpaper des Seed-Papers über den Paper-Ähnlichkeitsgraphen (Phase 3), je Nachbar der query-relevanteste Chunk als Beleg.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `query` | `str` | ja | Natürlichsprachige Anfrage; nicht leer. |
| `k` | `int` | nein | Maximale Zahl der Chunk-Nachbarn (> 0); Default `5`. |
| `fan_out` | `int` | nein | Maximale Zahl der Graph-Nachbarpaper (>= 0); Default `5`. `0` überspringt den Fan-out (benötigt keinen Graphen). |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).

## 3. Output-Schema

```json
{
  "query": "…",
  "seed": {
    "paper_id": "…",
    "section_title": "…",
    "page_number": 6,
    "page_end": 6,
    "chunk_id": "…",
    "score": 0.0325,
    "score_tfidf": 0.42,
    "score_bm25": 18.7,
    "source_uri": "file:///…",
    "snippet": "…"
  },
  "neighborhood": [ { "paper_id": "…", "section_title": "…", "page_number": 5, "page_end": 5, "chunk_id": "…", "score": 0.33, "score_tfidf": 0.33, "score_bm25": 0.0, "source_uri": "file:///…", "snippet": "…" } ],
  "fan_out": [ { "paper_id": "…", "weight": 0.46, "citation": { "paper_id": "…", "section_title": "…", "page_number": 6, "page_end": 7, "chunk_id": "…", "score": 0.0164, "score_tfidf": 0.2, "score_bm25": 9.1, "source_uri": "file:///…", "snippet": "…" } } ]
}
```

`seed` ist `null`, wenn keine Übereinstimmung besteht (dann sind `neighborhood`/`fan_out` leer). Ein Fan-out-`citation` kann `null` sein, wenn der Nachbar zur Anfrage keinen Treffer hat.

Bei `seed` und den Fan-out-Belegen ist `score` der **Fusionswert** der Hybrid-Wertung (BM25 + TF-IDF per Reciprocal Rank Fusion, [ADR 0014](../../../../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)), `score_tfidf`/`score_bm25` sind die Rohwerte. In der **`neighborhood`** bleibt `score` der TF-IDF-Kosinus zwischen zwei Chunks (identisch zu `score_tfidf`, `score_bm25` = `0.0`): BM25 ist ein Anfrage-Dokument-Modell und wird hier bewusst nicht angewendet.

## 4. Annahmen und Vorbedingungen

- Ein Index wurde gebaut (`python -m scripts.ingest`).
- Für `fan_out > 0` muss der Paper-Ähnlichkeitsgraph vorhanden sein (Phase 3, Teil der Ingestion).

## 5. Grenzen (Nicht-Ziele)

- Kein semantischer Entitäts-/Zitationsgraph (Phase 7); der Fan-out folgt der **thematischen** TF-IDF-Ähnlichkeit.
- Keine Community-Synthese (Global), kein DRIFT.
- Keine LLM-Formulierung im Tool – nur strukturierte Evidenz + Provenienz.

## 6. Fehlerverhalten

- `invalid_input`: leere `query`, `k <= 0` oder `fan_out < 0`.
- `not_found`: Index-Datei fehlt.
- `constraint_violation`: Index enthält keine Chunks; bzw. `fan_out > 0`, aber kein Graph gebaut.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- Seed und Chunk-Nachbarn: `paper_id`, `section_title`, `page_number`, `page_end`, `chunk_id`, `score`, `score_tfidf`, `score_bm25`, `source_uri`, `snippet`.
- Fan-out: Nachbar-`paper_id`, Kanten-`weight` und (optional) ein Chunk-`citation`.

## 8. Reproduzierbarkeit

- Deterministisch: Seed und Fan-out-Belege über die Hybrid-Wertung (BM25 `k1 = 1.5`/`b = 0.75` + TF-IDF, Reciprocal Rank Fusion `K = 60`, [ADR 0014](../../../../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)), Chunk-Nachbarschaft über den TF-IDF-Kosinus – jeweils mit Tie-Break über `chunk_id`; Graph-Kanten deterministisch aus Phase 3 (fixer Seed, `source < target`).

## 9. Testabdeckung

- `tests/retrieval/test_local.py`: Seed/Nachbarschaft/Fan-out, `fan_out=0` ohne Graph, No-Match, Fehler-/Edge-Cases (`invalid_input`, `not_found`, `constraint_violation`), Output-Schema.
