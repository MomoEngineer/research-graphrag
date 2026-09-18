# Tool-Spezifikation: `get_citations`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/citations.py` über
> `src/research_graphrag/indexing/citation_graph.py`; als MCP-Tool registriert
> ([ADR 0011](../../../../docs/adr/0011-intra-corpus-citation-graph-phase7.md)).

> **Änderung `0.2.0` → `0.3.0` ([ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md)):**
> Neuer Parameter `limit` deckelt `cites`/`cited_by` je Richtung (dieselbe `MAX_RESULT_COUNT` wie
> die übrigen Retrieval-Werkzeuge); neue Felder `cites_total`/`cited_by_total` machen eine
> Kürzung sichtbar. Abwärtskompatibel für jedes Paper mit höchstens 50 Kanten je Richtung
> (heute jedes Paper im Korpus).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `get_citations` |
| **Version** | `0.3.0` |
| **Capability-Schicht** | Graph / Zitationsnetz (siehe README.md) |
| **Status** | Implementiert (Phase 7 / A2) |

---

## 1. Zweck

Beantwortet **Zitationsfragen innerhalb des eigenen Korpus**: „welche Paper zitiert X?" und „welche Paper bauen auf X auf (zitieren X)?". Grundlage sind die beim Ingest deterministisch erzeugten `CITES`-Kanten (DOI-/arXiv-/Titel-Match im Referenzabschnitt). Ergänzt den **Ähnlichkeits**-Fan-out aus `search_local`, der bewusst *keine* Zitation abbildet.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `paper_id` | `str` | ja | Stabile Paper-ID (kein Datei-Pfad); nicht leer. Quelle: Treffer der `search_*`-Tools oder `list_topics`. |
| `limit` | `int` | nein | Maximale Zahl der Einträge **je Richtung** (`cites` und `cited_by` unabhängig; `0 < limit <= 50`); Default `50`. |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).
>
> Die Obergrenze `50` ist die geteilte `MAX_RESULT_COUNT` aller Retrieval-Werkzeuge ([ADR 0037](../../../../docs/adr/0037-mcp-tool-response-size-ceiling.md), Modul `research_graphrag.limits`).

## 3. Output-Schema

```json
{
  "paper": { "paper_id": "…", "document_kind": "full", "source_uri": "file:///…", "snippet": "…", "identifiers": { "arxiv": "…" }, "citation_key": "…" },
  "cites": [
    { "paper_id": "…", "document_kind": "reference", "source_uri": "file:///…", "snippet": "…", "identifiers": { "doi": "10.…" }, "citation_key": "Beispiel2023", "method": "doi" }
  ],
  "cites_total": 1,
  "cited_by": [
    { "paper_id": "…", "document_kind": "full", "source_uri": "file:///…", "snippet": "…", "identifiers": {}, "citation_key": "", "method": "title" }
  ],
  "cited_by_total": 1
}
```

- `cites` = Paper, die das angefragte Paper **zitiert**; `cited_by` = Paper, die es **zitieren**. Beide Listen sind auf `limit` Einträge gedeckelt; `cites_total`/`cited_by_total` nennen die tatsächliche Zahl **vor** der Deckelung – eine Kürzung ist damit immer sichtbar (`cites_total > limit` bzw. `cited_by_total > limit`).
- `document_kind` ist `full` (Volltext) oder `reference` (**Referenz-Eintrag ohne Volltext**). Gerade in `cites` ist das häufig: Ein Referenz-Eintrag existiert oft genau deshalb, weil sein Volltext nicht beschaffbar war – als Kanten**ziel** ist er trotzdem vollwertig ([ADR 0031](../../../../docs/adr/0031-reference-contract-and-guardrail-phase13.md)).
- `method` ∈ `doi` | `arxiv` | `title` und benennt das **präziseste** Kriterium, über das die Kante erkannt wurde (Präzedenz `doi` > `arxiv` > `title`) – damit ist die Belastbarkeit einer Kante für den Aufrufer sichtbar.
- `identifiers` und `citation_key` machen jedes genannte Paper **extern auflösbar**; beide stammen aus dem aufgelösten Metadatensatz und können leer sein ([ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md)). Belegte Schlüssel sind `doi`, `arxiv` und `url`.
- Beide Listen können leer sein (kein erkannter Bezug innerhalb des Korpus) und sind **stabil sortiert** (nach der `paper_id` des Gegenübers).

