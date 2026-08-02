# 0017 – Router-Härtung (Phase 7 / A7): Wortgrenzen, ausgewiesene Konfidenz, Fallback statt stiller Fehlleitung

- **Status:** Akzeptiert
- **Datum:** 2026-08-02

## Kontext

Die [Roadmap.md](../../Roadmap.md) beschreibt **Phase 7 / A7** so: Der Query-Router aus
[ADR 0008](0008-retrieval-and-query-router-phase4.md) ist „eine naive DE/EN-Substring-Heuristik
ohne Konfidenz/Fallback; eine Fehlklassifikation führt **still** in den falschen Modus".

Zwei Randbedingungen haben sich seit Phase 4 verschoben:

- **Der Router liegt heute auf dem Agentenpfad.** ADR 0008 rechtfertigte die dünne Heuristik
  damit, dass „in Phase 5 Copilot selbst zum Router wird". Seit [ADR 0012](0012-llm-bridge-and-answer-synthesis-phase7.md)
  hat das MCP-Tool `answer_question` jedoch `mode = "auto"` als **Default** – jede Frage, die
  Copilot über dieses Tool stellt, wird von dieser Heuristik geroutet. Die ursprüngliche
  Entlastungsbegründung trägt damit nicht mehr.
- **Es gibt seit [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md) eine Messbasis.**
  A6 hat ausdrücklich festgehalten, dass A7 „ohne diese Messbarkeit erneut nur Plausibilität als
  Grundlage" hätte.

### Gemessene Ausgangslage statt Vermutung

Nach der in [ADR 0013](0013-chunking-refinement-phase7.md), [ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md)
und [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md) etablierten Reihenfolge lief
**vor jeder Code-Änderung** eine Wegwerf-Messung gegen den realen Korpus (145 Paper, 11 181
Chunks) und die vorhandenen Fragenbestände (10 Prüf-Fragen aus [scripts/qa.py](../../scripts/qa.py),
34 Gold-Fragen aus [eval/retrieval-gold.json](../../eval/retrieval-gold.json)).

