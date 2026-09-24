# Tool-Spezifikation: `get_reference`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/reference.py`; als MCP-Tool registriert in **Phase 12 / K1**
> ([ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `get_reference` |
| **Version** | `0.2.0` |
| **Capability-Schicht** | Katalog / Zitation (siehe README.md) |
| **Status** | Implementiert (Phase 12 / K1) |

---

## 1. Zweck

Liefert die **fertige Literaturangabe** eines Papers anhand seiner stabilen `paper_id`: die
aufgelösten bibliografischen Felder **und** die formatierten Angaben in **Harvard**
(*Cite Them Right*) und **APA 7** samt Kurzbeleg für den Fließtext. Damit lässt sich ein
Suchtreffer ohne Zwischenschritt in einer wissenschaftlichen Arbeit zitieren.

Ergänzt `get_paper`: Dieses beschreibt das Dokument (Umfang, Abschnitte, Leit-Snippet),
`get_reference` beantwortet ausschließlich „wie zitiere ich das?".

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `paper_id` | `str` | ja | Stabile Paper-ID (kein Datei-Pfad); nicht leer. |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).
> Der Stil ist ebenfalls kein Parameter: Es werden **immer beide** Formen geliefert, damit ein
> Agent nicht raten muss, welcher Stil verlangt ist.

## 3. Output-Schema

```json
{
  "paper_id": "…",
  "source_uri": "file:///…",
  "styles": ["harvard", "apa"],
  "reference": {
    "paper_id": "…",
    "title": "…",
    "authors": ["Anna Beispiel", "Bert Muster"],
    "year": 2023,
    "venue": "…",
    "doi": "10.…",
    "arxiv_id": "2503.06689",
    "url": "",
    "identifiers": { "doi": "10.…", "arxiv": "2503.06689" },
    "citation_key": "Beispiel2023",
    "origins": { "title": "curated", "doi": "curated", "authors": "resolved" },
    "confidence": "strong",
    "citable": true,
    "author_identities": [
      { "name": "Anna Beispiel", "openalex_id": "A5023888391", "orcid": "0000-0002-1825-0097", "person_key": "A5023888391", "identity": "openalex" },
      { "name": "Bert Muster", "openalex_id": "", "orcid": "", "person_key": "name:bert muster", "identity": "name" }
    ],
    "harvard": "Beispiel, A. and Muster, B. (2023) 'Titel', Venue. Available at: https://doi.org/10.…",
    "apa": "Beispiel, A., & Muster, B. (2023). Titel. Venue. https://doi.org/10.…",
    "in_text": { "harvard": "(Beispiel and Muster, 2023)", "apa": "(Beispiel & Muster, 2023)" }
  },
  "missing": [],
  "note": ""
}
```

- `origins` weist **je Feld** die Herkunft aus (`manual` > `curated` > `resolved` > `extracted`).
- `confidence` ist die **niedrigste** Konfidenz der beteiligten Quellen (`strong`/`weak`/`none`).
- `author_identities` (seit Version 0.2.0, additiv, [ADR 0041](../../../../docs/adr/0041-author-identity-and-schema.md)):
  je Autor positionsgleich zu `authors` der Name in der Schreibweise der Quelle, die OpenAlex-Autor-ID
  und die ORCID (leer = unbekannt), der **Personenschlüssel** (`person_key`: OpenAlex-ID, sonst
  `orcid:<ORCID>`, sonst ausdrücklich `name:<normalisiert>`) und der Identitätsstatus
  (`openalex`/`orcid`/`name`). Die Kennungen stammen stets aus **derselben** Quelle wie die Namen;
  `identity = "name"` ist ausdrücklich **keine** bestätigte Identität.
- `missing` nennt fehlende Pflichtfelder (`title`, `authors`, `year`); `note` erklärt sie im
  Klartext und nennt den Weg zur Ergänzung. Bei vollständigem Datensatz sind beide leer.

## 4. Annahmen und Vorbedingungen

- Ein Index wurde gebaut (`python -m scripts.ingest`) und enthält das Teilschema
  `paper_metadata` (`metadata_schema_version` ≥ `0.1.0`).
- Fehlt das Teilschema (Index vor Phase 12), liefert das Tool einen leeren Datensatz mit
  `citable = false` statt zu scheitern.

## 5. Grenzen (Nicht-Ziele)

- **Keine** Auflösung zur Abfragezeit: Das Tool liest ausschließlich den Index; die
  Online-Anreicherung ist ein separater, manuell gestarteter Lauf
  ([ADR 0026](../../../../docs/adr/0026-online-metadata-resolution.md)).
- **Kein** Raten fehlender Angaben – Unvollständigkeit wird ausgewiesen.
- **Keine** weiteren Stile (nur Harvard und APA) und **kein** Zugriffsdatum (es wäre vom
  Ausführungstag abhängig und damit nicht deterministisch).

## 6. Fehlerverhalten

- `invalid_input`: leere `paper_id`.
- `not_found`: Index-Datei fehlt **oder** `paper_id` ist unbekannt.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- `source_uri` (Quelle zum Original), `identifiers`, `origins` (Herkunft je Feld) und
  `confidence` (schwächste beteiligte Quelle).

## 8. Reproduzierbarkeit

- Deterministisch: direkte Index-Reads (SQLite) plus rein funktionale Formatierung; keine
  stochastischen Anteile, kein Netz, kein Datum.

## 9. Testabdeckung

- `tests/retrieval/test_reference.py`: Funktions-/Provenienz-Test, unvollständiger Datensatz,
  fehlendes Teilschema, `not_found` (fehlender Index, unbekannte ID), `invalid_input`.
- `tests/bibliography/test_styles.py`: Stil-Formatierung inkl. Grenzfälle (kein Autor, kein
  Jahr, viele Autoren).
- `tests/mcp_server/test_server.py`: Tool-Contract über einen In-Memory-Client (Erfolg +
  Fehler-Envelope).

## 10. Beispiel

Real erzeugt gegen den Testindex aus `tests/mcp_server/conftest.py`; geprüft in `tests/mcp_server/test_spec_examples.py`. Ohne kuratierte/online aufgelöste Angabe fehlen die Autoren – `missing`/`note` weisen das aus, statt sie zu raten.

Anfrage:

```json
{ "paper_id": "aaaa0001" }
```

Antwort:

```json
{
  "paper_id": "aaaa0001",
  "source_uri": "file:///aaaa0001.pdf",
  "styles": ["harvard", "apa"],
  "reference": {
    "paper_id": "aaaa0001",
    "title": "aaaa0001",
    "authors": [],
    "year": 2024,
    "venue": "",
    "doi": "10.1145/1234",
    "arxiv_id": "2405.20455",
    "url": "",
    "identifiers": { "doi": "10.1145/1234", "arxiv": "2405.20455" },
    "citation_key": "aaaa00012024",
    "origins": { "arxiv_id": "extracted", "doi": "extracted", "title": "extracted", "year": "extracted" },
    "confidence": "weak",
    "citable": false,
    "author_identities": [],
    "harvard": "aaaa0001 (2024) Available at: https://doi.org/10.1145/1234",
    "apa": "aaaa0001. (2024). https://doi.org/10.1145/1234",
    "in_text": { "harvard": "(aaaa0001, 2024)", "apa": "(aaaa0001, 2024)" }
  },
  "missing": ["authors"],
  "note": "Unvollständige Angabe – es fehlen: Autoren. Fehlende Felder ergänzt der Auflösungslauf `python -m scripts.resolve_metadata` oder ein Eintrag der Herkunft 'manual' in metadata/paper_metadata.json."
}
```
