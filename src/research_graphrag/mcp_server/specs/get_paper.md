# Tool-Spezifikation: `get_paper`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/retrieval/paper.py`; als MCP-Tool registriert in **Phase 5**
> ([ADR 0009](../../../../docs/adr/0009-mcp-server-stdio-phase5.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `get_paper` |
| **Version** | `0.4.0` |
| **Capability-Schicht** | Katalog / Provenienz (siehe README.md) |
| **Status** | Implementiert (Phase 5) |

---

## 1. Zweck

Liefert die **Metadaten eines einzelnen Papers** anhand seiner stabilen `paper_id` **direkt aus dem Index** (Source of Truth): Quelle, Identifikatoren (DOI/arXiv), Seiten-/Chunk-Umfang, Abschnittstitel und ein Leit-Snippet. Dient einem Agenten zur schnellen Einordnung und zur **zitierfähigen** Referenzierung eines Treffers aus den `search_*`-Tools.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `paper_id` | `str` | ja | Stabile Paper-ID (kein Datei-Pfad); nicht leer. |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).

## 3. Output-Schema

```json
{
  "paper_id": "…",
  "document_kind": "full",
  "source_uri": "file:///…",
  "identifiers": { "doi": "…", "arxiv": "…" },
  "n_pages": 12,
  "n_chunks": 118,
  "sections": ["Abstract", "Introduction", "…"],
  "snippet": "…",
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
    "origins": { "title": "curated", "authors": "resolved" },
    "confidence": "strong",
    "citable": true,
    "author_identities": [
      { "name": "Anna Beispiel", "openalex_id": "A5023888391", "orcid": "0000-0002-1825-0097", "person_key": "A5023888391", "identity": "openalex" },
      { "name": "Bert Muster", "openalex_id": "", "orcid": "", "person_key": "name:bert muster", "identity": "name" }
    ],
    "review": null,
    "harvard": "Beispiel, A. and Muster, B. (2023) …",
    "apa": "Beispiel, A., & Muster, B. (2023). …",
    "in_text": { "harvard": "(Beispiel and Muster, 2023)", "apa": "(Beispiel & Muster, 2023)" }
  }
}
```

`identifiers` enthält nur tatsächlich erkannte Schlüssel (`doi`/`arxiv`) und kann leer sein. `sections` sind die **eindeutigen** (heuristischen) Abschnittstitel in Dokument-Reihenfolge; `snippet` ist der Ausschnitt des ersten nicht-leeren Chunks.

`document_kind` ist `full` (aus einem PDF extrahierter Volltext) oder `reference` (**Referenz-Eintrag ohne Volltext**). Bei `reference` sind `n_pages = 0`, `n_chunks = 1` und `sections = ["Abstract"]` **kein Befund**, sondern die vollständige Auskunft über ein Paper, dessen Volltext nicht beschaffbar war; die Literaturangabe in `reference` bleibt davon unberührt vollständig ([ADR 0031](../../../../docs/adr/0031-reference-contract-and-guardrail-phase13.md)).

`reference` ist der **aufgelöste** bibliografische Datensatz samt fertiger Angabe in Harvard und APA. Er ist die **gleiche** Nutzlast wie das Feld `reference` von `get_reference`; dort kommen mit `missing` und `note` zusätzlich die Diagnose der fehlenden Pflichtfelder hinzu. `origins` weist je Feld die Herkunft aus (`manual` > `curated` > `resolved` > `extracted`), `confidence` die schwächste beitragende Quelle, `citable` die Vollständigkeit ([ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md)).

- `author_identities` (seit Version 0.3.0, additiv, [ADR 0041](../../../../docs/adr/0041-author-identity-and-schema.md)):
  je Autor positionsgleich zu `authors` der Name in der Schreibweise der Quelle, die OpenAlex-Autor-ID
  und die ORCID (leer = unbekannt), der **Personenschlüssel** (`person_key`: OpenAlex-ID, sonst
  `orcid:<ORCID>`, sonst ausdrücklich `name:<normalisiert>`) und der Identitätsstatus
  (`openalex`/`orcid`/`name`). Die Kennungen stammen stets aus **derselben** Quelle wie die Namen;
  `identity = "name"` ist ausdrücklich **keine** bestätigte Identität.
- `review` (seit Version 0.4.0, additiv, [ADR 0042](../../../../docs/adr/0042-title-page-evidence-and-rejections.md)):
  `null` oder der **ausgewiesene Prüfstatus** `{"status": "unresolvable", "reason": "…"}`. Ein
  schwach belegter Datensatz mit diesem Status ist ausdrücklich als „nicht auflösbar“ ausgewiesen
  (Grund vom Menschen gesetzt), statt still `weak` zu bleiben.

## 4. Annahmen und Vorbedingungen

- Ein Index wurde gebaut (`python -m scripts.ingest`), Index-Schema ≥ `0.3.0` (enthält `identifiers`).

## 5. Grenzen (Nicht-Ziele)

- **Kein** Volltext-/Chunk-Inhalt (dafür `search_basic`/`search_local`) und **kein** Referenz-/Zitationsparsing (Phase 7).
- **Kein** Datei-Pfad-Zugriff: Eingabe ist ausschließlich eine `paper_id` (keine Pfad-Sicherheitsgrenze nötig).
- Keine LLM-Formulierung im Tool – nur strukturierte Metadaten + Provenienz.

## 6. Fehlerverhalten

- `invalid_input`: leere `paper_id`.
- `not_found`: Index-Datei fehlt **oder** `paper_id` ist unbekannt.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- `source_uri` (Quelle zum Original), `identifiers` (DOI/arXiv), `sections`, `snippet`.
- `reference` weist die Herkunft **je Feld** aus (`origins`) und die Belegstärke des Datensatzes (`confidence`); unvollständige Angaben werden nicht geraten, sondern über `citable = false` kenntlich gemacht.

## 8. Reproduzierbarkeit

- Deterministisch: direkte Index-Reads (SQLite), keine stochastischen Anteile.

## 9. Testabdeckung

- `tests/retrieval/test_paper.py`: Funktions-/Provenienz-Test, `not_found` (fehlender Index, unbekannte ID), `invalid_input`.
- `tests/mcp_server/test_server.py`: Tool-Contract über einen In-Memory-Client (Erfolg + Fehler-Envelope).

## 10. Beispiel

Real erzeugt gegen den Testindex aus `tests/mcp_server/conftest.py`; geprüft in `tests/mcp_server/test_spec_examples.py`. Ohne Online-Auflösung/kuratierte Angabe bleiben `title`/`authors`/`venue` extrahiert-leer – `reference.citable = false` weist das aus, statt einen Titel zu erfinden.

Anfrage:

```json
{ "paper_id": "aaaa0001" }
```

Antwort:

```json
{
  "paper_id": "aaaa0001",
  "document_kind": "full",
  "source_uri": "file:///aaaa0001.pdf",
  "identifiers": { "arxiv": "2405.20455", "doi": "10.1145/1234" },
  "n_pages": 2,
  "n_chunks": 2,
  "sections": ["Introduction", "Methods"],
  "snippet": "transformer attention mechanism self attention encoder doi:10.1145/1234",
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
    "review": null,
    "harvard": "aaaa0001 (2024) Available at: https://doi.org/10.1145/1234",
    "apa": "aaaa0001. (2024). https://doi.org/10.1145/1234",
    "in_text": { "harvard": "(aaaa0001, 2024)", "apa": "(aaaa0001, 2024)" }
  }
}
```
