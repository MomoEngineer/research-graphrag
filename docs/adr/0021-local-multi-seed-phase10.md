# 0021 – Local Multi-Seed (Phase 10 / V1): mehrere Anker statt einer Sollbruchstelle

- **Status:** Akzeptiert
- **Datum:** 2026-08-03

## Kontext

Die [Roadmap.md](../../Roadmap.md) beschreibt **Phase 10 / V1** so: Local erreicht Hit@5
**0,618** / MRR **0,532**, Basic dagegen **0,882** / **0,650** – „der Modus, den der
Fragetyp-Contract der README für **Detailfragen** vorsieht, ist damit schwächer als seine eigene
Rückfallebene."

[ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md) hat den Grund belegt und bewusst
nicht behoben: Von den 21 Treffern stammen **17 vom Seed**, 3 aus der Chunk-Nachbarschaft, 1 aus
dem Paper-Fan-out. Das ist kein Ranking-, sondern ein **Strukturproblem** – Nachbarschaft und
Fan-out messen Ähnlichkeit *zum Seed*, nicht *zur Frage*. Ist der eine Seed falsch, ist das
gesamte Bündel verloren, auch wenn die richtige Passage auf Rang 2 stand.

### Gemessene Ausgangslage statt Vermutung

Nach der in [ADR 0013](0013-chunking-refinement-phase7.md), [ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md)
und [ADR 0017](0017-router-hardening-phase7.md) etablierten Reihenfolge lief **vor jeder
Code-Änderung** eine Wegwerf-Simulation gegen den realen Korpus (145 Paper, 11 181 Chunks) und
das Gold-Set 1.2.0 (34 Fragen). Sie bildet den geplanten Produktivpfad nach, ohne ihn zu bauen.

**Validitätsanker:** Die Variante „ein Seed, Fan-out wie bisher" reproduziert die
ADR-0016-Zahlen exakt – Hit **0,618**, MRR **0,532**, Diagnose seed **17** / neighborhood **3** /
fan_out **1**. Erst damit sind die übrigen Zeilen belastbar.

| *m* | Deckelung: erwartetes Paper unter den Top-*m* Seeds | Volles Bündel (Hit / MRR) |
| --- | --- | --- |
| 1 | 17 / 34 | 0,618 / 0,532 |
| 2 | 23 / 34 | 0,706 / 0,596 |
| 3 | **28 / 34** | 0,853 / 0,642 |
| 4 | 29 / 34 | 0,882 / 0,648 |
| 5 | 30 / 34 | **0,912 / 0,654** |
| — | *Referenz Basic (k = 5)* | *0,882 / 0,650* |

