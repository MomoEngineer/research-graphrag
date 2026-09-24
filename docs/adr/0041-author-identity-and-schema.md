# 0041 – Personenkennung der Autoren und additives Schema (Phase 17 / A2)

- **Status:** Akzeptiert
- **Datum:** 2026-09-24

## Kontext

Phase 17 macht Personen zu einer eigenen Rechercheebene
([Roadmap](../../Roadmap.md#phase-17--autoren-als-rechercheebene)). Die Planungsmessung vom
2026-09-24 (3.579 Paper) hat drei Befunde geliefert, die dieses ADR betreffen:

1. **Namen sind keine Identität (Befund 4).** 2.389 Schreibweisen verteilen sich auf 443 Paper.
   „Asai, Akari" und „Akari Asai" sind dieselbe Person, 15 verschiedene „Y. … Wang" dagegen nicht.
2. **Die Identität ist schon heruntergeladen (Befund 5).** Jede OpenAlex-Antwort trägt je Autor
   `author.id` und `author.orcid`. Gespeichert wurde bisher nur `display_name`.
3. **Datenfluss-Lücke bei den Referenz-Einträgen (Befund 2).** Alle 366 `.refjson`-Stubs tragen
   Autoren, im Index kamen davon nur 5 an. Die Planung hatte die Stelle offengelassen. Das Lesen
   des Codes hat sie lokalisiert, ohne Daten:
   - `extraction.refstub.canonical_from_stub` übernahm aus der Stub-Datei nur DOI und arXiv-ID.
     Titel, Autoren, Jahr, Venue und URL gingen verloren.
   - `indexing.metadata_index.extracted_records` liest aus dem Canonical nur die Identifikatoren
     und den Titel aus dem Dateinamen.
   - Die 5 Stubs mit Autoren im Index stammen damit sehr wahrscheinlich aus einem nachträglichen
     `resolve_metadata`-Lauf. Bestätigt wird das beim nächsten Ingest am realen Bestand.

Beim Lesen fiel außerdem auf, dass `online/references.py` die Konstanten des Stub-Formats
(`STUB_SUFFIX`, `STUB_SCHEMA_VERSION`, `DOCUMENT_KIND_REFERENCE`) selbst definierte. Das
widerspricht der dokumentierten Regel, dass das Format genau **eine** Definitionsstelle hat, den
lesenden Adapter `extraction/refstub.py`.

Die Roadmap verlangt für A2: Die Kennungen werden **additiv** gespeichert, alte Dateien laden
unverändert, die Namen bleiben in der Schreibweise der Quelle, und `get_paper`/`get_reference`
liefern die Kennungen additiv (Minor-Version der Spec). Dieses ADR deckt A2, Punkte 1 und 2 ab.
Die Punkte 3 bis 5 (Nachtrag aus `data/online_raw/`, Auflösungslauf, `MAX_AUTHORS`) folgen als
Nachtrag, weil sie auf dem Seite-1-Beleg aus A1 aufbauen.

## Entscheidung

### 1. Positionsgleiche Kennungslisten statt Autorenobjekte

`MetadataRecord` und `PaperMetadata` erhalten `author_ids` (OpenAlex-Autor-ID, Kurzform
`A5023888391`) und `author_orcids`. Beide sind Tupel **positionsgleich** zu `authors`; ein leerer
String bedeutet „unbekannt“. `authors` bleibt ein Tupel von Namen in der Schreibweise der Quelle.

- **Speicherform:** `metadata/paper_metadata.json` schreibt die Schlüssel nur, wenn mindestens
  eine Kennung vorliegt. Ein Datensatz ohne Kennung bleibt byte-identisch zur bisherigen Form, und
  eine alte Datei lädt ohne Migration. Der `SCHEMA_VERSION`-Wert des Stores (`0.1.0`) bleibt
  unverändert, nach demselben Muster wie `cleared_fields` in
  [ADR 0040](0040-explicit-field-clearing.md).
- **Prüfung statt bloßer Kürzung:** Eine OpenAlex-Kennung muss dem Muster `A` + Ziffern folgen.
  Eine ORCID muss die Prüfziffer nach ISO 7064 (Mod 11-2) erfüllen. Alles andere wird zu `""`.
  Eine falsche Kennung wäre schlimmer als keine, weil sie zwei Personen still verbinden würde.
- **Verschoben heißt verworfen:** Steht eine Liste nicht mehr positionsgleich zu `authors`,
  etwa nach einer Handbearbeitung der Namen, entfällt sie ganz. Eine Kennung am falschen Namen
  würde zwei Personen vertauschen („Präzision vor Recall“).

### 2. Die Kennungen reisen mit der Autorenliste

In der feldweisen Auflösung (`bibliography/resolve.py`) sind die Kennungen **kein** eigenes Feld.
Sie stammen stets aus dem Datensatz, der `authors` gewonnen hat. Überschreibt eine
`manual`-Korrektur die Autoren, entfallen die Kennungen der `resolved`-Quelle mit ihnen. Das hält
auch die Festlegung „`manual` bleibt menschlich“ ein: Eine Handkorrektur behauptet keine Kennung,
die sie nicht geprüft hat.

### 3. Personenschlüssel und Identitätsstatus an einer Stelle

`bibliography/model.py` definiert:

- `person_name_key`: dreht „Nachname, Vorname“ um und faltet über das vorhandene `ascii_fold`.
  Eine zweite Faltung entsteht nicht.
- `person_key`: OpenAlex-ID, sonst `orcid:<ORCID>`, sonst ausdrücklich `name:<normalisiert>`.
- `AuthorIdentity` mit dem Identitätsstatus `openalex`/`orcid`/`name`.

Die Definition steht schon hier und nicht erst im Autorenindex (A3), weil `get_paper` und
`get_reference` den Schlüssel bereits jetzt ausliefern. A3 leitet seine Tabelle aus derselben
Funktion ab.

### 4. Stub-Lücke: Bibliografie im Canonical, additiv und ohne Versionssprung

- `CanonicalPaper` erhält das optionale Feld `bibliography: SourceBibliography | None`. Heute
  befüllt es nur der Stub-Adapter. Ein PDF trägt keins: Autoren werden aus dem PDF-Text bewusst
  nicht heuristisch gelesen (Roadmap, „Bewusst ausgeschlossen“). `to_dict` schreibt den Schlüssel
  nur, wenn er gesetzt ist, ein PDF-Canonical bleibt also byte-identisch.
- **Kein Sprung der Canonical-Version.** `pipeline._can_skip` vergleicht die Version exakt. Ein
  Sprung ließe damit **jedes** PDF neu extrahieren, rund 3.200 Dateien ohne jeden inhaltlichen
  Gegenwert. Stattdessen verlangt `_can_skip` nur für Referenz-Einträge zusätzlich den Schlüssel
  `bibliography`. Ein vor Phase 17 gelesener Stub wird dadurch einmalig neu gelesen, was
  Millisekunden kostet.
- **Herkunft `resolved`, Konfidenz `strong`.** `metadata_index.stub_records` macht aus der
  Bibliografie einen Datensatz. Er ist `strong`, weil eine Stub-Datei ausschließlich aus einer
  Abfrage über ihre **eigene** Kennung entsteht
  ([ADR 0029](0029-reference-stub-resolution-phase13.md)). Anders als beim PDF kann keine fremde
  Kennung aus einem Literaturverzeichnis hineingeraten. Der Beleg lautet
  `Referenz-Eintrag über <angefragte Kennung>, <Dienst>`.
- **Reihenfolge innerhalb von `resolved`:** Der Stub-Datensatz steht vor einem gespeicherten
  `resolved`-Datensatz desselben Papers. Die Stub-Datei beschreibt den Eintrag, ein späterer
  Auflösungslauf ergänzt nur fehlende Felder.

### 5. Stub-Format 0.2.0 und eine Definitionsstelle

- Die Stub-Datei trägt `author_ids`/`author_orcids`, positionsgleich zu `authors`.
- `STUB_SCHEMA_VERSION` steigt auf `0.2.0`. Der Leser prüft die Version bewusst nicht: Eine
  0.1.0-Datei ist eine gültige 0.2.0-Datei ohne Kennungen.
- Der Schreiber importiert Endung, Version und Dokumentart jetzt tatsächlich vom Leser, so wie es
  die Modul-Doku bereits behauptete.

### 6. Index-Teilschema `paper_metadata` 0.2.0

- Neue Spalten `author_ids` und `author_orcids`.
- Die Tabelle wird bei jedem Bau neu angelegt, eine Migration entfällt.
- `load_paper_metadata` fragt die Spalten nur ab, wenn es sie gibt. Ein älterer Index bleibt so
  lesbar und liefert Metadaten ohne Kennungen.

### 7. Ausgabe: `author_identities`, additiv

`PaperMetadata.to_dict` liefert zusätzlich `author_identities`: je Autor Name, OpenAlex-ID, ORCID,
`person_key` und `identity`. Die Nutzlast ist dieselbe in `get_reference`, `get_paper` und im
`references`-Block von `answer_question`. Alle drei Spezifikationen steigen daher in der
Minor-Version: `get_reference` 0.1.0 → 0.2.0, `get_paper` 0.2.0 → 0.3.0, `answer_question`
0.2.0 → 0.3.0. `authors` bleibt unverändert.

### 8. Abdeckung als Kennzahl jedes Ingest

`MetadataBuildReport` und `IngestReport` weisen `author_coverage` aus: den Anteil der Volltexte
mit Autoren aus einem `strong`-Datensatz. Das ist die Kennzahl des A0-Abbruchkriteriums (Schwelle
80 %). `python -m scripts.ingest` gibt sie nach jedem Lauf aus, zusammen mit der Zahl der Paper mit
Personenkennung und der Zahl der Referenz-Einträge mit Bibliografie.

## Alternativen

- **Autoren als Objektliste** (`[{name, openalex_id, orcid}]`) statt paralleler Listen.
  Verworfen: Das bricht jeden Verbraucher von `authors`, also Stile, Zitierschlüssel,
  Korrektur-Tool und die Contracts von drei Werkzeugen. Die parallelen Listen erreichen dasselbe
  additiv, und `AuthorIdentity` bietet die Objektsicht dort, wo sie gebraucht wird.
- **Anhebung der Canonical-Schema-Version.** Verworfen: erzwungene Neu-Extraktion aller PDFs ohne
  Gegenwert (siehe Entscheidung 4).
- **Die Stub-Datei beim Index-Bau direkt lesen** (`metadata_index` öffnet `papers/*.refjson`).
  Verworfen: Das wäre ein zweiter Leser des Formats neben `refstub` und ein Umweg am
  Canonical-Cache vorbei. Außerdem hinge der Bau davon ab, dass die Quelldatei zum Bauzeitpunkt
  noch liegt.
- **Stub-Angaben als Herkunft `extracted`.** Verworfen: Das würde die Provenienz falsch
  darstellen, denn die Werte stammen aus einer Online-Auflösung über die eigene Kennung. Zudem
  träte ein Konflikt gleicher Herkunft mit dem bestehenden `extracted`-Datensatz auf (Titel aus dem
  Dateinamen).
- **Namen beim Speichern normalisieren.** Verworfen: Das verstößt gegen „Provenienz zuerst“.
  Normalisiert wird nur im abgeleiteten Schlüssel.
- **ORCID ohne Prüfziffer übernehmen.** Verworfen: Ein Tippfehler in einer handbearbeiteten Datei
  ergäbe eine gültig aussehende, fremde Kennung.

## Konsequenzen

- **Positiv:**
  - Die Autoren aller Referenz-Einträge erreichen den Index ohne Netzzugriff. Erwartet sind 366
    statt 5; die Zahl wird beim nächsten Ingest am realen Bestand nachgetragen.
  - Jede künftige Auflösung speichert die Personenkennung mit.
  - Alte Dateien und ein alter Index bleiben lesbar.
  - Das Stub-Format hat wieder genau eine Definitionsstelle.
- **Negativ / Aufwand:**
  - Bereits aufgelöste Datensätze tragen bis zum Nachtrag aus `data/online_raw/` (A2, Punkt 3)
    noch keine Kennung.
  - Die `references`-Nutzlast von `answer_question` wächst um rund 150 Byte je Autor. Bei höchstens
    25 Autoren je Paper bleibt sie innerhalb des Budgets aus
    [ADR 0037](0037-mcp-tool-response-size-ceiling.md). Hebt A2, Punkt 5, `MAX_AUTHORS` an, muss
    die Ausgabe gesondert gedeckelt werden.
- **Folgeentscheidungen:** Nachtrag zu diesem ADR für A2, Punkte 3 bis 5. ADR 0042 für den
  Seite-1-Beleg und den Ablehnungsvermerk (A1). ADR 0043 für den Autorenindex und die
  Tool-Oberfläche (A3/A4).

## Nachtrag (2026-09-24): A2, Punkte 3 bis 5

### Punkt 3 – Nachtrag aus den Rohantworten, ohne Netz

- **Werkzeug:** `online/backfill.py` bzw. `python -m scripts.backfill_author_ids`. Beide lesen die
  OpenAlex-Rohantworten unter `data/online_raw/`, Einzelwerke wie Trefferlisten.
- **Zuordnung:** über die **Werk-DOI**, bei Preprints zusätzlich über den DataCite-DOI
  `10.48550/arxiv.<ID>`.
- **Übernahme nur bei identischer Namensliste:** Nur dann ist die Zuordnung Kennung ↔ Name
  belegt. Liefern mehrere Rohantworten zu einem Werk verschiedene Kennungen, bleibt das Paper
  ohne Kennung und steht als **Konflikt** im Protokoll.

Für Paper ohne gespeicherten `resolved`-Datensatz, typischerweise Referenz-Einträge, entsteht ein
**Kennungs-Datensatz**: `resolved`, nur Namen und Kennungen, alle übrigen Felder leer. Die
Stub-Datei selbst wird nicht verändert, sonst änderten sich ihr sha256 und damit die Paper-ID.

Dazu präzisiert Entscheidung 2: Die Kennungen reisen weiterhin mit der gewonnenen Autorenliste.
Trägt diese selbst keine, darf **ein anderer Datensatz mit Position für Position identischer
Namensliste** sie liefern. `origins.author_ids` weist dann deren Herkunft aus. Eine Kennung kann so
nie an einen fremden Namen geraten, auch nicht über eine `manual`-Korrektur mit abweichenden
Namen.

### Punkt 4 – Auflösungslauf fortsetzbar

- **Fortsetzbar:** `scripts.resolve_metadata` speichert den Zwischenstand alle zehn Paper
  (`SAVE_EVERY`) und auch bei einem Abbruch durch Netzfehler oder Strg+C.
- **Kontingent:** Antwortet ein Dienst mit HTTP 429, bricht `resolve_target` die übrigen Wege
  dieses Papers ab, und der Lauf hält an.
- **Idempotent:** Das galt schon vorher über `filter_pending`. Ein zweiter Lauf stellt keine
  Abfrage für ein bereits vollständiges Paper.
- **Beleg für jeden Treffer:** Jeder neue Treffer durchläuft den Seite-1-Beleg aus
  [ADR 0042](0042-title-page-evidence-and-rejections.md).

**Bewusst nicht gebaut:** OpenAlex-**Sammelabfragen** (mehrere DOIs je Anfrage). Ob sie über den
Proxy zulässig sind und das Kontingent wirksam schonen, ist laut Roadmap unbelegt und wird in A0,
Punkt 1, gemessen. Erst ein positiver Befund rechtfertigt den Umbau.

### Punkt 5 – `MAX_AUTHORS`: Entscheidung vertagt auf die A0-Messung

`MAX_AUTHORS = 25` bleibt bis zur Messung bestehen.

**Nutzen einer vollständigen Liste:** Die Personensuche fände alle Beteiligten. Heute sind laut
Planung 11 Listen abgeschnitten, betroffen sind also Personen jenseits der Position 25 in wenigen
großen Kollaborationspapern.

**Kosten:**

- Wachstum von `metadata/paper_metadata.json` und Index.
- Die Nutzlast `author_identities` in `answer_question` wäre ohne eigene Obergrenze nicht mehr
  durch [ADR 0037](0037-mcp-tool-response-size-ceiling.md) gedeckt. Ein einzelnes
  Kollaborationspaper trägt mehrere hundert Namen.

A0 beziffert beides aus den Rohantworten: die Zahl der Werke über 25 Autoren, die Verteilung und
den Größenzuwachs. Fällt die Entscheidung für die volle Liste, braucht die Ausgabe eine eigene
Kappung mit ausgewiesener Gesamtzahl. Das ist ein eigener Nachtrag.
