# 0039 – Korrektur bibliografischer Metadaten & lokaler Datei-Zugriff auf das Original-PDF (erste Schreib-Werkzeuge der MCP-Oberfläche)

- **Status:** Akzeptiert
- **Datum:** 2026-09-17

## Kontext

Bislang sind **alle neun** MCP-Werkzeuge dünne, lesende Wrapper um den deterministischen,
vollständig aus dem Canonical-Bestand neu gebauten Index (`search_*`, `get_paper`,
`get_citations`, `get_reference`, `list_topics`, `answer_question`,
[ADR 0009](0009-mcp-server-stdio-phase5.md)). Zwei neue Bedürfnisse passen in dieses Bild nicht
unverändert:

1. **Fehlerkorrektur.** Ein Agent (Copilot) soll erkannte Fehler in bibliografischen Metadaten
   (Titel, Autoren, Jahr, Venue, DOI/arXiv, URL) selbst korrigieren können, statt den Umweg über
   eine von Hand editierte Datei zu benötigen.
2. **Zugriff auf das Original-PDF.** Ein Agent soll das vollständige, unextrahierte PDF eines
   Papers einsehen können, wenn es lokal vorhanden ist – über das bisherige `snippet`/die
   Chunk-Auszüge hinaus.

Beide Bedürfnisse treffen auf bestehende, bewusst gesetzte Leitplanken:

- **Kein Datei-Pfad als Eingabe.** `get_paper` nimmt ausschließlich eine `paper_id` entgegen,
  nicht weil ein Pfad grundsätzlich verboten wäre, sondern um einen Pfad-Traversal-Vektor
  auszuschließen (ADR 0009, Alternativen). `get_paper` liefert dabei bereits heute `source_uri`
  (eine `file://`-URI) **als Ausgabe** zurück – ein Datei-Pfad ist also bereits Teil des
  Vertrags, nur eben nie als Eingabe.
- **1-MB-Antwortgrenze.** [ADR 0037](0037-mcp-tool-response-size-ceiling.md) misst eine harte,
  vom MCP-Transport durchgesetzte Obergrenze von ~1 MB je Werkzeug-Antwort. Ein reales
  Paper-PDF liegt fast immer deutlich darüber (erst recht Base64-kodiert, +33 % Aufwand) – ein
  Werkzeug, das PDF-Bytes einbettet, wäre für die meisten Paper von vornherein unbenutzbar.
- **Index ist die einzige Lesequelle zur Abfragezeit.** `get_paper`/`get_reference` lesen
  bibliografische Daten ausschließlich aus der im Index gebauten Tabelle `paper_metadata`
  ([indexing/metadata_index.py](../../src/research_graphrag/indexing/metadata_index.py)), **nicht**
  live aus `metadata/paper_metadata.json`. Diese Tabelle entsteht nur bei einem vollen
  `python -m scripts.ingest`/`intake`-Lauf. Das bestehende Skript
  `python -m scripts.resolve_metadata` respektiert das bereits: Es schreibt nach
  `metadata/paper_metadata.json` und weist selbst aus, dass das Ergebnis „wirksam wird beim
  nächsten `python -m scripts.ingest`" ([ADR 0026](0026-online-metadata-resolution.md)).
- **Vier-Herkünfte-Kette.** `metadata/paper_metadata.json` kennt bereits eine Herkunft `manual`
  mit höchstem Vorrang (`manual > curated > resolved > extracted`,
  [ADR 0025](0025-citable-paper-metadata.md)), feldweise aufgelöst
  ([bibliography/resolve.py](../../src/research_graphrag/bibliography/resolve.py)) und atomar/
  deterministisch persistiert ([bibliography/store.py](../../src/research_graphrag/bibliography/store.py)).
  Diese Herkunft wird bisher **nie** programmatisch geschrieben, nur von Hand gepflegt.

## Entscheidung

### 1. `correct_paper_metadata` – schreibt ausschließlich `manual`-Records nach `metadata/paper_metadata.json`