## 4. Annahmen und Vorbedingungen

- Ein Index wurde gebaut (`python -m scripts.ingest`) und enthält den Zitationsgraphen (`meta.citation_schema_version`, Tabelle `citation_edges`).

## 5. Grenzen (Nicht-Ziele)

- **Nur Intra-Korpus:** externe Referenzen werden nicht aufgelöst und nicht gemeldet (GROBID = Zielbild, [ADR 0005](../../../../docs/adr/0005-graphrag-index-backend-open.md)).
- **Kein Zitationskontext** (*warum*/*wo* zitiert) und keine Textstelle der Referenz – die Kante ist auf Paper-Ebene belegt, nicht auf Chunk-Ebene.
- **Kein Multi-Hop in einem Aufruf:** Pfade über mehrere Ebenen entstehen durch wiederholte Aufrufe (Text2Cypher/Kuzu = Zielbild).
- Keine LLM-Formulierung im Tool – nur strukturierte Kanten + Provenienz.
- **Recall ist begrenzt:** Paper ohne heuristisch erkannten Referenzabschnitt liefern keine ausgehenden Kanten; DOI/arXiv zählen nur, wenn sie im Frontmatter des Zielpapers belegt sind ([ADR 0011](../../../../docs/adr/0011-intra-corpus-citation-graph-phase7.md)).

## 6. Fehlerverhalten

- `invalid_input`: leere `paper_id`, `limit <= 0` oder `limit > 50`.
- `not_found`: Index-Datei fehlt **oder** `paper_id` ist unbekannt.
- `constraint_violation`: der Index enthält **keinen** Zitationsgraphen (Ingest mit älterem Stand gebaut).

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- Je Gegenüber `source_uri` (Quelle zum Original) und ein extraktives Leit-Snippet; zusätzlich `method` als Nachweis, **woran** die Kante erkannt wurde.

## 8. Reproduzierbarkeit

- Deterministisch: direkte Index-Reads (SQLite) auf einem deterministisch gebauten Kantensatz; keine stochastischen Anteile, keine Schwellenwert-Heuristik zur Abfragezeit.

## 9. Testabdeckung

- `tests/indexing/test_citation_graph.py`: Kantenbildung (DOI/arXiv/Titel, Präzedenz, Selbstzitat-Ausschluss), Determinismus, additive Persistenz, Fehlerfälle von `load_citations`.
- `tests/retrieval/test_citations.py`: Provenienz-Anreicherung, Sortierung, Deckelung (`limit`, `cites_total`/`cited_by_total`), Fehlerfälle.
- `tests/mcp_server/test_server.py`: Tool-Contract über einen In-Memory-Client (Erfolg + Fehler-Envelope).

## 10. Beispiel

Real erzeugt gegen den Testindex aus `tests/mcp_server/conftest.py`: `aaaa0002` zitiert `aaaa0001` über die DOI im Referenzabschnitt; geprüft in `tests/mcp_server/test_spec_examples.py`.

Anfrage:

```json
{ "paper_id": "aaaa0001" }
```

Antwort:

```json
{
  "paper": {
    "paper_id": "aaaa0001",
    "document_kind": "full",
    "source_uri": "file:///aaaa0001.pdf",
    "identifiers": { "doi": "10.1145/1234", "arxiv": "2405.20455" },
    "citation_key": "aaaa00012024",
    "snippet": "transformer attention mechanism self attention encoder doi:10.1145/1234"
  },
  "cites": [],
  "cites_total": 0,
  "cited_by": [
    {
      "paper_id": "aaaa0002",
      "document_kind": "full",
      "source_uri": "file:///aaaa0002.pdf",
      "identifiers": {},
      "citation_key": "aaaa0002",
      "snippet": "self attention transformer architecture heads",
      "method": "doi"
    }
  ],
  "cited_by_total": 1
}
```
