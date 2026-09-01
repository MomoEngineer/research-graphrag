# 0030 – Referenz-Einträge im Korpus (Phase 13 / R2): zweiter Dokumenttyp in Intake, Extraktion und Index

- **Status:** Akzeptiert
- **Datum:** 2026-08-09

## Kontext

[ADR 0029](0029-reference-stub-resolution-phase13.md) erzeugt aus einer kuratierten DOI-/arXiv-Liste
Stub-Dateien `*.refjson` im Eingangsordner. Sie sind bis hierher **wirkungslos**: Der Intake liest
ausschließlich `*.pdf` mit `%PDF-`-Signatur, `pipeline.ingest` iteriert `papers/*.pdf`, und
`quality.assess` kennt nur Dokumente mit Volltext.

R2 schließt genau diese Lücke – und nur sie. Der **Contract** (`document_kind` bis in `Citation`,
`PaperRef` und `EvidenceItem`), der Ausschluss aus der Gold-Ableitung und die
Nachrangigkeits-Guardrail bleiben R3 vorbehalten.

Vier Eigenschaften des Bestandes bestimmen den Zuschnitt; zwei davon nennt die Roadmap nicht:

1. **`CanonicalPaper` hat kein `title`-Feld.** Der Titel entsteht im ganzen Repo aus dem
   **Dateinamen** (`citation_graph.title_from_uri`). Daran hängen der Titel-Match des
   Zitationsgraphen, die dritte Intake-Stufe, `metadata_index.extracted_records` und die
   Übersichtszeile.
2. **`page_label` kennt kein `document_kind`** – die Roadmap verlangt die neue Kennzeichnung aber
   in R2, während der Contract-Bruch erst in R3 kommt.
3. **`citation_graph.front_matter_text` filtert auf `page_end <= 2`.** Ein Stub-Chunk erfüllt das
   ohne Zutun; seine DOI gilt damit als frontmatter-belegt, und er wird **Ziel** von
   `CITES`-Kanten. Genau das ist der bezifferte Hauptnutzen der Phase.
4. **Der Upgrade-Pfad löscht erstmals eine Datei *in* `papers/`.** Bisher löscht der Intake
   ausschließlich im Eingang.

## Entscheidung

### 1. Der Dateiname bleibt die einzige Titelquelle – der Intake benennt um

Beim Übernehmen wird die Stub-Datei nach `<Titel>.refjson` umbenannt. Der Titel stammt aus der
Datei, wird aber **dateisystemsicher erzeugt**: verbotene Zeichen entfallen, Länge begrenzt, bei
Kollision entscheidet die Namenskollisions-Stufe des Intake.

Die Alternative – ein `title`-Feld im `CanonicalPaper` – wäre im Datenmodell sauberer, schafft
aber **zwei** Titelquellen (Feld *oder* Dateiname) und damit genau die Dualität, die dieses Repo
konsequent vermeidet (vgl. „zwei Wahrheiten wären eine Fehlerquelle",
[ADR 0020](0020-online-candidate-search-phase9.md)). Mit der Umbenennung funktionieren
Titel-Match, Intake-Stufe 3, Übersichtszeile und Metadaten-Ableitung **unverändert**.

`title_from_uri` entfernt jetzt neben `.pdf` auch `.refjson` – die einzige nötige Anpassung.

### 2. `document_kind` im Canonical- und im Index-Schema

| Schema | Alt | Neu | Wirkung |
| --- | --- | --- | --- |
| Canonical | 0.4.0 | **0.5.0** | erzwingt Re-Extraktion (`_can_skip` prüft die Version) |
| Index | 0.4.0 | **0.5.0** | Spalte `papers.document_kind`, voller Re-Index genügt |

Die Anhebung ist gewollt, obwohl sie inhaltlich nur ein konstantes Feld ergänzt: Ein Canonical-JSON
soll **selbstbeschreibend** sein, statt seine Dokumentart aus der Abwesenheit eines Feldes
ableiten zu lassen. Dieselbe Handhabung wie bei
[ADR 0013](0013-chunking-refinement-phase7.md) und [ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md).
`from_dict` bleibt trotzdem tolerant (fehlendes Feld ⇒ `full`), damit ein Alt-Artefakt lesbar
bleibt.

### 3. Das Stub-Format wird von der Extraktion definiert, nicht vom Netzcode

Die Konstanten des Formats (`STUB_SCHEMA_VERSION`, `STUB_SUFFIX`, `DOCUMENT_KIND_REFERENCE`) und
der Leser leben in `extraction/refstub.py`; `online/references.py` **importiert** sie von dort.
Die Richtung ist zwingend: `intake` und `pipeline` hängen bereits an `extraction`, und ein
umgekehrter Import (`extraction` → `online`) ergäbe einen Zyklus. Vor allem aber gilt: Wer ein
Format schreibt und wer es liest, teilen sich **eine** Definition.