- **Kein neuer Speicherweg.** Das Werkzeug ist ein dünner Aufrufer der bestehenden
  `bibliography.store`-Funktionen (`load_records`, `upsert_records`, `save_records`) und der
  bestehenden `MetadataRecord`/`ORIGIN_MANUAL`-Typen. Es entsteht **keine** neue Datei, kein
  neues Schema.
- **Eingabe:** `paper_id` (Pflicht, muss im Index existieren), `evidence` (Pflicht, nicht-leer –
  handlungsleitender Beleg, wiederverwendet das bestehende `MetadataRecord.evidence`-Feld) sowie
  **je ein optionaler, typisierter Parameter** für jedes Feld aus
  `bibliography.model.METADATA_FIELDS` (`title`, `authors`, `year`, `venue`, `doi`, `arxiv_id`,
  `url`). Bewusst **keine** generische `fields`-Map: explizite, typisierte Parameter geben dem
  aufrufenden Agenten ein selbsterklärendes, stabiles Schema (Präzedenz: jedes bestehende
  Werkzeug nutzt benannte Parameter, nie eine freie Map). Mindestens ein Feld muss gesetzt sein.
- **Feld-Merge statt Ersetzen.** Ein vorhandener `manual`-Record desselben Papers wird vor dem
  Schreiben geladen; nur die übergebenen Felder werden überschrieben, alle anderen bereits
  manuell gesetzten Felder bleiben erhalten. Ohne diesen Merge würde `upsert_records` (das den
  ganzen `(paper_id, "manual")`-Record ersetzt) eine zweite Korrektur an einem anderen Feld die
  erste stillschweigend löschen.
- **Wirkung erst beim nächsten Ingest – und das wird ausgewiesen.** Genau wie
  `resolve_metadata.py` schreibt das Werkzeug nur die JSON-Quelle; die Response nennt das
  Feld `effective_after` mit dem Klartext-Hinweis, dass `get_paper`/`get_reference`/
  `answer_question` die Korrektur erst nach einem `python -m scripts.ingest`-Lauf zeigen. Eine
  direkte Live-Änderung der Index-Tabelle wurde geprüft und verworfen (siehe Alternativen).
- **Append-only Protokoll `data/corrections_log.md`.** Gleiches Format/gleicher
  Anhänge-Mechanismus wie `data/metadata_log.md`/`data/references_log.md`
  (`online.report.append_section`, Byte-erhaltend, atomar über `os.replace`). Jeder Eintrag
  nennt Zeitstempel, `paper_id`, geänderte Felder mit altem und neuem Wert sowie den Beleg – das
  ist die **granulare** Audit-Spur, während der live-Record im JSON nur den aktuellen Stand
  trägt. Zusätzlich ist `metadata/paper_metadata.json` selbst git-versioniert: Jede Korrektur
  erscheint als Diff, bevor Moritz sie committet – dieselbe Nachvollziehbarkeits-Eigenschaft, auf
  der auch die bestehende Herkunftskette beruht.
- **Validierung:** Feldnamen sind auf `METADATA_FIELDS` begrenzt; `year` muss ein plausibles Jahr
  sein (`1000 <= year <= aktuelles Jahr + 1`); Zeichenketten dürfen nach `strip()` nicht leer
  sein; `authors` darf nicht leer sein, wenn übergeben. Verstöße sind `invalid_input`.

### 2. `get_paper_file` – liefert den lokalen Dateipfad, keine Bytes

- **`paper_id` als einzige Eingabe** (kein Pfad-Parameter) – der Pfad-Traversal-Schutz aus
  ADR 0009 bleibt vollständig erhalten, es entsteht kein neuer Angriffsvektor.
- **Ausgabe:** `document_kind`, `available` (bool), `path` (nativer Dateisystem-Pfad, aus der
  bereits vorhandenen `source_uri` über `urllib.request.url2pathname` aufgelöst – kein
  hand-geschriebenes URI-Parsing), `size_bytes`, `reason` (leer, `"reference_only"` oder
  `"file_missing"`) und `note` (Klartext). Es werden **keine** Datei-Bytes übertragen; das Werkzeug
  beantwortet „wo liegt das Original", nicht „hier ist das Original" – der aufrufende Agent
  (GitHub Copilot in VS Code) liest die Datei über sein **eigenes** Dateisystem-Werkzeug weiter.
  Das hält die Antwort im Byte-Bereich der übrigen Katalog-Werkzeuge (nicht bei mehreren MB) und
  bleibt damit konsistent mit ADR 0037, ohne dessen Grenzwerte anzutasten.
