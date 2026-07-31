# Tool-Spezifikation: `list_topics`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/indexing/graph_index.py` (`load_communities`); als MCP-Tool
> registriert in **Phase 5** ([ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `list_topics` |
| **Version** | `0.1.0` |
| **Capability-Schicht** | Übersicht / Katalog (siehe README.md) |
| **Status** | Implementiert (Phase 5) |

---

## 1. Zweck

Listet die **Themencluster des Korpus** – die Louvain-Communities des Paper-Ähnlichkeitsgraphen ([ADR 0007](../../../../docs/adr/0007-graphrag-index-phase3-option-b.md)) – mit Größe, Keywords, Mitglieds- und Vertreter-Papern. Gibt einem Agenten einen corpusweiten Überblick und hilft, eine Community für `search_global`/`search_drift` auszuwählen.

## 2. Input-Schema

Keine Parameter.

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).

## 3. Output-Schema

```json
{
  "topics": [
    {
      "community_id": 0,
      "size": 12,
      "keywords": ["…"],
      "summary": "…",
      "members": ["…"],
      "representatives": ["…"]
    }
  ]
}
```

`topics` ist aufsteigend nach `community_id` sortiert. `summary` ist ein **extraktives** Leit-Snippet (repräsentatives Paper); `representatives` sind die zentralsten Paper der Community.

## 4. Annahmen und Vorbedingungen

- Ein Index **und** der Paper-Ähnlichkeitsgraph wurden gebaut (`python -m scripts.ingest`, Phase 3).

## 5. Grenzen (Nicht-Ziele)

- **Keine** Query/Relevanz-Filterung (dafür `search_global`) und **keine** Chunk-Provenienz.
- Keine LLM-Formulierung im Tool – nur strukturierte Community-Sichten.

## 6. Fehlerverhalten

- `not_found`: Index-Datei fehlt.
- `constraint_violation`: kein Graph/keine Communities gebaut (Phase 3 nicht ausgeführt).

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- Je Community: Mitglieds- (`members`) und Vertreter-Paper-IDs (`representatives`).

## 8. Reproduzierbarkeit

- Deterministisch: persistierte Communities mit fixem Louvain-Seed aus Phase 3 ([ADR 0007](../../../../docs/adr/0007-graphrag-index-phase3-option-b.md)).

## 9. Testabdeckung

- `tests/indexing/test_graph_index.py`: `CommunityView.to_dict()` (Serialisierung).
- `tests/mcp_server/test_server.py`: Tool-Contract über einen In-Memory-Client (Erfolg + Fehler-Envelope).
