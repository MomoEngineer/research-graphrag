# Tool-Spezifikation: `get_author`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/authors.py`; als MCP-Tool registriert in **Phase 17 / A4**
> ([ADR 0043](../../../../docs/adr/0043-author-index-and-person-tools.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `get_author` |
| **Version** | `0.1.0` |
| **Capability-Schicht** | Personen (siehe README.md) |
| **Status** | Implementiert (Phase 17 / A4) |

---

## 1. Zweck

Beantwortet **„Was hat X im Korpus?“** mit einem schlanken Profil zu **einem**
Personenschlüssel (aus `search_authors`):

- die Paperliste samt Autorposition, Jahr, Dokumentart und Zitierschlüssel,
- die Jahresspanne,
- die Themen-Communities dieser Paper,
- die **direkten** Mitautoren im Korpus mit der Zahl gemeinsamer Paper.

Es bildet keine Gruppen.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `person_key` | `str` | ja | Personenschlüssel aus `search_authors` (`A…`, `orcid:…` oder `name:…`); nicht leer. |
| `limit` | `int` | nein | Höchstzahl je Liste (Paper, Communities, Mitautoren; `0 < limit <= 50`); Default `50`. |

## 3. Output-Schema

```json
{
  "person_key": "A5023888391",
  "identity": "openalex",
  "openalex_id": "A5023888391",
  "orcid": "",
  "names": ["Akari Asai", "Asai, Akari"],
  "papers": [
    {
      "paper_id": "…",
      "title": "…",
      "year": 2025,
      "document_kind": "full",
      "source_uri": "file:///…",
      "citation_key": "Asai2025",
      "identifiers": { "doi": "10.…" },
      "position": 1
    }
  ],
  "papers_total": 2,
  "year_span": [2024, 2025],
  "communities": [ { "community_id": 0, "n_papers": 2, "keywords": ["attention", "…"] } ],
  "communities_total": 1,
  "coauthors": [
    { "person_key": "name:bert muster", "identity": "name", "names": ["Bert Muster"], "n_shared": 1 }
  ],
  "coauthors_total": 2,
  "coverage": { "full_texts_with_authors": 3, "full_texts": 4, "share": 0.75, "note": "…" }
}
```

- `papers` ist nach Jahr (absteigend, unbekanntes Jahr zuletzt), dann `paper_id` sortiert.
  `position` ist die 1-basierte Autorposition. `year` ist `null`, wenn es unbekannt ist.
  `source_uri` ist die Quelle im Korpus, wie bei den übrigen Werkzeugen.
- `communities` nennt die Louvain-Communities der Paper samt Anzahl (absteigend) und ihre ersten
  fünf Keywords. Ohne gebauten Graphen ist die Liste leer.
- `coauthors` sind Personen, die mit X mindestens ein Paper teilen, je Personenschlüssel mit der
  Zahl gemeinsamer Paper (absteigend, dann Schlüssel). Eine Namensidentität bleibt als solche
  erkennbar (`identity = "name"`).
- `openalex_id`/`orcid`: die Kennungen der Person. Tragen ihre Nennungen verschiedene ORCIDs,
  steht hier die häufigste.
- Alle Listen sind auf `limit` gekappt; `*_total` nennt die Zahl vor der Kappung.
- `coverage`: siehe `search_authors`.

## 4. Annahmen und Vorbedingungen

- Ein Index ab Phase 17 / A3. Communities setzen den Ähnlichkeitsgraphen voraus (Phase 3).

## 5. Grenzen (Nicht-Ziele)

- **Keine** Gruppenbildung, **keine** Ko-Autor-Communities, **keine** Bibliometrie (h-Index,
  externe Zitationszahlen), **keine** Affiliationen.
- Keine Online-Suche nach weiteren Papern der Person.

## 6. Fehlerverhalten

- `invalid_input`: leerer `person_key`; `limit <= 0` oder `limit > 50`.
- `not_found`: unbekannter Personenschlüssel (die Meldung nennt die Abdeckung), oder die
  Index-Datei fehlt.

## 7. Provenienz

- Je Paper `paper_id`, `source_uri`, `identifiers` und `citation_key`. Die vollständige Angabe
  liefert `get_reference`.

## 8. Reproduzierbarkeit

- Deterministisch: Index-Reads, stabile Sortierung.

## 9. Testabdeckung

- `tests/retrieval/test_authors.py`: Profil, Sortierung, Mitautoren, Communities, Kappung,
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
  "identity": "openalex",
  "openalex_id": "A5023888391",
  "orcid": "",
  "names": ["Akari Asai", "Asai, Akari"],
  "papers": [
    {
      "paper_id": "aaaa0002",
      "title": "Reflection Tokens for Retrieval",
      "year": 2025,
      "document_kind": "full",
      "source_uri": "file:///aaaa0002.pdf",
      "citation_key": "Asai2025",
      "identifiers": { "doi": "10.1000/reflect" },
      "position": 1
    },
    {
      "paper_id": "aaaa0001",
      "title": "Self-RAG: Learning to Retrieve, Generate, and Critique",
      "year": 2024,
      "document_kind": "full",
      "source_uri": "file:///aaaa0001.pdf",
      "citation_key": "Asai2024",
      "identifiers": { "doi": "10.1000/selfrag" },
      "position": 1
    }
  ],
  "papers_total": 2,
  "year_span": [2024, 2025],
  "communities": [
    {
      "community_id": 0,
      "n_papers": 2,
      "keywords": ["attention", "graph", "selfrag", "self", "muster"]
    }
  ],
  "communities_total": 1,
  "coauthors": [
    { "person_key": "name:zeqiu wu", "identity": "name", "names": ["Zeqiu Wu"], "n_shared": 2 },
    {
      "person_key": "A5000000003",
      "identity": "openalex",
      "names": ["Hannaneh Hajishirzi"],
      "n_shared": 1
    },
    {
      "person_key": "name:bert muster",
      "identity": "name",
      "names": ["Bert Muster"],
      "n_shared": 1
    }
  ],
  "coauthors_total": 3,
  "coverage": {
    "full_texts_with_authors": 4,
    "full_texts": 6,
    "share": 0.6667,
    "note": "Nur 4 von 6 Volltexten (67 %) tragen belegte Autoren. Paper ohne belegte Zitierdaten fehlen auf der Personenebene; ein fehlender Treffer heißt nicht, dass die Person nichts im Korpus hat."
  }
}
```
