# 0033 – Antwortzeit ohne Neubau des Vektorraums (Prozess-Cache + persistierter TF-IDF-Zustand)

- **Status:** Akzeptiert
- **Datum:** 2026-09-01

## Kontext

[G0.6](../roadmap-historie.md#g0--alles-hinterfragen-und-messen-zwingend-zuerst) hat gemessen: Jeder
Aufruf von `TfidfIndex.load()` fittet `CountVectorizer` und `TfidfTransformer` **neu** aus den in
SQLite gespeicherten Chunk-Texten – bei jeder einzelnen Anfrage, unabhängig davon, ob sich der
Index seit dem letzten Aufruf verändert hat. Bei 606 Papern/42.388 Chunks kostet allein dieser
Neubau spürbare Zeit; die verschärfte Nutzervorgabe (2026-09-01) verlangt **< 1 s warm im
MCP-Server** – eine engere Marke als die ursprüngliche 5-Sekunden-Grenze des kalten CLI-Pfads.

G0.6 hat zusätzlich festgehalten, dass die **warme** Suchzeit selbst nicht konstant ist: Basic
Search bewertet strukturell jeden Chunk (Kosinus/BM25 über die volle Matrix), wächst also mit dem
Korpus. Ein Prozess-Cache (**Weg C**) beseitigt nur den *Neubau*-Anteil, nicht diesen
strukturellen Anteil – und war deshalb als *notwendig, aber nicht automatisch hinreichend*
eingestuft, mit einer gestaffelten Regel: Weg B (FTS5) nur bauen, wenn Weg C allein die 1-s-Marke
nicht hält.

Drei Stellen im heutigen Code widersprechen zusätzlich der Nutzervorgabe unabhängig vom Cache:

1. **Jeder Chunk-Text liegt vollständig im Speicher** (`_ChunkRef.text`), obwohl für die Wertung
   nur Kennungen und Gewichte gebraucht werden ([G0.0](../roadmap-historie.md#g00--die-vorgaben-dieser-phase-auf-den-prüfstand-stellen) Punkt 1 vermutete
   diesen Speicheranteil als unterschätzt).
2. Ein Prozess-Cache darf die **On-Read-Frische** nicht brechen: Ein nach dem Laden neu gebauter
   Index (atomarer Swap via `os.replace`, [ADR 0010](0010-drop-in-workflow-and-qa-phase6.md))
   muss beim nächsten Aufruf weiterhin ohne Server-Neustart wirken.
3. [ADR 0005](0005-graphrag-index-backend-open.md) hat SQLite explizit **ohne** persistierten
   Vektorisierer-Zustand entworfen, mit der Begründung, kein `pickle`/keine Versionskopplung an
   `scikit-learn`-Objekte einzugehen. Diese Begründung steht einem persistierten TF-IDF-Zustand
   nicht grundsätzlich entgegen – sie richtet sich gegen das *Pickeln von Objekten*, nicht gegen
   das Persistieren von *reinen Zahlen* (Vokabular als JSON, Zähl-Matrix als Rohbytes). Das war
   in ADR 0005 nicht ausgesprochen und wird hier präzisiert.

## Entscheidung

### 1. Weg A + Weg C, gebaut wie im Statusblock vorgesehen – Weg B (FTS5) zurückgestellt

**Gewählt: Weg A (persistierter Vokabular-/Zähl-Zustand) + Weg C (Prozess-Cache).** Weg B nicht
gebaut. Begründung mit Zahlen (gemessen auf dem realen Korpus, 606 Paper/42.388 Chunks, siehe
Statusblock zu G2 in Roadmap.md):

| Messung | Ergebnis |
| --- | --- |
| Kalt (CLI, echter Prozessstart, `--mode basic`) | 3,69 s / 3,71 s / 3,96 s (3 Wiederholungen) |
| Warm (Cache-Hit, `TfidfIndex.load(...).search(...)`, 20 Anfragen) | Median 0,169 s, Max 0,227 s |
| Cache-Miss innerhalb eines laufenden Prozesses (Neubau nach Rebuild) | 0,927 s |

Die warme Marke liegt mit knapp einer Größenordnung Marge unter der 1-s-Vorgabe. Die
gestaffelte Regel aus G0.6 (*Weg B nur, wenn Weg C allein nicht reicht*) greift damit **nicht** –
Weg B wird nicht gebaut. Das ist an dieser Korpusgröße keine Ermessensfrage, sondern die
gemessene Konsequenz: Der Neubau-Anteil (vormals der dominante Kostenblock) entfällt durch Weg A
vollständig aus dem warmen Pfad; was bleibt, ist der strukturelle, mit dem Korpus wachsende Such-
Anteil (Kosinus/BM25 über die volle Matrix), der bei 606 Papern noch weit unter der Marke liegt.

**Auslöser für eine Revision:** Wächst der Korpus deutlich über die heutige Größenordnung (grobe
Anhaltszahl: **~1.500–2.000 Paper**, das 3–5-Fache des heutigen Standes) und rückt die warme
Suchzeit dadurch wieder an die 1-s-Marke heran, ist Weg B erneut zu prüfen – mit derselben
Messdisziplin wie hier, nicht vorsorglich.

### 2. Additive Schema-Erweiterung statt Migration (`0.5.0 -> 0.6.0`)

Neue Tabelle `tfidf_state` (eine Zeile, `id = 0`): `n_docs`, `n_features`, `vocabulary` (JSON,
Term -> Spaltenindex, `int`), `counts_data`/`counts_indices`/`counts_indptr` (CSR-Rohbytes,
fester Speichertyp `int64` – unabhängig von der internen Laufzeit-Dtype-Wahl von
`scikit-learn`/`scipy`, die sich zwischen Versionen ändern kann). `build_index()` fittet
`CountVectorizer` **einmal** und persistiert Vokabular und Zähl-Matrix zusätzlich zu den
unveränderten `papers`/`chunks`-Tabellen. Kein Migrationscode: Ein voller Re-Index (Standard des
Projekts, siehe Roadmap.md) genügt; ein Index ohne `tfidf_state` (Vor-G2-Schema) liefert beim
Laden `constraint_violation` statt eines stillen Fallbacks.

**Präzisierung von ADR 0005:** *Nichts wird als Objekt serialisiert* – das gilt weiterhin und
unverändert (kein `pickle`, keine Versionskopplung an eine `scikit-learn`-Objektform). Persistiert
werden ausschließlich **plattform- und versionsunabhängige Zahlen und Zeichenketten** (JSON,
Rohbytes fester Breite), aus denen `CountVectorizer(vocabulary=…).fit([])` und
`TfidfTransformer().fit_transform(counts)` beim Laden denselben Bewertungsraum **rekonstruieren**,
den ein frischer Fit über dieselben Texte ergäbe – nur ohne die Tokenisierung selbst zu
wiederholen. Der byte-genaue Nachweis (Alt-Vokabular/Zähl-Matrix aus frischem Fit **gegen** die
persistierte, deserialisierte Fassung) steht im G2-Statusblock der Roadmap.

### 3. Prozess-Cache über den Dateizustand, nie über eine Zeitspanne

`TfidfIndex.load()` cacht pro **aufgelöstem Pfad** ein fertiges `TfidfIndex`-Objekt, geschlüsselt
über `(mtime_ns, Dateigröße)` des jeweils zuletzt gesehenen Zustands (`threading.Lock`-geschützt,
Prozess-weit gültig). Ein Treffer wird **nur** zurückgegeben, wenn beide Werte mit dem aktuellen
`stat()` übereinstimmen; sonst wird `_build_from_db` erneut ausgeführt und der Cache-Eintrag
ersetzt. Das erfüllt die On-Read-Frische wörtlich: Ein atomarer Swap (`os.replace`) ändert immer
mindestens die Dateigröße (neuer Inhalt) und in der Praxis auch die Änderungszeit – der nächste
Aufruf sieht den neuen Stand, ohne Serverneustart und ohne eine Zeitspanne abzuwarten. Regressions-
test: `test_load_reloads_after_index_rebuilt_at_same_path`
([tests/indexing/test_tfidf_index.py](../../tests/indexing/test_tfidf_index.py)); das bestehende
Phase-6-Freshness-Szenario
([tests/integration/test_phase6_freshness.py](../../tests/integration/test_phase6_freshness.py))
deckt denselben Pfad zusätzlich end-to-end ab.

**Akzeptierter Grenzfall (Mikro-Race):** Zwischen dem `stat()`-Aufruf in `load()` und dem
späteren, verzögerten Nachladen der Chunk-Texte in `search()`/`neighbors_of_chunk()` (siehe unten)
liegt ein Fenster im Mikrosekundenbereich, in dem ein weiterer atomarer Swap theoretisch
dazwischenfunken könnte. Das ist dieselbe Klasse von Grenzfall, die der atomare Swap selbst schon
grundsätzlich in Kauf nimmt (Eventual Consistency statt Sperren), und wird hier bewusst nicht
zusätzlich abgesichert – der Aufwand stünde in keinem Verhältnis zum Risiko.

### 4. Chunk-Texte werden für die Top-*k* nachgeladen, nicht vollständig gehalten

`_ChunkRef` trägt keinen Text mehr; `TfidfIndex._fetch_texts()` lädt die Texte **nur** für die
tatsächlich ausgewählten Top-*k*-Treffer in einer einzigen `IN (...)`-Abfrage nach – in
`search()` und `neighbors_of_chunk()` jeweils nach der Rangbildung, vor dem Aufbau der
`Hit`-Objekte. Das ist unabhängig vom gewählten Weg (A/B/C) und adressiert direkt den in
[G0.0](../roadmap-historie.md#g00--die-vorgaben-dieser-phase-auf-den-prüfstand-stellen) Punkt 1 vermuteten unterschätzten Speicheranteil: Bei Tausenden von
Chunks ist der Volltext der mit Abstand größte, aber für die Wertung ungenutzte Speicheranteil.

## Alternativen

- **Weg B (FTS5) zusätzlich bauen.** Verworfen für diesen Schnitt: Die Messung zeigt, dass Weg
  A + C die 1-s-Marke mit deutlicher Marge einhalten; FTS5 hätte einen Bruch der
  Vergleichbarkeit (andere Tokenisierung/Ranking) samt Neueinfrieren beider Baselines erzwungen,
  ohne dass die Akzeptanzkriterien das heute verlangen. Aufgehoben als klar benannte, an einer
  Korpusgröße festgemachte Revisionsbedingung (siehe oben), statt stillschweigend verworfen.
- **`pickle` des gesamten `CountVectorizer`/`TfidfTransformer`-Objekts statt Rohzahlen.**
  Verworfen: koppelt den Index an eine `scikit-learn`-Version und widerspräche damit dem Kern von
  ADR 0005, den dieses ADR gerade präzisiert statt aufweicht.
  Zeitbasierter TTL-Cache statt Dateizustand. Verworfen: Ein TTL wäre entweder zu kurz (Cache
  nutzlos) oder zu lang (veralteter Index wird ausgeliefert) – die Roadmap verlangt ausdrücklich
  Invalidierung über den Dateizustand, nicht über Zeit.
- **Cache mit LRU-Eviction über mehrere Indexpfade.** Zurückgestellt: In der Praxis läuft ein
  Prozess (MCP-Server oder CLI) über die gesamte Lebensdauer gegen **einen** Indexpfad; eine
  Eviction-Strategie wäre Komplexität ohne beobachtetem Bedarf (YAGNI).

## Konsequenzen

- **Positiv:** Warme Anfragen halten die 1-s-Vorgabe mit großer Marge (Median 0,169 s bei 606
  Papern); On-Read-Frische bleibt wörtlich erhalten; kein Bruch der Vergleichbarkeit (byte-
  identischer Nachweis alt/neu über 130 Prüfungen, siehe G2-Statusblock); geringerer
  Speicherbedarf pro geladenem Index (Chunk-Texte nicht mehr vollständig gehalten).
- **Negativ / Aufwand:** Schema-Anhebung `0.5.0 -> 0.6.0` erzwingt einen vollen Re-Index (keine
  Migration, wie im Projekt Standard); `build_index()` wird geringfügig langsamer (persistiert
  zusätzlich die Zähl-Matrix), was ausschließlich beim *Bau* anfällt, nie beim *Laden*; ein
  Mikro-Race zwischen Cache-Treffer und Text-Nachladen wird bewusst in Kauf genommen (siehe oben).
- **Folgeentscheidungen:** Weg B (FTS5) bleibt eine offene, an einer konkreten Korpusgröße
  festgemachte Option für einen späteren Schnitt, keine automatische Folgearbeit.

## Nachtrag (2026-09-16)

Die hier benannte Revisionsbedingung („~1.500–2.000 Paper") ist eingetreten: Der reale Bestand
liegt bei 3.461 Papern. [ADR 0038](0038-corpus-ceiling-revision-local-search-latency.md) löst die
damit fällige Nachmessung ein – mit ernüchterndem Ergebnis: Der hier gebaute Prozess-Cache (Weg C)
hält die 1-s-Marke für Basic/Global noch (mit stark geschrumpfter Marge), aber nicht mehr für
Local (warmer Median 6,064 s) und nicht mehr für DRIFT (1,722 s). Das bestätigt die hier getroffene
Einschätzung, Weg C sei „notwendig, aber nicht automatisch hinreichend" – am heutigen Bestand ist
er für Local nicht mehr hinreichend. Weg B (FTS5) ist damit von der offenen Option zur empfohlenen
nächsten Phase erhoben (noch nicht umgesetzt, siehe ADR 0038).
