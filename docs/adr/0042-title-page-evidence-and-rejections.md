# 0042 – Seite-1-Beleg, Ablehnungsvermerk und LLM-Arbeitsliste (Phase 17 / A1)

- **Status:** Akzeptiert
- **Datum:** 2026-09-24

## Kontext

Befund 3 der Phase-17-Planung ([Roadmap](../../Roadmap.md#phase-17--autoren-als-rechercheebene))
zeigt, dass die Konfidenzstufe `weak` aus [ADR 0026](0026-online-metadata-resolution.md) mehr
verdeckt als eine Unsicherheit:

- **Umfang:** 427 der 3.213 Volltexte sind `weak`: 335 nur aus der Extraktion, 92 online
  aufgelöst.
- **Befund:** Bei 44 der 92 stehen weder Titel noch Autoren des Treffers auf Seite 1 des PDFs. Alle
  sechs von Hand geprüften Fälle waren **fremde** Paper. Die VisRAG-Datei wird etwa als „GPT-4
  Technical Report“ zitiert.
- **Ursache:** Die aufgelöste Kennung stammte aus dem Literaturverzeichnis.

Das ist ein **Korrektheitsfehler** in `get_reference`, keine bloße Lücke.

Die Roadmap legt für A1 fest:

1. Ein **deterministischer Seite-1-Beleg** wertet auf. Er verwendet denselben Titel-Mechanismus
   wie Intake und S2 und einen in A0 kalibrierten Mindestanteil der Nachnamen.
2. **Fremd-Paper-Fälle** werden verworfen. Ein **Ablehnungsvermerk** hält die Bereinigung stabil.
3. Der Rest läuft über eine **LLM-Arbeitsliste**. Das LLM liefert nur Kennung oder Titel; das Skript
   prüft.
4. Was in keiner Quelle steht, wird von Hand korrigiert (`manual`) oder mit Grund als „nicht
   auflösbar“ ausgewiesen.

Kein `weak` bleibt ohne ausgewiesenen Status.

Eine Bedingung schränkt die Umsetzung ein: A0, Punkt 3, soll den Beleg an mindestens 30 von Hand
geprüften Fällen kalibrieren, Schwelle **0 falsch-positive** Aufwertungen. Diese Messung läuft am
realen Bestand beim Nutzer und liegt beim Bau noch nicht vor
([Umsetzungsblock](../../Roadmap.md#umsetzung-stand-und-reihenfolge)).

## Entscheidung

### 1. Der Seite-1-Beleg (`bibliography/titlepage.py`)

- **Titel:** `intake.read_front_pages` + `intake.title_candidates` + `intake.best_title_match` mit
  `TITLE_SIMILARITY` (0,85), also genau der Mechanismus des Intake und aus S2. Eine zweite
  Ähnlichkeitslogik entsteht nicht.
- **Autoren:** Anteil der ersten zehn Nachnamen (`MAX_CHECKED_SURNAMES`), die als **ganzes Wort**
  auf Seite 1 stehen. Die Faltung erfolgt über `ascii_fold`, sodass „Li“ nicht in „Library“
  zählt.
- **Die Titelseite ist Beleg, nie Quelle.** Aus dem PDF-Text wird kein Wert übernommen.
- **Urteile:** `confirmed`, `foreign`, `unconfirmed` und `unreadable` (Seite 1 ohne Text, etwa
  bei einem Scan).

### 2. Zwei kalibrierte Schwellen, bis dahin keine automatische Entscheidung

Die Roadmap nennt eine Schwelle für die Aufwertung. Die Umsetzung braucht **zwei**, gebündelt in
`Calibration`:

- **`min_author_share`:** Aufwertung, wenn der Titel steht **und** mindestens dieser Anteil der
  Nachnamen. Kalibriert auf 0 falsch-positive Aufwertungen.
- **`max_share_for_rejection`:** Ablehnung nur, wenn der Titel fehlt **und** höchstens dieser
  Anteil der Nachnamen steht. Kalibriert auf **0 falsche Ablehnungen**.

Die zweite Schwelle präzisiert A1, Punkt 2 („steht der Titel nicht auf der Titelseite, wird der
Treffer verworfen“), aus zwei Gründen:

1. Die Planung zählte 7 Fälle „Titel fehlt, Autoren stehen“. Sie deuten auf eine unleserliche oder
   umbrochene Titelzeile, nicht auf ein fremdes Paper.
2. Eine falsche Ablehnung sperrt über den Vermerk ausgerechnet den **richtigen** Treffer dauerhaft.

Bis A0, Punkt 3, beantwortet ist, steht `CALIBRATION` auf `Calibration()`: beide Schwellen `None`,
Urteil immer `unconfirmed` (bei lesbarer Seite). Das ist der Rückfall aus dem A0-Abbruchkriterium.
Die Mechanik ist gebaut und getestet, entscheidet aber nichts, bevor die Messung es erlaubt. Nach
der Kalibrierung werden beide Werte samt Beleg (Datum, Stichprobe) in **einem** Commit in
`CALIBRATION` eingetragen. Sie sind kein Laufzeitparameter, damit jede Aufwertung auf einen
versionierten Stand rückführbar bleibt.

### 3. Neue Belegklasse in der Konfidenztabelle

Ergänzt [ADR 0026](0026-online-metadata-resolution.md), Abschnitt 2 (dort als Nachtrag vermerkt):

| Beleg | Konfidenz | Konsequenz |
| --- | --- | --- |
| Treffer (beliebiger Weg) **und** Titel und Autoren auf S. 1 belegt | `strong` | Herkunft bleibt `resolved`; Beleg „Titel und Autoren auf S. 1 belegt (Titel 0.97, Autoren 4/5 auf S. 1)“ wird angehängt |
| Treffer, aber weder Titel noch (kalibriert) Autoren auf S. 1 | – | **verworfen**, Ablehnungsvermerk |

### 4. Ablehnungsvermerk und Prüfstatus in derselben Datei

`metadata/paper_metadata.json` erhält den additiven Schlüssel `reviews`: je Paper einen
`PaperReview` mit Ablehnungsvermerken (`Rejection`: DOI, arXiv-ID, Titel, Grund, Datum) und einem
optionalen Status `unresolvable` samt Pflicht-Grund.

- **Eine Datei, ein atomarer Schreibvorgang.** Das Entfernen eines Treffers und sein Vermerk
  entstehen gemeinsam. Getrennte Dateien könnten nach einem Abbruch den Datensatz ohne Vermerk
  zurücklassen, und der nächste Lauf spielte den Treffer wieder ein.
- **`save_records` behält den Prüfstand standardmäßig** (`reviews=None`). Jeder bestehende
  Aufrufer, also Auflösungslauf und Korrektur-Tool, kann keinen Vermerk verlieren, ohne dass er
  dafür geändert werden müsste.
- **Additiv:** Der Schlüssel erscheint nur, wenn es einen Prüfstand gibt. Die Store-Version bleibt
  `0.1.0`, wie bei `cleared_fields` ([ADR 0040](0040-explicit-field-clearing.md)).
- **Vergleich:** Ein Treffer gilt als abgelehnt, wenn DOI (ohne Groß-/Kleinschreibung), arXiv-ID
  **oder** normalisierter Titel übereinstimmen. Derselbe fremde Treffer kann über jeden Weg
  zurückkehren.

### 5. Wirkung in der Auflösung

`online.metadata.resolve_target` erhält `rejections`, `verify`, `calibration` und `today`:

- Ein abgelehnter Treffer wird übersprungen, und der nächste Weg wird versucht.
- Mit `verify` wird jeder Treffer gegen Seite 1 geprüft:
  - `foreign` ⇒ neuer Vermerk, nächster Weg.
  - `confirmed` ⇒ `strong`.
  - sonst unverändert; der Befund reist als `check` mit.

`scripts.resolve_metadata` übergibt dafür die gespeicherten Vermerke und das lokale PDF
(`--papers`). Es speichert neue Vermerke und fragt ein als `unresolvable` ausgewiesenes Paper
nicht erneut ab (`skip_settled`). Damit gilt die A1-Akzeptanz: **Ein zweiter
`resolve_metadata`-Lauf spielt keinen verworfenen Treffer zurück.**

### 6. Die Triage des Bestands (`bibliography/triage.py`, `scripts.verify_metadata`)

- **Anwendungsbereich:** Der Beleg läuft über die gespeicherten `resolved`-Datensätze der
  **offen schwachen** Volltexte. „Offen“ heißt: ohne ausgewiesenen Status.
- **Entscheidungen:** `upgraded`, `rejected`, `unchanged` oder `not_checkable` (kein gespeicherter
  Treffer, kein PDF, Referenz-Eintrag).
- **Kein Netz:** Der Lauf hat keinen Netzzugriff. Ein verworfenes Paper fällt auf seine übrigen
  Herkünfte zurück und wird beim nächsten `resolve_metadata`-Lauf neu aufgelöst: über die
  Kennung der Titelseite bzw. den Titel aus dem Dateinamen (Korpus-Konvention „Dateiname =
  Titel“), wieder mit Beleg und unter Beachtung des Vermerks.

### 7. LLM-Arbeitsliste (`bibliography/worklist.py`, `scripts.metadata_worklist`)

- **Export:** Nach `data/worklists/<Zeitstempel>/` (JSON und Markdown). Die Liste ist
  regenerierbar und liegt deshalb unter `data/`. Je Paper enthält sie:
  - Paper-ID und Dateiname,
  - den aktuellen Datensatz,
  - Befund und Grund,
  - einen bereinigten Auszug der Titelseite, **ausdrücklich als Fremdtext markiert**: auf 1.500
    Zeichen begrenzt, druckbar, ohne Codezaun-Zeichen.
- **Antwortformat:** `{"antworten": [{"paper_id": …, "doi" | "arxiv_id" | "title": …}]}`, je
  Paper **genau eine** Angabe. Jedes weitere Feld, also auch Autoren, Jahr oder Venue, macht die
  Antwort ungültig. Validiert wird **einzeln**: Eine ungültige Zeile verwirft nur sich selbst.
  Kennungen werden über das bestehende `online.references.normalize_identifier` gedeutet.
- **Import:**
  - Die Antwort wird **unverändert** unter `metadata/llm_answers/<Zeitstempel>.json` abgelegt,
    weil sie nicht rekonstruierbar ist (Sicherungsumfang, siehe unten).
  - Jeder Vorschlag wird über `resolve_target` aufgelöst. `identifier_backed` ist dabei `False`,
    denn eine vorgeschlagene Kennung ist nicht lokal belegt.
  - Übernommen wird **ausschließlich**, was der Seite-1-Beleg bestätigt. Der Beleg nennt den
    Vorschlag (`Vorschlag Arbeitsliste <Zeitstempel> (doi:…)`), die Herkunft bleibt `resolved`.
  - Ein fremder Vorschlag wird verworfen und vermerkt.
  - `--dry-run` prüft nur das Format und erzeugt keinen Client.
- **Status:** `markieren <paper_id> --grund …` setzt `unresolvable`; `--aufheben` löscht ihn. Das
  ist eine menschliche Entscheidung, kein LLM-Schritt.
- **`manual` bleibt menschlich.** Korrekturen ohne Quelle laufen über `correct_paper_metadata`,
  nach Freigabe des Nutzers je Charge. Falsche Felder niedrigerer Herkunft werden dabei über
  `clear_fields` geleert ([ADR 0040](0040-explicit-field-clearing.md)).

### 8. Ausgewiesener Status bis in die Werkzeuge

- **Index:** Das Teilschema `paper_metadata` steigt auf **0.3.0** (Spalte `review`).
- **Ausgabe:** `PaperMetadata.to_dict` liefert additiv `review` (`null` oder `{status, reason}`).
- **Spezifikationen:** `get_reference` 0.2.0 → 0.3.0, `get_paper` 0.3.0 → 0.4.0,
  `answer_question` 0.3.0 → 0.4.0.
- **Wirkung:** Ein Agent sieht bei einer schwachen Angabe damit, ob sie ausdrücklich als nicht
  auflösbar ausgewiesen ist.

### 9. Protokoll und Sicherung

- **Protokoll:** Triage und Import schreiben in dasselbe append-only Protokoll
  `data/metadata_log.md` wie der Auflösungslauf (`append_metadata_section`). Der Auflösungslauf
  weist verworfene Treffer mit Grund aus. Jede Aufwertung steht dort mit ihrem Beleg.
- **Sicherung:** `metadata/llm_answers/` kommt in den Sicherungsumfang
  ([ADR 0027](0027-corpus-backup-phase11.md), Nachtrag). `metadata/paper_metadata.json` mit den
  Vermerken war bereits enthalten.

## Alternativen

- **Ablehnung schon, wenn nur der Titel fehlt** (wörtlich A1, Punkt 2). Verworfen: Die Planung
  zählte 7 Fälle mit fehlendem Titel, aber vorhandenen Autoren. Eine falsche Ablehnung sperrt den
  richtigen Treffer dauerhaft. Die zweite Bedingung kostet nichts, und ihre Schwelle wird wie die
  der Aufwertung kalibriert.
- **Schwellen jetzt schätzen** (etwa 0,5 aus der Planungsheuristik). Verworfen: Das wäre genau die
  unbelegte Zahl, die die Roadmap ausschließt. Ein fälschlich `strong` ist schlimmer als ein
  ehrliches `weak`.
- **Vermerke in einer eigenen Datei.** Verworfen: Das hätte keinen atomaren Zusammenhang mit dem
  Entfernen des Datensatzes (siehe Entscheidung 4), und der Sicherungsumfang würde breiter.
- **Das LLM liefert die Metadaten direkt.** Verworfen durch die Festlegung „Das LLM schlägt vor,
  das Skript prüft“ und durch „Bewusst ausgeschlossen: Metadatenwerte, die ein LLM schreibt“.
- **LLM-Entscheidungen als `manual`.** Verworfen: Das würde eine menschliche Prüfung behaupten,
  die nicht stattfand.
- **Die Arbeitsliste als MCP-Werkzeug.** Verworfen wie in ADR 0026: Der Lauf ist schreibend und
  netzgebunden und gehört nicht in Agent-Reichweite.

## Konsequenzen

- **Positiv:**
  - Die Fremd-Paper-Fälle werden erkennbar und nach der Kalibrierung automatisch bereinigt.
  - Die Bereinigung ist stabil gegen Wiedereinspielen.
  - Kein Wert aus einer LLM-Antwort gelangt ungeprüft in die Metadaten.
  - Jeder schwache Datensatz hat einen Ausweg mit ausgewiesenem Ergebnis.
- **Negativ / Aufwand:**
  - Vor der Kalibrierung misst der Lauf nur. Die Akzeptanz „die belegten Fremd-Paper-Fälle
    (VisRAG, AgentBench, MCIP) liefern die korrekte Angabe“ ist deshalb erst **nach** A0, Punkt
    3, und einem Lauf am realen Bestand erfüllt.
  - Der Titel-Mechanismus des Intake verlangt Kandidaten mit mindestens 30 Zeichen und fünf
    Wörtern. Sehr kurze Titel werden deshalb nie bestätigt, sondern bleiben `unconfirmed` und gehen
    in die Arbeitsliste. Diese Grenze wird bewusst mit übernommen („eine Ähnlichkeitslogik“).
- **Folgeentscheidungen:**
  - Nachtrag mit den kalibrierten Werten nach A0, Punkt 3.
  - A2, Punkt 4, nutzt denselben Beleg für jeden neuen Treffer. Damit entstehen keine neuen `weak`
    mehr unbemerkt.
