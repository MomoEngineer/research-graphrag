# 0026 – Online-Auflösung der Zitationsdaten: automatisch, aber belegt

- **Status:** Akzeptiert
- **Datum:** 2026-08-05

## Kontext

[ADR 0025](0025-citable-paper-metadata.md) hat die Herkünfte, die Auflösungsregel und die
Durchreichung geschaffen – aber eine Lücke offen gelassen: Lokal sind **Autoren**, **Venue** und
der **Publikationsjahrgang** schlicht nicht vorhanden. Aus dem PDF-Text sind sie nicht
zuverlässig zu gewinnen (das wäre GROBID, siehe [ADR 0005](0005-graphrag-index-backend-open.md)),
und die kuratierte Übersicht kennt nur den Identifikator. Ohne diese Felder bleibt jede
Literaturangabe unvollständig – `is_citable()` liefert `false`, und der Nutzer müsste die Angabe
doch wieder von Hand bauen.

Die Vorgabe lautete deshalb: **Die Auflösung soll automatisch passieren**, damit niemand die
Zitation manuell zusammensetzen muss.

### Was bereits vorhanden ist

[ADR 0020](0020-online-candidate-search-phase9.md) hat für die Kandidatensuche das Paket
`online/` mit genau den Bausteinen gebaut, die hier gebraucht werden: einen **injizierbaren
Transport-Port** (`HttpClient`), den Proxy-/SSPI-Tunnel, die TLS-Verifikation über `certifi`, die
Entschärfung fremder Zeichenketten und die Rohantwort-Ablage. Gemessen wurde dort außerdem, dass
**OpenAlex** genau die fehlenden Felder liefert (Autoren, Jahr, Venue, DOI, OA-Link) und arXiv
Titel und Abstract, aber weder Lizenz noch DOI.

## Entscheidung

### 1. Ein eigener, manuell gestarteter Lauf – nicht der Ingest

`python -m scripts.resolve_metadata` ist ein **separates** Kommando, wie
`python -m scripts.discover`. Der Ingest bleibt **netzfrei und deterministisch**: Ein HTTP-Aufruf
in `pipeline.ingest` würde jeden Index-Bau proxy- und verfügbarkeitsabhängig machen und den
Byte-Vergleich zerstören, mit dem in [ADR 0013](0013-chunking-refinement-phase7.md) und
[ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md) jede Änderung abgesichert wurde.

Der Lauf schreibt ausschließlich nach `metadata/paper_metadata.json`; wirksam wird das Ergebnis
beim nächsten `python -m scripts.ingest`. Damit bleibt die Kette **Netz → Datei → Index**
einseitig gerichtet und jederzeit nachvollziehbar.

### 2. Automatische Übernahme – mit ausgewiesener Belegstärke

Die Frage war „Vorschlag oder Automatik?". Beides zugleich ist möglich, wenn nicht die
*Übernahme*, sondern die *Belegstärke* differenziert wird:

| Beleg | Konfidenz | Konsequenz |
| --- | --- | --- |
| Treffer über die **eigene, frontmatter-belegte** DOI/arXiv-ID | `strong` | wird übernommen |
| Treffer über eine **nicht** belegte oder mehrdeutige ID | `weak` | wird übernommen, im Bericht markiert |
| Titel-Suche, Ähnlichkeit ≥ `TITLE_SIMILARITY` (0,85) | `weak` | wird übernommen, im Bericht markiert |
| Titel-Suche darunter | – | **verworfen** |

Übernommen wird also immer, wenn ein Beleg existiert – der Nutzer muss nichts bestätigen. Was
nicht eindeutig belegt ist, trägt jedoch `confidence = weak` bis in `get_reference` hinein und
steht im Bericht. Die Schwelle 0,85 wird **nicht** neu erfunden: Sie ist dieselbe, die
[ADR 0019](0019-corpus-intake-new-papers-phase8.md) am realen Korpus kalibriert hat (22 von 25
umbenannten Papern erkannt, **0** falsche Ziele).

Der letzte Schutz ist die Auflösungsregel aus [ADR 0025](0025-citable-paper-metadata.md): `manual`
und `curated` stehen **über** `resolved`. Eine automatische Auflösung kann kuratierte Wahrheit
also nicht überschreiben – sie füllt nur Lücken.

### 3. OpenAlex als Quelle, arXiv als Rückfall

OpenAlex wird zuerst befragt, weil nur dort **Autoren und Venue** vorliegen. Führt das zu keinem
Treffer und ist eine arXiv-ID bekannt, liefert der arXiv-Feed wenigstens Titel, Autoren und das
Preprint-Jahr. Crossref bleibt außen vor: gemessen schlechteres Ranking, Abstract nur in einem
Drittel der Fälle, zusätzliche Ratenbegrenzung – für den Zugewinn zu teuer.

Der **Identifikator-Weg hat Vorrang vor der Titel-Suche**: Eine ID-Abfrage ist eindeutig, eine
Titel-Suche ist eine Ähnlichkeitsaussage.

