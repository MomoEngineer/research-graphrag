# 0038 – Korpus-Ceiling überholt: Local Search reißt die Marke auch warm, Weg B (FTS5) wird fällig

- **Status:** Akzeptiert
- **Datum:** 2026-09-16

## Kontext

[ADR 0037](0037-mcp-tool-response-size-ceiling.md) hat die Diskrepanz bereits benannt, aber bewusst
nicht bearbeitet: Der reale Bestand liegt mit **3.461 Papern / 220.964 Chunks / 1.170 Communities**
beim **4,6-Fachen** der in [Phase 15 / G5](../roadmap-historie.md#g5--auslegung-neu-festschreiben)
gemessenen Auslegung (≤ 750 Volltexte / ≤ 1500 Gesamteinträge, Stand 2026-09-01). G5 selbst hatte
die Korpusgröße als **bindenden** Faktor identifiziert – nicht Basic oder DRIFT, sondern **Local**
(laut Fragetyp-Contract der primäre Modus für Detailfragen) reißt die 5-s-Marke bereits zwischen
800 und 900 Papern, weil `search_local` bis zu **elf** volle Korpus-Scorings je Anfrage ausführt
(eine Seed-Suche + bis zu fünf Nachbarschafts-Scorings + bis zu fünf Fan-out-Suchen), während Basic
mit einem auskommt. [ADR 0033](0033-response-latency-cache-and-persisted-tfidf-state-phase15.md)
hat dazu eine eigene, enger gefasste Revisionsbedingung geschrieben: Wächst der Korpus auf
„grobe Anhaltszahl: ~1.500–2.000 Paper" (das 3–5-Fache des damaligen 606-Paper-Stands), ist **Weg B
(FTS5)** mit derselben Messdisziplin erneut zu prüfen. Bei 3.461 Papern ist diese Marke um das
**1,7- bis 2,3-Fache** überschritten – dieses ADR löst die damit fällige Nachmessung ein.

**Methodik – bewusst am realen Live-Index, nicht per Chimären-Bisektion wie G5.** G5 musste den
zukünftigen Wandpunkt durch synthetische Paper simulieren, weil der reale Bestand (606) die Wand
noch nicht erreicht hatte. Diese Voraussetzung gilt nicht mehr: Der reale Bestand **liegt bereits
jenseits jeder plausiblen neuen Wand**, eine Simulation wäre hier der Umweg. Gemessen wurde
stattdessen direkt gegen `data/index/index.sqlite` (nur lesend, kein Index-Bau, kein Re-Ingest),
mit zwei Methoden nebeneinander:

1. **Kalt, wie G5:** echter Subprozessstart je Anfrage (`python -m scripts.ask --mode <modus>`),
   3 Wiederholungen je Modus.
2. **Warm, wie ADR 0033:** ein Prozess, Index einmal geladen (Prozess-Cache nach Weg C aktiv),
   danach 20 Anfragen mit wechselndem Wortlaut je Modus, Median/Max/Min über die 20 warmen Läufe.

Beide Läufe sind ein Wegwerf-Skript (nicht Teil des Repos, wie in G5 und G0 üblich).

### Ergebnis

| Modus | Warm: 1. Aufruf (Cache-Miss)¹ | Warm: Median (n=20) | Warm: Max | Warm: Min | Kalt: Median (n=3, Subprozess) |
| --- | --- | --- | --- | --- | --- |
| Basic | 10,824 s | 0,872 s | 1,508 s | 0,791 s | **11,832 s** ⚠ |
| **Local** | 7,490 s | **6,064 s** ⚠ | 9,647 s | 5,155 s | **15,805 s** ⚠ |
| Global | 2,597 s | 0,839 s | 1,337 s | 0,774 s | **9,645 s** ⚠ |
| DRIFT | 2,767 s | 1,722 s | 2,722 s | 1,560 s | **10,289 s** ⚠ |

¹ Alle vier Modi liefen nacheinander **im selben Prozess**; nur Basics erster Aufruf ist ein echter
Cache-Miss des `TfidfIndex`-Objekts selbst (Betriebssystem-Dateicache zu diesem Zeitpunkt noch
kalt). Global/DRIFTs „erster Aufruf" trifft die bereits warme `TfidfIndex`, misst aber zusätzlich
den Cache-Miss von `load_communities` (eigener, in Phase 15 / G3 gebauter Prozess-Cache über 1.170
Communities, geprüft in `src/research_graphrag/indexing/graph_index.py`) – das erklärt den Abstand
zum jeweiligen Median plausibel. **Local hat keine vergleichbare Erklärung:** `load_neighbors`
(Fan-out) ist **ungecacht** – jeder Aufruf öffnet eine eigene, kurzlebige SQLite-Verbindung ohne
Prozess-Cache. Der Abstand zwischen Locals „1. Aufruf" (7,490 s) und Median (6,064 s) ist damit
keine Cache-Miss-Erklärung, sondern liegt schlicht innerhalb der ohnehin hohen Streuung der warmen
Local-Läufe (Min 5,155 s – Max 9,647 s, Spanne 4,5 s). Insgesamt also kein direkter Quervergleich
zwischen den vier „1. Aufruf"-Werten, wohl aber innerhalb jeder Zeile zwischen „1. Aufruf" und
„Median" (mit der genannten Ausnahme bei Local). Die Kalt-Messungen liefen nach den Warm-Messungen
im selben Lauf; der OS-Dateicache war für alle vier bereits warm – ein echter Kaltstart nach einem
Systemneustart dürfte eher langsamer als schneller ausfallen.

**Beide Marken sind gerissen, nicht nur bei Local:**

- **Kalt (G5s eigene 5-s-Marke):** Alle **vier** Modi liegen bei 9,6–15,8 s – das **1,9- bis
  3,2-Fache** der Marke. G5 maß bei 606 Papern noch 3,9 s (Basic und Local gleich); der Faktor bei
  Local (~4,1×) liegt damit bereits nahe am Faktor des Paperwachstums selbst (~5,7×) – obwohl in die
  kalte Zeit **zwei** Kostenanteile eingehen, die getrennt gewachsen sein könnten (der strukturelle
  Suchanteil und ein, wie unten gezeigt, ebenfalls deutlich gewachsener Ladeanteil). Eine genaue
  Aufschlüsselung der beiden Anteile an der kalten Zeit hat dieses ADR nicht vorgenommen – das
  bleibt der in Abschnitt 2 verlangten Folgephase überlassen.
- **Warm (ADR 0033s eigentlich maßgebliche 1-s-Marke für den MCP-Server-Betrieb):** Basic (0,872 s)
  und Global (0,839 s) halten die Marke noch, aber mit stark geschrumpfter Marge (vormals ~6-fache
  Marge bei 606 Papern, jetzt noch 12,8 % bzw. 16,1 % Puffer bis zur Marke). DRIFT liegt mit
  1,722 s bereits **über** der 1-s-Marke, aber
  noch unter der 5-s-Marke. **Local liegt mit 6,064 s Median über beiden Marken** – 6-mal über dem
  1-s-Ziel, ~20 % über der 5-s-Marke selbst im günstigsten (warmen) Fall.

**Neuer Befund, den weder G5 noch ADR 0033 gemessen hatten: die warme Local-Latenz selbst.** ADR
0033s warme Messung (Median 0,169 s) rief `TfidfIndex.search()` **direkt** auf – strukturell
gleichwertig zu Basic (eine Scoring-Runde), nie zu Locals elffachem Muster. G5 maß Local nur
**kalt**. Die warme Local-Latenz von 6,064 s ist damit die **erste** direkte Messung dieser Art
überhaupt – und sie zeigt, dass der in ADR 0033 als „notwendig, aber nicht automatisch
hinreichend" eingestufte Prozess-Cache (Weg C) für Local **nicht mehr hinreichend** ist: Der
strukturelle, mit dem Korpus wachsende Scoring-Anteil (Kosinus/BM25 über die volle Matrix, elffach
für Local) dominiert inzwischen so stark, dass selbst ein perfekt warmer Cache die 1-s-Marke nicht
mehr hält.

**Zusätzlich gewachsen: der einmalige Ladeanteil selbst.** ADR 0033 maß den Cache-Miss innerhalb
eines laufenden Prozesses bei 606 Papern mit 0,927 s, über eine strukturell einfache
Einzel-Suche (ein Scoring, wie Basic) – die vergleichbare, gleich strukturierte Messung ist deshalb
Basics erster Aufruf: **10,824 s** bei 3.461 Papern, ein Zuwachs, der die 5,7-fache Paperzahl
deutlich übersteigt. Global/DRIFTs erste Aufrufe (2,597 s / 2,767 s) sind **nicht** direkt
vergleichbar – sie tragen zusätzlich den (echten, gecachten) Cache-Miss von `load_communities`
oben drauf, während die zugrunde liegende `TfidfIndex` zu diesem Zeitpunkt bereits warm war (s.
Fußnote 1). Festzuhalten bleibt unabhängig von dieser Einschränkung: Der Ladeanteil war zum
Zeitpunkt von ADR 0033 gegenüber dem strukturellen Suchanteil vernachlässigbar und ist es jetzt
nicht mehr – jede erste Anfrage nach einem MCP-Server-Neustart zahlt ihn, unabhängig vom gewählten
Modus.

## Entscheidung

### 1. Die ≤ 750/≤ 1500-Ceiling aus G5 wird als überholt markiert, nicht durch eine neue Zahl ersetzt

Anders als G5 (die eine **künftige** Wand vor Erreichen bezifferte) stünde eine per Chimären-
Bisektion neu hergeleitete Zahl heute **unterhalb** des bereits produktiv laufenden Bestands
(3.461 Paper) – ein neuer, kleinerer Grenzwert änderte nichts an der Tatsache, dass der reale
Korpus ihn bereits verletzt. Eine reine Zahlenkorrektur wäre deshalb keine Lösung, sondern eine
kosmetische Neuetikettierung eines strukturellen Problems. Statt einer neuen Zahl dokumentieren
README/CONTRIBUTING/Roadmap ab sofort den **gemessenen Ist-Zustand mit Datum**: der Bestand liegt
bei 3.461 Papern, sowohl der Kaltstart (alle vier Modi) als auch die warme Local-Latenz reißen die
zuvor gültigen Marken messbar, und eine neue verlässliche Zahl setzt die in Abschnitt 2
beschriebene strukturelle Arbeit voraus.

### 2. ADR 0033s Revisionsbedingung ist ausgelöst: Weg B (FTS5) wird empfohlene nächste Phase – aber nicht in diesem ADR umgesetzt

Der in ADR 0033 benannte Auslöser („~1.500–2.000 Paper, Weg B erneut prüfen, mit derselben
Messdisziplin") ist mit den Zahlen aus diesem ADR **eingelöst**, nicht nur formal überschritten.
Dieses ADR trifft die Prüfung selbst (siehe Ergebnis oben) und hält fest: Ein reiner Prozess-Cache
(Weg C) kann den strukturellen, mit der Chunkzahl linear wachsenden Scoring-Anteil nicht beseitigen
– das war in ADR 0033 bereits so benannt, jetzt ist es an Local **gemessen** statt nur befürchtet.
**Weg B (FTS5) wird damit von einer offen ausgewiesenen, unentschiedenen Option zur empfohlenen
nächsten Phase erhoben.** Dieses ADR **entscheidet die Migration nicht** und **baut sie nicht** –
das wäre ein Bruch mit „Erst messen, dann bauen" (Roadmap.md, Leitprinzipien): FTS5 hat eine andere
Tokenisierung und ein anderes Ranking als der heutige TF-IDF/BM25-Hybrid, ein Umstieg bräuchte eine
eigene Vorabmessung (Retrieval-Güte gegen das eingefrorene Gold-Set, Performance-Nachweis über
mehrere Korpusgrößen) und ein Neueinfrieren beider Baselines – Aufwand, der eine eigene, dedizierte
Phase mit eigenem Statusblock verdient, nicht einen Nebensatz in diesem ADR.

### 3. Sekundär notiert, nicht entschieden: eine schmalere Optimierung von `search_local` als Alternative zu FTS5

[G5](../roadmap-historie.md#g5--auslegung-neu-festschreiben) hatte bereits vermerkt, dass „eine
gemeinsame Vektorisierung der Anfrage über Seed-, Nachbarschafts- und Fan-out-Suchen" ein möglicher,
damals bewusst nicht umgesetzter Folgeschritt bliebe. `search_local`s Fan-out ruft
`index.search(query, 1, paper_ids={neighbor_id})` **je Nachbarpaper** auf; `TfidfIndex.search()`
wertet dabei strukturell **immer** die volle Matrix (`_all_scores`) und filtert erst danach auf
`paper_ids` – der `paper_ids`-Parameter spart also keine Rechenzeit, nur Ergebniszeilen. Eine
Vorfilterung auf den Fan-out-Nachbarn **vor** dem Scoring (statt danach) reduzierte die
tatsächliche Matrixgröße pro Fan-out-Aufruf drastisch und wäre eine kleinere, in sich abgeschlossene
Änderung als eine FTS5-Migration. Dieses ADR **entscheidet nicht** zwischen FTS5 und dieser
schmaleren Optimierung – beide sind Kandidaten für die in Abschnitt 2 verlangte dedizierte Phase,
mit eigener Messung, welche der Kandidaten (oder beide) die 1-s-Marke wieder herstellt.

## Alternativen

- **Eine neue, kleinere Ceiling-Zahl per Chimären-Bisektion ableiten (wie G5).** Zurückgestellt:
  Der reale Bestand liegt bereits über jeder plausiblen neuen Zahl – die Bisektion würde eine
  Grenze exakt vermessen, die längst überschritten ist, ohne die eigentliche Handlungsempfehlung
  (strukturelle Arbeit statt Zahlenkorrektur) zu ändern. Eine solche Messung bliebe als Werkzeug
  sinnvoll, falls künftig ein kleinerer, dedizierter Teilbestand (z. B. ein Offline-Export)
  gebraucht wird – dafür jetzt keine Vorabarbeit, YAGNI.
- **Die Ceiling unverändert lassen (weiter ≤ 750/≤ 1500 behaupten).** Verworfen: Das widerspräche
  „Provenienz zuerst"/„Nachvollziehbarkeit vor Tempo" (CONTRIBUTING.md) – eine seit Monaten faktisch
  falsche Zahl in README/CONTRIBUTING stehen zu lassen, obwohl der reale Bestand und jetzt auch die
  Latenz nachweislich abweichen, wäre die stillschweigende Duldung eines bekannten Fehlers.
- **FTS5 (Weg B) sofort in diesem ADR umsetzen.** Verworfen: Scope-Sprung ohne eigene
  Vorabmessung – genau das Vorgehen, das CONTRIBUTING.md („Erst messen, dann bauen") und ADR 0033
  selbst ausschließen. Eine Migration ohne gemessenen Parität-Nachweis gegen das eingefrorene
  Gold-Set riskierte eine stille Qualitätsregression.
- **Nur den Fan-out-Vorfilter aus Abschnitt 3 sofort umsetzen, ohne FTS5 zu prüfen.** Zurückgestellt:
  Ungeklärt ist, ob eine Vorfilterung allein die 1-s-Marke bei weiterem Korpuswachstum trägt (sie
  senkt Locals Fan-out-Anteil, aber nicht den Seed- und Nachbarschafts-Anteil, die weiterhin die
  volle Matrix scoren) – das ist Gegenstand der in Abschnitt 2 verlangten dedizierten Messung, nicht
  eine hier vorweggenommene Vermutung.

## Konsequenzen

- **Positiv:** README/CONTRIBUTING/Roadmap zeigen ab sofort den tatsächlichen, gemessenen Zustand
  statt einer seit dem 4,6-fachen Bestandswachstum stillen falschen Zahl. ADR 0033s
  Revisionsbedingung ist formal eingelöst statt offen zu verjähren. Die warme Local-Latenz ist
  erstmals direkt gemessen (vorher nur indirekt aus der kalten G5-Messung hergeleitet) und schließt
  eine Lücke, die sowohl G5 als auch ADR 0033 einzeln offen gelassen hatten.
- **Negativ / Aufwand:** Es gibt vorerst **keine** neue verlässliche Korpusgrenze – „wachstumsfähig"
  aus den Leitprinzipien ist bis zur nächsten, dedizierten Phase nicht mit einer Zahl unterlegt.
  Der MCP-Server liefert Local-Search-Antworten heute nachweislich mit 5–10 s Latenz (warm) bzw.
  bis über 17 s (Kaltstart) – das bleibt bis zur strukturellen Fix-Phase unverändert; dieses ADR
  behebt nichts am Code. Nutzer des Werkzeugs (der Autor selbst, begleitend zur Masterarbeit) sind
  davon bereits betroffen.
- **Folgeentscheidungen:** Eine dedizierte Phase „Weg B (FTS5) vs. Fan-out-Vorfilterung" mit eigenem
  Statusblock, eigener Vorabmessung (Retrieval-Güte-Parität gegen das eingefrorene Gold-Set,
  Latenz über mehrere Korpusgrößen) und eigenem Baseline-Neueinfrieren, falls die gewählte Option
  das Ranking verändert. Bis dahin bleibt Basic/Global der einzige Modus mit verlässlicher Marge
  unter der 1-s-Marke; DRIFT und insbesondere Local sind als **bekannt langsam** dokumentiert.

## Nachtrag (2026-09-25): Die dedizierte Phase ist umgesetzt – Phase 16, ADR 0044

Die in Abschnitt 2 verlangte Phase hat beide offenen Fragen dieses ADR beantwortet, und zwar
anders, als hier vermutet
([ADR 0044](0044-response-latency-bit-identical-scoring-and-fts5-phase16.md)):

- **Weg B (FTS5) als Vorauswahl** wurde gemessen und **verworfen**. Die FTS5-Stufe allein kostet
  0,3 s je Anfrage, weil Allerweltswörter fast jeden Chunk treffen, und sie ist nie bit-identisch.
  FTS5 kommt nur als Phrasenindex (Infrastruktur für Phase 17) in den Index.
- **Der Fan-out-Vorfilter aus Abschnitt 3** ist in der hier beschriebenen Form (Filter **vor** der
  Wertung) **nicht** bit-identisch: Die Hybrid-Wertung fusioniert korpusweite Ränge. Gebaut ist er
  als Filter vor der **Sortierung**.
- **Die eigentliche Ursache** lag in der Wertung selbst: Jede Anfrage wurde gegen alle 23 Mio.
  Nicht-Null-Einträge der Matrix multipliziert. Die Wertung läuft jetzt spaltenweise nur über die
  Anfrage-Terme, bitgleich. Warm liegen am realen Bestand (3.579 Paper) alle Modi im Median bei
  0,05–0,21 s; Local lag vorher bei 6,1–6,9 s.

**Die „vorerst fehlende Korpusgrenze“ (Konsequenzen) ist ersetzt:** ≤ 7.150 Gesamteinträge /
≤ 450.000 Chunks, gemessen am 2026-09-25 als der doppelte Bestand. Warm halten dort alle vier Modi
die 1-s-Marke (schlechtester Einzellauf 0,66 s). Der kalte CLI-Pfad bleibt über der 5-s-Marke
(8,6–9,5 s real); der MCP-Server lädt deshalb beim Start vor. **Neue Revisionsbedingung:** erneut
messen, sobald der Bestand 450.000 Chunks oder 7.150 Einträge überschreitet oder die Bestätigung
auf dem Arbeitsrechner warm über 0,8 s liegt.
