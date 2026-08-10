# Tool-Spezifikation: `search_basic`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/basic.py`; als MCP-Tool registriert in **Phase 5**
> ([ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `search_basic` (generisch) |
| **Version** | `0.2.0` |
| **Capability-Schicht** | Retrieval – Basic Search (siehe README.md) |
| **Status** | Implementiert (Phase 0b, Durchstich) |

---

## 1. Zweck

Beantwortet exakte/faktische Fragen über **Top-k-Vektorsuche (TF-IDF)** auf Paper-Chunks und liefert **belegte Zitate** (Provenienz). Entspricht dem GraphRAG-Suchmodus **Basic**; die natürlichsprachige Antwort formuliert der aufrufende Agent (Copilot) über die LLM-Bridge ([ADR 0004](../../../../docs/adr/0004-llm-bridge-via-mcp-sampling.md)).

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `query` | `str` | ja | Natürlichsprachige Anfrage; nicht leer. |
| `k` | `int` | nein | Maximale Trefferzahl (> 0); Default `5`. |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).

## 3. Output-Schema

```json
{
  "query": "…",
  "citations": [
    {
      "paper_id": "…",
      "document_kind": "full",
      "section_title": "…",
      "page_number": 1,
      "page_end": 1,
      "chunk_id": "…",
      "score": 0.0325,
      "score_tfidf": 0.42,
      "score_bm25": 18.7,
      "source_uri": "file:///…",
      "snippet": "…",
      "identifiers": { "doi": "10.…", "arxiv": "2503.06689", "url": "https://…" },
      "citation_key": "Beispiel2023"
    }
  ]
}
```

`citations` ist absteigend nach `score` sortiert (Tie-Break über `chunk_id`) und **leer**, wenn keine Übereinstimmung besteht.

`document_kind` ist `full` (Volltext) oder `reference` (**Referenz-Eintrag ohne Volltext** – nur Titel und Abstract). Ein Beleg mit `reference` trägt `page_number = 0`; er belegt die Aussage **nicht vollständig** und ist deshalb in der Trefferliste **nachrangig** ([ADR 0031](../../../../docs/adr/0031-reference-contract-and-guardrail-phase13.md)).

`identifiers` und `citation_key` machen jeden Beleg **extern auflösbar** und stammen aus dem aufgelösten Metadatensatz des Papers; `identifiers` enthält nur belegte Schlüssel und kann leer sein, `citation_key` ist eine Anzeigehilfe ohne Eindeutigkeitsgarantie. Die **fertige** Literaturangabe liefert `get_reference` ([ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md)).

`score` ist der **Fusionswert** der Hybrid-Wertung (Reciprocal Rank Fusion über BM25 und TF-IDF, [ADR 0014](../../../../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)) – ein **Rangmaß, keine Ähnlichkeit**; Werte sind nur *innerhalb* einer Antwort vergleichbar. `score_tfidf` und `score_bm25` sind die Rohwerte der beiden Verfahren und jeweils `0.0`, wenn dieses Verfahren den Chunk nicht positiv bewertet hat.

## 4. Annahmen und Vorbedingungen

- Ein Index wurde gebaut (`python -m scripts.ingest`).

## 5. Grenzen (Nicht-Ziele)

- Kein Graph-Traversal (Local), keine Community-Synthese (Global), kein DRIFT.
- Keine LLM-Formulierung im Tool – nur strukturierte Evidenz + Provenienz.

## 6. Fehlerverhalten

- `invalid_input`: leere `query` oder `k <= 0`.
- `not_found`: Index-Datei fehlt.
- `constraint_violation`: Index enthält keine Chunks.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- Je Zitat: `paper_id`, `section_title`, `page_number`, `page_end`, `chunk_id`, `score`, `score_tfidf`, `score_bm25`, `source_uri`, `snippet`.
- `page_number` ist die Start-, `page_end` die Endseite des Chunks; beide sind identisch, solange der Chunk auf einer Seite liegt ([ADR 0013](../../../../docs/adr/0013-chunking-refinement-phase7.md)).

## 8. Reproduzierbarkeit

- Deterministisch: eine gemeinsame Tokenisierung (`scikit-learn`), daraus TF-IDF-Kosinus über l2-normalisierte Vektoren **und** handimplementiertes BM25 (`k1 = 1.5`, `b = 0.75`), fusioniert per Reciprocal Rank Fusion (`K = 60`); Tie-Break über `chunk_id` ([ADR 0014](../../../../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)).

## 9. Testabdeckung

- `tests/retrieval/test_basic.py`: Funktions-/Provenienz-Test, No-Match, Fehler-/Edge-Cases (`not_found`, `invalid_input`).
