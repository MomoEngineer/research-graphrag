# Tool-Spezifikation: `search_authors`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/authors.py` über `src/research_graphrag/indexing/author_index.py`;
> als MCP-Tool registriert in **Phase 17 / A4**
> ([ADR 0043](../../../../docs/adr/0043-author-index-and-person-tools.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `search_authors` |
| **Version** | `0.1.0` |
| **Capability-Schicht** | Personen (siehe README.md) |
| **Status** | Implementiert (Phase 17 / A4) |

---

## 1. Zweck

Beantwortet **„Wer ist gemeint?“**: Zu einem Namen oder Namensteil liefert es die passenden
**Personen-Kandidaten** im Korpus. Je Kandidat stehen dort der Personenschlüssel, die
Schreibweisen, die Zahl der Paper, die Jahresspanne und Beispieltitel. Der **Identitätsstatus**
sagt, ob die Person über eine OpenAlex-ID, nur über eine ORCID oder nur über den Namen bestimmt
ist. Ein mehrdeutiger Name wird als solcher ausgewiesen und nie still zusammengeführt. Der
Personenschlüssel ist die Eingabe für `get_author`, `search_author_papers` und
`get_author_citations`.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `name` | `str` | ja | Name oder Namensteil in beliebiger Schreibweise („Asai, Akari“, „akari asai“, „Y. Wang“); nicht leer. |
| `limit` | `int` | nein | Höchstzahl der Kandidaten (`0 < limit <= 50`); Default `20`. |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter.

## 3. Output-Schema

```json
{
  "query": "Asai",
  "candidates": [
    {
      "person_key": "A5023888391",
      "identity": "openalex",
      "openalex_id": "A5023888391",
      "orcid": "",
      "names": ["Akari Asai", "Asai, Akari"],
      "n_papers": 2,
      "year_span": [2024, 2025],
      "sample_titles": ["…", "…"]
    }
  ],
  "total_matching": 1,
  "ambiguous": false,
  "coverage": {
    "full_texts_with_authors": 3,
    "full_texts": 4,
    "share": 0.75,
    "note": "…"
  }
}
```

- **Suchregel:** Die Anfrage wird wie ein Name normalisiert, sodass beide Schreibweisen
  zusammenfallen. Suchwörter ab drei Zeichen müssen als Teilstring, kürzere als Wortanfang
  vorkommen.
- **Kandidaten:** je Personenschlüssel **ein** Kandidat, sortiert nach Paperzahl (absteigend),
  dann Schlüssel. `names` sind die Schreibweisen der Quellen.
- **`identity`:** `openalex`, `orcid` oder `name`. `name` bedeutet ausdrücklich **keine**
  bestätigte Identität; der Schlüssel beginnt dann mit `name:`.
- **`ambiguous`:** `true`, sobald mehr als ein Kandidat passt, etwa zwei Kennungen mit demselben
  Namen oder eine Kennung plus eine reine Namensidentität. Der Aufrufer wählt, das Werkzeug führt
  nicht zusammen.
- **`total_matching`:** die Zahl aller Kandidaten vor der Kappung auf `limit`.
- **`coverage`:** Die Personenebene kennt nur die Autoren **belegter** (`strong`) Zitierdaten. Der
  Block weist aus, für wie viele Volltexte das gilt; `note` erklärt die Lücke im Klartext.
- **`year_span`:** `null`, wenn kein Paper ein Jahr trägt.
- **`sample_titles`:** höchstens drei Titel, die jüngsten Paper zuerst.
- **`openalex_id`/`orcid`:** Tragen die Nennungen verschiedene ORCIDs, steht hier die häufigste.

## 4. Annahmen und Vorbedingungen

- Ein Index ab Phase 17 / A3 (`meta.author_schema_version`). Ein älterer Index enthält keine
  Personenebene; die Suche liefert dann `not_found` mit einer Abdeckung von 0.

## 5. Grenzen (Nicht-Ziele)

- **Kein** Zusammenführen von Namensidentitäten, **keine** Arbeitsgruppen.
- **Keine** Tippfehlertoleranz: Die Suche ist teilstring- bzw. präfixbasiert.
- Keine Paper-Liste: dafür `get_author`. Keine Inhaltssuche: dafür `search_author_papers`.
- Autoren schwach belegter Datensätze fehlen, siehe `coverage`.

## 6. Fehlerverhalten

- `invalid_input`: leerer oder zeichenloser `name`; `limit <= 0` oder `limit > 50`.
- `not_found`: kein Kandidat (die Meldung nennt die Abdeckung), oder die Index-Datei fehlt.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- Je Kandidat die Schreibweisen der Quelle und die Kennungen. Die Herkunft der Kennungen weist
  `get_reference` feldweise aus (`origins.author_ids`).

## 8. Reproduzierbarkeit

- Deterministisch: Index-Reads, stabile Sortierung, keine stochastischen Anteile.

## 9. Testabdeckung

- `tests/retrieval/test_authors.py`: Kandidatenbildung, Mehrdeutigkeit, Kappung, `coverage`,
  Fehlerfälle.
- `tests/mcp_server/test_person_tools.py`: Tool-Contract über einen In-Memory-Client
  (Erfolg + Fehler-Envelope) und Beispiel-Regression.

## 10. Beispiel

Real erzeugt gegen den Personen-Testindex (`make_person_index` in `tests/conftest.py`); geprüft in `tests/mcp_server/test_person_tools.py`.

Anfrage:

```json
{ "name": "Asai" }
```

Antwort:

```json
{
  "query": "Asai",
  "candidates": [
    {
      "person_key": "A5023888391",
      "identity": "openalex",
      "openalex_id": "A5023888391",
      "orcid": "",
      "names": ["Akari Asai", "Asai, Akari"],
      "n_papers": 2,
      "year_span": [2024, 2025],
      "sample_titles": [
        "Reflection Tokens for Retrieval",
        "Self-RAG: Learning to Retrieve, Generate, and Critique"
      ]
    },
    {
      "person_key": "name:akari asai",
      "identity": "name",
      "openalex_id": "",
      "orcid": "",
      "names": ["Akari Asai"],
      "n_papers": 1,
      "year_span": [2023, 2023],
      "sample_titles": ["Message Passing on Graphs"]
    }
  ],
  "total_matching": 2,
  "ambiguous": true,
  "coverage": {
    "full_texts_with_authors": 4,
    "full_texts": 6,
    "share": 0.6667,
    "note": "Nur 4 von 6 Volltexten (67 %) tragen belegte Autoren. Paper ohne belegte Zitierdaten fehlen auf der Personenebene; ein fehlender Treffer heißt nicht, dass die Person nichts im Korpus hat."
  }
}
```
