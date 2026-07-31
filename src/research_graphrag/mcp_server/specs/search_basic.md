# Tool-Spezifikation: `search_basic`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/basic.py`. Als MCP-Tool wird `search_basic` in **Phase 5**
> registriert; diese Spec beschreibt bereits den Vertrag.

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `search_basic` (generisch) |
| **Version** | `0.1.0` |
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
      "section_title": "…",
      "page_number": 1,
      "chunk_id": "…",
      "score": 0.42,
      "source_uri": "file:///…",
      "snippet": "…"
    }
  ]
}
```

`citations` ist absteigend nach `score` sortiert (Tie-Break über `chunk_id`) und **leer**, wenn keine Übereinstimmung besteht.

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

- Je Zitat: `paper_id`, `section_title`, `page_number`, `chunk_id`, `score`, `source_uri`, `snippet`.

## 8. Reproduzierbarkeit

- Deterministisch: TF-IDF (`scikit-learn`), Kosinus über l2-normalisierte Vektoren, Tie-Break über `chunk_id`.

## 9. Testabdeckung

- `tests/retrieval/test_basic.py`: Funktions-/Provenienz-Test, No-Match, Fehler-/Edge-Cases (`not_found`, `invalid_input`).
