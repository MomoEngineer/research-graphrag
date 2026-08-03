# Modul-Doku: `sources.py`

| Feld | Wert |
| --- | --- |
| **Modul** | `src/research_graphrag/online/sources.py` |
| **Paket** | `online` – Kandidatensuche im Netz |
| **Phase** | 9 / S1 |
| **Grundlagen** | [ADR 0020](../../../../docs/adr/0020-online-candidate-search-phase9.md) |

---

## 1. Zweck

Übersetzt zwischen zwei fremden APIs und dem eigenen Kandidaten-Modell: Anfrage bauen, abrufen,
Antwort in `Candidate` überführen. Die beiden Quellen antworten in unterschiedlichen Formaten
(Atom-XML und JSON) und benennen dieselben Dinge verschieden – dieses Modul verbirgt das.

## 2. Öffentliche Schnittstelle

| Symbol | Art | Aufgabe |
| --- | --- | --- |
| `SearchQuery` | Dataclass | Anfrage: Kennung, Suchbegriffe, Herkunftsbegründung |
| `SourceResult` | Dataclass | Antwort einer Quelle: Status, Roh-Nutzlast, Kandidaten, Kontingent |
| `arxiv_url`, `openalex_url` | Funktionen | Bauen die jeweilige Anfrage-URL |
| `parse_arxiv`, `parse_openalex` | Funktionen | Lesen die Antwort (ohne Netz testbar) |
| `fetch_arxiv`, `fetch_openalex` | Funktionen | Abruf über den injizierten Port plus Auswertung |
| `ARXIV_ENDPOINT`, `OPENALEX_ENDPOINT` | Konstanten | Basis-URLs |
| `OPENALEX_FIELDS`, `DEFAULT_LIMIT`, `MAX_ARXIV_TERMS` | Konstanten | Umfang der Anfrage |

## 3. Ablauf

```mermaid
flowchart TD
    Q["SearchQuery"] --> A["arxiv_url: all:\"t1\" AND all:\"t2\""]
    Q --> O["openalex_url: Freitext + schmale Feldliste"]
    A --> C["HttpClient.get"]
    O --> C
    C --> S{"Status 200?"}
    S -- nein --> N["SourceResult mit Notiz,<br/>ohne Kandidaten"]
    S -- ja --> P["parse_arxiv / parse_openalex"]
    P --> R["SourceResult mit Kandidaten"]
```

### Zwei Formate, ein Modell

| Feld | arXiv | OpenAlex |
| --- | --- | --- |
| Identifikator | aus `id`, Version abgeschnitten | aus `doi`; arXiv-ID nur, wenn der DOI sie trägt |
| Abstract | `summary` (Whitespace verdichtet) | **invertierter Index**, wird zurückgebaut |
| Verweis | PDF-Link, sonst der Eintrag selbst | `open_access.oa_url`, sonst die Werk-URL |
| Lizenz | **nicht enthalten** | `primary_location.license`, oft leer |

Die fehlende Lizenzangabe bei arXiv ist kein Versehen des Adapters, sondern eine Eigenschaft des
Feeds – und der Grund, warum der Volltext-Download zurückgestellt bleibt.

### Warum höchstens drei UND-Terme

Die arXiv-Suche verknüpft die Terme konjunktiv. Mit den zehn Keywords einer Community liefe sie
praktisch immer leer; `MAX_ARXIV_TERMS` schneidet deshalb ab. OpenAlex bekommt dieselben Terme als
Freitext, weil es sie gewichtet statt sie zu erzwingen.

### Ein Rate-Limit bricht den Lauf nicht ab

Antwortet eine Quelle nicht mit 200, entsteht ein `SourceResult` **ohne** Kandidaten, aber mit
Notiz. So liefert die andere Quelle weiterhin Ergebnisse, und der Bericht weist den Ausfall aus,
statt ihn zu verschweigen. Die Kontingent-Kopfzeilen von OpenAlex werden durchgereicht.

### Härtung gegen fremdes XML

Die Standardbibliothek schützt nicht gegen Entity-Expansion. Deshalb wird eine Antwort mit
`<!DOCTYPE` oder `<!ENTITY` **abgelehnt**, bevor sie geparst wird. Zusammen mit der Größengrenze
des Transports ist das die Absicherung, für die sonst ein Zusatzpaket nötig wäre.

## 4. Zusammenspiel

Aufgerufen von [`search`](search.md); nutzt [`transport`](transport.md) über den Port und erzeugt
`Candidate` aus [`candidates`](candidates.md). Keine Datei- oder Indexzugriffe.

## 5. Fehler und Grenzfälle

| Fall | Verhalten |
| --- | --- |
| Anfrage ohne Suchbegriffe | `invalid_input` |
| XML mit Dokumenttyp-Deklaration | `parse_error` |
| Unlesbares XML oder JSON | `parse_error` |
| HTTP-Fehler der Quelle | kein Fehler – `SourceResult` mit Notiz |
| Fehlende Felder im Treffer | leere Werte statt Abbruch |

## 6. Determinismus

Die Anfrage-URL ist für eine gegebene `SearchQuery` eindeutig, und die Auswertung erhält die
Trefferreihenfolge der Quelle. Nicht deterministisch ist allein, **was** die Quelle liefert.

## 7. Grenzen

Nur arXiv und OpenAlex; Crossref, Semantic Scholar und Unpaywall sind in
[ADR 0020](../../../../docs/adr/0020-online-candidate-search-phase9.md) mit Messwerten
ausgeschlossen. Keine Paginierung, keine Sortierung außer der Relevanz der Quelle, kein Abruf von
Volltexten.