- **`document_kind = "reference"` ist kein Fehler.** Ein Referenz-Eintrag hat kein lokales PDF
  (`source_uri` zeigt auf die `*.refjson`-Stub-Datei, nicht auf ein PDF,
  [ADR 0030](0030-reference-entries-in-corpus-phase13.md)). Die Antwort bleibt ein Erfolg mit
  `available = false`, `reason = "reference_only"` und dem etablierten Klartext „Referenz-Eintrag
  ohne Volltext" (wiederverwendet aus [ADR 0031](0031-reference-contract-and-guardrail-phase13.md))
  – dasselbe Prinzip „Abweichung sichtbar machen, nicht als Fehler tarnen" wie beim
  DRIFT-`fallback` oder `list_topics`s `truncated`.
- **Fehlt die Datei trotz `document_kind = "full"`** (z. B. `papers/` extern verschoben – der
  Ordner ist ein nicht versionierter Symlink), ist das **kein** `not_found`, sondern derselbe
  weiche `available = false`-Pfad mit `reason = "file_missing"`: Der Agent bekäme sonst zwei
  unterschiedliche Antwortformen (Erfolg vs. strukturierter Fehler) für denselben Sachverhalt
  „kein Zugriff auf den Inhalt möglich".

## Alternativen

- **Korrekturen als reine Vorschlags-Warteschlange statt Direktschreiben.** Verworfen (mit dem
  Auftraggeber abgestimmt): Für ein persönliches Werkzeug mit einem einzigen Nutzer und
  git-versionierter, diffbarer Zieldatei ist die zusätzliche Freigabe-Stufe ein Aufwand ohne
  proportionalen Sicherheitsgewinn; die Pflichtfelder `evidence` + append-only Protokoll +
  Git-Historie decken denselben Nachvollziehbarkeits-Bedarf ab, den CONTRIBUTING.md fordert.
