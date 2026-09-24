# Tool-Spezifikation: `search_author_papers`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/authors.py` über `TfidfIndex.search(..., paper_ids=…)`; als
> MCP-Tool registriert in **Phase 17 / A4**
> ([ADR 0043](../../../../docs/adr/0043-author-index-and-person-tools.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `search_author_papers` |
| **Version** | `0.1.0` |
| **Capability-Schicht** | Personen / Retrieval (siehe README.md) |
| **Status** | Implementiert (Phase 17 / A4) |

---

## 1. Zweck

Beantwortet **„Was schreibt X über Y?“**. Es ist eine Inhaltssuche, **beschränkt auf die Paper
einer Person**. Suchlogik und Ausgabe sind dieselben wie bei `search_basic`: Hybrid-Wertung aus
BM25 und TF-IDF sowie belegte Zitate mit Paper, Abschnitt, Seite und Chunk. Es gibt keine zweite
Implementierung.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `person_key` | `str` | ja | Personenschlüssel aus `search_authors`; nicht leer. |
| `query` | `str` | ja | Natürlichsprachige Anfrage; nicht leer. |
| `k` | `int` | nein | Höchstzahl der Zitate (`0 < k <= 50`); Default `5`. |

## 3. Output-Schema

```json
{
  "person_key": "A5023888391",
  "query": "attention",
  "papers_searched": 2,
  "citations": [ { "paper_id": "…", "page_number": 1, "section_title": "…", "score": 0.03, "…": "…" } ],
  "coverage": { "full_texts_with_authors": 3, "full_texts": 4, "share": 0.75, "note": "…" }
}
```

- `citations` hat exakt das `Citation`-Schema von `search_basic`, siehe
  [search_basic.md](search_basic.md). Das gilt einschließlich `document_kind`, Teil-Scores,
  `identifiers` und `citation_key`.
- `papers_searched` ist die Zahl der Paper der Person, in denen gesucht wurde.
- Ohne passenden Chunk ist `citations` leer; das ist kein Fehler.

## 4. Annahmen und Vorbedingungen

- Ein Index ab Phase 17 / A3 mit Chunks.

## 5. Grenzen (Nicht-Ziele)

- **Nur Basic, kein Local.** Chunk-Nachbarschaft und Fan-out verlassen per Konstruktion die Paper
  der Person und lieferten Belege anderer Autoren (ADR 0043).
- Keine Suche über die Grenzen der Personenebene hinaus. Paper mit schwach belegten Autoren fehlen,
  siehe `coverage`.

## 6. Fehlerverhalten

- `invalid_input`: leerer `person_key` oder `query`; `k <= 0` oder `k > 50`.
- `not_found`: unbekannter Personenschlüssel, oder die Index-Datei fehlt.
- `constraint_violation`: Der Index enthält keine Chunks.

## 7. Provenienz

- Wie `search_basic`: je Zitat Paper, Abschnitt, Seite bzw. Seitenbereich, Chunk, Score und
  Snippet.

## 8. Reproduzierbarkeit

- Deterministisch wie `search_basic`.

## 9. Testabdeckung

- `tests/retrieval/test_authors.py`: Beschränkung auf die Paper der Person, leeres Ergebnis,
  Fehlerfälle.
- `tests/mcp_server/test_person_tools.py`: Tool-Contract und Beispiel-Regression.

## 10. Beispiel

Real erzeugt gegen den Personen-Testindex (`make_person_index` in `tests/conftest.py`); geprüft in `tests/mcp_server/test_person_tools.py`.

Anfrage:

```json
{ "person_key": "A5023888391", "query": "attention", "k": 2 }
```

Antwort (gekürzt auf den ersten Treffer; bei `k=2` folgt `aaaa0001` als zweiter Eintrag, nie `dddd0001`, obwohl es die offene Suche nach „attention“ anführt):

```json
{
  "person_key": "A5023888391",
  "query": "attention",
  "papers_searched": 2,
  "citations": [
    {
      "paper_id": "aaaa0002",
      "document_kind": "full",
      "section_title": "Introduction",
      "page_number": 1,
      "page_end": 1,
      "chunk_id": "aaaa0002-c0000",
      "score": 0.0323,
      "score_tfidf": 0.261,
      "score_bm25": 0.907,
      "source_uri": "file:///aaaa0002.pdf",
      "identifiers": { "doi": "10.1000/reflect" },
      "citation_key": "Asai2025",
      "snippet": "reflection tokens attention retrieval augmented language model training doi:10.1000/reflect"
    }
  ],
  "coverage": {
    "full_texts_with_authors": 4,
    "full_texts": 6,
    "share": 0.6667,
    "note": "Nur 4 von 6 Volltexten (67 %) tragen belegte Autoren. Paper ohne belegte Zitierdaten fehlen auf der Personenebene; ein fehlender Treffer heißt nicht, dass die Person nichts im Korpus hat."
  }
}
```
