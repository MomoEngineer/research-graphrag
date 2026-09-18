# Zusammenspiel mit `docx-mcp`

Dieses Dokument beschreibt ein **Nutzungsmuster auf Ebene des aufrufenden Agenten**: wie ein
Agent `research-graphrag` zusammen mit dem separaten, allgemeinen MCP-Server `docx-mcp`
(eigenes Repository, lokal unter `C:\Users\moritz\Repositories\docx-mcp`) nutzt, um
Literaturrecherche direkt und belegt in ein Word-Dokument zu überführen – z. B. die
Masterarbeit, die README.md als Nutzungskontext nennt ("u. a. begleitend zu einer Masterarbeit
genutzt", siehe [README.md](../README.md)).

**Wichtig:** Dies ist **keine Code-Kopplung**. `research-graphrag` kennt `docx-mcp` nicht als
Abhängigkeit, und umgekehrt – `docx-mcp` ist bewusst ein allgemeines, wiederverwendbares
Werkzeug ohne Bezug zu einem einzelnen Korpus oder Projekt. Die Aufgabenteilung nach
[ADR 0018](adr/0018-code-documentation-architecture.md) gilt unverändert; dieses Dokument
gehört in dieselbe Kategorie wie [docs/vscode-integration.md](vscode-integration.md) und
[docs/online-recherche.md](online-recherche.md): eine Bedienungsanleitung für ein
Zusammenspiel, nicht eine Architekturentscheidung.

---

## 1. Voraussetzungen

- `research-graphrag` als MCP-Server eingebunden (siehe
  [docs/vscode-integration.md](vscode-integration.md)).
- `docx-mcp` **separat** als eigener MCP-Server eingebunden (`pip install docx-mcp` oder
  `uvx docx-mcp`, siehe dessen README) – mit `DOCX_MCP_ALLOWED_ROOTS` auf das Verzeichnis
  gesetzt, in dem das Zieldokument liegt.

## 2. Kernmuster: Suche → Schreiben → Zitieren

Der wiederkehrende Ablauf für einen literaturbelegten Absatz:

1. **Literatur finden.** `search_basic`/`search_local`/`search_global`/`search_drift` je nach
   Fragetyp (siehe [README.md](../README.md) für die Modus-Wahl), oder `answer_question` für
   den geroutet-in-einem-Aufruf-Fall.
2. **Beleg sichern.** `get_reference(paper_id)` liefert die fertige Literaturangabe in Harvard
   **und** APA samt Kurzbeleg – **wörtlich** übernehmen, nicht neu formulieren, um
   Transkriptionsfehler zu vermeiden.
3. **In den Text schreiben.** `docx-mcp`s `insert_paragraph(path, text, after_paragraph_index)`
   für den Fließtext.
4. **Zitieren.** `docx-mcp`s `add_footnote(path, paragraph_index, content)` mit dem
   `harvard`- oder `apa`-String aus Schritt 2 als `content`.

Konkretes Beispiel (Werte aus dem realen Test-Index in
`tests/mcp_server/conftest.py`):

```json
// 1. research-graphrag: search_basic
{ "query": "attention mechanism", "k": 3 }
// → citations[0].paper_id = "aaaa0001"

// 2. research-graphrag: get_reference
{ "paper_id": "aaaa0001" }
// → reference.harvard = "aaaa0001 (2024) Available at: https://doi.org/10.1145/1234"

// 3. docx-mcp: insert_paragraph
{ "path": "C:/thesis/chapter3.docx", "text": "Attention mechanisms improve retrieval quality.", "after_paragraph_index": 41 }
// → { "paragraph_index": 42 }

// 4. docx-mcp: add_footnote
{ "path": "C:/thesis/chapter3.docx", "paragraph_index": 42, "content": "aaaa0001 (2024) Available at: https://doi.org/10.1145/1234" }
// → { "footnote_id": "12" }
```

Dieser Pfad funktioniert bereits heute, ohne Änderung an einem der beiden Server: Beide folgen
unabhängig demselben Anthropic-Prinzip, lieber einen Verweis/eine fertige Zeichenkette
zurückzugeben als Rohdaten, die der Agent erst zusammensetzen müsste (`get_paper_file` liefert
z. B. bewusst nur den Pfad, keine Datei-Bytes – siehe
[ADR 0039](adr/0039-correction-tool-and-pdf-file-access.md); vgl. Anthropic, *"Writing effective
tools for AI agents"*, Engineering-Blog 2026).

## 3. Zitations-Rückverfolgbarkeit (freiwillige Konvention, kein Server-Code nötig)

Weder `research-graphrag` noch `docx-mcp` speichert dauerhaft, **welche** `paper_id` hinter
**welcher** Fußnote in einem `.docx` steckt. Für ein Dokument mit vielen Zitaten ist das
unbefriedigend, sobald sich später eine Angabe korrigiert (`correct_paper_metadata`,
wirksam erst nach dem nächsten Ingest – siehe
[ADR 0039](adr/0039-correction-tool-and-pdf-file-access.md)): Ohne Rückverfolgbarkeit muss der
Agent sich merken oder erraten, welche Fußnote betroffen ist.

**Empfohlene Konvention**, ausschließlich auf Ebene des Agenten, ohne Änderung an einem der
beiden Server: Der Agent pflegt neben dem `.docx` eine Sidecar-Datei
`<dokument>.citations.json`:

```json
{
  "12": { "paper_id": "aaaa0001", "chunk_id": "aaaa0001-c0000", "retrieved_at": "2026-09-18" }
}
```

- Schlüssel ist die `footnote_id` (aus `add_footnote`s Antwort bzw. `docx-mcp`s
  `get_footnotes`).
- Bei einer späteren Korrektur: `get_reference(paper_id)` erneut aufrufen, dann
  `edit_footnote(path, footnote_id, content=<neue Angabe>, expected_content=<alte Angabe>)` –
  der `expected_content`-Staleness-Check verhindert, dass eine zwischenzeitlich von Hand
  geänderte Fußnote versehentlich überschrieben wird.

Dies ist eine **Empfehlung**, keine Pflicht, und erfordert keine Änderung an `research-graphrag`
oder `docx-mcp`.

## 4. Bekannte Reibungspunkte und wie sie adressiert sind

| Reibungspunkt | Status |
| --- | --- |
| `docx-mcp`s `read_document`/`get_structure` wuchsen mit der Dokumentgröße – jede Prüfung vor einem Edit kostete Token proportional zur Gesamtlänge | **Behoben** in `docx-mcp` ab Phase 9 (siehe dessen `docs/adr/0008-scoped-paragraph-range-reads.md`): optionale `start_paragraph`/`end_paragraph` an beiden Werkzeugen, `get_structure` liefert zusätzlich `total_paragraphs`. Ein Agent, der ein wachsendes Kapitel prüft, liest gezielt das Ende statt des ganzen Dokuments. |
| Round-Trip-Kosten bei zitatreichem Schreiben (ein `insert_paragraph`- + ein `add_footnote`-Aufruf je Zitat) | **Bewusst zurückgestellt** (siehe `docx-mcp`s ADR-0008, Abschnitt "Folgeentscheidungen"): keine Messung zeigt bislang, dass die Aufrufzahl selbst ein Engpass ist. Erst messen, dann entscheiden – siehe Abschnitt 5 unten. |
| Sprachasymmetrie: `research-graphrag` dokumentiert auf Deutsch ([CONTRIBUTING.md §7](../CONTRIBUTING.md#7-sprache-der-dokumentation)), `docx-mcp` auf Englisch | Bewusst **nicht vereinheitlicht** – beide Sprachwahlen sind projekteigene, begründete Entscheidungen; moderne Modelle handhaben das gemischt zuverlässig, und eine Vereinheitlichung würde eines der beiden Projekte gegen seine eigene Konvention ändern. |

## 5. Qualitätsmerkmale & wie man sie prüft

Kein neues, separates Test-Framework – ein manuelles Mess-Rezept, konsistent mit der
"erst messen, dann entscheiden"-Kultur dieses Repos (siehe z. B. [ADR
0038](adr/0038-corpus-ceiling-revision-local-search-latency.md), Roadmap-Abschnitt V2). Vor
einer Optimierung an einem der beiden Server: die betroffene Kennzahl unten tatsächlich
messen, nicht nur vermuten.

| Merkmal | Wie messen |
| --- | --- |
| Effizienz | Tool-Calls & Tokens für eine repräsentative Verbund-Aufgabe (z. B. "Absatz mit 2 Zitaten schreiben") zählen, vorher/nachher einer Änderung |
| Latenz | Laufzeit derselben Aufgabe stoppen |
| Zitier-Treue | Fußnotentext gegen den `get_reference`-String vergleichen (Ziel: exakte Übereinstimmung) |
| Rückverfolgbarkeit | Anteil Fußnoten, die sich über die Sidecar-Datei (Abschnitt 3) auf eine gültige `paper_id` zurückführen lassen |
| Regressionssicherheit | Bestehende Testsuiten beider Projekte bleiben grün (`pytest`, `ruff`, `mypy` je Repo) |

## 6. Grenzen dieses Dokuments

- Beschreibend, nicht normativ (wie [docs/vscode-integration.md](vscode-integration.md) und
  [docs/online-recherche.md](online-recherche.md)) – bei Widerspruch gilt der tatsächliche
  Tool-Vertrag (Tool-Spezifikation) beider Projekte, nicht dieses Dokument.
- Setzt keine Versionen von `docx-mcp` voraus außer der in Abschnitt 4 genannten Untergrenze
  für die Paginierung.