- **Korrektur sofort wirksam durch Live-Patch der Index-Tabelle `paper_metadata`.** Verworfen:
  Der Index wäre keine deterministisch aus dem Canonical-Bestand + `metadata/paper_metadata.json`
  reproduzierbare Ableitung mehr, sondern trüge eigenen, nicht aus einer Quelle nachvollziehbaren
  Zustand – dieselbe Erwägung, mit der ADR 0009 einen Canonical-Cache-Zugriff für `get_paper`
  bereits verworfen hat („riskiert Divergenz"). Ein Re-Ingest ist mit `python -m scripts.ingest`
  ohnehin ein einziger Befehl.
- **Freie `fields`-Map statt benannter Parameter bei `correct_paper_metadata`.** Verworfen:
  bricht mit dem Schema-Stil aller bestehenden Werkzeuge und verlangt vom Agenten, Feldnamen als
  Strings zu kennen statt sie aus dem Tool-Schema abzulesen.
- **PDF-Bytes Base64-kodiert in der Tool-Antwort.** Verworfen (ADR 0037): kollidiert nachweislich
  mit der 1-MB-Grenze bei den meisten realen Papern.
- **Bereitstellung über MCP „Resources" statt Tool-Antwort.** Zurückgestellt: ungemessen, ob
  dasselbe Transport-Limit dort ebenfalls greift; ein Pfad-Rückgabe-Werkzeug löst das Bedürfnis
  ohne dieses offene Risiko und ohne neue Protokoll-Mechanik im Server.
- **`correct_paper_metadata` erlaubt auch Korrekturen an extrahiertem Volltext/Chunk-Text.**
  Bewusst **nicht** Teil dieses ADR (Scope-Entscheidung mit dem Auftraggeber): Der Index wird bei
  jedem Ingest voll aus dem Canonical-Bestand neu gebaut; eine überdauernde Korrektur bräuchte
  eine neue Overlay-Schicht in der Extraktions-/Ingestion-Pipeline, keine MCP-Werkzeug-Frage.
  Bleibt als möglicher, eigenständiger Folge-ADR offen.
- **Kuratierungsurteil (`metadata/curation.json`) korrigierbar machen.** Verworfen: seit
  [ADR 0034](0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md) bewusst eingefroren
  („bekommt keine neuen Zeilen mehr").

## Konsequenzen

- **Positiv:** Beide Werkzeuge sind dünne Wrapper um bereits getestete, bestehende Bausteine
  (`bibliography.store`, `online.report.append_section`, `source_uri`); kein neues Speicherformat,
  keine neue Fehlerkategorie, kein neuer Pfad-Traversal-Vektor. Die Korrektur bleibt über
  Git-Historie **und** append-only Protokoll doppelt nachvollziehbar. Der PDF-Zugriff bleibt weit
  unter der 1-MB-Grenze, unabhängig von der tatsächlichen PDF-Größe.
- **Negativ / Aufwand:** `correct_paper_metadata` ist das **erste** Schreib-Werkzeug der
  MCP-Oberfläche – ein Präzedenzfall, den künftige Werkzeuge gegen dieses ADR abgleichen sollten.
  Die Wirkung einer Korrektur ist nicht sofort sichtbar (erst nach dem nächsten Ingest); das muss
  jede Tool-Beschreibung/Antwort klar ausweisen, sonst wirkt das Werkzeug fälschlich synchron.
  `get_paper_file` liefert bewusst keinen Inhalt – ein MCP-Client ohne eigenen
  Dateisystem-Zugriff (heute: nicht der Fall, Copilot läuft in VS Code) könnte das Werkzeug nicht
  sinnvoll nutzen.
- **Folgeentscheidungen:** Eine Korrektur-Fähigkeit für extrahierten Volltext/Chunk-Text bleibt
  ein offener, eigenständiger Folge-ADR. Eine Live-Wirkung ohne Re-Ingest wäre ebenfalls ein
  eigener, separat zu rechtfertigender Bruch mit „Index als einzige Lesequelle".

## Nachtrag (2026-09-19)

Die in Abschnitt 5 dieser Entscheidung genannte Grenze *„Kein Zurücksetzen/Löschen eines Feldes
auf dieser Schnittstelle […] Ein vollständiger Rückbau bleibt der Handbearbeitung von
`metadata/paper_metadata.json` vorbehalten"* wird durch
[ADR 0040](0040-explicit-field-clearing.md) **aufgehoben**: `correct_paper_metadata` erlaubt
seither über den Parameter `clear_fields`, ein Feld ausdrücklich als leer zu bestätigen (statt
nur „nie gesetzt"), ohne die versionierte Datei von Hand zu editieren.

## Nachtrag (2026-09-19, zweiter Eintrag): Drei Härtungen nach einem nicht-diagnostizierbaren `correct_paper_metadata`-Fehler

Ein Aufruf schlug zweimal mit dem generischen `internal_error` aus `mcp_server.server._guard`
fehl (dessen Text bewusst keine Details preisgibt, siehe dessen Modul-Doku), ohne dass der
aufrufende Client (Claude Code) den zugrunde liegenden Fehler erkennen konnte. Die Untersuchung
(isolierte Reproduktion der exakten Nutzlast gegen den echten Index, sowie ein direkter
MCP-Client-Test des Servers **ohne** `cwd`) deckte drei unabhängige Schwachstellen auf, von denen
mindestens die erste am wahrscheinlichsten zutraf:

1. **`.mcp.json` (Claude Code) setzte `RESEARCH_GRAPHRAG_METADATA`/`_DATA` nicht.** Anders als
   `.vscode/mcp.json` kennt Claude Codes `mcpServers`-Schema kein `cwd`-Feld (bestätigt gegen die
   offizielle Claude-Code-Dokumentation) – der Serverprozess erbt daher das Arbeitsverzeichnis des
   aufrufenden Claude-Code-Prozesses, nicht notwendig die Repository-Wurzel. Mit nur
   `RESEARCH_GRAPHRAG_INDEX` explizit gesetzt (absolut, daher unempfindlich gegen die cwd)
   funktionierten alle lesenden Werkzeuge anstandslos, während `correct_paper_metadata` über die
   cwd-relativen Defaults von `RESEARCH_GRAPHRAG_METADATA`/`_DATA`
   (`metadata/paper_metadata.json` bzw. `data`) **in ein anderes Verzeichnis schrieb** – im
   günstigen Fall silent (neue Ordner an falscher Stelle, reproduziert), im ungünstigen Fall mit
   einem `OSError` (z. B. ein nicht anlegbares Verzeichnis), der bis zu dieser Härtung nicht von
   der generischen `internal_error`-Meldung unterschieden werden konnte. **Fix:** `.mcp.json`
   setzt jetzt alle drei Umgebungsvariablen explizit und absolut
   (`${CLAUDE_PROJECT_DIR}`-basiert), symmetrisch zum bereits gesetzten
   `RESEARCH_GRAPHRAG_INDEX`.
2. **OS-Lese-/Schreibfehler in `apply_manual_correction` wurden nicht anerkannt, sondern
   generisch maskiert.** Anders als der bereits bestehende Lesepfad an anderer Stelle im System
   (`extraction.pdf.extract_pdf` fängt `OSError` gezielt ab und liefert `internal_error` **mit**
   Exception-Text) hatte `apply_manual_correction` keine eigene Behandlung für `OSError` an
   seinen **drei** Datei-Zugriffsstellen: dem `load_records`-Aufruf vor dem Merge (liest den
   bestehenden `manual`-Record) sowie den beiden Schreibzugriffen
   (`store.save_records`/`online.report.append_section`) – ein Fehler an jeder dieser Stellen
   fiel durch bis zum generischen Catch-all in `_guard`, dessen Meldungstext bewusst keine
   Details trägt (Begründung: ein **unerwarteter** Programmfehler könnte beliebige interne
   Zustände preisgeben). Ein OS-Lese-/Schreibfehler ist dagegen ein **erwarteter**, benannter Fall
   (Sperre, Rechte, fehlendes Verzeichnis) – **Fix:** `apply_manual_correction` fängt `OSError` an
   allen drei Stellen gezielt ab und liefert `internal_error` mit Exception-Typ, Exception-Text
   und dem betroffenen Pfad in `details` (Analogie zu `extract_pdf`); `_guards` generische
   Absicherung für wirklich unvorhergesehene Fehler bleibt bewusst unverändert.
3. **Zwei fast gleichzeitige Schreibversuche teilten sich denselben Temporärpfad – und selbst mit
   eindeutigem Pfad kann `os.replace` auf dieselbe Zieldatei transient scheitern.**
   `store.save_records` und `online.report.append_section` nutzten je einen festen
   `<name>.tmp`-Pfad. Schickt ein Client zwei `correct_paper_metadata`-Aufrufe ohne Warten auf die
   erste Antwort ab (technisch möglich, MCP serialisiert das nicht), können zwei nahezu
   gleichzeitige Schreibversuche denselben Temporärpfad treffen: Der zuerst fertige
   `os.replace()` verschiebt ihn weg, der zweite `os.replace()` träfe dann ins Leere
   (`FileNotFoundError`) – wieder nur als generischer `internal_error` sichtbar gewesen. Eine
   Nachmessung mit acht parallelen Schreibversuchen auf **eine** eindeutige Temporärdatei je
   Aufruf zeigte zusätzlich: Das allein genügt nicht – zwei nahezu gleichzeitige `os.replace`-
   Aufrufe auf **dieselbe Zieldatei** scheiterten reproduzierbar bei 2–4 von 8 Versuchen mit
   `PermissionError` (`[WinError 5]`), weil ein anderer, ebenfalls gerade ersetzender Aufruf die
   Zieldatei im selben Moment kurz hält. **Fix:** Ein neues, geteiltes Modul
   [`atomic_write.py`](../../src/research_graphrag/atomic_write.py)
   (Modul-Doku: [`atomic_write.md`](../../src/research_graphrag/doc/atomic_write.md)) bündelt für
   beide Funktionen eine **eindeutige** Temporärdatei je Aufruf (`tempfile.mkstemp`, schließt die
   `FileNotFoundError`) **und** einen knappen Retry auf genau diese `PermissionError`
   (5 Versuche, 50 ms Abstand). Eine erweiterte Messung (16/32/50/100 parallele Schreibversuche)
   zeigt die Grenze dieses Retries ehrlich: 0 Fehlschläge bis 32, 1 von 50, 7 von 100 – für den
   tatsächlichen Anwendungsfall (wenige, nicht Dutzende gleichzeitige Aufrufe eines einzigen
   MCP-Clients) reichlich bemessen, aber bewusst **kein** unbedingtes Versprechen. Bleiben die
   Versuche erschöpft, greift weiterhin Fix (2): eine diagnostizierbare `internal_error`-Meldung
   statt eines stillen oder nichtssagenden Fehlers. Das bereits dokumentierte, akzeptierte
   „letzter gewinnt"-Verhalten bei echten inhaltlichen Konflikten (kein Lock über den ganzen
   Lade-Merge-Schreib-Zyklus, siehe
   [`store.md`](../../src/research_graphrag/bibliography/doc/store.md), Abschnitt 7) ändert sich
   dadurch **nicht** – behoben ist der Absturz, nicht das Nebenläufigkeits-Update.

Welche der drei Ursachen den ursprünglichen Fehlerbericht auslöste, ließ sich ohne den echten
Server-Traceback zum Zeitpunkt des Vorfalls nicht mehr abschließend zurückverfolgen (stderr-Log
lag nicht vor) – (1) ist am plausibelsten, weil sie als einzige beide beobachteten Aufrufe (zwei
verschiedene `paper_id`s, gleicher generischer Fehler) ohne Sonderannahme erklärt; (3) ist am
solidesten **empirisch belegt**, weil die `PermissionError`-Rennbedingung reproduzierbar gemessen
wurde, statt nur plausibel zu sein. Alle drei Fixes sind unabhängig voneinander korrekt und werden
deshalb gemeinsam übernommen; (2) macht jeden künftigen Fall dieser Art beim nächsten Auftreten
selbst-diagnostizierend.

**Abschließend verifiziert:** Nach allen drei Fixes wurden exakt die beiden ursprünglich
fehlgeschlagenen Nutzlasten (Paper `396a0fadeb4cd40f`, `730f1a9f38d16689`) end-to-end gegen einen
echten, per `stdio` gestarteten Serverprozess ohne `cwd` (wie unter (1) beschrieben) erneut
gesendet – gegen eine isolierte Kopie von `metadata/paper_metadata.json`/`data/`, nicht gegen den
Produktivbestand. Beide Aufrufe liefern jetzt `isError = false` mit den erwarteten
`applied_fields` und einem Protokoll-Eintrag in `corrections_log.md`.

## Nachtrag (2026-09-23): Rückfall trotz aller drei Härtungen – vierte, bisher übersehene Stelle ohne Retry

Zwei weitere `correct_paper_metadata`-Aufrufe (Paper `228ab36678b84808`, `1368b41612825326`)
scheiterten erneut, diesmal aber **nicht** mehr am generischen `internal_error` aus `_guard` –
Härtung (2) griff wie vorgesehen und lieferte den vollen Exception-Text:

```
error.message: Korrektur nicht speicherbar (PermissionError): [WinError 5] Zugriff verweigert: 'metadata'
error.details: { "metadata_path": "metadata\\paper_metadata.json" }
```

Zwei Beobachtungen grenzten die Ursache sofort ein:

- Die Meldung nennt **einen** Pfad (`'metadata'`), nicht ein `'quelle' -> 'ziel'`-Paar. `os.replace`
  liefert bei einem Fehler immer beide Pfade – die fehlgeschlagene Operation konnte also nicht
  `os.replace` sein, sondern nur ein Aufruf mit einem einzelnen Pfadargument.
- Der genannte Pfad ist der **bare** Ordnername `metadata`, nicht der volle, konfigurierte Pfad aus
  `metadata_path` in `error.details`. Das passt exakt zu `Path("metadata").parent` aus
  `store.save_records`, das per `Path(path).parent.mkdir(parents=True, exist_ok=True)` – **ohne**
  jeden Retry – aufgerufen wird.

Der zeitliche Zusammenhang bestätigte den Verdacht: Kurz vor den beiden Aufrufen war `metadata/`
lokal von einem versionierten Ordner auf eine NTFS-Junction auf ein externes Datenverzeichnis
umgestellt worden (derselbe Schritt, mit dem `data/` und `papers/` bereits am 2026-09-01
umgestellt wurden; Commit „Refactor code structure for improved readability and maintainability“,
2026-09-21). `Path.mkdir(exist_ok=True)` schluckt eine `OSError` beim Anlegen nur, wenn der
anschließende `is_dir()`-Check im selben Moment ebenfalls erfolgreich ist (CPython-Quelle,
`pathlib.py`); bei einem frisch eingerichteten Verzeichnis – ob Junction oder gerade erst
angelegter Ordner – können beide Schritte im selben kurzen Fenster scheitern, sodass die
`PermissionError` unverändert durchschlägt. Ein direkter Nachbau des Round-Trips
(`load_records`/`save_records` gegen die reale, inzwischen eingerichtete Junction) lief zum
Diagnosezeitpunkt bereits wieder fehlerfrei – die Bedingung ist folgerichtig transient (dasselbe
Muster wie die bereits gemessene `os.replace`-Rennbedingung aus Härtung (3)), nicht dauerhaft
falsch konfiguriert.

**Root Cause:** Härtung (3) (2026-09-19) fügte den `PermissionError`-Retry ausschließlich für
`os.replace` ein. `store.save_records` und `online.report.append_section` legten ihren Zielordner
aber weiterhin **je selbst**, über eine eigene, ungeschützte `Path.mkdir(parents=True,
exist_ok=True)`-Kopie – genau die Art doppelten, unabgestimmten Codes, die
[`atomic_write.py`](../../src/research_graphrag/atomic_write.py) laut eigener Modul-Doku eigentlich
vermeiden sollte. Der Retry deckte damit nur eine von zwei Stellen ab, die denselben,
gemessenen Windows-Fehlertyp auslösen können.

**Fix:** `atomic_write_bytes` legt den Elternordner jetzt selbst an (`os.makedirs(...,
exist_ok=True)`), mit demselben Retry-Mechanismus wie `os.replace` (Konstanten vereinheitlicht zu
`_PERMISSION_RETRY_ATTEMPTS`/`_PERMISSION_RETRY_SECONDS`, Modul-Doku
[`atomic_write.md`](../../src/research_graphrag/doc/atomic_write.md), Abschnitt „Warum zusätzlich
ein Retry auf `os.makedirs`“). `store.save_records` und `report.append_section` verloren dadurch
ihre je eigene `mkdir`-Zeile ersatzlos – der Vertrag „Elternordner muss bereits existieren“ aus
`atomic_write_bytes`s früherer Docstring-Fassung entfällt. Tests
(`tests/test_atomic_write.py::test_retries_mkdir_on_permission_error_then_succeeds`,
`::test_raises_after_exhausting_mkdir_retries`, `::test_creates_missing_parent_directories`)
belegen Retry, Erschöpfung und das (neue) automatische Anlegen fehlender, auch mehrstufiger
Elternordner.

Damit sind jetzt **alle** Stellen, an denen `store.save_records`/`report.append_section`
`OSError` auslösen können (Ordner anlegen, Temporärdatei schreiben, Zieldatei ersetzen), hinter
demselben, einmal gemessenen Retry versammelt – eine erneute Divergenz wie bei diesem Rückfall ist
strukturell ausgeschlossen, weil es nur noch eine Kopie der Logik gibt.

**Betroffene, weiterhin ausstehende Korrekturen:** `228ab36678b84808` (Neuidentifikation am
Volltext nötig, siehe Fehlerprotokoll) und `1368b41612825326` (Venue-Ergänzung, Autoren noch nicht
verifiziert) sind durch diesen Fix **nicht** automatisch erneut ausgeführt worden – das sind
inhaltliche Recherche-Aufgaben am jeweiligen Volltext, keine Bug-Fixes, und bleiben bewusst
offen für einen eigenen Aufruf von `correct_paper_metadata`, sobald der MCP-Server verbunden ist.
