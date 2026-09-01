# 0036 – Global: Community-Ranking über die Mitglieds-Chunks (Phase 10 / V4)

- **Status:** Akzeptiert
- **Datum:** 2026-09-01

## Kontext

Die [Roadmap.md](../../Roadmap.md) beschreibt **Phase 10 / V4** so: Global erreicht Hit@5
**0,353** / MRR **0,269** bei einem Lift von **3,55** gegen ≈ 1,0 beider Trivial-Baselines – die
Auswahl ist klar besser als Zufall, die Coverage bleibt mit **0,248** aber niedrig. *Verdacht:*
Das Ranking vergleicht die Frage gegen einen sehr dünnen Text – zehn Keywords plus eine
extraktive Zusammenfassung je Community. Die eigentliche Textmasse der Mitglieder bleibt
ungenutzt.

Der Punkt war lange **nachgelagert**: Die ursprüngliche Prämisse befürchtete, ein Referenz-Zufluss
aus Phase 14 würde den Bestand mit hunderten einchunkigen Einträgen fluten, bevor V4 überhaupt
misst. Phase 14 hat diese Prämisse mit **E0** widerlegt (kein Ernte-/Kurationswerkzeug, ein
etwaiger künftiger Harvest bleibt bei ~20–50 Kandidaten) und Phase 15 hat den Bestand auf **606**
Paper wachsen lassen, ohne dass [G0.4](../roadmap-historie.md#g04--trägt-die-community-struktur-den-gewachsenen-bestand)
seine Lift-Schwelle (≥ 3,0) im gemessenen Bereich verfehlt hätte. V4 war damit **nicht mehr
blockiert**, blieb aber ohne aktiven Anlass zurückgestellt, bis diese Umsetzung sie aufgegriffen
hat.

DRIFT ([ADR 0022](0022-drift-community-union-and-fallback-phase10.md)) nutzt exakt dieselbe
Funktion `rank_communities` für seine Top-*m*-Community-Auswahl. Jede Änderung an der
Community-Scoring-Logik wirkt sich daher **automatisch auch auf DRIFT** aus – ADR 0022 hat das
bereits vorausgesehen: „V4 wird die hier gemessenen Zahlen verschieben, weil es dieselbe
Community-Auswahl betrifft – deshalb die getrennte Ausweisung."

### Gemessene Ausgangslage statt Vermutung

Wegwerf-Messung gegen den realen Korpus (606 Paper, 42 388 Chunks, 184 Communities, Gold-Set
1.5.0, `global_n = drift_n = 5`, Wertung `hybrid`). **Validitätsanker:** Der unveränderte
Produktivcode reproduziert exakt die aktuelle Baseline – Global Hit **0,529** / MRR **0,435**
(`community_missed` 14, `in_community` 18, `no_community` 2), Coverage **0,173** / Selektivität
**0,037** / Lift **4,67**; DRIFT Hit **0,588** / MRR **0,489** (`fallback` 2). Diese Zahlen weichen
von den in der Roadmap zitierten (0,353 / 0,269 / Coverage 0,248) ab, weil der Bestand seit jener
Messung von 145 auf 606 Paper gewachsen ist und beide Gold-Sets in Phase 11 / B5 neu abgeleitet
wurden – **nicht** vergleichbar, aber dieselbe qualitative Diagnose (dünnes Community-Dokument,
niedrige Coverage).

Getestet wurden vier Aggregationskandidaten über `TfidfIndex.score_chunks_by_paper` (dieselbe
Hybrid-Chunk-Wertung wie Basic/Local/DRIFT), monkeypatch-gegen-Produktivcode gemessen (damit
`evaluate_mode` unverändert bleibt und Global **und** DRIFT in einem Lauf entstehen):

| Kandidat | Global Hit / MRR | Coverage / Selektivität / Lift | DRIFT Hit / MRR |
| --- | --- | --- | --- |
| **Baseline** (Keywords+Summary) | 0,529 / 0,435 | 0,173 / 0,037 / **4,67** | 0,588 / 0,489 |
| Mean-Top-3 | 1,000 / 0,860 | 0,558 / 0,160 / 3,49 | 0,912 / 0,784 |
| **Mean-Top-5 (gewählt)** | 1,000 / 0,860 | 0,555 / 0,163 / 3,41 | 0,882 / 0,765 |
| Mean-Top-10 | 0,971 / 0,863 | 0,559 / 0,173 / 3,23 | 0,912 / 0,772 |
| Summe (alle positiven Chunks) | 0,971 / 0,878 | 0,527 / 0,276 / **1,91** | 0,912 / 0,821 |
| Mean-Alle (kein Top-*k*) | 0,853 / 0,623 | 0,225 / 0,020 / 11,06 | 0,824 / 0,699 |

## Warum das vorgegebene Akzeptanzkriterium eine zusätzliche Messung brauchte

Die Roadmap fragt „Hebt die Aggregation Lift **und** Coverage bei **gleicher** Selektivität?".
Bei `n = 5` (dem Produktivwert) steigt mit jedem Kandidaten aber auch die Selektivität deutlich
(0,037 → 0,16–0,28) – ein Nebeneffekt, der aus einer anderen Roadmap-Stelle bereits als Falle
bekannt ist: eine simple **Summe** über Mitglieds-Chunks bevorzugt strukturell große Communities,
genau wie die triviale „größte Communities"-Strategie (A6). Der Lift fällt deshalb bei `n = 5` für
jeden Kandidaten unter den Baseline-Wert – **obwohl** die Auswahl objektiv besser wird.

Um „bei gleicher Selektivität" wörtlich zu prüfen statt die 5er-Zahlen unkommentiert
gegenüberzustellen, wurde `n` (die Zahl der zurückgegebenen Communities) für die beiden
Top-*k*-Mittel-Kandidaten heruntergefahren, bis die Selektivität die der Baseline (0,037) trifft:

| Kandidat, `n` | Coverage | Selektivität | Lift | Hit / MRR |
| --- | --- | --- | --- | --- |
| Baseline, `n = 5` | 0,173 | 0,037 | 4,67 | 0,529 / 0,435 |
| Mean-Top-3, `n = 1` | 0,270 | 0,032 | 8,45 | 0,765 / 0,765 |
| **Mean-Top-5, `n = 1`** | **0,301** | **0,036** | **8,29** | **0,765 / 0,765** |

Bei **tatsächlich** gleicher Selektivität (0,036 gegen 0,037) steigen sowohl Coverage (0,173 →
0,301) als auch Lift (4,67 → 8,29) deutlich – mit nur **einer** statt fünf Communities. Das ist
der belastbare Nachweis: Die niedrigere Lift-Zahl bei `n = 5` ist keine Verschlechterung des
Rankings, sondern der Preis einer bewusst breiteren Auswahl (fünf statt eine Community), die bei
gleichbleibender Selektivität nicht zur Verfügung stünde. Beide Sichten gehören in die
Dokumentation, weil `n = 5` der tatsächlich produktive Wert ist.

## Entscheidung

Der Community-Score ist das **Mittel der `MEMBER_TOP_K` (= 5) höchsten Hybrid-Chunk-Scores** der
Mitgliederpaper, berechnet über die neue Methode `TfidfIndex.score_chunks_by_paper` (Rang-Fusion
aus BM25 + TF-IDF, identisch zu Basic/Local/DRIFT). Keywords und extraktive Zusammenfassung
bleiben unverändert Teil von `CommunityMatch` – nur für die **Anzeige**, nicht mehr für das
Ranking. Der bisherige, separate `TfidfVectorizer` über Community-Dokumenten entfällt vollständig.

### 1. Mittel der Top-*k* statt Summe – die Größenverzerrung ist gemessen, nicht vermutet

Eine Summe aller positiven Mitglieds-Chunk-Scores wurde ausdrücklich mitgetestet und **verworfen**:
Sie hebt Selektivität auf 0,276 (nahe an der „größte-5"-Trivial-Baseline mit 0,335) bei
eingebrochenem Lift (1,91 gegenüber 3,2–3,5 der Mittel-Varianten) – der befürchtete
Größenbias tritt exakt so ein, wie die Roadmap ihn an anderer Stelle für Coverage ohne Lift
beschreibt. Ein Mittel **ohne** Top-*k*-Grenze (alle positiven Mitglieds-Chunks) wurde ebenfalls
gemessen und verworfen: Es verdünnt einen einzelnen starken Treffer in großen Communities zu stark
(Hit fällt auf 0,853, Coverage auf 0,225) – der hohe Lift (11,06) ist hier eine Selektivität nahe
Null, kein Verdienst.

### 2. `MEMBER_TOP_K = 5` – strukturell begründet, nicht nachträglich getunt

Mean-Top-3, -5 und -10 unterscheiden sich am 34-Fragen-Gold-Set um höchstens **eine** Frage in
jede Richtung – ein am Gold-Set minimal besserer Wert (Top-3: DRIFT Hit 0,912 statt 0,882) wäre
Overfitting auf eine kleine Stichprobe, dieselbe Zurückhaltung wie bei `DEFAULT_COMMUNITIES = 5`
in [ADR 0022](0022-drift-community-union-and-fallback-phase10.md). Gewählt ist deshalb **5** – der
bestehende `k`/`n`-Wert, den Basic, Local, DRIFT und `DEFAULT_TOP_COMMUNITIES` bereits als
Konvention tragen –, statt eines separat optimierten Parameters.

### 3. Ein neuer, schlanker Baustein statt eines Umwegs über `search()`

`TfidfIndex.search()` lädt Text für jeden zurückgegebenen Treffer nach und begrenzt auf `k` – für
eine Aggregation über **alle** positiv bewerteten Chunks eines Korpus (potenziell tausende) wäre
das unnötiger Overhead. Neu ist `score_chunks_by_paper(query, scoring=...)`: Sie teilt sich den
Berechnungskern (`_all_scores`, ein Query-Vektor, eine Fusion) mit `search()`, überspringt aber
Top-k-Begrenzung und Text-Fetch und gruppiert direkt nach Paper. Für `rank_communities` ist das
in etwa **eine** zusätzliche volle Corpus-Bewertung je Anfrage – vergleichbar mit den Kosten einer
einzelnen Basic-Suche (median 0,169 s, [ADR 0033](0033-response-latency-cache-and-persisted-tfidf-state-phase15.md)),
nicht mit denen von Local (bis zu elf Bewertungen je Anfrage, [Phase 15 / G5](../../Roadmap.md)).
Eine dedizierte Latenzmessung im Stil von G0/G5 war deshalb nicht nötig: Die Änderung fügt jedem
betroffenen Modus strukturell **eine** zusätzliche volle Corpus-Bewertung hinzu, nicht mehrere.

### 4. Referenz-Einträge werden nicht gesondert behandelt

Ein Referenz-Eintrag (Abstract ohne Volltext) kann Mitglied einer Community sein wie jedes andere
Paper; sein Chunk-Score geht unverändert in die Aggregation ein. Ein Ausschluss wurde nicht
gemessen und ist damit **außerhalb** dieses Punktes – die Roadmap dokumentiert für die Chunk-Suche
bereits eine eigene Nachrangigkeits-Regel ([ADR 0031](0031-reference-contract-and-guardrail-phase13.md));
ob eine analoge Regel für die Community-Aggregation nötig ist, ist unbelegt.

## Ergebnis nach der Umsetzung (realer Korpus, `python -m scripts.eval_retrieval --modi`)

| Ebene | vorher | nachher |
| --- | --- | --- |
| `primitive` | 0,912 / 0,819 | **unverändert** |
| `basic` | 0,912 / 0,819 | **unverändert** |
| `local` | 0,912 / 0,819 | **unverändert** |
| `global` | 0,529 / 0,435 — `community_missed` 14, `in_community` 18, `no_community` 2 | **1,000 / 0,860** — `in_community` **34** |
| `drift` | 0,588 / 0,489 — `community_missed` 14, `in_community` 18, `fallback` 2 | **0,882 / 0,765** — `in_community` **34** |
| Coverage (Global, `n=5`) | 0,173 / Selektivität 0,037 / Lift 4,67 | **0,555** / Selektivität 0,163 / Lift 3,41 |

**Der qid-genaue Nachweis** (`--check` gegen die alte Baseline, Fingerprint unverändert): **1
Regression**, 37 weitere Abweichungen – **allesamt Verbesserungen** bis auf zwei kleine
Rang-Verschlechterungen (Global G06 1→2, V04 2→3; DRIFT G05 1→2, G09 2→3, V04 5→6). Auf den Ebenen
`primitive`, `basic` und `local` **keine einzige** Abweichung – die Änderung betrifft
nachweislich nur Global und DRIFT. Anschließend wurde die Baseline neu eingefroren; ein `--check`
direkt danach meldet **keine Abweichung** (Determinismus).

**Die eine Regression (DRIFT, G15) ist eine bereits bekannte Schwäche, jetzt ausgelöst statt nur
beobachtet.** G15 fragt nach einem Benchmark mit **elf** erwarteten Papern – einer breit
gestreuten Frage. [ADR 0022](0022-drift-community-union-and-fallback-phase10.md) hatte für
dieselbe Frage bereits notiert: „Die Kandidatenmenge wächst dort auf 33 Paper, und die erwarteten
Paper landen nicht mehr unter den ersten sechs Chunks." V4 verschärft genau diesen Mechanismus,
weil jetzt **mehr** Communities positiv scoren und die Vereinigung ihrer Mitglieder dadurch
tendenziell größer wird – G15 rutscht von Rang 4 auf „kein Treffer" (`drift_k = 6`). Global selbst
verbessert sich für dieselbe Frage (Rang 3 → 2); der Schaden entsteht ausschließlich in DRIFTs
lokaler Verfeinerung der vergrößerten Kandidatenmenge.

**Ein bestehender Test testete eine jetzt unerreichbare Situation.**
`test_drift_falls_back_to_the_corpus_search` konstruierte einen Begriff, der nur im zweiten Chunk
eines isolierten Papers steht (außerhalb der alten Top-10-Keywords) – vor V4 fand deshalb keine
Community den Treffer, obwohl Basic ihn fand, und DRIFT fiel sichtbar zurück. Seit V4 teilen sich
Community-Score und Basic-Suche dieselbe Chunk-Wertung: Jeder Chunk, den Basic findet, trägt
automatisch eine positiv scorende Community. Der Test wurde zu
`test_drift_finds_the_orphans_own_community_instead_of_falling_back` umgebaut und dokumentiert
jetzt genau diese geschlossene Lücke, statt sie stillschweigend grün werden zu lassen.
`test_drift_without_any_match_returns_no_citations` (echtes Fehlen jeder Übereinstimmung) bleibt
unverändert gültig – der Fallback-Pfad selbst ist **nicht** entfernt, nur sein Nutzungsfall ist am
realen Korpus (0 von 34 statt 12 von 34) fast verschwunden.

## Alternativen

| Alternative | Warum verworfen |
| --- | --- |
| **Summe der Mitglieds-Chunk-Scores** | Bevorzugt große Communities strukturell (Selektivität 0,276, Lift 1,91) – dieselbe Falle wie die triviale „größte Communities"-Baseline. |
| **Mittel über alle positiven Mitglieds-Chunks (kein Top-*k*)** | Verdünnt einzelne starke Treffer in großen Communities; Hit fällt auf 0,853. |
| **`MEMBER_TOP_K = 3`** (minimal besser am Gold-Set) | Unterschied ≤ 1 Frage von 34 – Overfitting; kein struktureller Grund gegenüber dem bestehenden `k=5`. |
| **Keywords/Summary zusätzlich in die Aggregation mischen** | Hätte zwei Signalquellen mit unklarer Gewichtung erzeugt, ohne gemessenen Zusatznutzen gegenüber reiner Chunk-Aggregation. |
| **Referenz-Einträge von der Aggregation ausschließen** | Kein gemessener Bedarf; außerhalb des Zuschnitts dieses Punktes (siehe Entscheidung, Punkt 4). |
| **Abwarten, bis G0.4 seine Schwelle verfehlt** | Die Roadmap macht V4 dann zur Voraussetzung statt zur Kür – ein Grund, sie umzusetzen, kein Grund, weiter zu warten. |

## Konsequenzen

- **Positiv:** Global löst das Gold-Set nahezu vollständig (Hit 1,000, MRR 0,860) und schließt die
  Coverage-Lücke deutlich (0,173 → 0,555 bei `n=5`; 0,173 → 0,301 bei gleicher Selektivität). DRIFT
  profitiert automatisch mit (Hit 0,588 → 0,882) und verliert nie mehr eine Community-Übereinstimmung
  wegen eines zu dünnen Community-Dokuments.
- **Positiv:** `TfidfIndex.score_chunks_by_paper` ist ein wiederverwendbarer, getesteter Baustein
  (100 % Zeilenabdeckung in `global_search.py` und `tfidf_index.py`) für künftige
  Chunk-Mengen-Aggregationen.
- **Negativ / Aufwand:** Der Lift bei `n = 5` (dem Produktivwert) sinkt von 4,67 auf 3,41 – kein
  Rückschritt des Rankings, sondern der Preis der breiteren, jetzt genutzten Auswahl (siehe die
  matched-Selektivität-Messung oben). Wer nur die 5er-Lift-Zahl liest, ohne die Selektivität
  danebenzustellen, überschätzt den Rückgang.
- **Negativ / Aufwand:** Eine DRIFT-Regression (G15) – dieselbe, in ADR 0022 bereits als Grenze
  benannte Schwäche der lokalen Verfeinerung bei großer Kandidatenmenge, jetzt ausgelöst statt nur
  beobachtet.
- **Negativ / Aufwand:** DRIFTs Fallback-Pfad ([ADR 0022](0022-drift-community-union-and-fallback-phase10.md))
  wird für seinen ursprünglichen Anlass (Community-Pfad leer trotz echtem Basic-Treffer) am realen
  Korpus praktisch nie mehr erreicht; die Garantie bleibt als Auffangnetz bestehen, ein zugehöriger
  Test musste umgebaut werden.
- **Folgeentscheidungen:** keine Schema-Änderung, kein Re-Ingest, kein Contract-Bruch (`score`
  bleibt ein `float` an derselben Stelle, nur seine Herkunft ändert sich). [ADR 0028](0028-similarity-graph-degree-phase11.md)
  hatte V4 bereits als Voraussetzung für die volle Wirkung eines dichteren Ähnlichkeitsgraphen
  benannt – dieser Zusammenhang ist mit dieser Umsetzung nicht erneut gemessen worden.

## Grenzen (offen ausgewiesen)

- **Das Gold-Set bleibt fakt-orientiert.** Gemessen wird, ob die thematisch richtige Nachbarschaft
  oben landet – nicht die Güte einer corpusweiten Synthese (dieselbe Aussagegrenze wie bei jeder
  Global-Messung dieses Repos).
- **Die Kandidatenmenge von DRIFT wächst durch V4 tendenziell weiter**, weil mehr Communities
  positiv scoren. Für breit gestreute Fragen (wie G15) kann das die lokale Verfeinerung verdünnen;
  das ist keine neue Schwäche, sondern eine durch V4 häufiger ausgelöste.
- **Referenz-Einträge sind nicht gesondert behandelt** (siehe Entscheidung, Punkt 4) – ein
  möglicher Folgepunkt, sobald ein größerer Referenz-Zufluss real ansteht.
- **Kein erneuter Nachweis des in ADR 0028 vermuteten Zusammenhangs** zwischen Graph-Dichte und
  Community-Lift unter der neuen Aggregation.
