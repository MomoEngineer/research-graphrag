# 0016 – Quantitative, offline Retrieval-Evaluation (Phase 7 / A6): Modus-Ebene, Trivial-Baselines, Regressions-Check

- **Status:** Akzeptiert
- **Datum:** 2026-08-02

> **Nachtrag (2026-08-03, [ADR 0021](0021-local-multi-seed-phase10.md)):** Der hier belegte, aber
> bewusst nicht behobene Befund „Local ist schwächer als Basic" ist adressiert – die unten
> genannten Local-Werte (0,618 / 0,532) und die Diagnose-Verteilung (seed 17 / neighborhood 3 /
> fan_out 1) sind damit **historisch**; aktuell sind 0,912 / 0,654 bei seed 30 / neighborhood 1.
> Der Messapparat selbst ist unverändert; die **Baseline wurde neu eingefroren**, und
> `RunParameters` trägt zusätzlich die Zahl der Seeds. Alles Übrige dieses ADR gilt unverändert –
> insbesondere die Trennung von steuerndem Maß und Veto, der Lift als Vergleichsinstrument und
> der Fingerprint-Guard, der genau diesen Parameterwechsel sichtbar gemacht hat.

> **Nachtrag (2026-08-03, [ADR 0022](0022-drift-community-union-and-fallback-phase10.md)):** Auch
> der hier belegte DRIFT-Befund ist adressiert – die unten genannten Werte (0,235 / 0,235) und die
> Diagnose (`in_community` 8 / `community_missed` 14 / `no_community` 12) sind damit
> **historisch**. Zwei Aussagen dieses ADR sind ausdrücklich **überholt**: Die Eigenschaft
> „Treffer == Deckelung" (fehlerfreie Verfeinerung) gilt nicht mehr – sie war eine Eigenschaft der
> **engen** Kandidatenmenge, nicht des Verfahrens –, und das Diagnose-Vokabular der DRIFT-Ebene
> lautet jetzt `in_community | community_missed | fallback` (`no_community` kann dort nicht mehr
> auftreten; für Global bleibt es unverändert). Die Baseline wurde erneut eingefroren, und
> `RunParameters` trägt zusätzlich die Zahl der Communities.

> **Nachtrag (2026-08-03, [ADR 0023](0023-multihop-citation-evaluation-phase10.md)):** Von den
> unter Punkt 4 **bewusst zurückgestellten** Erweiterungen sind zwei eingelöst: Es gibt jetzt eine
> **zweite Label-Quelle** (`citation_graph`) und mit Multi-Hop die fehlende **Fragenklasse** –
> beides genau auf dem hier vorgezeichneten Weg, nämlich additiv und ohne die nachrechenbare
> Basis zu verdrängen. Offen bleibt bewusst das breitere Fragenset desselben lexikalischen Typs.
>
> Zwei Festlegungen dieses ADR werden dabei **ergänzt, nicht abgelöst**: Die Multi-Hop-Ebene
> bekommt ein **eigenes** Gold-Set und ein **eigenes** Baseline-Artefakt, damit die hier
> fortgeschriebene Kennzahlreihe vergleichbar bleibt und der Regressions-Check kurz. Und
> `read_fingerprint` nimmt seither die Gold-Set-**Version** und ein Parameter-**Mapping** statt
> `GoldSet`/`RunParameters`; das Dateiformat der Baseline ändert sich dadurch **nicht**.
>
> Ein Befund dieses ADR ist zudem als **Artefakt des Gold-Sets** entlarvt: „Der Fan-out trägt kaum
> bei" (rettet 1 von 34 Fragen) gilt für fakt-orientierte Fragen – auf der Multi-Hop-Ebene steuert
> er 13 von 28 Treffern der Themen-Anfrage bei.

## Kontext

