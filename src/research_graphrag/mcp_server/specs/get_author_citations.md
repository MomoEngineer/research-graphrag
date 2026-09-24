# Tool-Spezifikation: `get_author_citations`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/authors.py` über die `CITES`-Kanten aus
> `src/research_graphrag/indexing/citation_graph.py`; als MCP-Tool registriert in **Phase 17 / A4**
> ([ADR 0043](../../../../docs/adr/0043-author-index-and-person-tools.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `get_author_citations` |
| **Version** | `0.1.0` |
| **Capability-Schicht** | Personen / Zitationsnetz (siehe README.md) |
| **Status** | Implementiert (Phase 17 / A4) |

---

## 1. Zweck

Beantwortet **„Wer zitiert X, wen zitiert X?“** auf Personenebene:

- **`cited_by`:** die Korpus-Paper, die ein Paper der Person zitieren,
- **`cites`:** die Korpus-Paper, die die Person in ihren Papern zitiert.

Grundlage sind die bestehenden `CITES`-Kanten. Die Grenze „nur innerhalb des Korpus“ wird in
jeder Antwort ausgewiesen.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `person_key` | `str` | ja | Personenschlüssel aus `search_authors`; nicht leer. |
| `limit` | `int` | nein | Höchstzahl **je Richtung** (`0 < limit <= 50`); Default `50`. |

## 3. Output-Schema

```json
{
  "person_key": "A5023888391",
  "scope": "corpus",
  "note": "Nur Zitationen innerhalb des Korpus …",
  "cites": [
    {
      "paper": {
        "paper_id": "…",
        "title": "…",
        "year": 2024,
        "document_kind": "full",
        "source_uri": "file:///…",
        "citation_key": "…",
        "identifiers": {}
      },
      "via": ["<paper_id eines Papers der Person>"],
      "methods": ["doi"],
      "self": true
    }
  ],
  "cites_total": 1,
  "cited_by": [],
  "cited_by_total": 0,
  "coverage": { "full_texts_with_authors": 3, "full_texts": 4, "share": 0.75, "note": "…" }
}
```

- `paper` ist die Kurzangabe wie in `get_author` (ohne `position`); `year` ist `null`, wenn es
  unbekannt ist.
- Je Gegenüber **ein** Eintrag:
  - `via` nennt die beteiligten Paper der Person (sortiert).
  - `methods` nennt die Kriterien der Kanten (`doi`/`arxiv`/`title`).
  - `self` ist `true`, wenn das Gegenüber selbst ein Paper der Person ist (Selbstzitat).
- **Sortierung:** nach Zahl der beteiligten Paper (absteigend), dann `paper_id`.
- **Kappung:** Beide Listen sind auf `limit` gekappt; `*_total` nennt die Zahl vor der Kappung.
- **`scope`:** immer `corpus`. `note` erklärt, dass Zitationen von oder zu Werken außerhalb des
  Korpus nicht erfasst sind.

## 4. Annahmen und Vorbedingungen

- Ein Index ab Phase 17 / A3 mit Zitationsgraph (Tabelle `citation_edges`).

## 5. Grenzen (Nicht-Ziele)

- **Nur Intra-Korpus**, **keine** externen Zitationszahlen, **kein** Zitationskontext.
- Paper mit schwach belegten Autoren fehlen auf der Personenseite, siehe `coverage`.

## 6. Fehlerverhalten

- `invalid_input`: leerer `person_key`; `limit <= 0` oder `limit > 50`.
- `not_found`: unbekannter Personenschlüssel, oder die Index-Datei fehlt.
- `constraint_violation`: Der Index enthält keinen Zitationsgraphen.

## 7. Provenienz

- Je Gegenüber Paper-Referenz mit `source_uri`, `identifiers` und `citation_key`, dazu `methods`
  als Nachweis, **woran** die Kanten erkannt wurden.

## 8. Reproduzierbarkeit

- Deterministisch: Index-Reads auf einem deterministisch gebauten Kantensatz.

## 9. Testabdeckung

- `tests/retrieval/test_authors.py`: beide Richtungen, Selbstzitate, Kappung, fehlender Graph,
  Fehlerfälle.
- `tests/mcp_server/test_person_tools.py`: Tool-Contract und Beispiel-Regression.

## 10. Beispiel

Real erzeugt gegen den Personen-Testindex (`make_person_index` in `tests/conftest.py`); geprüft in `tests/mcp_server/test_person_tools.py`.

Anfrage:

```json
{ "person_key": "A5023888391" }
```

Antwort:

```json
{
  "person_key": "A5023888391",
  "scope": "corpus",
  "note": "Nur Zitationen innerhalb des Korpus: Werke außerhalb des Korpus und Verweise, die der Zitationsgraph nicht erkannt hat, fehlen. `methods` nennt, woran eine Kante erkannt wurde (doi, arxiv oder title).",
  "cites": [
    {
      "paper": {
        "paper_id": "aaaa0001",
        "title": "Self-RAG: Learning to Retrieve, Generate, and Critique",
        "year": 2024,
        "document_kind": "full",
        "source_uri": "file:///aaaa0001.pdf",
        "citation_key": "Asai2024",
        "identifiers": { "doi": "10.1000/selfrag" }
      },
      "via": ["aaaa0002"],
      "methods": ["doi"],
      "self": true
    },
    {
      "paper": {
        "paper_id": "cccc0001",
        "title": "Louvain Communities Revisited",
        "year": 2022,
        "document_kind": "full",
        "source_uri": "file:///cccc0001.pdf",
        "citation_key": "Muster2022",
        "identifiers": { "doi": "10.1000/muster" }
      },
      "via": ["aaaa0002"],
      "methods": ["doi"],
      "self": false
    }
  ],
  "cites_total": 2,
  "cited_by": [
    {
      "paper": {
        "paper_id": "cccc0001",
        "title": "Louvain Communities Revisited",
        "year": 2022,
        "document_kind": "full",
        "source_uri": "file:///cccc0001.pdf",
        "citation_key": "Muster2022",
        "identifiers": { "doi": "10.1000/muster" }
      },
      "via": ["aaaa0001", "aaaa0002"],
      "methods": ["doi"],
      "self": false
    },
    {
      "paper": {
        "paper_id": "aaaa0002",
        "title": "Reflection Tokens for Retrieval",
        "year": 2025,
        "document_kind": "full",
        "source_uri": "file:///aaaa0002.pdf",
        "citation_key": "Asai2025",
        "identifiers": { "doi": "10.1000/reflect" }
      },
      "via": ["aaaa0001"],
      "methods": ["doi"],
      "self": true
    },
    {
      "paper": {
        "paper_id": "bbbb0001",
        "title": "Message Passing on Graphs",
        "year": 2023,
        "document_kind": "full",
        "source_uri": "file:///bbbb0001.pdf",
        "citation_key": "Asai2023",
        "identifiers": {}
      },
      "via": ["aaaa0001"],
      "methods": ["doi"],
      "self": false
    }
  ],
  "cited_by_total": 3,
  "coverage": {
    "full_texts_with_authors": 4,
    "full_texts": 6,
    "share": 0.6667,
    "note": "Nur 4 von 6 Volltexten (67 %) tragen belegte Autoren. Paper ohne belegte Zitierdaten fehlen auf der Personenebene; ein fehlender Treffer heißt nicht, dass die Person nichts im Korpus hat."
  }
}
```
