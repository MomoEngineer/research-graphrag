# Tool-Spezifikation: `answer_question`

> Pro-Tool-Spezifikation (Single Source of Truth für Contract-/Funktionstests). Umsetzung:
> `src/research_graphrag/generation/` (Port, Evidenz, Synthese) + `mcp_server/sampling.py`
> (Async-Brücke); als MCP-Tool registriert
> ([ADR 0012](../../../../docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md)).

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `answer_question` |
| **Version** | `0.4.0` |
| **Capability-Schicht** | Antwort / Synthese (siehe README.md) |
| **Status** | Implementiert (Phase 7 / A1) |

---

## 1. Zweck

Beantwortet eine Frage in **einem** Aufruf: wählt den Suchmodus (heuristischer Router oder explizit), sammelt die Belege und liefert sie als **einheitliche, durchnummerierte Evidenz** mit Zitier-Contract – unabhängig davon, welcher Modus gegriffen hat. Optional (`synthesize = true`) formuliert der Server daraus über **MCP-Sampling** eine belegte Antwort.

Für Clients mit eigenem Modell (GitHub Copilot) ist der **Default ohne Synthese** der empfohlene Weg: Er spart eine zweite Generierung und bleibt deterministisch.

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `query` | `str` | ja | Natürlichsprachige Frage; nicht leer. |
| `mode` | `str` | nein | `auto` (Default, Heuristik-Router – die Entscheidung steht im Ausgabefeld `routing`) · `basic` · `local` · `global` · `drift`. |
| `k` | `int` | nein | Trefferzahl je Modus (Default `5`, > 0). |
| `synthesize` | `bool` | nein | `false` (Default) = nur Evidenz; `true` = Antwort per Client-Sampling formulieren lassen. |

> Der Index-Pfad ist **Server-Konfiguration**, kein Tool-Parameter (Standard: `data/index/index.sqlite`).

## 3. Output-Schema

```json
{
  "query": "…",
  "mode": "local",
  "routing": {
    "mode": "local",
    "confidence": "strong",
    "signals": ["build on"],
    "rationale": "Signal 'build on' → local"
  },
  "answer": "",
  "generated": false,
  "model": "",
  "citation_contract": "Antworte ausschließlich …",
  "evidence": {
    "query": "…",
    "mode": "local",
    "items": [
      {
        "index": 1,
        "paper_id": "…",
        "document_kind": "full",
        "label": "Paper … · Abschnitt … · Seite 7",
        "snippet": "…",
        "source_uri": "file:///…",
        "identifiers": { "doi": "10.…", "arxiv": "2503.06689", "url": "https://…" },
        "citation_key": "Beispiel2023"
      }
    ]
  },
  "references": [
    {
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
  ]
}
```

