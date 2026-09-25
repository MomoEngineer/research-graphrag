# 0044 – Antwortzeit: bit-identische Wertung ohne volle Matrixmultiplikation, FTS5 nur als Infrastruktur

- **Status:** Akzeptiert
- **Datum:** 2026-09-25

## Kontext

[ADR 0038](0038-corpus-ceiling-revision-local-search-latency.md) hat gemessen, dass der reale
Bestand (damals 3.461 Paper) beide Marken reißt: warm lag Local im Median bei 6,064 s, DRIFT bei
1,722 s, kalt lagen alle vier Modi bei 9,6–15,8 s. Das ADR hat **Weg B (FTS5)** zur empfohlenen
nächsten Phase erhoben und eine schmalere Alternative notiert (Fan-out-Vorfilter), aber bewusst
nichts entschieden. Die Entscheidung fiel in
[Phase 16](../../Roadmap.md#phase-16--antwortzeit-weg-b-fts5) über eine vorab fixierte Regel (aus
G0.6 übernommen): Bit-identische Kandidaten zuerst, eine FTS5-Vorauswahl nur, wenn sie die warme
Marke für Local sonst verfehlt, FTS5 als Infrastruktur nur unter 50 % Indexzuwachs und 20 %
Ingest-Mehrdauer. **Bit-Identität schlägt Geschwindigkeit.**

Die Vorabmessung F0 (2026-09-25, am realen Bestand: 3.579 Paper, 225.126 Chunks, 714 MB;
Statusblock in der Roadmap) hat zwei Annahmen korrigiert:

1. **Teuer ist die Matrixmultiplikation, nicht nur die Python-Sortierung.** Jede Wertung
   multiplizierte die Anfrage gegen alle 23 Mio. Nicht-Null-Einträge (`linear_kernel` und das
   BM25-Produkt), ~1 s je Aufruf. Local ruft das bis zu elfmal auf (Seed, fünf Nachbarschaften,
   fünf Fan-out-Suchen); dazu kamen Python-Ranglisten über alle Chunks.
2. **Der Fan-out-Vorfilter aus ADR 0038, Abschnitt 3, ist in der dort beschriebenen Form nicht
   bit-identisch.** Die Hybrid-Wertung fusioniert **korpusweite** Ränge. Filtert man vor der
   Wertung, entstehen Ränge innerhalb der Teilmenge und damit andere Fusionswerte – am Mini-Index
   in 239 von 240 gefilterten Suchen, teils mit anderer Reihenfolge.

## Entscheidung

### 1. Die Wertung wird bit-identisch begradigt (F1)

In `indexing/tfidf_index.py`, ohne Schema- und ohne Contract-Änderung:

| Baustein | Was sich ändert | Warum bitgleich |
| --- | --- | --- |
| Spaltenweise Wertung (`_by_term`) | Scores entstehen nur über die Spalten der Anfrage-Terme (spaltenweise Kopien beider Matrizen, einmal beim Laden) | Die Summation je Chunk beginnt bei `0.0` und folgt derselben Termreihenfolge wie scipys `csr_matmat`: gespeicherte Folge des Anfragevektors (TF-IDF), aufsteigende Spalten (BM25). Produkte sind kommutativ |
| Vektorisierte Ranglisten und Fusion | `np.lexsort` mit einem vorab berechneten Rang der `chunk_id`; Fusion als `0.0 + 1/(K+Rang)`, erst TF-IDF, dann BM25 | Derselbe Tie-Break wie der Python-Stringvergleich; dieselbe Additionsfolge wie `fuse_rankings` |
| Top-*k* per Partition | Nur Zeilen ≥ dem *k*-größten Wert werden sortiert | Gleichstände an der Grenze bleiben vollständig im Rennen |
| Filter vor der Sortierung | `paper_ids` wirkt **nach** der korpusweiten Wertung auf die Mitgliedszeilen | Die Werte sind dieselben wie ohne Filter |
| Gemeinsame Wertung (`_scored`) | Die letzten `SCORE_MEMO_SIZE` (4) Anfrage-Wertungen werden am Index-Objekt gemerkt | Dasselbe Ergebnis wird wiederverwendet; der Merker verfällt mit dem Objekt über den Dateizustand ([ADR 0033](0033-response-latency-cache-and-persisted-tfidf-state-phase15.md)) |
| Schnelle Nachbarschaft | Zeile per Wörterbuch statt linearer Suche, Ähnlichkeit wie oben spaltenweise, Top-*k* statt Vollsortierung | wie oben |
| Sortierte Zeilen als Invariante | `counts.sort_indices()` direkt nach dem Deserialisieren | Bisher sortierte scikit-learn nebenbei in place; die Werte beider Matrizen sind nachweislich bitgleich |

`retrieval/local.py`, `drift.py` und `global_search.py` bleiben unverändert; sie profitieren über
die gemeinsame Wertung. Kein Nachbarschafts-Cache: Er traf in F0 bei 3 von 100 Aufrufen.

### 2. Keine FTS5-Vorauswahl

Regel 2 greift nicht: F1 hält die warme Marke für Local am Auslegungspunkt (doppelter Bestand,
Max 0,45 s). Unabhängig davon wäre die Vorauswahl langsamer als das, was sie einspart. Die
FTS5-Stufe kostet 0,29–0,33 s je Anfrage, weil Allerweltswörter fast jeden Chunk treffen und FTS5
alle Treffer bewertet, während die exakte Wertung über alle Chunks nach F1 5 ms dauert. Außerdem
wäre sie nie bit-identisch (0 Rangabweichungen erst ab *N* = 20.000).

### 3. FTS5 als Infrastruktur

Regel 3 greift (F0: +16,0 % Index, +6,7 % Ingest mit `unicode61 remove_diacritics 2`,
`detail=full`). Umsetzung und Schema: siehe Nachtrag F2.

## Alternativen

- **FTS5 als Vorauswahl für das Ranking (Weg B im engeren Sinn).** Verworfen, siehe
  Entscheidung 2.
- **Dichter Anfragevektor mit `csr_matvec` statt spaltenweiser Kopien.** Ebenfalls bitgleich und
  ohne Ladezeit und zusätzlichen Speicher. Verworfen, weil er am Auslegungspunkt ohne Reserve bleibt
  (Local-Max 0,93 s, Global 0,91 s gegen 0,45 s bzw. 0,77 s mit spaltenweiser Wertung).
- **Fan-out-Vorfilter vor der Wertung (ADR 0038, Abschnitt 3).** Verworfen: nicht bit-identisch
  (Kontext, Punkt 2).
- **Nachbarschafts-Cache.** Verworfen: bitgleich, aber wirkungslos (3 % Trefferquote).

## Konsequenzen

- **Positiv:** Warm liegen alle vier Modi am realen Bestand im Median bei 0,05–0,23 s (vorher
  1,3–6,9 s), am doppelten Bestand bei höchstens 0,77 s. Jede Ausgabe bleibt bitgleich; die
  Baselines müssen dafür **nicht** neu eingefroren werden.
- **Negativ / Aufwand:** Die spaltenweisen Kopien kosten beim Laden 1–3 s und halten beide
  Matrizen ein zweites Mal im Speicher. Der Spitzenspeicher steigt dadurch nicht, er entsteht beim
  Laden selbst. Der Kaltstart hält die 5-s-Marke damit weiterhin nicht (siehe Nachtrag F3).
- **Folgeentscheidungen:** FTS5-Schema (F2), Kaltstart (F3), Auslegung (F4) als Nachträge unten.