| Befund | Messung | Konsequenz |
| --- | --- | --- |
| **Die Substring-Semantik schadet asymmetrisch.** | Von den einwortig messbaren Signalen haben die deutschen **14 von 15** keinen einzigen Teilwort-Träger im Korpusvokabular (die Ausnahme `metrik` siehe unten); englische Signale kommen auf bis zu 46 (`score`), 30 (`differ`), 23 (`metric`) | Teilwort-Matching wird **nicht pauschal** abgeschafft, sondern je Signal **deklariert**: deutsche Stämme behalten es (belegt unbedenklich, unverzichtbar für Komposita/Beugung), englische Signale bekommen Wortgrenzen |
| **Der Schaden ist beziffert.** | Von 26 korpus-häufigen Teilwort-Trägern leiten **15** eine neutrale Detailfrage in einen fremden Modus (`different`/`differently`/`differentiation` → drift, `contextcite` → local, `trends` → global) | Wortgrenzen sind der eigentliche Hebel – nicht die Konfidenz |
| **Signal-Konflikte sind praktisch inexistent.** | Nur **1 von 44** realen Fragen trägt Signale aus mehr als einem Modus; die Präzedenz hat **nie** eine Signal-Mehrheit überstimmt | Ein aufwändiges Score-Modell wäre Wegwerf-Mechanik. Der Nutzen der Wertung liegt in der **Sichtbarkeit**, nicht in der Konfliktauflösung |
| **Der Router verfehlt den dokumentierten Contract – durch Lücken, nicht durch Fehlgriffe.** | 6/10 Prüf-Fragen; **alle vier** Fehlschläge fallen mangels Signal auf den Default zurück (S2 „thematic clusters", N2 „works relate to") | Es fehlen Signale für zwei dokumentierte Fragetypen; ergänzt wird **a priori** entlang der Frageform, nicht entlang der Fehlerliste |
| **Ein einzelnes Signal richtet messbaren Schaden an.** | `which papers` leitet **16 von 22** Fakt-Fragen des Gold-Sets nach `local` – A6 hat für genau diese Fragen local **0,618** gegen basic **0,882** gemessen | `which papers` benennt einen **Gegenstand** („Paper"), keine **Frageform**; es wird gestrichen. Die Netz-Semantik tragen die spezifischen Marker (`build on`, `cite`, `related work`) |
| **Das Lexikon ist überwiegend ungeprüft.** | **9 von 51** Signalen feuern auf den 44 vorhandenen Fragen | Ohne ein Fragenset, das jedes Signal berührt, ist jede Lexikon-Änderung unbelegt |

## Zwei Maßstäbe – und warum sie getrennt bleiben müssen

Die naheliegende Idee, den Router am A6-Gold-Set (Hit@5/MRR) zu optimieren, ist eine Falle:
A6 hat für die vier Modi 0,882 (basic) · 0,618 (local) · 0,353 (global) · 0,235 (drift) gemessen.
Das globale Optimum eines darauf optimierten Routers ist **„immer basic"** – er würde sich selbst
abschaffen. Zudem wären die Zahlen als Zielfunktion unehrlich: Die Gold-Labels entstehen
mechanisch aus dem Chunk-Text und bevorzugen damit strukturell die lexikalische Chunk-Suche.

Deshalb gilt:

| Rolle | Maß | Wirkung |
| --- | --- | --- |
| **Steuernd** | **Contract-Treue** gegen das dokumentierte Fragetyp→Modus-Mapping der [README.md](../../README.md) | sagt, *was* zu reparieren ist |
| **Veto** | A6-Gold-Set, end-to-end über `mode = auto` gefahren | verhindert, dass eine „vertragstreue" Änderung die Antworten verschlechtert |
| **Nie** | Optimierung auf das Veto-Maß | verhindert die Degeneration zu „immer basic" |

## Entscheidung

A7 wird als **Härtung der bestehenden Heuristik** umgesetzt – deterministisch, DB-frei, offline,
ohne neue Abhängigkeit, **ohne Schema-Eingriff und ohne Re-Ingest**. Ein ML-/LLM-Klassifikator
bleibt verworfen ([ADR 0008](0008-retrieval-and-query-router-phase4.md)).

### 1. Signale werden deklariert statt roh gematcht

Ein Signal ist kein nackter Substring mehr, sondern ein Wertobjekt mit **deklarierter Match-Art**:

| Art | Semantik | Anwendung |
| --- | --- | --- |
| `word` | Treffer nur an Wortgrenzen | englische Signale, deren Ableitungen die Bedeutung verlassen |
| `prefix` | wortanfangs-verankert samt Beugung | englische Signale mit bedeutungstreuer Ableitung (`contradict`, `cite`, `score`) |
| `stem` | Teilwort-Treffer (wie bisher) | **nur** deutsche Wortstämme (`widerspr`, `zitier`, `themen` …) |

Die Asymmetrie ist gemessen, nicht gefühlt: Deutsche Stämme haben im Korpus – bis auf die eine
unten korrigierte Ausnahme – keine Teilwort-Fläche, brauchen die Teilwort-Semantik aber für
Komposita (`Themenüberblick`) und Beugung (`widersprechen`/`Widerspruch`) – eine
Morphologie-Bibliothek ist offline nicht beschaffbar
([ADR 0005](0005-graphrag-index-backend-open.md)).

Drei englische Wortfamilien **spalten sich in der Bedeutung** und stehen deshalb als explizite
Wortliste statt als Wortanfang: `differ` (nicht `different`/`differently`/`differentiation`),
`compare` (nicht `comparable`/`comparative`) und das deutsche Gegenstück `unterschied` (nicht
`unterschiedlich`). Wo eine Beugung das Signal **trägt**, wird sie explizit aufgenommen
(`differs`, `differences`, `compared`, `comparisons`, `unterschiede`).

### 2. Lexikon-Revision – a priori nach Frageform, nicht nach Fehlerliste

Leitfrage jedes Eintrags: *Markiert der Term die **Form der Frage** oder nur einen **Gegenstand**
im Korpus?* Nur Frageform-Marker bleiben.

| Änderung | Begründung |
| --- | --- |
| `which papers` / `welche paper` **gestrichen** | benennt den Gegenstand, nicht die Frageform (jede Korpusfrage handelt von Papern); messbarer Schaden an 16 Fakt-Fragen |
| `trend` → nur Plural `trends`/`Trends` | der Singular bezeichnet einen Gegenstand („der Trend in Abbildung 3"), der Plural die Übersichtsfrage |
| `corpus`/`korpus` → nur Reichweiten-Formen (`across the corpus`, `im korpus`, `über den korpus`, `corpus-wide`, `korpusweit`) | das nackte Wort ist zweideutig (Gegenstand „der Korpus" vs. Reichweite „über den Korpus hinweg") |
| **ergänzt** `relate to`/`relates to`/`related to`, `verwandt mit` | Beziehungsmarker – deckt den dokumentierten Fragetyp „Methodennetze" (N2) ab |
| **ergänzt** `thematic cluster` | deckt den dokumentierten Fragetyp „Cross-Paper-Synthese" (S2) ab; das deutsche Pendant („Themencluster", „Themenfeld") fällt bereits unter den Stamm `themen` |

### 3. Entscheidungsregel: strukturelle Kandidaten gegen einen Default

1. **Kandidaten** sind nur die *strukturellen* Modi `drift`, `global`, `local`. `basic` ist der
   **Default**, kein Kandidat – es braucht kein Signal, um gewählt zu werden.
2. Die `basic`-Signale (`doi`, `f1`, `metric`, `exact` …) sind **bestätigend**: Sie erscheinen in
   der Begründung, verschieben aber keine Entscheidung. Andernfalls würde „Vergleiche den
   F1-Score von A und B" durch zwei Fakt-Signale von der (korrekten) Vergleichsfrage weggezogen.
3. Der Kandidat mit den **meisten** Signalen gewinnt.
4. **Gleichstand ⇒ Fallback `basic`**, Konfidenz `weak`, Begründung nennt die unterlegenen
   Kandidaten. Damit **entfällt die feste Präzedenz** `drift > global > local > basic` aus
   [ADR 0008](0008-retrieval-and-query-router-phase4.md): Sie war eine stille Rangordnung ohne
   Beleg; die Roadmap fordert an dieser Stelle ausdrücklich einen „definierten Fallback (z. B.
   Basic bei Unsicherheit)", und A6 stützt `basic` als belegstärkste Rückfallebene.
5. **Kein Signal ⇒ `basic`**, Konfidenz `none`.

### 4. Konfidenz wird ausgewiesen – als Stufe, nicht als Pseudo-Wahrscheinlichkeit

`RouteDecision` trägt zusätzlich `confidence` und `signals`:

| Stufe | Bedeutung |
| --- | --- |
| `strong` | genau ein struktureller Kandidat bzw. ein eindeutiger Sieger |
| `weak` | Gleichstand → Fallback `basic`, Konkurrenten benannt |
| `none` | kein strukturelles Signal → Default `basic` |

Ein Fließkomma-„Score" wäre hier Pseudo-Präzision: Schlüsselwort-Treffer sind keine
kalibrierten Wahrscheinlichkeiten. Drei benannte Stufen sagen dasselbe ehrlicher und sind
testbar.

### 5. Die Entscheidung wird sichtbar

- **CLI:** `python -m scripts.ask` zeigt Modus, Konfidenz und die auslösenden Signale.
- **MCP:** `answer_question` weist die Routing-Entscheidung **additiv** als `routing` aus – nur
  bei `mode = "auto"`, sonst `null`. Damit sieht Copilot (und der Mensch), *warum* ein Modus
  gewählt wurde; das behebt die in der Roadmap benannte Lücke „führt still in den falschen
  Modus". Die sechs Evidenz-Tools bleiben unverändert.
- **Layering:** `SynthesisResult.routing` ist bewusst eine einfache Abbildung
  (`dict[str, Any] | None`) und kein `RouteDecision`, damit `generation/synthesis.py`
  retrieval-frei bleibt ([ADR 0012](0012-llm-bridge-and-answer-synthesis-phase7.md)).

### 6. Messbar gemacht – mit einer nachrechenbaren Label-Regel

Neu ist ein **Router-Gold-Set** ([eval/router-gold.json](../../eval/router-gold.json)). Seine
Labels sind **keine Urteile**, sondern eine Ableitung aus der dokumentierten Tabelle
„Fragetypen → Suchmodus" der [README.md](../../README.md):

| Fragetyp (`kind`) | zulässige Modi |
| --- | --- |
| `detail` | `local`, `basic` (die README nennt für Detailfragen ausdrücklich „Local + Basic") |
| `synthesis` | `global` |
| `network` | `local` |
| `fact` | `basic` |
| `contrast` | `drift` |

Diese Abbildung ist im Code hinterlegt und wird **mechanisch verifiziert**: `verify_router_labels`
prüft, dass die eingefrorene Modus-Menge jeder Frage exakt der Abbildung ihres Fragetyps
entspricht – das Pendant zu `--verify-labels` des Retrieval-Gold-Sets
([ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md)). Zusätzlich prüft
`signal_coverage`, dass **jedes** Signal des Lexikons von mindestens einer Frage berührt wird
(Befund M5).

Ausgewertet wird über `research_graphrag.evaluation.routing` (Treffer, Aufschlüsselung je
Fragetyp, Verwechslungsmatrix, Konfidenz- und Fallback-Verteilung), abrufbar über
`python -m scripts.eval_retrieval --router`.

**Kein Baseline-Artefakt.** Anders als in A6 gibt es keine eingefrorene Datei und keinen
Fingerprint: Der Router ist **korpus-unabhängig** und in Millisekunden auswertbar. Die Regression
ist deshalb ein regulärer, deterministischer **Test** in der Suite statt ein zusätzliches
Artefakt – billiger, schneller und ohne Pflegeaufwand.

## Ergebnis nach der Umsetzung

Alle Zahlen stammen aus derselben Messanordnung wie die Ausgangslage (realer Korpus: 145 Paper,
11 181 Chunks; Retrieval-Gold-Set 1.2.0; Router-Gold-Set 1.0.0 mit 84 Fragen und 69 Signalen).

| Messung | vorher | nachher |
| --- | --- | --- |
| Contract-Treue auf den 10 Prüf-Fragen | 6/10 | **10/10** (streng 8/10 – D1/D2 landen auf `basic`, was die README für Detailfragen ausdrücklich zulässt) |
| Contract-Treue auf dem Router-Gold-Set | – | **83/84 (0,988)** |
| Signal-Abdeckung durch Fragen | 9 von 51 | **69 von 69** |
| Fehlleitung neutraler Detailfragen (Sonden über korpus-häufige Teilwort-Träger) | 15 | **0 sachlich falsche** |
| Gold-Set end-to-end über `mode = auto` | Hit@5 0,765 · MRR@5 0,618 | **Hit@5 0,882 · MRR@5 0,650** |
| … davon Fakt-Fragen (n = 22) | Hit 0,773 · MRR 0,644 | **Hit 0,955 · MRR 0,695** |

Drei Ergebnisse verdienen eine genaue Lesart:

- **Die verbleibenden Sonden-Treffer sind keine Fehlalarme.** Von den 15 fehlgeleiteten Sonden
  verschwinden genau die fünf sachlich falschen (`different`, `differently`, `differentiation`,
  `contextcite`, `trends` als Träger von `trend`). Die zehn übrigen Wörter (`cited`, `citations`,
  `compared`, `comparisons`, `differences` …) sind **bewusst aufgenommene Signalformen** – dass
  sie „feuern", ist die Absicht, nicht der Defekt.
- **Die Konfidenzstufe ist aussagekräftig.** Auf dem Router-Gold-Set trifft `strong` in **59 von
  59** Fällen den Contract und `none` in **24 von 24**; der einzige Fehlgriff ist der einzige
  `weak`-Fall (R83, bewusst konstruierter Gleichstand `drift`/`global`). Genau dieser Fall ist im
  Gold-Set als **bekannte Grenze** eingefroren, statt ihn wegzudefinieren.
- **Das Veto misst nur Nicht-Verschlechterung.** Der neue Router leitet **alle 34** Gold-Fragen
  nach `basic` – korrekt, denn es sind fakt-orientierte Fragen ohne strukturellen Marker. Die
  End-to-End-Werte sind damit **identisch** zu den in [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md)
  gemessenen Basic-Werten (0,882/0,650). Das bestätigt die Trennung der Maßstäbe: Auf diesem Set
  ist „gut routen" von „immer basic" **nicht unterscheidbar** – unterscheidbar ist es nur auf dem
  Router-Gold-Set. Der Zugewinn gegenüber dem alten Router (0,765 → 0,882) ist entsprechend
  nicht ein „besseres Ranking", sondern das **Ausbleiben einer Fehlleitung**.

Regressionsgesichert ist der Stand über einen deterministischen Test, der die Fehlgriff-Menge
**qid-genau** einfriert (`EXPECTED_MISSES = ("R83",)`), sowie über die Prüfungen „jedes Label
folgt dem Contract" und „jedes Signal ist durch eine Frage abgedeckt".

### Eine Ausnahme, die die Messung selbst gefunden hat

Die abschließende QA prüfte die Kernannahme dieses ADR **mechanisch** gegen das reale
Korpusvokabular – diesmal **ohne Häufigkeitsschwelle**: *Hat ein `stem`-Signal irgendeinen
Teilwort-Träger?* Genau eines hatte einen: **`metrik` steckt in `Biometrika`**
(Zeitschriftenname, ein einziges Vokabel). Die Vorabmessung hatte den Fall gesehen, ihn aber
hinter ihrer Schwelle „mindestens 20 Vorkommen" verborgen – die Filterung sollte Rauschen
ausblenden und hat dabei einen echten Treffer verdeckt.

Der Schaden wäre gering gewesen, weil `metrik` nur ein **bestätigendes** Fakt-Signal ist und
keinen Modus verschiebt; die Begründung hätte aber eine falsche Aussage getroffen. Korrigiert
wurde deshalb die **Ursache**: `metrik` steht jetzt als Wortform da (plus `metriken` für den
Plural). Die Invariante „kein `stem`-Signal hat einen Teilwort-Träger im Korpus" gilt damit
**ausnahmslos** und ist als Prüfung hinterlegt – korpusfrei in der Testsuite (`biometrika` unter
den Sonden), korpusgestützt in der QA.

## Alternativen

- **ML-/LLM-Klassifikator.** Verworfen (unverändert gegenüber [ADR 0008](0008-retrieval-and-query-router-phase4.md)):
  offline aufwändig, nicht deterministisch, und für eine Handvoll Frageformen unverhältnismäßig.
- **Gewichtete Signale / kalibrierte Scores.** Verworfen: Jedes Gewicht wäre auf einem Set von
  wenigen Dutzend Fragen gefittet – exakt der Overfitting-Fehler, den [ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md)
  bewusst vermieden hat. Alle Signale zählen gleich.
- **Präzedenz beibehalten.** Verworfen zugunsten des Fallbacks: Die Präzedenz *versteckt*
  Unsicherheit, statt sie zu melden – genau die Lücke, die A7 schließen soll. Sie hat in der
  Messung ohnehin nie eine Mehrheit überstimmt.
- **Substring-Matching komplett abschaffen.** Verworfen: Es würde die deutschen Komposita
  (`Themenüberblick`) und Beugungen (`widersprechen`) unauffindbar machen, obwohl die Messung
  dort **null** Fehlalarm-Fläche zeigt. Die Match-Art wird deshalb je Signal deklariert.
- **Nur Wortgrenzen, ohne die Zwischenstufe `prefix`.** Verworfen: Jede bedeutungstreue Beugung
  (`cites`, `cited`, `citing`, `citations`, `contradicts`, `scores`) wäre ein eigener Eintrag –
  ein längeres Lexikon ohne zusätzliche Trennschärfe. Der Wortanfangs-Anker genügt und fängt
  gleichzeitig die gemessene Falle `contextcite`.
- **Pro Signal ein eigener regulärer Ausdruck.** Verworfen: mächtiger, aber unlesbar und
  schwerer zu prüfen. Zwei deklarative Match-Arten decken den gemessenen Bedarf.
- **Eingefrorene Router-Baseline wie in A6.** Verworfen: Der Router hängt an keinem Korpus; ein
  Fingerprint-Guard wäre eine Lösung ohne Problem.
- **Router auf das A6-Gold-Set optimieren.** Verworfen – siehe „Zwei Maßstäbe": Das Optimum wäre
  ein Router, der immer `basic` wählt.
- **Detail-Signale ergänzen, damit Detailfragen sicher auf `local` gehen.** Verworfen: „Detail"
  ist keine sprachlich abgrenzbare Frageform (jede Frage ohne Spezialmarker ist potenziell eine
  Detailfrage). Die README nennt für diesen Typ ohnehin „Local + Basic", der Default deckt ihn ab.

## Konsequenzen

- **Positiv:** Die gemessene Fehlleitungsfläche verschwindet; die Entscheidung ist erklärbar
  (Signale + Konfidenz) statt still; Unsicherheit endet in der belegstärksten Rückfallebene; der
  Router ist erstmals **messbar** und regressionsgesichert; keine neue Abhängigkeit, kein
  Schema-Eingriff, kein Re-Ingest; unverändert deterministisch.
- **Negativ / Aufwand:** Das Lexikon wird länger (explizite Beugungen statt Substrings) und muss
  bei neuen Formulierungen gepflegt werden; die Ausgabe von `answer_question` wächst um ein Feld
  (Spec-/Test-Nachzug); die Präzedenz aus [ADR 0008](0008-retrieval-and-query-router-phase4.md)
  ist abgelöst – ein bewusster Contract-Bruch, der dort als Nachtrag vermerkt ist.
- **Bekannte Grenze:** Der Router bleibt eine **lexikalische** Heuristik. Eine Frageform, die
  keines der Signale verwendet, landet bei `basic` – sichtbar an `confidence = "none"`, aber
  unerkannt. Das ist gewollt: Der Fallback ist die belegstärkste Rückfallebene, und die explizite
  Modus-Wahl bleibt gleichwertig.
- **Folgeentscheidungen:** Das Router-Gold-Set ist additiv erweiterbar (weitere Fragetypen oder
  Sprachen ohne Codeänderung). Ein semantischer Router bliebe Gruppe B
  ([ADR 0005](0005-graphrag-index-backend-open.md)).
