# Modul-Doku: `refstub.py`

| Feld | Wert |
| --- | --- |
| **Modul** | `src/research_graphrag/extraction/refstub.py` |
| **Paket** | `extraction` – Quelldatei zu Canonical JSON |
| **Phase** | 13 / R2, erweitert in 17 / A2 |
| **Grundlagen** | [ADR 0030](../../../../docs/adr/0030-reference-entries-in-corpus-phase13.md) · [ADR 0029](../../../../docs/adr/0029-reference-stub-resolution-phase13.md) · [ADR 0006](../../../../docs/adr/0006-canonical-model-phase2-scope.md) · [ADR 0041](../../../../docs/adr/0041-author-identity-and-schema.md) |

---

## 1. Zweck

Zweiter Extraktions-Adapter neben [`pdf.py`](pdf.md): Er liest die nativen Stub-Dateien
`*.refjson` – Paper, von denen nur der **Abstract** öffentlich ist – und überführt sie **ohne
Heuristik** in ein `CanonicalPaper`. Der Umweg über eine synthetische PDF wäre ein Verlustkanal
ohne Gegenwert.

Das Modul ist zugleich die **einzige Definitionsstelle des Stub-Formats**: Konstanten und Leser
leben hier, der schreibende Online-Lauf
([`online/references.py`](../../online/doc/references.md)) importiert sie. Wer ein Format schreibt
und wer es liest, teilen sich damit eine Wahrheit. *Nachtrag Phase 17 / A2:* Tatsächlich
definierte der Schreiber Endung, Formatversion und Dokumentart bis dahin noch einmal selbst. Seit
ADR 0041 importiert er sie wirklich von hier.

## 2. Öffentliche Schnittstelle

| Symbol | Art | Aufgabe |
| --- | --- | --- |
| `extract_stub` | Funktion | Datei → `CanonicalPaper` (der reguläre Weg) |
| `parse_stub` | Funktion | Rohbytes → `ReferenceStub` (Formatprüfung und Bereinigung) |
| `canonical_from_stub` | Funktion | Werte → `CanonicalPaper` (netzfrei, dateisystemfrei) |
| `ReferenceStub` | Dataclass | der geprüfte Inhalt einer Stub-Datei; `bibliography` liefert ihn als `SourceBibliography` |
| `STUB_SUFFIX` / `STUB_SCHEMA_VERSION` | Konstanten | Endung und Formatversion (`0.2.0` seit Phase 17 / A2) |
| `ABSTRACT_SECTION_TITLE` | Konstante | Titel der einzigen Section |
| `MAX_TITLE_CHARS` / `MAX_ABSTRACT_CHARS` | Konstanten | Längengrenzen fremder Eingaben |

## 3. Ablauf

```mermaid
flowchart TD
    A["*.refjson"] --> B["parse_stub"]
    B --> C{"lesbares JSON-Objekt?"}
    C -- nein --> E["parse_error"]
    C -- ja --> D{"document_kind == reference?"}
    D -- nein --> E
    D -- ja --> F{"Titel vorhanden?"}
    F -- nein --> E
    F -- ja --> G["Werte bereinigen<br/>einzeilig · druckbar · begrenzt"]
    G --> H["canonical_from_stub"]
    H --> I["1 Section (abstract)<br/>1 Chunk: Titel + Abstract<br/>page 0 · n_pages 0<br/>+ bibliography (Titel, Autoren samt Kennung, Jahr, Venue)"]
    I --> J{"Abstract da?"}
    J -- nein --> K["reference_without_abstract"]
```

### Bibliografie der Datei (Phase 17 / A2)

Bis Phase 17 gingen Autoren, Jahr, Venue und URL der Stub-Datei hier verloren. Das Canonical trug
nur die Identifikatoren, und im Index kamen 5 von 366 Autorenlisten an, und zwar nur über einen
nachträglichen Auflösungslauf (Roadmap Phase 17, Befund 2). Jetzt reicht der Adapter die Angaben als
`SourceBibliography` an das Canonical weiter. [`metadata_index`](../../indexing/doc/metadata_index.md)
macht daraus einen `resolved`-Datensatz.

Format **0.2.0** ergänzt je Autor `author_ids` (OpenAlex) und `author_orcids`, positionsgleich zu
`authors`. Der Leser prüft jede Kennung. Fällt beim Bereinigen ein leerer Name heraus, wäre die
Zuordnung verschoben; dann entfallen die Kennungen ganz. Eine 0.1.0-Datei ist eine gültige
0.2.0-Datei ohne Kennungen, und die Version wird bewusst nicht geprüft.

### Drei gesetzte Eigenschaften

| Eigenschaft | Warum |
| --- | --- |
| **Genau ein Chunk** aus Titel *und* Abstract | Fehlt der Abstract, bleibt der Titel – nur so ist der Eintrag auffindbar, und das ist Voraussetzung für die **Titel-Kanten** des Zitationsgraphen |
| **Keine Seitenangabe** (`page_number = page_end = 0`) | „Seite 1" wäre eine falsche Aussage über die Herkunft; die Anzeigeform liefert [`provenance.page_label`](../../retrieval/doc/provenance.md) |
| **Keine Referenz-Sektion** | Ein Stub ist **Ziel** von `CITES`-Kanten, nie deren Quelle |

### Warum vollständig geprüft wird, obwohl die Datei aus dem eigenen Werkzeug stammt

Der manuelle Weg führt ausdrücklich über **diese** Datei: Liefert keine Quelle einen Abstract,
wird er von Hand hineinkopiert ([ADR 0029](../../../../docs/adr/0029-reference-stub-resolution-phase13.md)).
Damit ist die Datei eine bearbeitete Eingabe – Titel, Autoren, Venue und Abstract werden auf
druckbare Zeichen reduziert, in Whitespace verdichtet und längenbegrenzt.

## 4. Grenzen

- Ein Stub trägt `n_pages = 0` und genau einen Chunk. Kennzahlen, die über Seiten oder
  Chunk-Größen mitteln, verschieben sich dadurch geringfügig.
- Die Dokumentart ist die **Signaturprüfung** dieses Dokumenttyps – was für PDFs die
  `%PDF-`-Signatur ist. Eine beliebige fremde `.refjson` im Eingang wird abgelehnt.
- Ob ein Referenz-Eintrag in Ausgaben als unvollständig **ausgewiesen** wird, entscheidet erst
  Phase 13 / R3 (Contract-Bruch bis in `Citation`).