Das **Abbruchkriterium der Roadmap** („hebt *m* = 3 die erreichbare Deckelung nicht, entfällt der
Punkt") ist damit klar **nicht** ausgelöst: 17 → 28 von 34.

### Zwei Maßstäbe – und warum das Roadmap-Kriterium allein nicht trägt

Das dort formulierte Kriterium „Local erreicht mindestens die Basic-Werte" ist
**definitorisch erfüllbar**: Gibt Local seine Top-*m*-Chunks als Belege aus, ist sein Bündel bei
*m* = *k* per Konstruktion eine Obermenge von Basics Top-*k*. Es taugt deshalb – wie das
End-to-End-Maß in [ADR 0017](0017-router-hardening-phase7.md) – nur als **Veto**, nicht als
Erfolgsmaß.

| Rolle | Maß | Wirkung |
| --- | --- | --- |
| **Veto** | Nicht-Unterlegenheit gegen Basic auf Hit **und** MRR, zusätzlich je Fragetyp | verhindert, dass die Umstellung Antworten verschlechtert |
| **Substanziell** | Verschiebung der Diagnose-Verteilung + Treffer **jenseits** von Basic@k | zeigt, ob der Anker wirklich robuster wurde |
| **Nie** | Optimierung auf die Aggregatzahl | Die Gold-Labels entstehen mechanisch aus dem Chunk-Text und bevorzugen strukturell die lexikalische Chunk-Suche ([ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md)) |

**Vorab festgelegte Entscheidungsregel** (vor Kenntnis der Zahlen fixiert): gewählt wird das
**kleinste** *m*, das gegenüber Basic auf **beiden** Kennzahlen nicht unterlegen ist. Erreicht
kein *m* das, entscheidet der Zusatznutzen und die Unterlegenheit wird offen ausgewiesen.

Angewandt: *m* = 3 (0,853/0,642) und *m* = 4 (0,882/**0,648**) bleiben unter Basics MRR von
0,650; **erst *m* = 5 ist auf beiden Kennzahlen nicht unterlegen** (0,912/0,654).

## Entscheidung

Local verankert sein Ergebnis an den **Top-5 Chunks der Hybrid-Wertung** statt an einem einzigen.
Die Änderung ist rein **laufzeitseitig**: kein Schema-Eingriff, **kein Re-Ingest**, keine neue
Abhängigkeit, keine Änderung an Index, Graph oder Router.

### 1. Seeds: Top-*m* mit `DEFAULT_SEEDS = 5`

`search_local` liest die Seeds mit **einem** Aufruf `index.search(query, seeds)`. Der Wert 5
folgt der oben angewandten Entscheidungsregel und ist als Modulkonstante neben
`DEFAULT_NEIGHBORHOOD`/`DEFAULT_FANOUT` sichtbar.

### 2. Chunk-Nachbarschaft: je Seed gebildet, per Rang-Fusion zusammengeführt

Für jeden Seed entsteht eine eigene Nachbarschaftsliste (`neighbors_of_chunk`); die Teilranglisten
werden per **Reciprocal Rank Fusion** ([indexing/fusion.py](../../src/research_graphrag/indexing/fusion.py),
[ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md)) zu **einer** Liste verbunden und auf `k`
gekürzt. Chunks, die bereits Seed sind, werden ausgeschlossen – ein Beleg erscheint nie doppelt.
Die Fusion arbeitet über Ränge, weil die Kosinuswerte verschiedener Seeds nicht auf einer
gemeinsamen Skala liegen; Tie-Break bleibt die `chunk_id`.

`k` bleibt die Größe der **gesamten** Nachbarschaft, nicht die je Seed. Andernfalls wüchse das
Bündel mit *m* unkontrolliert, und der Parameter verlöre seine Bedeutung für den Aufrufer.

### 3. Fan-out bleibt unverändert am Ankerpaper – weil der Mehrwert nicht messbar ist

Geprüft wurde die naheliegende Erweiterung „Nachbarn **aller** Seed-Paper vereinigen, je Nachbar
das höchste Kantengewicht": Bei *m* = 5 unterscheidet sie sich auf **0 von 34** Fragen vom
bisherigen Verhalten; über alle gemessenen *m* ändert sich genau **eine** Frage (G14 bei *m* = 2).
Der Fan-out folgt deshalb weiterhin dem Paper des **ersten** Seeds.

Das ist bewusst keine Aussage „die Erweiterung nützt nichts", sondern „ihr Nutzen ist mit dem
heutigen Messapparat **nicht sichtbar**": Der Fan-out steuert bei *m* = 5 null Treffer bei, und
das Gold-Set enthält ausschließlich lexikalisch verankerte Fragen. Erst die Multi-Hop-Labels aus
V3 machen diese Ebene messbar – dort gehört die Frage erneut auf den Tisch.

### 4. Contract: `seed` wird zu `seeds`

`LocalSearchResult.seed: Citation | None` wird zu `seeds: tuple[Citation, ...]`; „kein Treffer"
ist das leere Tupel. Das ist ein **bewusster Bruch** des Output-Schemas von `search_local`
(Spec-Version `0.1.0` → `0.2.0`).

Die additive Alternative (`seed` bleibt als Top-1 stehen, `seeds` tritt daneben) wurde verworfen:
Sie hielte zwei Quellen für dieselbe Information vor und würde den „einen Anker" als Contract
zementieren, den dieser ADR gerade auflöst. Da es außer diesem Repository keine Konsumenten gibt
und der Bruch an genau einer Stelle sichtbar wird, ist der ehrliche Schnitt der billigere.

### 5. Keine erzwungene Paper-Diversität der Seeds

Die Variante „Top-*m* Chunks aus *verschiedenen* Papern" misst **besser** (bei *m* = 5:
0,941 / 0,664 statt 0,912 / 0,654) und wird trotzdem verworfen. Grund ist eine Asymmetrie des
Messapparats: Die Gold-Labels sind **paper-basiert**, ein Paper zählt einmal. Der *Nutzen* der
Diversität ist damit sichtbar, ihr *Preis* nicht – denn sie verdrängt systematisch die
zweitbeste Passage **desselben** Papers, also genau die Evidenz, die eine Detailfrage
(„Welche Methode verwendet Paper X in Abschnitt 4?") braucht. Eine Kennzahl, die den Preis einer
Änderung nicht abbilden kann, darf sie nicht entscheiden – dieselbe Begründung, mit der
[ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md) die Stopword-Variante im
Vektorraum verworfen hat.

### 6. `seeds` wird **nicht** als MCP-Parameter exponiert

CLI (`--seeds`) und Python-API bekommen den Schalter, das Werkzeug `search_local` nicht.
`k` und `fan_out` beantworten „wie viel Evidenz will ich sehen"; `seeds` beantwortet „wie bildet
der Modus seinen Anker" – eine Systemeigenschaft wie die Wertung, die aus demselben Grund nicht
am Werkzeug hängt ([ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md)).

Die Bedingung, unter der diese Entscheidung gekippt wäre, war vorab benannt: Wenn verschiedene
Fragetypen verschiedene *m* brauchen, ist *m* eine Aufrufer-Entscheidung. Gemessen ist das
Gegenteil – *m* = 5 ist in **jeder** Fragenklasse nicht unterlegen (concept 0,80/0,70 · fact
1,00/0,70 · paraphrase 0,71/0,48 gegen Basic 0,80/0,70 · 0,95/0,69 · 0,71/0,48). Ein optionaler
Parameter bliebe zudem jederzeit **additiv** nachrüstbar, während seine Rücknahme ein Bruch wäre.

### 7. Baseline: erst der qid-genaue Nachweis, dann der Neufreeze

Der Nachweis läuft zweistufig, damit die eingefrorene Baseline nicht ihre Beweiskraft verliert:

1. **Mit unverändertem `RunParameters`** – der Fingerprint bleibt identisch, `--check` vergleicht
   qid-genau und zeigt, was sich auf der Ebene `local` ändert **und** dass Primitive, Basic,
   Global und DRIFT unberührt bleiben.
2. **Danach** wandert `seeds` in `RunParameters` (der Fingerprint ändert sich damit
   zwangsläufig), und die Baseline wird mit den neuen Werten eingefroren.

## Ergebnis nach der Umsetzung (realer Korpus)

Gemessen mit `python -m scripts.eval_retrieval --modi` gegen den Live-Index (145 Paper, 11 181
Chunks, 44 Communities, Gold-Set 1.2.0, Wertung `hybrid`):

| Ebene | vorher | nachher |
| --- | --- | --- |
| `primitive` | 0,882 / 0,650 | **unverändert** |
| `basic` | 0,882 / 0,650 | **unverändert** |
| `local` | 0,618 / 0,532 — seed 17, neighborhood 3, fan_out 1 | **0,912 / 0,654** — seed 30, neighborhood 1, fan_out 0 |
| `global` | 0,353 / 0,269 | **unverändert** |
| `drift` | 0,235 / 0,235 | **unverändert** |

Die realen Zahlen decken sich **exakt** mit der Vorabsimulation – inklusive der Diagnose-Zählung.

**Der qid-genaue Nachweis** (`--check` gegen die alte Baseline, Fingerprint unverändert): **0
Regressionen**, 13 Verbesserungen (davon 9 „kein Treffer → Treffer"), **1 ausgewiesene
Verschlechterung** (G11: Rang 2 → 9, Treffer bleibt erhalten) – und **keine einzige** Abweichung
auf den Ebenen `primitive`, `basic`, `global`, `drift`. Damit ist belegt, dass die Änderung
ausschließlich Local betrifft.

Anschließend wurde `seeds` in die Messparameter aufgenommen und die Baseline neu eingefroren; ein
`--check` direkt danach meldet **keine Abweichung** (Determinismus).

## Alternativen

| Alternative | Warum verworfen |
| --- | --- |
| **Punkt entfällt** (Abbruchkriterium der Roadmap) | Nicht ausgelöst: *m* = 3 hebt die Deckelung von 17 auf 28 von 34. |
| ***m* = 3** wie in der Roadmap vorgeschlagen | Bleibt mit 0,853 / 0,642 unter Basic – der Modus bliebe seiner Rückfallebene unterlegen und M7 unerfüllt. |
| **Seeds nur als Anker, nicht als Beleg** (die Top-*m* würden nicht ausgegeben) | Absurd für den Nutzer: Die besten Passagen zur Frage zurückzuhalten, um eine Kennzahl „ehrlicher" zu machen, verschlechtert die Antwort. |
| **Score-basierte Fusion statt RRF** | Kosinuswerte verschiedener Seeds sind nicht vergleichbar; dieselbe Begründung wie in [ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md). |
| **`k` je Seed statt insgesamt** | Das Bündel wüchse mit *m* auf bis zu 25 Nachbarn; `k` verlöre seine Bedeutung. |
| **Iteratives Nachfassen (echtes DRIFT-artiges Local)** | Außerhalb des V1-Zuschnitts; bleibt Zielbild. |

## Konsequenzen

- **Positiv:** Der Modus ist seiner eigenen Rückfallebene nicht länger unterlegen (M7). Die
  Sollbruchstelle „ein Seed" ist beseitigt – die Diagnose verschiebt sich von seed **17** auf
  **30** von 34. Eine Frage (G11) findet Local, die Basic@5 verfehlt.
- **Negativ / Aufwand:** Der Zugewinn ist **überwiegend definitorisch** – Local enthält jetzt
  Basics Top-5. Nachbarschaft (1 Treffer) und Fan-out (0) tragen zur Kennzahl kaum bei; ihr Wert
  ist Kontext, nicht Trefferquote, und bleibt mit diesem Gold-Set ungemessen.
- **Negativ / Aufwand:** **Eine Frage verschlechtert sich qid-genau** – G11 rutscht von Rang 2 auf
  Rang 9, weil vier zusätzliche Seeds vor dem Nachbarschaftstreffer stehen. Der Treffer bleibt
  erhalten (keine Regression im Sinne der Baseline), die Verschlechterung wird ausgewiesen.
- **Negativ / Aufwand:** Ein Aufruf kostet bei geladenem Index **0,07 s → 0,18 s** (fünf statt
  einer Chunk-Nachbarschaftsberechnung). Gegenüber dem Index-Ladevorgang (~2,2 s) fällt das nicht
  ins Gewicht; die Ladezeit selbst ist Gegenstand von Phase 11 / B3.
- **Negativ / Aufwand:** Bruch des `search_local`-Output-Schemas (siehe Punkt 4) mit Nachzug in
  Spec, Modul-Doku, CLI, QS-Harness, Evidenz-Adapter und Tests.
- **Folgeentscheidungen:** [ADR 0008](0008-retrieval-and-query-router-phase4.md) wird in der
  Local-Definition abgelöst (Nachtrag dort). V3 (Multi-Hop-Labels) nimmt die Fan-out-Frage aus
  Punkt 3 erneut auf.

## Grenzen (offen ausgewiesen)

- **Drei Fragen bleiben ohne Treffer** (G15, V13, V15) – zwei Paraphrasen und eine Konzeptfrage.
  Sie scheitern bereits an der Chunk-Primitive; mehr Seeds können daran nichts ändern.
- **Der Fan-out ist mit diesem Gold-Set nicht bewertbar.** Er steuert bei *m* = 5 null Treffer bei.
  Das ist kein Beleg gegen ihn, sondern eine Messgrenze (siehe V3).
- **Die Nicht-Unterlegenheit gegen Basic ist bei *m* = *k* teilweise strukturell** und darf nicht
  als Beleg für „besseres Retrieval" gelesen werden (siehe „Zwei Maßstäbe").
