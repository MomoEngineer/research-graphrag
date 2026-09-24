# 0043 – Autorenindex und Personen-Werkzeuge (Phase 17 / A3 + A4)

- **Status:** Akzeptiert
- **Datum:** 2026-09-24

## Kontext

Phase 17 macht Personen zu einer eigenen Rechercheebene
([Roadmap](../../Roadmap.md#phase-17--autoren-als-rechercheebene)). Abfragbar sollen sein:

- alle Korpus-Paper einer Person,
- ihr schlankes Profil,
- die Suche in ihren Papern,
- ihre Zitationsbeziehungen im Korpus.

Die Erwähnungen im Text (A5) folgen nach Phase 16 / F2. Die Grundlage legen
[ADR 0041](0041-author-identity-and-schema.md) (Personenkennung) und
[ADR 0042](0042-title-page-evidence-and-rejections.md) (belegte Zitierdaten).

Drei Rahmenbedingungen prägen die Entscheidung:

1. **Die Abdeckung ist unvollständig.** Heute tragen rund 12 % der Volltexte Autoren. A2 und A1
   heben das, das Ergebnis misst aber erst A0 am realen Bestand. Das Abbruchkriterium verlangt:
   Wird die Schwelle von 80 % nicht erreicht, weisen die Werkzeuge die Lücke in **jeder**
   Antwort aus.
2. **Reihenfolge gegenüber Phase 16:** Am 2026-09-24 mit dem Nutzer festgelegt
   ([Umsetzungsblock](../../Roadmap.md#umsetzung-stand-und-reihenfolge)). A3 legt die kleine
   Trigramm-Tabelle für Namen schon jetzt an; die F0-Schwellen betreffen den Chunk-Index. Die
   Entschärfung von FTS5-Anfragen entsteht an **einer** Stelle, die F2 übernimmt.
3. **Mehr Werkzeuge verschlechtern die Tool-Wahl** (Jia et al. 2025, arXiv:2510.24563, S. 9).
   Die Nutzervorgabe lautet trotzdem „lieber ein MCP-Tool zu viel als zu wenig“. Die Antwort
   darauf sind scharf abgegrenzte Beschreibungen und die Handprobe zur Tool-Wahl in A6.

## Entscheidung

### A3 – Autorenindex

1. **Tabelle `paper_authors`**, im Index-Bau nach `paper_metadata` abgeleitet, im selben atomaren
   Fenster, mit eigener Teilschema-Version `author_schema_version = 0.1.0`. Je Paper und
   Autorposition eine Zeile:
   - Schreibweise der Quelle,
   - Namensschlüssel (`person_name_key`, eine Faltung über `ascii_fold`),
   - OpenAlex-ID und ORCID,
   - Personenschlüssel (Kennung vor Name, sonst ausdrücklich `name:<normalisiert>`),
   - Identitätsstatus und Dokumentart.
2. **Nur `strong`-Datensätze.** Ein schwach belegter Datensatz kann ein fremdes Paper beschreiben.
   Seine Autoren würden sonst einer Person Paper zuschreiben, die sie nie geschrieben hat.
3. **Namenssuche** über die FTS5-Tabelle `author_name_search` (Tokenizer `trigram`) mit einer
   Zeile je verschiedenem Namensschlüssel. Die Anfrage wird wie ein Name normalisiert:
   - Suchwörter ab drei Zeichen müssen als Teilstring vorkommen.
   - Kürzere Suchwörter, etwa die Initiale in „Y. Wang“, müssen als Wortanfang vorkommen. Der
     Tokenizer findet sie nicht; er liefert dann still nichts.
   - **Rückfallweg:** Fehlt FTS5 oder `trigram`, oder sind alle Suchwörter kurz, wird die kleine
     Schlüsselmenge direkt durchsucht, mit demselben Ergebnis (getestet).
     `meta.author_name_search` nennt den Weg.
4. **Gemeinsame FTS5-Bausteine in `indexing/fts.py`:**
   - Verfügbarkeitsprüfung (Tokenizer-Name per Whitelist),
   - Entschärfung (jedes Token als String-Literal, Operatoren wirkungslos),
   - Übersetzung von `sqlite3.OperationalError` in `invalid_input`.

   Phase 16 / F2 übernimmt das Modul für die Chunk-Phrasensuche.
5. **Kein Retrieval-Modus liest die Tabelle.** `--check` bleibt davon unberührt.

### A4 – Personen-Werkzeuge (Spezifikation vor Code)

Vier neue Werkzeuge. `get_paper` und `get_reference` liefern den Personenschlüssel je Autor bereits
über `author_identities` (ADR 0041), ein fünftes Werkzeug entsteht dafür nicht.

| Werkzeug | Beantwortet | Kern der Antwort |
| --- | --- | --- |
| `search_authors` | „Wer ist gemeint?“ | Kandidaten je Personenschlüssel: Identitätsstatus, Schreibweisen, Paperzahl, Jahresspanne, Beispieltitel; `ambiguous`, sobald mehr als ein Kandidat passt |
| `get_author` | „Was hat X im Korpus?“ | Paperliste (ID, Titel, Jahr, Position, Dokumentart, Zitierschlüssel), Jahresspanne, Communities der Paper, direkte Mitautoren mit Zahl gemeinsamer Paper |
| `search_author_papers` | „Was schreibt X über Y?“ | Basic-Suche (Hybrid-Wertung, `Citation`-Contract), beschränkt auf die Paper der Person |
| `get_author_citations` | „Wer zitiert X, wen zitiert X?“ | Korpus-Paper, die Paper der Person zitieren, und solche, die sie zitiert; Selbstzitate markiert; Grenze „nur innerhalb des Korpus“ ausgewiesen |

Gemeinsame Regeln:

- **`coverage` in jeder Antwort:**
  - Volltexte mit Autoren in der Personenebene / Volltexte gesamt,
  - Anteil und Klartext.

  So wird keine Vollständigkeit suggeriert (Abbruchkriterium A0).
- **Obergrenze:** Jede Liste hält `MAX_RESULT_COUNT` ([ADR 0037](0037-mcp-tool-response-size-ceiling.md))
  ein und weist `total_matching` aus.
- **Mehrdeutigkeit ist kein Fehler.** `search_authors` liefert eine Kandidatenliste, und
  Namensidentitäten werden **nie** still zusammengeführt:
  - Eine Person mit OpenAlex-ID und dieselbe Schreibweise ohne Kennung erscheinen als **zwei**
    Kandidaten.
  - Die Antwort trägt dann `ambiguous = true`.
- **Unbekannte Personen:** Ein unbekannter Name bzw. Personenschlüssel ergibt `not_found`, die
  Meldung nennt die Abdeckung.
- **Keine Gruppenbildung:** `get_author` nennt nur direkte Mitautoren.
- **Nur Lesezugriff:** Die Werkzeuge lesen ausschließlich den Index, kein Netz.
- **CLI:** Jedes Werkzeug hat ein Gegenstück in `python -m scripts.authors` (Unterbefehle
  `suchen`, `profil`, `paper`, `zitationen`), nach dem Muster von `scripts.cite` und
  `scripts.citations`.
- **Zahl der Werkzeuge:** Der Server wächst von elf auf **fünfzehn**. Jede Beschreibung grenzt
  ausdrücklich gegen die bestehenden Suchwerkzeuge ab.

#### `search_author_papers` nutzt Basic, nicht Local

Die Roadmap nennt „Basic/Local“. Umgesetzt ist die Basic-Suche mit Paper-Filter
(`TfidfIndex.search(..., paper_ids=…)`). Das ist exakt die Logik und der `Citation`-Contract von
`search_basic`, eine zweite Implementierung entsteht nicht. Local wird bewusst **nicht**
angeboten: Chunk-Nachbarschaft und Fan-out verlassen per Konstruktion die Paper der Person. Auf
„Was schreibt X über Y?“ antwortete Local deshalb mit Belegen **anderer** Autoren. Eine auf die
Person beschränkte Local-Variante wäre in Wahrheit Basic plus Rauschen.

## Alternativen

- **Autoren schwacher Datensätze aufnehmen, aber markieren.** Verworfen: Das würde einer Person
  im Zweifel ein fremdes Paper zuschreiben. Die Markierung stünde in der Liste, der Fehler in der
  Antwort des Agenten.
- **Reine Namenssuche per `LIKE` ohne FTS5.** Für einige tausend Schlüssel schnell genug und als
  Rückfallweg ohnehin vorhanden. Die Roadmap sieht die Trigramm-Tabelle aber vor, sie kostet
  wenig, und sie legt die gemeinsamen FTS5-Bausteine, die F2 braucht. Beibehalten mit
  Rückfallweg.
- **Namensidentitäten automatisch an Kennungs-Identitäten hängen**, etwa „Akari Asai“ ohne ID an
  A1111. Verworfen: Namensgleichheit trennt Gleichnamige nicht (15 verschiedene „Y. … Wang“).
  „Bewusst ausgeschlossen: automatisches Zusammenführen reiner Namensidentitäten.“
- **Ein Sammelwerkzeug `authors` mit Aktions-Parameter.** Verworfen: Das widerspricht der
  Nutzervorgabe „jede Fähigkeit ein eigenes, scharf abgegrenztes Tool“, und ein
  Aktions-Parameter verschiebt die Wahl nur in die Parameter.
- **Local in `search_author_papers`.** Verworfen (siehe oben).

## Konsequenzen

- **Positiv:**
  - Personen sind über eine Kennung recherchierbar, und Mehrdeutigkeit bleibt sichtbar.
  - Die Lücke der Abdeckung wird ausgewiesen statt verschwiegen.
  - F2 findet die FTS5-Regeln fertig vor.
- **Negativ / Aufwand:**
  - Vier neue Werkzeuge vergrößern die Tool-Metadaten jeder Interaktion (Hasan et al. 2026,
    arXiv:2602.14878, S. 3). Die Handprobe zur Tool-Wahl (A6) entscheidet, ob die Beschreibungen
    geschärft werden müssen.
  - Die Qualität der Personenebene hängt an der Abdeckung, also an A0 bis A2 am realen Bestand.
- **Folgeentscheidungen:** A5 (`find_person_mentions`) nach F2. Nachtrag zu diesem ADR, falls die
  Handprobe Beschreibungen ändert.

## Nachtrag (2026-09-24): Umsetzung von A4

Die vier Werkzeuge sind nach den Spezifikationen unter
[`mcp_server/specs/`](../../src/research_graphrag/mcp_server/specs) umgesetzt
([retrieval/authors](../../src/research_graphrag/retrieval/doc/authors.md)). Beim Bau wurden fünf
Punkte festgelegt, die die Entscheidung oben präzisieren:

1. **Paper-Kurzangabe mit Quelle.** Die Paperlisten von `get_author` und
   `get_author_citations` tragen zusätzlich die `source_uri`, wie jede andere Paper-Referenz der
   Werkzeuge. Ohne sie wäre ein Paper ohne DOI und ohne Zitierdaten nur über eine interne ID
   greifbar. `year` ist `null`, wenn das Jahr unbekannt ist, statt einer irreführenden `0`.
2. **Kandidaten umfassen alle Schreibweisen.** Die Namenssuche liefert Namensschlüssel, daraus
   entstehen Personenschlüssel, und erst dann werden **alle** Zeilen dieser Personen geladen. Die
   Suche nach „Asai“ zählt so auch das Paper, auf dem dieselbe OpenAlex-ID als „Asai, Akari“
   steht. Tragen die Nennungen einer Person verschiedene ORCIDs, steht die häufigste in der
   Antwort.
3. **Abdeckung im Klartext.** `coverage.note` benennt die Lücke mit Zahlen („Nur 4 von 6
   Volltexten (67 %) tragen belegte Autoren …“) und sagt ausdrücklich, dass ein fehlender Treffer
   nicht „nicht im Korpus“ bedeutet. Dieselbe Angabe steht in jeder `not_found`-Meldung zu einem
   unbekannten Namen oder Personenschlüssel. Ein
   Index von vor A3 meldet stattdessen, dass `python -m scripts.ingest` die Personenebene baut.
4. **Selbstzitate je Gegenüber.** `get_author_citations` fasst die Kanten je Gegenüber zusammen
   (`via`, `methods`) und markiert mit `self`, wenn das Gegenüber selbst ein Paper der Person ist.
   Sortiert wird nach der Zahl beteiligter eigener Paper.
5. **Eine Faktenlage für alle Tests.** Funktions-, CLI- und Contract-Tests teilen den
   Personen-Index `make_person_index` (`tests/conftest.py`). Er enthält bewusst eine gleichnamige
   Namensidentität, einen nur `weak` belegten Datensatz derselben Person und einen Volltext ohne
   Zitierdaten.

## Nachtrag (2026-09-24, zweiter Eintrag): Befunde aus der Gesamtprüfung

Eine End-to-End-Prüfung mit echten PDFs, dem MCP-Server als stdio-Unterprozess, gezielten
Randfällen und einem synthetischen Index von 3.500 Papern ergab zwei Korrekturen am Verhalten:

1. **Zerlegte Umlaute.** `ascii_fold` setzt jetzt vor der Transliteration nach NFC zusammen. Ein
   „u + Trema“ in NFD (etwa aus macOS oder einer PDF-Extraktion) faltete vorher zu „u“ statt „ue“:
   „Müller“ lag dann je nach Kodierung auf zwei Schlüsseln. Das betrifft auch den Seite-1-Beleg,
   der denselben Schlüssel vergleicht.
2. **Namen ohne lateinische Buchstaben.** Solche Nennungen fielen still aus der Personenebene,
   auch mit OpenAlex-ID, und ohne Kennung trugen sie den geteilten Schlüssel `name:`. Jetzt gilt:
   - Mit Kennung bleibt die Nennung erhalten. Sie ist über den Personenschlüssel erreichbar,
     nicht über die Namenssuche.
   - Ohne Kennung ist `person_key` leer, und die Nennung entfällt. Der Ingest zählt sie
     („ohne Personenschlüssel“), statt sie still zu verlieren.

   Eine zweite, Unicode-fähige Faltung bleibt bewusst aus. Ob sie nötig ist, zeigt erst die
   Zahl im Ingest am realen Bestand.

Außerdem belegt dieselbe Prüfung die Aussage aus A6: Nach dem Upgrade sind Papers, Chunks,
Graphen, Communities, Zitationskanten und der Eval-Fingerprint bitgleich. Alle Suchmodi liefern
dieselben Ergebnisse (30 von 30 Vergleichen). Die größte Antwort der Personen-Werkzeuge lag am
synthetischen Index bei 45 KB.

**Offen:** Die Handprobe aus A0, Punkt 4 läuft am realen Bestand beim Nutzer (Schwelle: Recall
≥ 0,9 und 0 Fehltreffer je Person mit Kennung, bestanden bei mindestens 8 von 10 Personen). Bis
dahin ist die Akzeptanz von A4 nur für Spezifikation und Tests belegt.
