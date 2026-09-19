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