- `mode` ist der **tatsächlich verwendete** Modus (bei `auto` die Router-Entscheidung).
- `routing` weist aus, **warum** dieser Modus gewählt wurde – `confidence` ist `strong` (eindeutiger Kandidat), `weak` (Gleichstand → Fallback `basic`) oder `none` (kein strukturelles Signal → Default `basic`), `signals` nennt die auslösenden Signale. Bei **explizit** gewähltem `mode` ist das Feld `null`, weil keine Heuristik beteiligt war ([ADR 0017](../../../../docs/adr/0017-router-hardening-phase7.md)).
- `evidence.items` sind **deterministisch nummeriert** (`index` = Zitatmarke `[n]`); `label` bündelt die Provenienz (Paper · Abschnitt · Seite bzw. Community-Vertreter). Läuft ein Chunk über einen Seitenumbruch, nennt das Label eine Range („Seiten 7–8", [ADR 0013](../../../../docs/adr/0013-chunking-refinement-phase7.md)). `identifiers` und `citation_key` machen jeden Beleg **extern auflösbar** und können leer sein.
- `document_kind` ist `full` (Volltext) oder `reference` (**Referenz-Eintrag ohne Volltext**). Bei `reference` trägt das `label` zusätzlich den Klartext-Zusatz „Referenz-Eintrag ohne Volltext" und statt einer Seite die Angabe „ohne Seite (Abstract)". Der `citation_contract` verlangt, diese Einschränkung im Antworttext zu **benennen**; die zugehörige Literaturangabe in `references` bleibt davon unberührt vollständig ([ADR 0031](../../../../docs/adr/0031-reference-contract-and-guardrail-phase13.md)).
- `references` ist die **Literaturliste** zur Evidenz: je beteiligtem Paper **ein** Eintrag mit der fertigen Angabe in Harvard und APA, in der Reihenfolge des ersten Auftretens in `evidence.items`. Die Nutzlast ist dieselbe wie das Feld `reference` von `get_reference`; `citable = false` weist einen unvollständigen Datensatz aus, statt fehlende Felder zu raten ([ADR 0025](../../../../docs/adr/0025-citable-paper-metadata.md)).
- `author_identities` (seit Version 0.3.0, additiv, [ADR 0041](../../../../docs/adr/0041-author-identity-and-schema.md)):
  je Autor positionsgleich zu `authors` der Name in der Schreibweise der Quelle, die OpenAlex-Autor-ID
  und die ORCID (leer = unbekannt), der **Personenschlüssel** (`person_key`: OpenAlex-ID, sonst
  `orcid:<ORCID>`, sonst ausdrücklich `name:<normalisiert>`) und der Identitätsstatus
  (`openalex`/`orcid`/`name`). Die Kennungen stammen stets aus **derselben** Quelle wie die Namen;
  `identity = "name"` ist ausdrücklich **keine** bestätigte Identität. Trägt die gewonnene
  Namensliste selbst keine Kennung, darf sie ein anderer Datensatz mit **identischer** Namensliste
  liefern; `origins.author_ids` nennt dann deren Herkunft (fehlt, wenn es keine Kennung gibt).
- `review` (seit Version 0.4.0, additiv, [ADR 0042](../../../../docs/adr/0042-title-page-evidence-and-rejections.md)):
  `null` oder der **ausgewiesene Prüfstatus** `{"status": "unresolvable", "reason": "…"}`. Ein
  schwach belegter Datensatz mit diesem Status ist ausdrücklich als „nicht auflösbar“ ausgewiesen
  (Grund vom Menschen gesetzt), statt still `weak` zu bleiben.
- `answer` ist bei `generated = false` leer; `model` benennt bei erfolgreichem Sampling das Client-Modell.
- `citation_contract` ist die verbindliche Vorgabe für die Formulierung (auch für den Aufrufer, der selbst formuliert).

## 4. Annahmen und Vorbedingungen

- Ein Index wurde gebaut (`python -m scripts.ingest`).
- Für `synthesize = true`: Der Client unterstützt **MCP-Sampling** (in VS Code mit Zustimmung/Modellwahl des Nutzers).

## 5. Grenzen (Nicht-Ziele)

- **Keine Recherche über die gewählten Belege hinaus:** ein Modus, ein Durchgang – kein iteratives Nachfassen.
- **Keine Garantie auf eine generierte Antwort:** ohne Sampling-Fähigkeit oder bei leerer Evidenz bleibt `generated = false` (die Evidenz bleibt vollständig).
- **Nicht deterministisch** ist ausschließlich der Synthese-Pfad; die Evidenz ist es immer.
- **Kein Modellzugang im Server:** keine Keys, keine gebundenen Modelle ([ADR 0004](../../../../docs/adr/0004-llm-bridge-via-mcp-sampling.md)).

## 6. Fehlerverhalten

- `invalid_input`: leere `query`, unbekannter `mode` oder `k <= 0`.
- `not_found`: Index-Datei fehlt.
- Ein **fehlgeschlagenes Sampling** ist **kein** Fehler: Das Tool antwortet mit `generated = false` und voller Evidenz.

Kategorien gemäß [docs/error-model.md](../../../../docs/error-model.md).

## 7. Provenienz

- Je Beleg `paper_id`, `label` (Abschnitt/Seite bzw. Community-Kontext), `snippet` und `source_uri`; die Nummerierung ist die Zitatmarke der Antwort.

## 8. Reproduzierbarkeit

- Evidenz: deterministisch (gleiche Anfrage → gleiche Belege in gleicher Reihenfolge).
- Routing: deterministisch – eine reine Textheuristik ohne Index- oder Modellzugriff
  ([ADR 0017](../../../../docs/adr/0017-router-hardening-phase7.md)).
- Synthese: best effort – Sampling mit `temperature = 0`; das Modell bestimmt der Client und wird im Feld `model` mitgeliefert.

## 9. Testabdeckung

- `tests/generation/test_provider.py`, `test_synthesis.py`, `test_evidence.py`: Port, Fallback, Evidenz-Adapter je Modus, Nummerierung, Contract.
- `tests/generation/test_answer.py`: Modus-Contract (`auto`/explizit/unbekannt), ausgewiesenes `routing` bzw. `null` bei expliziter Wahl, Evidenz ohne Provider, injizierter Provider, `k <= 0`.
- `tests/retrieval/test_router.py`, `tests/evaluation/test_routing.py`: Signal-Lexikon, Grenzfälle der Wortgrenzen, Fallback bei Gleichstand und die Contract-Treue gegen [eval/router-gold.json](../../../../eval/router-gold.json).
- `tests/generation/test_ask_synthesis.py`: CLI-Pfad `--synthese` (Noop-Degradation und generierte Antwort).
- `tests/mcp_server/test_sampling.py`: Capability-Fallback der Sampling-Brücke (ohne Sampling → Noop).
- `tests/mcp_server/test_server.py`: Tool-Contract über einen In-Memory-Client – Default ohne Synthese, **echter Sampling-Roundtrip** über einen Sampling-Callback und sichtbare Degradation ohne Sampling-Fähigkeit.

## 10. Beispiel

Real erzeugt gegen den Testindex aus `tests/mcp_server/conftest.py` mit `synthesize=false` (Default); geprüft in `tests/mcp_server/test_spec_examples.py`. Die Frage enthält kein Router-Signal, deshalb fällt `auto` auf `basic` zurück (`routing.confidence = "none"`).

Anfrage:

```json
{ "query": "How does attention work?", "k": 2 }
```

Antwort (`evidence.items`/`references` gekürzt auf den ersten Eintrag):

```json
{
  "query": "How does attention work?",
  "mode": "basic",
  "routing": {
    "mode": "basic",
    "confidence": "none",
    "signals": [],
    "rationale": "Kein Modus-Signal erkannt → Standard basic"
  },
  "answer": "",
  "generated": false,
  "model": "",
  "citation_contract": "Du beantwortest Fragen zu einem wissenschaftlichen Paper-Korpus. Nutze ausschließlich die nummerierten Belege im Kontext … Antworte knapp und auf Deutsch.",
  "evidence": {
    "query": "How does attention work?",
    "mode": "basic",
    "items": [
      {
        "index": 1,
        "paper_id": "aaaa0001",
        "document_kind": "full",
        "label": "Paper aaaa0001 · Abschnitt Introduction · Seite 1",
        "snippet": "transformer attention mechanism self attention encoder doi:10.1145/1234",
        "source_uri": "file:///aaaa0001.pdf",
        "identifiers": { "doi": "10.1145/1234", "arxiv": "2405.20455" },
        "citation_key": "aaaa00012024"
      }
    ]
  },
  "references": [
    {
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
  ]
}
```