> **Nachtrag (2026-08-10): Der arXiv-Rückfall war wirkungslos – behoben.** Er rief den Feed über
> `search_query=all:"<id>"` ab. Diese Suche geht in den **Volltext**, nicht in die Kennung; in
> Phase 13 / R1 lieferte sie für `1706.03762` das fremde Werk `2002.05202`
> ([ADR 0029](0029-reference-stub-resolution-phase13.md)). Die ID-Prüfung dieses Moduls hat solche
> Fehlgriffe zwar stets verworfen – es entstand also **nie ein falscher Datensatz** –, aber der
> Rückfall griff dadurch praktisch nie. Zusätzlich setzte er `authors=()` hart, obwohl der Feed die
> Autoren nennt. Beides ist jetzt behoben: Abfrage über `fetch_arxiv_by_id` (`id_list`), Autoren
> über `authors_from_feed`. Betroffen waren am realen Korpus **10** von 373 Papern, bei denen
> ausschließlich die Autoren fehlten. Zwei Regressionstests halten den Fall fest: Die URL muss
> `id_list` enthalten und darf **kein** `search_query` tragen, und die Autoren müssen ankommen.
> Kein Schema-Eingriff, keine Baseline berührt – die Auflösung ist ein separater Lauf.

### 4. Schonender Umgang mit fremden Diensten

Standardmäßig werden nur Paper angefragt, deren Datensatz **unvollständig** ist
(`--alle` erzwingt den Rest). `--limit` deckelt die Zahl der Anfragen je Lauf; der Default
(50) bleibt deutlich unter dem gemessenen OpenAlex-Kontingent. `--dry-run` zeigt die Auswahl,
**ohne** eine Verbindung zu öffnen – dasselbe Muster wie bei `scripts.discover`.

### 5. Fremde Daten werden entschärft, bevor sie ins Repository gelangen

Titel, Autoren und Venue stammen aus fremden Quellen und landen in einer versionierten Datei und
später in Modell-Prompts. Sie werden deshalb wie in
[ADR 0020](0020-online-candidate-search-phase9.md) bereinigt: Zeilenumbrüche und nicht druckbare
Zeichen entfallen, Längen sind begrenzt, und für den Bericht greift `escape_markdown`. Neu ist
die Begrenzung der **Autorenzahl** – eine Autorenliste mit tausenden Einträgen (real bei
Physik-Kollaborationen) würde die Datei sonst unbrauchbar machen.

## Alternativen

- **Auflösung im Ingest.** Verworfen (Punkt 1): Netzabhängigkeit und Determinismusverlust.
- **Nur Vorschläge, Übernahme per Hand.** Verworfen auf ausdrücklichen Wunsch – der manuelle
  Schritt ist genau das, was entfallen soll. Der Kompromiss ist die ausgewiesene Belegstärke.
- **Crossref oder Semantic Scholar zusätzlich.** Verworfen: Semantic Scholar antwortet ohne Key
  mit HTTP 429 (gemessen), Crossref bringt gegenüber OpenAlex keinen Zugewinn an den hier
  benötigten Feldern.
- **Titel-Suche ohne Mindestähnlichkeit.** Verworfen: Das produziert genau die Art von falscher
  Zuordnung, die eine Literaturangabe wertlos macht.
- **Ein MCP-Werkzeug für die Auflösung.** Verworfen aus demselben Grund wie beim Intake
  ([ADR 0019](0019-corpus-intake-new-papers-phase8.md), §7): Ein Agent ruft Werkzeuge autonom auf;
  ein schreibender Lauf mit Netzzugriff gehört nicht in Agent-Reichweite. Der Server bleibt bei
  **neun** Werkzeugen.

## Konsequenzen

- **Positiv:** Vollständige Literaturangaben ohne Handarbeit; kuratierte Daten bleiben geschützt;
  der netzfreie Kern bleibt unangetastet; jede Übernahme ist mit Quelle, Belegart und Konfidenz
  protokolliert.
- **Negativ / Aufwand:** Ein zwölftes Skript und ein weiteres Modul in `online/`; der Lauf
  benötigt Netz (Proxy) und ist daher nicht Teil der Standard-Kette; schwach belegte Übernahmen
  müssen gelesen werden, wenn Präzision zählt.
- **Bekannte Grenze:** Für Paper ohne Identifikator **und** mit kurzem Titel (gemessen 3 von 341,
  siehe [ADR 0020](0020-online-candidate-search-phase9.md)) bleibt nur die Handpflege über einen
  `manual`-Eintrag.
- **Testgrenze:** `online/transport.py` bleibt die dokumentierte Coverage-Ausnahme; die neue
  Auflösungslogik ist über den injizierten Port **vollständig offline** getestet.

## Nachtrag (2026-09-24, Phase 17 / A1): Seite-1-Beleg als neue Belegklasse

Die Planungsmessung der Phase 17 zeigte, dass `weak` häufig ein **fremdes** Paper verdeckt: Bei
44 von 92 online aufgelösten `weak`-Volltexten stehen weder Titel noch Autoren des Treffers auf
Seite 1. [ADR 0042](0042-title-page-evidence-and-rejections.md) ergänzt die Tabelle aus
Abschnitt 2 um zwei Zeilen:

- Ein Treffer, dessen Titel **und** Autoren auf Seite 1 des lokalen PDFs stehen, wird `strong`.
  Die Herkunft bleibt `resolved`.
- Ein Treffer ohne Titel und ohne (nennenswert) Autoren auf Seite 1 wird verworfen, und ein
  **Ablehnungsvermerk** verhindert das Wiedereinspielen.

Beide Schwellen werden in Phase 17 / A0, Punkt 3, kalibriert. Bis dahin entscheidet der Beleg
nichts, sondern misst nur.
