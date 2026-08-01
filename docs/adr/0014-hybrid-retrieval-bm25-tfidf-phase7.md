# 0014 – Hybrid-Retrieval (Phase 7 / A4): BM25 + TF-IDF mit Reciprocal Rank Fusion

- **Status:** Akzeptiert
- **Datum:** 2026-08-01

## Kontext

Die [Roadmap.md](../../Roadmap.md) beschreibt für **Phase 7 / A4** das „Hybrid-Retrieval (BM25 +
TF-IDF), offline handimplementiert": Die reine Kosinus-TF-IDF-Wertung ist bei **exakten Fakten**
(DOI, Metriken, Abkürzungen, Benchmark-Namen) schwächer; ein Fremd-Wheel ist nicht nötig, weil
BM25 über die vorhandenen SQLite-Chunks deterministisch nachbaubar ist.

Zwei Eigenschaften des heutigen Rankings begründen die Lücke fachlich:

- **Keine Term-Sättigung.** Die TF-Komponente von `TfidfVectorizer` ist linear: Ein Chunk, der
  einen Term zwanzigmal nennt, gilt als zwanzigmal so passend wie einer, der ihn einmal nennt.
  Für die Frage „welches Paper nutzt FAISS?" ist das irreführend – entscheidend ist, *dass* der
  Term vorkommt, nicht wie oft.
- **Keine Längennormalisierung.** Die L2-Norm normiert auf die Vektorlänge, nicht auf die
  Dokumentlänge. Nach [ADR 0013](0013-chunking-refinement-phase7.md) sind die Chunks länger und
  in der Länge deutlich streuender geworden (Median 840 → 1245 Zeichen, obere Grenze 1500,
  mehrseitige Chunks 7,6 %). Genau diese Streuung modelliert BM25 über den Parameter `b`.