### 4. Ein Referenz-Eintrag hat genau einen Chunk – auch ohne Abstract

Der einzige Chunk trägt **Titel und Abstract** (durch eine Leerzeile getrennt). Fehlt der
Abstract, bleibt der Titel – so ist der Eintrag über seinen Titel auffindbar, was Voraussetzung
für die Titel-Kanten des Zitationsgraphen ist. Die Alternative „kein Abstract ⇒ kein Chunk" hätte
einen unsichtbaren Korpus-Eintrag erzeugt.

Der Stub hat genau **eine** Section (`kind = abstract`) und **keine** Referenz-Sektion; er ist
damit Ziel, aber nie Quelle von `CITES`-Kanten.

### 5. Qualitäts-Gates werden typabhängig

`empty_document`, `no_chunks`, `missing_abstract`, `missing_references`, `no_sections_detected`,
`ocr_noise`, `possible_headless_table`, `short_chunks` und `long_chunk` sind für einen
Referenz-Eintrag entweder sinnlos oder sachlich falsch. Ungeprüft löste jeder Stub zwei bis drei
Flags aus und verrauschte den Report, der in A3/A5 mühsam von 3074 auf 316 gedrückt wurde.

Statt einer Fallunterscheidung *innerhalb* von `assess` gibt es eine eigene, winzige Funktion
`assess_reference` mit genau einem Befund: **`reference_without_abstract`**.

### 6. Keine Seitenangabe – und keine erfundene

Der Referenz-Chunk trägt `page_number = 0` und `page_end = 0`. `page_label` liefert dafür
**„ohne Seite (Abstract)"** statt „Seite 1".

Das ist bewusst eine Aussage **im Datenmodell** statt im Contract: Die Null ist selbst der
Marker, und R2 muss `document_kind` deshalb **nicht** durch `Citation`, `PaperRef` und
`EvidenceItem` reichen. Der Contract-Bruch bleibt vollständig in R3 – wo er hingehört, weil dort
auch Specs, Baselines und Guardrail dazugehören.

### 7. Upgrade-Pfad: „Volltext schlägt Referenz-Eintrag", automatisch

Trifft ein eingehendes **PDF** in Stufe 2 auf einen Korpus-Eintrag, der ein **Referenz-Eintrag**
ist, wird es **übernommen** und der Stub aus `papers/` entfernt. Ohne diese Regel griffe die
Quarantäne – und das *echte* Paper landete im `_duplikate/`-Ordner, während der Abstract-Stub im
Korpus bliebe. Genau verkehrt herum.

Die Regel ist **automatisch**, nicht opt-in: Ein Stub ist aus `new_papers/referenzen.txt`
jederzeit neu erzeugbar, ein PDF nie. Sie ist damit die einzige Löschung im Repo, die
konstruktionsbedingt unbedenklich ist. Sichtbar ist sie trotzdem vollständig: in `--dry-run`, im
Abschlussbericht und mit **sha256 der gelöschten Datei** in `data/intake_log.md`.

Der umgekehrte Fall bleibt unverändert: Ein **Stub** zu einem bereits vorhandenen Paper – egal ob
Volltext oder Stub – wandert in die Quarantäne.

### 8. Die Übersichtszeile wird umgebogen, nicht dupliziert

Beim Upgrade zeigt die vorhandene `Z`-Zeile auf eine gelöschte Datei. Drei Möglichkeiten standen
zur Wahl: den toten Link stehen lassen, eine zweite Zeile anhängen, oder die vorhandene Zeile
anpassen. Gewählt ist die dritte:

- Geändert werden **nur** die Spalten `Name` und `Interner Link`.
- Die wertenden Spalten (`Themenfokus`, `Relevanz fuer Expose`, `SRQ-Zuordnung`) und alle
  übrigen Zellen bleiben **unangetastet** – eine bereits erfolgte Kuratierung überlebt den
  Upgrade.
- Alle anderen Zeilen der Datei bleiben **byte-identisch** (binäres Lesen, Ersetzen genau einer
  Zeile, atomares Schreiben).

Das bricht die append-only-Regel aus [ADR 0019](0019-corpus-intake-new-papers-phase8.md) an genau
einer Stelle. Die Begründung ist Korrektheit: Ein toter interner Link in einer **versionierten,
kuratierten** Datei ist ein Schaden, eine Dublette ebenso. Der Eingriff trifft ausschließlich eine
Zeile, die das Werkzeug selbst erzeugt hat, und er steht im Protokoll.

