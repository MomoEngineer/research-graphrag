# Tool-Spezifikation: `search_drift`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/drift.py`; als MCP-Tool registriert in **Phase 5**
> ([ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `search_drift` (generisch) |
| **Version** | `0.1.0` |
| **Capability-Schicht** | Retrieval – DRIFT Search (siehe README.md) |
| **Status** | Implementiert (Phase 4) |

---

## 1. Zweck

Beantwortet **Widerspruchs-/Vergleichsfragen** über einen **pragmatischen Global→Local-Hybrid** ([ADR 0008](../../../../docs/adr/0008-retrieval-and-query-router-phase4.md)): zuerst die thematisch passendste **Community** bestimmen (Global-Ranking), dann **innerhalb** ihrer Mitglieds-Paper die query-relevantesten Chunks suchen (lokale Verfeinerung). So verbindet DRIFT den corpusweiten Kontext mit belegten Einzelpassagen. Bewusst **kein** echtes iteratives Multi-Step-DRIFT (right-sized).

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `query` | `str` | ja | Natürlichsprachige Anfrage; nicht leer. |
| `k` | `int` | nein | Maximale Zahl der lokal verfeinerten Chunk-Belege (> 0); Default `6`. |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).

## 3. Output-Schema

```json
{
  "query": "…",
  "community": {
    "community_id": 0,
    "score": 0.21,
    "size": 27,
    "keywords": ["graph", "graphrag", "retrieval", "…"],
    "representatives": [ { "paper_id": "…", "source_uri": "file:///…", "snippet": "…" } ]
  },
  "citations": [
    { "paper_id": "…", "section_title": "…", "page_number": 6, "chunk_id": "…", "score": 0.3, "source_uri": "file:///…", "snippet": "…" }
  ]
}
```

`community` ist `null` und `citations` leer, wenn keine Community zur Anfrage passt.

## 4. Annahmen und Vorbedingungen

- Ein Index **inklusive Graph/Communities** wurde gebaut (`python -m scripts.ingest`, Phase 3).

## 5. Grenzen (Nicht-Ziele)

- Kein echtes iteratives DRIFT; nur **eine** Community-Auswahl plus lokale Verfeinerung.
- Keine LLM-Formulierung im Tool – nur strukturierte Evidenz + Provenienz.

## 6. Fehlerverhalten

- `invalid_input`: leere `query` oder `k <= 0`.
- `not_found`: Index-Datei fehlt.
- `constraint_violation`: kein Graph gebaut bzw. keine Communities vorhanden.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- **Community-Kontext**: `community_id`, `score`, `size`, `keywords`, repräsentative Paper.
- **Lokale Belege**: Chunk-Zitate (`paper_id`, `section_title`, `page_number`, `chunk_id`, `score`, `source_uri`, `snippet`), beschränkt auf die Mitglieds-Paper der Community.

## 8. Reproduzierbarkeit

- Deterministisch: Community-Auswahl über das Global-Ranking (Phase-3-Communities, fixer Seed); lokale Verfeinerung über TF-IDF mit Tie-Break über `chunk_id`.

## 9. Testabdeckung

- `tests/retrieval/test_drift.py`: Community-Auswahl + lokale Verfeinerung (auf Mitglieder beschränkt), No-Match, Fehler-/Edge-Cases (`invalid_input`, `not_found`, `constraint_violation`), Output-Schema.