Die [Roadmap.md](../../Roadmap.md) führt **Phase 7 / A6** („Quantitative, offline
Retrieval-Evaluation") bereits als *teilweise erledigt*: In A4 entstanden als Vorgriff ein
versioniertes Gold-Set ([eval/retrieval-gold.json](../../eval/retrieval-gold.json), 34 Fragen
mit mechanisch abgeleiteten Labels) und ein Harness
([scripts/eval_retrieval.py](../../scripts/eval_retrieval.py)) mit **Hit@k/MRR**
([ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md)).

Gemessen wird damit aber ausschließlich die **geteilte lexikalische Primitive**
`TfidfIndex.search` – der Pfad, den Basic, der Local-Seed, der Local-Fan-out und die
DRIFT-Verfeinerung gemeinsam nutzen. **Unvermessen sind bis heute genau die Bestandteile, die
den GraphRAG-Anspruch tragen:** der Paper-Fan-out über den Ähnlichkeitsgraphen und die
Community-Auswahl von Global/DRIFT. Jede künftige Änderung dort wäre nicht überprüfbar; auch die
in der Roadmap vorgesehene **Router-Härtung (A7)** hätte ohne diese Messbarkeit erneut nur
Plausibilität als Grundlage.

### Gemessene Ausgangslage statt Vermutung

Nach der Lehre aus [ADR 0013](0013-chunking-refinement-phase7.md) und
[ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md) („erst messen, dann umsetzen")
wurde **vor jeder Code-Änderung** eine Wegwerf-Messung über alle vier Modi gegen die 34
bestehenden Gold-Fragen gefahren (realer Korpus: 145 Paper, 11 181 Chunks, 44 Communities,
Gold-Set 1.2.0). Fünf Befunde prägen die Entscheidungen:

| Befund | Messung | Konsequenz |
| --- | --- | --- |
| **Basic ist die Primitive.** | Hit 0,882 · MRR 0,650 – identisch zu den in ADR 0015 dokumentierten Primitiv-Werten | Basic erzeugt keine zusätzliche Erkenntnis; die Gleichheit wird als **Contract-Test** gesichert, nicht als zweite Kennzahl gepflegt |
| **Local ist schwächer als Basic.** | Hit 0,618 vs. 0,882 | Das gesamte Bündel hängt an **einem** Top-1-Seed: Nachbarschaft und Fan-out messen Ähnlichkeit *zum Seed*, nicht zur Anfrage. Ein falscher Seed vergiftet alles – das ist ein Struktur-, kein Ranking-Problem |
| **Der Fan-out trägt kaum.** | rettet 1 von 34 Fragen; liefert überhaupt nur in 8/34 ein erwartetes Paper | Der Nutzen des Graph-Fan-outs ist erstmals beziffert statt vermutet |
| **Nackte Coverage ist irreführend.** | echte Auswahl 0,248 – triviale „größte fünf Communities" 0,567 | Eine Coverage-Kennzahl allein würde die **triviale Strategie als doppelt so gut** ausweisen |
| **…bis die Selektivität danebensteht.** | echt 7,0 % des Korpus vs. 55,9 % (größte-5) | Erst der **Lift** (Coverage ÷ Selektivität) ordnet richtig: echt **3,5×**, größte-5 **1,0×** |
| **DRIFT scheitert nie an der Verfeinerung.** | Deckelung 8/34, tatsächliche Treffer 8/34, in 12/34 wird gar keine Community gefunden | **100 %** der DRIFT-Fehlschläge entstehen in der Community-Auswahl – die Ursache ist damit lokalisierbar statt nur sichtbar |

Der vierte und fünfte Befund sind der Kern dieses ADR: Eine unbedachte Global-Kennzahl hätte
eine triviale Strategie belohnt und wäre zum Optimierungsziel geworden.

## Entscheidung

A6 wird als **Erweiterung der bestehenden Messung um die Modus-Ebene plus ein
Regressions-Werkzeug** umgesetzt – deterministisch, offline, ohne neue Abhängigkeit, ohne
Änderung am Retrieval-Contract und **ohne Re-Ingest**.

### 1. Evaluation wird ein Paket in `src/`, die CLI bleibt dünn

Die Logik zieht von [scripts/eval_retrieval.py](../../scripts/eval_retrieval.py) nach
`src/research_graphrag/evaluation/` und unterliegt damit `mypy src`, dem Coverage-Richtwert und
dem regulären Testbaum; sie ist zudem von [scripts/qa.py](../../scripts/qa.py) importierbar.
Begründung: Mit A6 wird Evaluation von einem einmaligen Messvorgriff zu einer **dauerhaften
Fähigkeit** des Systems – dann gehört sie in das Paket, nicht in ein Skript. Aufteilung nach
Verantwortlichkeit:

| Modul | Verantwortung |
| --- | --- |
| `gold.py` | Gold-Set laden, Label-Regel anwenden, eingefrorene Labels verifizieren |
| `metrics.py` | Kennzahl-Datentypen und Aggregation – **retrieval-frei** (analog `generation/synthesis.py`) |
| `runner.py` | Primitive und Modi gegen einen realen Index ausführen |
| `baseline.py` | Fingerprint, Einfrieren, qid-genauer Vergleich |
| `report.py` | Textausgabe (Präsentation an einer Stelle) |

### 2. Modus-Ebene: eine uniforme Sicht plus modus-spezifische Diagnose

Jeder Modus liefert ein **Evidenz-Bündel**; dessen Paper-Reihenfolge wird einheitlich gegen die
Gold-Labels gewertet (Hit und Kehrwert des ersten relevanten Rangs). Die Bündel-Reihenfolge ist
die Reihenfolge, in der der Modus seine Belege präsentiert:

| Modus | Bündel-Reihenfolge | Zusätzliche Diagnose |
| --- | --- | --- |
| Basic | Zitate (= Primitive) | – (Gleichheit per Contract-Test) |
| Local | Seed → Chunk-Nachbarschaft → Paper-Fan-out | **welcher Baustein** den ersten Treffer beisteuert |
| Global | Top-n Communities | siehe Punkt 3 |
| DRIFT | Zitate innerhalb der gewählten Community | **Deckelung** (enthält die Community überhaupt ein erwartetes Paper?) und „keine Community gefunden" |

Die Local-Zerlegung und die DRIFT-Deckelung sind der eigentliche Erkenntnisgewinn: Sie trennen
**Auswahlfehler** von **Rankingfehlern**. Eine aggregierte Zahl allein könnte das nicht.

### 3. Global wird als Erreichbarkeits-Diagnose gemessen – nie ohne Trivial-Baselines

Für Global gilt zusätzlich zu Hit/MRR (auf **Community**-Rängen):

- **Coverage** – Anteil der erwarteten Paper, die Mitglied einer der Top-n-Communities sind,
- **Selektivität** – Anteil des Korpus, den diese Communities umfassen,
- **Lift** = Coverage ÷ Selektivität, gebildet als **Verhältnis der Mittelwerte** (die
  Frage-für-Frage-Division ist undefiniert, sobald keine Community gefunden wird),
- verglichen gegen zwei Trivial-Baselines: **„größte n Communities"** (deterministisch) und
  **„zufällige n Communities"**, gemittelt über mehrere Ziehungen mit festem Seed.

Coverage wird **nie ohne Selektivität** und **nie ohne Baselines** ausgegeben. Ergänzend wird im
Berichtskopf die Aussagegrenze deklariert: Das Gold-Set ist fakt-orientiert; gemessen wird, ob
die thematisch richtige Nachbarschaft oben landet – **nicht**, ob die corpusweite Synthese gut
ist.

### 4. Labels bleiben mechanisch – ergänzt statt ersetzt

Die Roadmap fordert „inhaltlich **statt** nur lexikalisch abgeleitete Labels". Diese Formulierung
wird bewusst **abgelehnt**: Die mechanische Regel ist über `--verify-labels` gegen den Index
nachrechenbar, und genau das hat in A5 den Re-Ingest abgesichert (Gold-Set 1.1.0 → 1.2.0, Labels
neu abgeleitet, 34/34 reproduzierbar). Geurteilte Labels wären semantisch stärker, aber nicht
mehr verifizierbar – eine stille Drift bliebe unentdeckt. Die Architektur weist deshalb die
**Label-Quelle** aus, sodass spätere Quellen (Zitationsgraph, Urteil) additiv danebentreten
können, ohne die verifizierbare Basis zu verlieren.

**Bewusst zurückgestellt** (A6 bleibt damit „teilweise erledigt"):

- **Inhaltlich abgeleitete Labels.** Naheliegender nächster Schritt ohne Subjektivität sind
  Multi-Hop-Fragen gegen den **Zitationsgraphen** aus [ADR 0011](0011-intra-corpus-citation-graph-phase7.md)
  (382 `CITES`-Kanten; 52 Paper mit ≥ 2, 44 mit ≥ 3 zitierenden Papern) – „welche Paper bauen auf
  X auf?" ist damit objektiv und nicht-lexikalisch labelbar.
- **Breiteres Fragenset.** Mehr Fragen desselben lexikalisch verankerten Typs erhöhen die
  statistische Stabilität, nicht den Erkenntnisgewinn; sinnvoll wären fehlende **Klassen**
  (Themenfragen, Multi-Hop, Negativkontrollen) – und die brauchen die Label-Quellen von oben.

### 5. Regressions-Check statt Aggregat-Schwelle

- Die Baseline ist ein **eigenes, versioniertes Artefakt**
  ([eval/retrieval-baseline.json](../../eval/retrieval-baseline.json)), erzeugt vom Harness
  selbst. Sie speichert **ausschließlich den ersten relevanten Rang je Frage und Modus**; alle
  Aggregate werden daraus abgeleitet – keine doppelt gepflegten Kennzahlen.
- **Zwei Schweregrade.** `Treffer → kein Treffer` ist eine **Regression** (Exit-Code 1); eine
  reine Rangverschiebung wird **nur berichtet**. Begründung: Rangrauschen ist bei jeder
  Indexänderung normal, der Verlust einer Fähigkeit nicht. Aggregat-Schwellen wären bei 34 Fragen
  Scheingenauigkeit – **eine** Frage entspricht 2,9 Prozentpunkten Hit@5.
- **Fingerprint-Guard gegen Verrotten.** Passt der Index nicht mehr zur Baseline (Gold-Set-Version,
  Index-Schema, Paper-/Chunk-/Community-Zahl, Parameter), wird **nicht still verglichen**, sondern
  die Unvergleichbarkeit gemeldet (Exit-Code 2) und ein bewusstes Neu-Einfrieren verlangt. Ohne
  diesen Guard würde nach dem nächsten Drop-in unbemerkt gegen einen fremden Korpus geprüft.
- **Kein DoD-Gate.** Der Check braucht den realen Index, den die Testsuite bewusst nicht hat. Er
  bleibt ein **manueller QS-Lauf** neben `scripts.status`/`scripts.qa`
  ([ADR 0010](0010-drop-in-workflow-and-qa-phase6.md)); die Logik selbst wird mit synthetischen
  Fixtures getestet.

### 6. Bewusste Nicht-Ziele

- **Kein Eingriff in den Retrieval-Contract.** Die Modus-Funktionen nehmen weiterhin einen
  Datenbankpfad und laden den Index selbst (On-Read, [ADR 0010](0010-drop-in-workflow-and-qa-phase6.md)).
  Das kostet den Messlauf ~190 s für 34 Fragen × 4 Modi, weil `TfidfIndex.load` je Aufruf erneut
  läuft. Ein injizierbarer Index wäre schneller, würde aber vier Modul-Signaturen und die
  zugehörigen Tool-Spezifikationen für ein **selten laufendes Werkzeug** ändern – das Verhältnis
  stimmt nicht. Die Laufzeit ist dokumentiert, nicht wegoptimiert.
- **Kein Tuning.** Es werden keine Parameter (k, Fan-out, RRF-`K`, Community-Zahl) anhand dieser
  34 Fragen nachgezogen; das wäre Überanpassung ([ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md)).
- **Kein Schema-/Index-Eingriff**, kein Re-Ingest, keine neue Abhängigkeit.

## Alternativen

- **Alles in `scripts/eval_retrieval.py` belassen** (Konvention wie `scripts/qa.py`). Verworfen:
  Die Datei verdoppelt ihren Umfang, bliebe außerhalb von `mypy src` und dem Coverage-Richtwert
  und wäre aus `scripts/qa.py` nur als Skript-Import nutzbar. Die Einmalkosten des Umzugs
  (Testbaum, Doku) sind gegen dauerhafte Prüfbarkeit gut angelegt.
- **Aggregierte Schwellenwerte als Gate** („Hit@5 darf nicht unter 0,85 fallen"). Verworfen:
  bei 34 Fragen ist das Rauschen größer als jede sinnvolle Schwelle, und die Meldung nennt nicht,
  *welche* Frage kaputtging.
- **Nackte Coverage für Global.** Verworfen – gemessen widerlegt: Die triviale Strategie „größte
  Communities" gewinnt (0,567 vs. 0,248) und wäre zum Optimierungsziel geworden.
- **Communities als Ground Truth** („liegt das erwartete Paper in der thematisch richtigen
  Community?"). Verworfen: Die Communities stammen aus demselben TF-IDF-Raum wie das Retrieval –
  das wäre ein Zirkelschluss.
- **Geurteilte (LLM-/menschliche) Labels sofort.** Zurückgestellt, siehe Punkt 4: Sie kosten die
  Nachrechenbarkeit, die heute die einzige Absicherung gegen Label-Drift ist.
- **Injizierbarer Index für Tempo.** Verworfen, siehe Punkt 6.

## Konsequenzen

- **Positiv:** Fan-out, Community-Auswahl und DRIFT-Deckelung sind erstmals beziffert; Fehlschläge
  sind nach **Auswahl** vs. **Ranking** trennbar. Der qid-genaue Regressions-Check macht künftige
  Eingriffe (A7 Router-Härtung, A8 inkrementelles Update) überprüfbar statt plausibel. Der
  Fingerprint-Guard verhindert, dass die Baseline still veraltet. Die Evaluation ist ein
  reguläres, typgeprüftes und getestetes Paket.
- **Negativ / Aufwand:** Ein vollständiger Modus-Lauf dauert ~190 s (bewusst nicht optimiert). Die
  Kennzahlen für Global und DRIFT sind mit einem fakt-orientierten Gold-Set **niedrig und nur
  eingeschränkt aussagekräftig** – die Aussagegrenze muss mitgelesen werden. Die Baseline ist ein
  weiteres zu pflegendes Artefakt; nach jedem Korpuszuwachs ist ein bewusstes Neu-Einfrieren
  nötig.
- **Folgeentscheidungen:** Die beiden zurückgestellten Roadmap-Punkte (inhaltliche Labels,
  breiteres Fragenset) bleiben als Rest von A6 offen. Der Befund „Local hängt an einem Seed" und
  „12/34 Anfragen finden keine Community" sind Kandidaten für eigene Punkte – sie werden hier
  **nur belegt, nicht behoben** (kein Scope-Kriechen).

## Ergebnis nach der Umsetzung

Realer Korpuslauf (145 Paper, 11 181 Chunks, 44 Communities, Gold-Set 1.2.0, Wertung `hybrid`,
`k = 5`), `python -m scripts.eval_retrieval --write-baseline`:

| Ebene | Hit | MRR | Diagnose |
| --- | --- | --- | --- |
| `primitive` | 0,882 | 0,650 | – (identisch zu [ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md): das Messgerät selbst hat sich nicht verändert) |
| `basic` | 0,882 | 0,650 | – (**identisch zur Primitive**, jetzt auch am realen Korpus bestätigt) |
| `local` | 0,618 | 0,532 | Seed 17 · Nachbarschaft 3 · Fan-out 1 |
| `global` | 0,353 | 0,269 | in_community 12 · community_missed 10 · no_community 12 |
| `drift` | 0,235 | 0,235 | in_community 8 · community_missed 14 · no_community 12 |

| Strategie | Coverage | Selektivität | Lift |
| --- | --- | --- | --- |
| echte Community-Auswahl | 0,248 | 0,070 | **3,55** |
| größte 5 Communities | 0,567 | 0,559 | 1,01 |
| zufällige 5 Communities | 0,120 | 0,114 | 1,05 |

**Eine Zahl der Vorabmessung war Rauschen – und die Korrektur macht die Metrik erst lesbar.**
Die zufällige Baseline stammte dort aus **einer** Ziehung (Lift 0,39). Über `RANDOM_DRAWS = 100`
Ziehungen gemittelt liegt sie bei **1,05**. Damit sitzen **beide** trivialen Strategien auf
Zufallsniveau (≈ 1,0), und der Lift bekommt eine klare Ablesevorschrift: *1,0 = Zufall*, die
echte Auswahl ist mit **3,55** rund dreieinhalbmal so treffsicher wie ein gleich großer
zufälliger Ausschnitt. Die nackte Coverage hätte weiterhin die triviale Strategie gekürt
(0,567 vs. 0,248).

**Drei Befunde, die ohne die Modus-Ebene unsichtbar geblieben wären:**

1. **Local ist für Fakt-Fragen schwächer als Basic** (0,618 vs. 0,882) – kein Ranking-, sondern
   ein Strukturproblem: Nachbarschaft und Fan-out messen Ähnlichkeit **zum Seed**, nicht zur
   Anfrage. Der Fan-out rettet genau **eine** von 34 Fragen.
2. **DRIFTs lokale Verfeinerung ist fehlerfrei.** Treffer (8) und erreichbare Deckelung (8) sind
   identisch: Sobald die Community ein erwartetes Paper enthält, findet DRIFT es auch. **Alle**
   Fehlschläge entstehen davor – 12× wird gar keine Community gefunden, 14× die falsche.
3. **Die Beschränkung auf die Top-1-Community kostet DRIFT ein Drittel.** Global erreicht mit
   fünf Communities 12 Fragen, DRIFT mit einer nur 8.

**Determinismus belegt:** Ein `--check` unmittelbar nach dem Einfrieren meldet über alle fünf
Ebenen und 34 Fragen **keine einzige Abweichung** – ein vollständiger zweiter Lauf reproduziert
jeden Rang. Laufzeit ~190 s (wie prognostiziert, dominiert vom wiederholten Index-Laden).

**Umfang:** Paket `src/research_graphrag/evaluation/` (fünf Module), 41 Tests, **100 %**
Zeilenabdeckung in allen fünf Modulen; die CLI [scripts/eval_retrieval.py](../../scripts/eval_retrieval.py)
ist auf Argumentbehandlung zusammengeschrumpft, [scripts/qa.py](../../scripts/qa.py) ruft den
Check optional über `--quantitativ` auf. Beide Fehlerpfade sind **fail-fast**: Eine fehlende
(Exit 1) oder veraltete Baseline (Exit 2) wird gemeldet, **bevor** der dreiminütige Messlauf
startet – geprüft wurde das gegen den realen Index.