Die Reihenfolge ist dabei nicht beliebig: Erst wird die Zeile umgebogen, **dann** laufen die
Entwurfszeilen – sonst gilt der neue Dateiname als unbekannt und bekäme eine zweite Zeile.

### 9. Kennzeichnung in der Übersicht

Die Zusammenfassungsspalte beginnt mit `ENTWURF (Referenz-Eintrag, nur Abstract):` statt
`ENTWURF:`. Kein Spaltenlayout wird verändert – das würde jede kuratierte Zeile brechen.

### 10. Robustheits-Gate für den zweiten Dokumenttyp

Was für PDFs die `%PDF-`-Signatur ist, ist für Stubs die **Formatprüfung**: lesbares JSON,
`document_kind = reference`, nicht-leerer Titel. Andernfalls bleibt die Datei liegen
(`invalid_stub`) – kein Abbruch des Laufs. Damit kann eine beliebige fremde `.refjson` im Eingang
keinen Schaden anrichten.

## Alternativen

**`title` als Feld im Canonical.** Siehe Abschnitt 1 – verworfen wegen der zweiten Titelquelle.

**`document_kind` schon in R2 bis in `Citation` durchreichen.** Hätte die Ausweisung sofort
verfügbar gemacht, zieht aber Tool-Specs, Baselines und die Guardrail nach sich – also den
gesamten R3-Umfang. Der Schnitt bliebe nicht erhalten. Stattdessen gilt die **Betriebsregel**:
Vor R3 gehören keine Referenz-Einträge in den Produktivkorpus (siehe Konsequenzen).

**Seitenangabe „1".** Wäre eine falsche Aussage über die Herkunft – und Provenienz ist das erste
Leitprinzip dieses Repos.

**Upgrade als Opt-in-Flag.** Verworfen: Ohne die Regel ist das Standardverhalten *falsch* (das
echte Paper wandert in die Quarantäne). Eine Sicherung, die man vergessen kann, schützt hier
nicht, sondern schadet.

**Fallunterscheidung in `assess`.** Verworfen zugunsten einer eigenen Funktion – `assess` prüft
Seitentext, Sections und Chunk-Größen, wovon für einen Stub nichts zutrifft.

## Konsequenzen

- **Positiv:** Ein Paper, dessen Volltext nicht beschaffbar ist, wird zu einem regulären
  Korpus-Eintrag – auffindbar, im Ähnlichkeitsgraphen, als Ziel von `CITES`-Kanten und über
  `metadata_index` zitierfähig. Der Weg dorthin ist derselbe wie für jedes PDF: **ein** Befehl,
  dieselben drei Prüfstufen, dasselbe Protokoll.
- **Negativ / Aufwand:** Die Schema-Anhebung erzwingt einen **vollen Re-Extract** des Korpus.
  Inhaltlich ändert sich dabei nichts außer dem neuen Feld – das wird byte-genau nachgewiesen.
- **Betriebsregel bis R3 (wichtig):** Ein Referenz-Eintrag ist im Retrieval bereits auffindbar,
  aber in den Ausgaben **noch nicht** als unvollständig ausgewiesen – das ist genau der Zustand,
  den R3 beendet. Bis dahin gehören keine Stubs in den Produktivkorpus; der Nachweis dieser Phase
  läuft deshalb auf einer **Korpus-Kopie** (Muster aus
  [ADR 0019](0019-corpus-intake-new-papers-phase8.md)).
- **Bewusst getragene Grenze:** Ein Stub hat `n_pages = 0` und genau einen Chunk. Kennzahlen, die
  über Seiten oder Chunk-Größen mitteln, verschieben sich dadurch geringfügig, sobald
  Referenz-Einträge im Korpus liegen. Der Qualitätsreport weist sie über
  `reference_without_abstract` bzw. gar nicht aus – das ist gewollt.
- **Folgeentscheidungen:** R3 reicht `document_kind` in den Contract durch, schließt
  Referenz-Einträge aus der Gold-Ableitung aus, friert beide Baselines neu ein und baut die
  Nachrangigkeits-Guardrail (belegt durch die 13 qid-Regressionen aus R0).

> **Nachtrag (2026-09-01, Phase 15 / G4):** Ein neu aufgenommener Referenz-Eintrag bekommt seither
> **keine** Entwurfszeile mehr in `Übersicht.md` – der Intake schreibt nicht mehr in die Datei
> ([ADR 0034](0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md)). Der
> Upgrade-Pfad („Volltext schlägt Referenz-Eintrag") bleibt unverändert; das Umbiegen einer
> **bereits bestehenden** Zeile (`retarget_overview_row`) wirkt nur noch dann, wenn diese Zeile
> aus der Zeit vor G4 stammt – für danach aufgenommene Stubs bleibt es ein folgenloser No-Op.
