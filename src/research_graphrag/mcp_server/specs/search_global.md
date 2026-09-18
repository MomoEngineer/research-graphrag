# Tool-Spezifikation: `search_global`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/global_search.py`; als MCP-Tool registriert in
> **Phase 5** ([ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md)).

> **Änderung `0.2.0` → `0.3.0` ([ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md)):**
> `n` hat jetzt eine Obergrenze (`50`, geteilt mit den übrigen Retrieval-Werkzeugen). Abwärtskompatibel
> für jeden bestehenden Aufruf mit `n <= 50`.

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `search_global` (generisch) |
| **Version** | `0.3.0` |
| **Capability-Schicht** | Retrieval – Global Search (siehe README.md) |
| **Status** | Implementiert (Phase 4) |

---

## 1. Zweck

Beantwortet **Cross-Paper-/Themenfragen** als Offline-Analog zum GraphRAG-„Global"-Map-Reduce ([ADR 0008](../../../../docs/adr/0008-retrieval-and-query-router-phase4.md)): Jede Louvain-Community (Phase 3) wird über die **Hybrid-Chunk-Scores ihrer Mitgliederpaper** gescort – der Community-Score ist das Mittel der fünf höchsten Mitglieds-Chunk-Scores der Anfrage, dieselbe Wertung, die Basic/Local/DRIFT teilen ([ADR 0036](../../../../docs/adr/0036-global-community-ranking-over-member-chunks-phase10.md), Phase 10 / V4). Keywords und Summary bleiben Teil der Ausgabe, tragen aber seit V4 nicht mehr das Ranking – die passendsten Communities werden mit **repräsentativer Paper-Provenienz** zurückgegeben.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `query` | `str` | ja | Natürlichsprachige Anfrage; nicht leer. |
| `n` | `int` | nein | Maximale Zahl der Communities (`0 < n <= 50`); Default `5`. |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).
>
> Die Obergrenze `50` ist die geteilte `MAX_RESULT_COUNT` aller Retrieval-Werkzeuge ([ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md), Modul `research_graphrag.limits`).

## 3. Output-Schema

```json
{
  "query": "…",
  "communities": [
    {
      "community_id": 9,
      "score": 0.18,
      "size": 4,
      "keywords": ["graph", "retrieval", "…"],
      "representatives": [
        {
          "paper_id": "…",
          "document_kind": "full",
          "source_uri": "file:///…",
          "snippet": "…",
          "identifiers": { "doi": "10.…", "arxiv": "2503.06689", "url": "https://…" },
          "citation_key": "Beispiel2023"
        }
      ]
    }
  ]
}
```

`communities` ist absteigend nach `score` sortiert (Tie-Break kleinere `community_id`) und **leer**, wenn keine Community zur Anfrage passt.

`document_kind` ist `full` (Volltext) oder `reference` (**Referenz-Eintrag ohne Volltext**, [ADR 0031](../../../../docs/adr/0031-reference-contract-and-guardrail-phase13.md)). Als Community-Vertreter treten Referenz-Einträge nicht auf – sie gehören keiner Community an.

Jeder Vertreter trägt zusätzlich `identifiers` und `citation_key` und ist damit **extern auflösbar**; beide stammen aus dem aufgelösten Metadatensatz des Papers und können leer sein ([ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md)).

## 4. Annahmen und Vorbedingungen

- Ein Index **inklusive Graph/Communities** wurde gebaut (`python -m scripts.ingest`, Phase 3).

## 5. Grenzen (Nicht-Ziele)

- Communities sind **lexikalisch-thematisch** (TF-IDF/Louvain), kein semantischer Entitätsgraph.
- Zusammenfassungen sind **extraktiv** (Phase 3), nicht LLM-generiert; keine Chunk-Belege auf Seiten-Ebene (dafür Basic/Local/DRIFT).
- Keine LLM-Formulierung im Tool – nur strukturierte Evidenz + Provenienz.

## 6. Fehlerverhalten

- `invalid_input`: leere `query`, `n <= 0` oder `n > 50`.
- `not_found`: Index-Datei fehlt.
- `constraint_violation`: kein Graph gebaut bzw. keine Communities vorhanden.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- Je Community: `community_id`, `score`, `size`, `keywords` und **repräsentative Paper** (`paper_id`, `source_uri`, Leit-`snippet`, `identifiers`, `citation_key`).

## 8. Reproduzierbarkeit

- Deterministisch: Communities/Keywords aus Phase 3 (fixer Louvain-Seed); Query-Ranking über den persistierten, tokenisierten Zustand des Chunk-Index (`TfidfIndex.score_chunks_by_paper`, Hybrid-Wertung aus BM25 + TF-IDF per Rang-Fusion) mit Tie-Break über `community_id` ([ADR 0036](../../../../docs/adr/0036-global-community-ranking-over-member-chunks-phase10.md)). Die Keywords sind zusätzlich über die kuratierte **Keyword-Politik** gefiltert ([ADR 0015](../../../../docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)).

## 9. Testabdeckung

- `tests/retrieval/test_global.py`: Community-Ranking, No-Match, Fehler-/Edge-Cases (`invalid_input`, `not_found`, `constraint_violation`), Output-Schema.

## 10. Beispiel

Real erzeugt gegen den Testindex aus `tests/mcp_server/conftest.py` (zwei Communities: Attention/Transformer und Graph/Community-Detection); geprüft in `tests/mcp_server/test_spec_examples.py`.

Anfrage:

```json
{ "query": "graph communities", "n": 1 }
```

Antwort:

```json
{
  "query": "graph communities",
  "communities": [
    {
      "community_id": 1,
      "score": 0.0320,
      "size": 2,
      "keywords": ["graph", "dataset", "community", "detection", "louvain", "message", "modularity", "network", "neural", "nodes"],
      "representatives": [
        {
          "paper_id": "bbbb0001",
          "document_kind": "full",
          "source_uri": "file:///bbbb0001.pdf",
          "snippet": "graph neural network message passing nodes",
          "identifiers": {},
          "citation_key": "bbbb0001"
        },
        {
          "paper_id": "bbbb0002",
          "document_kind": "full",
          "source_uri": "file:///bbbb0002.pdf",
          "snippet": "citation graph clustering communities dataset",
          "identifiers": {},
          "citation_key": "bbbb0002"
        }
      ]
    }
  ]
}
```