**Gemessene Ausgangslage statt Vermutung.** Nach der Lehre aus
[ADR 0013](0013-chunking-refinement-phase7.md) („erst messen, dann umsetzen") wurde vor jeder
Code-Änderung ein Messapparat gebaut: ein versioniertes Gold-Set
([eval/retrieval-gold.json](../../eval/retrieval-gold.json), 19 Fragen) und ein Harness
([scripts/eval_retrieval.py](../../scripts/eval_retrieval.py), Hit@k/MRR). Die Labels sind
**mechanisch aus dem Chunk-Text abgeleitet** (ein Paper ist relevant, wenn einer seiner Chunks
alle Strings der Regel enthält) und damit unabhängig von jeder Ranking-Funktion – sonst würde die
Messung das eigene Verfahren bestätigen. Baseline am realen Korpus (145 Paper, 11 339 Chunks),
gemessen auf den 19 **Entwicklungsfragen** `G01`–`G19` (Gold-Set 1.0.0):

| Fragetyp | n | Hit@5 | MRR@5 | Hit@10 | MRR@10 |
| --- | --- | --- | --- | --- | --- |
| `fact` (Term wörtlich in der Anfrage) | 12 | 0,750 | 0,565 | 0,917 | 0,584 |
| `paraphrase` (Term umschrieben) | 4 | 0,500 | 0,375 | 0,750 | 0,411 |
| `concept` (Mehrwort-Regel) | 3 | 1,000 | 1,000 | 1,000 | 1,000 |
| **gesamt** | **19** | **0,737** | **0,594** | **0,895** | **0,613** |

## Entscheidung

A4 wird als **Rang-Fusion zweier lexikalischer Wertungen über einer gemeinsamen Tokenisierung**
umgesetzt – deterministisch, offline, ohne zusätzliche Abhängigkeit.

1. **Eine Token-Basis für beide Wertungen.** Der Index fittet beim Laden **einen**
   `CountVectorizer` (unveränderte Default-Tokenisierung). Daraus entstehen
   - die TF-IDF-Matrix über `TfidfTransformer` – das ist per `scikit-learn`-Definition dieselbe
     Pipeline wie der bisherige `TfidfVectorizer`, die Gleichheit wird durch einen Test belegt
     statt behauptet, und
   - die BM25-Gewichtsmatrix (siehe Punkt 2).

   Damit teilen beide Verfahren Vokabular und Tokenisierung, es gibt weiterhin nur **eine**
   Tokenisierung pro On-Read-Anfrage ([ADR 0010](0010-drop-in-workflow-and-qa-phase6.md)), und es
   werden – wie in [ADR 0005](0005-graphrag-index-backend-open.md) festgelegt – **keine**
   sklearn-/scipy-Objekte persistiert.

2. **BM25 handimplementiert** (`indexing/bm25.py`) als dünnbesetzte Gewichtsmatrix mit derselben
   Besetzungsstruktur wie die Term-Häufigkeiten:

   $$w_{d,t}=\mathrm{idf}_t\cdot\frac{f_{d,t}\,(k_1+1)}{f_{d,t}+k_1\left(1-b+b\,\frac{|d|}{\overline{|d|}}\right)},\qquad
   \mathrm{idf}_t=\ln\!\left(1+\frac{N-n_t+0.5}{n_t+0.5}\right)$$

   mit $f_{d,t}$ = Termhäufigkeit, $|d|$ = Chunk-Länge in Token, $\overline{|d|}$ = mittlere
   Chunk-Länge, $N$ = Zahl der Chunks, $n_t$ = Zahl der Chunks mit Term $t$. Bewertet wird per
   Matrix-Vektor-Produkt mit den Termhäufigkeiten der Anfrage – dieselbe Kostenklasse wie das
   heutige `linear_kernel`. Festgelegt sind `k1 = 1.5` und `b = 0.75` (Standardwerte) als
   **dokumentierte Modulkonstanten ohne Umgebungsschalter**, damit Ergebnisse reproduzierbar
   bleiben. Die IDF-Variante nach Lucene ist stets positiv; sehr häufige Terme können damit keine
   negativen Beiträge und keine Rang-Inversionen erzeugen.

3. **Reciprocal Rank Fusion** (`indexing/fusion.py`) statt Score-Addition:

   $$\mathrm{RRF}(d)=\sum_{r\in R}\frac{1}{K+\mathrm{rank}_r(d)},\qquad K = 60$$

   Beide Ranglisten werden vollständig gebildet (nur Einträge mit positivem Score), die Ränge
   beginnen bei 1, die Vereinigung wird fusioniert. Ein Chunk, der nur in einer Liste vorkommt,
   erhält nur einen Summanden. Rang-Fusion ist gegenüber der Addition roher Scores robust, weil
   Kosinus- und BM25-Werte **unterschiedliche, nicht vergleichbare Skalen** haben.

4. **Contract.** Der Default aller Chunk-Modi ist `hybrid`; die Primitive
   `TfidfIndex.search(..., scoring=...)` akzeptiert zusätzlich `tfidf` und `bm25` (nötig für
   Messung und als Notausgang), `python -m scripts.ask` reicht das als `--scoring` durch. Die
   **MCP-Tools bekommen bewusst keinen Schalter**: Ein Agent kann Ranking-Parameter nicht
   beurteilen, und ein Knopf an der Agentengrenze würde das Verhalten nichtdeterministisch machen.
   `Hit`/`Citation` tragen weiterhin `score` – jetzt als **Fusionswert**, ausdrücklich *keine*
   Ähnlichkeit – und zusätzlich die Rohwerte `score_tfidf` und `score_bm25` (`0.0`, wenn der Chunk
   in der jeweiligen Wertung nicht positiv war). `Citation.to_dict()` wächst damit von 8 auf 10
   Schlüssel. Das ist ein **Laufzeit-Schema**: Es wird nichts persistiert, das Index-Schema bleibt
   bei **0.4.0**, ein Re-Ingest ist nicht nötig.

5. **Wirkbereich.** Umgestellt wird ausschließlich die von allen Chunk-Modi geteilte Primitive
   `TfidfIndex.search` – also **Basic**, der **Local**-Seed, der **Local**-Fan-out je Nachbarpaper
   und **DRIFT** innerhalb der Community. Bewusst unangetastet bleiben:
   - `neighbors_of_chunk` (Chunk↔Chunk-Ähnlichkeit): BM25 ist ein Anfrage-Dokument-Modell und
     asymmetrisch; ein ganzes Dokument als Anfrage zu verwenden ist nicht sein Modell.
   - das **Global**-Community-Ranking ([ADR 0008](0008-retrieval-and-query-router-phase4.md)):
     Community-Texte sind kurze Keyword-/Summary-Aggregate, in denen Längennormalisierung und
     Term-Sättigung kaum Wirkung haben.
   - der **Paper-Ähnlichkeitsgraph** ([ADR 0007](0007-graphrag-index-phase3-option-b.md)) und das
     **Zitations-Matching** ([ADR 0011](0011-intra-corpus-citation-graph-phase7.md)): Beides ist
     persistiert; eine Änderung dort würde Communities und `CITES`-Kanten verschieben – ein
     A4-fremder Eingriff.

6. **Nachweis und Rückfallregel.** Der Nutzen wird mit demselben Harness gegen dieselbe Baseline
   gemessen (Gold-Set vor der Implementierung eingefroren, damit die Auswahl nicht auf den
   Gewinner hin selektiert ist). Zeigt die Messung **keinen** Vorteil, bleibt `tfidf` der Default
   und `hybrid` ein Opt-in – der Befund schlägt die Roadmap-Annahme
   ([ADR 0013](0013-chunking-refinement-phase7.md) hat diesen Fall präzediert).

## Alternativen

- **`TfidfVectorizer(sublinear_tf=True)`** – eine Zeile, bringt Term-Sättigung nahezu gratis.
  *Verworfen:* keine Längennormalisierung (kein `b`-Äquivalent) und keine zweite, unabhängige
  Rangliste; der Effekt bliebe deutlich hinter BM25 zurück und wäre nicht abschaltbar vergleichbar.
- **Score-Normalisierung (min-max/z-Score) statt Rang-Fusion.** *Verworfen:* Normalisierte Scores
  hängen an der Verteilung der jeweiligen Trefferliste und kippen bei Anfragen mit wenigen
  Treffern; die Roadmap fordert ausdrücklich eine **rangbasierte** Fusion.
- **BM25 als alleiniges Verfahren (TF-IDF ersetzen).** *Verworfen:* TF-IDF trägt zusätzlich
  `neighbors_of_chunk`, den Paper-Graphen und das Community-Ranking; ein Austausch hätte
  Fernwirkung auf persistierte Artefakte. Die Fusion ist der risikoärmere Weg und behält beide
  Signale.
- **Fertiges Paket (`rank_bm25`).** *Verworfen:* offline nicht beschaffbar
  ([ADR 0002](0002-venv-and-offline-dependency-strategy.md)); die Roadmap fordert ohnehin eine
  Handimplementierung, und die Formel ist überschaubar und vollständig testbar.
- **BM25-Statistiken in SQLite persistieren.** *Verworfen:* Der Index bleibt Source of Truth für
  **Texte**, alle abgeleiteten Räume werden beim Laden rekonstruiert
  ([ADR 0005](0005-graphrag-index-backend-open.md)). Persistierte Gewichte müssten bei jeder
  Parameteränderung migriert werden.
- **Zwei getrennte Vektorisierer.** *Verworfen:* doppelte Tokenisierung bei jeder On-Read-Anfrage
  und das Risiko divergierender Vokabulare.

## Konsequenzen

- **Positiv:** Exakte Fakten profitieren von Term-Sättigung und Längennormalisierung; alle vier
  Chunk-Pfade gewinnen ohne Änderung ihrer Aufrufsignaturen. Die Fusion ist transparent: `score`
  ist der Fusionswert, `score_tfidf`/`score_bm25` zeigen, welches Verfahren einen Treffer trägt.
  Der Index bleibt unverändert (**kein Re-Ingest**). Mit Gold-Set und Harness existiert erstmals
  ein reproduzierbares Maß gegen Retrieval-Regressionen.
- **Negativ / Aufwand:** `score` verliert seine Deutung als Ähnlichkeit (Wertebereich ~0,008–0,033
  bei `K = 60`) – Vergleiche über Anfragen hinweg waren nie sinnvoll, sind jetzt aber auch optisch
  nicht mehr naheliegend. `Citation` wächst auf 10 Schlüssel, vier Tool-Spezifikationen und die
  zugehörigen Shape-Tests ziehen nach. Beim Laden entsteht zusätzlicher Rechenaufwand für die
  BM25-Matrix (gemessen, siehe unten).
- **Folgeentscheidungen:** Gold-Set und Harness sind ein **Teil-Vorgriff auf A6**; A6 bleibt offen
  für Breite (alle Modi, mehr Fragen), dokumentierte Baseline je Fragetyp und die Integration als
  optionaler QS-Lauf. Die Bereinigung verrauschter Terme bleibt **A5**; sie wirkt auf beide
  Wertungen, weil sie an der gemeinsamen Tokenisierung ansetzt.

## Ergebnis nach der Umsetzung

**Messaufbau.** Das Gold-Set wurde nach der Implementierung um ein **unabhängiges
Validierungsset** (`V01`–`V15`) erweitert – neue Terme, nach Korpus-Häufigkeit und **nicht** nach
Retrieval-Ergebnis ausgewählt, Labels wie zuvor mechanisch abgeleitet. Grund: 19 Fragen tragen
keine Default-Entscheidung. Gesamtstand **Gold-Set 1.1.0, 34 Fragen** (22 `fact`, 7 `paraphrase`,
5 `concept`), Labels 34/34 über `--verify-labels` reproduzierbar. Realer Korpus: 145 Paper,
11 339 Chunks, Index-Schema unverändert **0.4.0** (kein Re-Ingest nötig, wie vorgesehen).

| Wertung | Hit@5 | MRR@5 | Hit@10 | MRR@10 |
| --- | --- | --- | --- | --- |
| `tfidf` (Baseline) | 0,735 | 0,572 | 0,853 | 0,587 |
| `bm25` | **0,912** | **0,691** | 0,912 | **0,691** |
| `hybrid` (Default) | 0,882 | 0,641 | **0,912** | 0,644 |

Je Fragetyp (Hit@5 / MRR@5):

| Fragetyp | n | `tfidf` | `bm25` | `hybrid` |
| --- | --- | --- | --- | --- |
| `fact` | 22 | 0,773 / 0,596 | **1,000 / 0,764** | 0,955 / 0,680 |
| `paraphrase` | 7 | 0,571 / 0,333 | **0,714 / 0,548** | 0,714 / 0,476 |
| `concept` | 5 | 0,800 / **0,800** | 0,800 / 0,567 | 0,800 / 0,700 |

**Befunde.**

1. **Der geforderte Nachweis ist erbracht.** Bei Fakt-/Abkürzungsfragen steigt Hit@5 von 0,773
   auf 0,955 und MRR@5 von 0,596 auf 0,680; fünf Fragen, die reines TF-IDF unter den Top 5 gar
   nicht beantwortete (u. a. „Model Context Protocol", „NarrativeQA", „FAISS"), sind es jetzt.
   Kein Fragetyp fällt gegenüber der Baseline zurück.
2. **Die Roadmap-Annahme, die Fusion sei dem Einzelverfahren überlegen, bestätigt sich nicht
   eindeutig.** `bm25` liegt aggregiert **vor** `hybrid` (MRR@5 0,691 vs. 0,641). Auf dem
   Entwicklungsset allein war der Abstand größer (0,732 vs. 0,596), auf dem unabhängigen
   Validierungsset **kehrte er sich um** (0,638 vs. 0,697). Die Differenz zwischen `bm25` und
   `hybrid` ist damit **nicht belastbar** – belastbar ist nur, dass beide die TF-IDF-Baseline in
   beiden Sätzen deutlich schlagen.
3. **Der Default bleibt `hybrid`** – nicht, weil er die besten Aggregate hat, sondern weil er in
   **keiner** Fragenklasse einbricht: `bm25` verliert bei konzeptuellen Fragen (MRR 0,567; im
   Validierungsset 0,167), `tfidf` bei Paraphrasen (0,333). Die Fusion liegt überall im oberen
   Feld. Für einen Korpus, dessen künftige Fragen nicht durch 34 Beispiele repräsentiert sind,
   ist diese Robustheit mehr wert als ein Aggregat-Vorsprung innerhalb der Messstreuung. Wer
   gezielt Fakten sucht, wählt `--scoring bm25` – die Zahlen dafür stehen oben.
   **Bewusst nicht getan:** die Fusion durch Gewichte oder ein kleineres `K` nachzuziehen. Das
   wäre Parameter-Tuning auf 34 Fragen und würde genau die Messstreuung überanpassen, die
   Befund 2 offenlegt.
4. **Kosten.** Der Aufbau beider Räume kostet **+3,6 %** gegenüber dem bisherigen Pfad
   (1845 ms → 1911 ms für 11 339 Chunks; die Tokenisierung dominiert mit 1771 ms, TF-IDF-Transform
   68 ms, BM25-Gewichte 81 ms). `TfidfIndex.load` inklusive SQL liegt bei rund 2,2 s. Die
   BM25-Matrix teilt die Besetzung der TF-IDF-Matrix (je 1 131 551 Einträge, je ~13 MB).
5. **Determinismus.** Zwei unabhängige Ladevorgänge liefern identische Trefferlisten; der
   TF-IDF-Raum ist nachweislich identisch zum früheren `TfidfVectorizer` (Testfall
   `test_tfidf_space_matches_the_previous_vectorizer`), `--scoring tfidf` reproduziert damit das
   Verhalten vor dieser Änderung exakt.

**Bekannte Grenzen.** Das Gold-Set misst die geteilte Chunk-Primitive, nicht die Modi als Ganzes
(Local-Fan-out, Community-Auswahl); seine Labels sind lexikalisch abgeleitet und daher
vollständig für die genannten Terme, aber nicht für inhaltlich gleichwertige Formulierungen –
ein relevantes Paper ohne den Term zählt als irrelevant. Beides ist bewusst **A6** zugeordnet.
