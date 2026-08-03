# 0022 – DRIFT: Vereinigung der Top-*m* Communities und sichtbarer Basic-Fallback (Phase 10 / V2)

- **Status:** Akzeptiert
- **Datum:** 2026-08-03

## Kontext

Die [Roadmap.md](../../Roadmap.md) beschreibt **Phase 10 / V2** so: DRIFT erreicht **0,235 / 0,235**,
und die Diagnose aus [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md) ist ungewöhnlich
eindeutig – Treffer (8) und erreichbare Deckelung (8) sind **identisch**. Die lokale Verfeinerung
arbeitet also fehlerfrei; **100 %** der Fehlschläge entstehen davor, in der Community-Wahl:
**12×** wurde gar keine Community gefunden, **14×** die falsche.

Vorgeschlagen sind zwei Maßnahmen: (a) die Kandidatenmenge aus den Top-*m* Communities
vereinigen statt nur der besten, (b) bei fehlender Community sichtbar auf Basic zurückfallen –
dasselbe Muster, das [ADR 0017](0017-router-hardening-phase7.md) im Router etabliert hat.

### Warum die vorgegebenen Akzeptanzkriterien nicht als Erfolgsmaß taugen

Beide sind **rechnerisch vorbestimmt**, nicht verdient:

- DRIFTs erreichbare Deckelung bei *m* Communities **ist definitionsgemäß** Globals
  `in_community` bei *n* = *m*. Global steht bei fünf Communities auf **12** – die geforderte
  „Deckelung ≥ 12" tritt allein dadurch ein, dass *m* = 5 gewählt wird.
- „`no_community` geht auf 0" ist trivial erfüllt, sobald ein Fallback existiert.

Gemessen wurde deshalb an zwei anderen Fragen – und die erste davon ist ein **Regressionsrisiko**,
das die Vorgabe nicht benennt: Die heutige Fehlerfreiheit der Verfeinerung („Treffer ==
Deckelung") beruht darauf, dass sie über die Mitglieder **einer** Community rankt. Mit der
Vereinigung rankt sie über ein Vielfaches – sie kann Fragen verlieren, die sie heute gewinnt.

| Rolle | Maß |
| --- | --- |
| **Steuernd** | Erhöht die Vereinigung die **Treffer**, ohne eine heute gewonnene Frage zu verlieren? |
| **Ehrlichkeits-Auflage** | Der Fallback-Beitrag wird **getrennt** ausgewiesen – er ist Basic, nicht DRIFT |
| **Nie** | Die Aggregatzahl als Erfolg lesen: Der Fallback allein hebt sie um mehr als das Doppelte |

**Vorab festgelegte Entscheidungsregel** (vor Kenntnis der Zahlen fixiert, Raster
*m* ∈ {1, 2, 3, 5}): das **größte** *m*, das die Treffer erhöht, **ohne** eine heute gewonnene
Frage zu verlieren; bei Gleichstand das kleinere *m*.

### Gemessene Ausgangslage statt Vermutung

Wegwerf-Simulation gegen den realen Korpus (145 Paper, 11 181 Chunks, 44 Communities, Gold-Set
1.2.0, `drift_k = 6`). **Validitätsanker:** *m* = 1 ohne Fallback reproduziert die
ADR-0016-Zahlen exakt – Hit **0,235**, MRR **0,235**, `in_community` **8** / `community_missed`
**14** / `no_community` **12**, Deckelung **8**, Selektivität **0,021**.

| *m* | Deckelung | Treffer | Hit | MRR | Selektivität |
| --- | --- | --- | --- | --- | --- |
| 1 | 8 / 34 | 8 | 0,235 | 0,235 | 0,021 |
| 2 | 9 / 34 | 9 | 0,265 | **0,221** | 0,039 |
| 3 | 9 / 34 | 9 | 0,265 | **0,221** | 0,046 |
| **5** | **12 / 34** | **11** | **0,324** | **0,256** | 0,070 |

**Verluste: keine.** Bei keinem *m* verliert die Verfeinerung eine heute gewonnene Frage. Zwei
Fragen rutschen um einen Rang (G13 und V12 jeweils 1 → 2) – das ist der gesamte Preis.

Bemerkenswert ist die **MRR-Delle**: *m* = 2 und *m* = 3 gewinnen zwar eine Frage, verschlechtern
den MRR aber gegenüber *m* = 1. Nur *m* = 5 verbessert **beide** Kennzahlen. Die vorab fixierte
Regel und die Kennzahlen zeigen damit in dieselbe Richtung.

### Drei Befunde, die die Vorgabe nicht vorhergesehen hat

**1. Die Vereinigung kann nur bei 15 von 34 Fragen überhaupt wirken.** Für **12** Fragen scort
*keine* Community über 0, für weitere **7** genau **eine**. Der Engpass ist damit nicht die Zahl
der berücksichtigten Communities, sondern das **dünne Community-Dokument** (zehn Keywords plus
eine kurze extraktive Zusammenfassung) – exakt die Hypothese von **V4**. V2 behandelt insoweit ein
Symptom; der Fallback bleibt aber auch nach V4 gerechtfertigt, weil er eine **Garantie** ist und
keine Rankingverbesserung.

**2. „Treffer == Deckelung" gilt nicht mehr.** Bei *m* = 5 stehen 11 Treffer einer Deckelung von
12 gegenüber. Die eine Lücke ist **G15**: Die Kandidatenmenge wächst dort auf **33** Paper, und
die erwarteten Paper landen nicht mehr unter den ersten sechs Chunks. Die in
[ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md) gefeierte Fehlerfreiheit der
Verfeinerung war also eine Eigenschaft der **engen** Kandidatenmenge, keine Eigenschaft des
Verfahrens.

**3. Der Fallback trägt die Hälfte der Treffer – und zwar als Basic.** Mit *m* = 5 und Fallback:
Hit **0,647**, MRR **0,525**; der Fallback greift **12×** und trifft dabei **11×**. Von 22
Treffern stammen damit **11 aus Basic**. Eine Aggregatzahl ohne diese Aufteilung wäre eine Lüge
mit Nachkommastellen.

## Entscheidung

DRIFT sucht in der **Vereinigung der Top-5 Communities** und fällt sichtbar auf die Basic-Suche
zurück, wenn dieser Pfad keine Belege liefert. Die Änderung ist rein **laufzeitseitig**: kein
Schema-Eingriff, **kein Re-Ingest**, keine neue Abhängigkeit, kein Eingriff in Index, Graph oder
Router.

### 1. `DEFAULT_COMMUNITIES = 5` – und warum nicht 8

Eine **nachgelagerte** Messung (außerhalb des vorab fixierten Rasters) zeigt bei *m* = 8 einen
weiteren Treffer und einen besseren MRR (13 / 12 / 0,285), bei *m* = 10 und *m* = 20 dagegen
keinen weiteren Gewinn mehr (12 Treffer, MRR 0,262). **Gewählt wird trotzdem 5**, aus drei
Gründen:

- Der Unterschied beträgt **eine Frage von 34**. Einen Parameter darauf zu optimieren ist genau
  das Overfitting, das [ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md) für `K` und die
  Fusionsgewichte ausdrücklich abgelehnt hat.
- Der Wert wurde **nach** Kenntnis der Ergebnisse ins Raster genommen; ihn zu wählen hieße, die
  vorab fixierte Regel nachträglich zu dehnen.
- 5 hat eine **strukturelle** Begründung statt einer getunten: Es ist der Default der Global
  Search (`DEFAULT_TOP_COMMUNITIES`). Beide Modi sehen damit dieselbe Community-Auswahl, und
  DRIFTs Deckelung ist per Konstruktion Globals Trefferzahl – das macht die beiden Ebenen
  vergleichbar, statt sie auseinanderlaufen zu lassen.

Die Selektivität bleibt mit **0,070** klein (im Mittel rund zehn von 145 Papern): DRIFT bleibt
eine **Auswahl**, keine verkappte Korpussuche.

### 2. Schlichte Vereinigung statt Fusion je Community

Die Mitglieder aller gewählten Communities bilden **eine** Kandidatenmenge, in der die
Chunk-Wertung entscheidet. Die Alternative – je Community ranken und per Rang-Fusion verbinden –
wurde verworfen: Sie bevorzugte kleine Communities systematisch (in einer Einer-Community ist
jeder Chunk auf Rang 1) und hätte einen zweiten, nur hier gültigen Ranking-Mechanismus
eingeführt. Die Community-Rangfolge wirkt damit **nur noch über die Zugehörigkeit**, nicht mehr
über die Reihenfolge der Belege – ein bewusster Verzicht zugunsten eines einzigen,
nachvollziehbaren Kriteriums.

### 3. Fallback: eine Regel, ein sichtbares Feld

Der Fallback greift, wenn der Community-Pfad **keine Belege** liefert. Das ist bewusst **eine**
Regel statt zweier: Ob gar keine Community gefunden wurde oder ob eine gefundene Community keinen
passenden Chunk enthält, ist für den Nutzer derselbe Defekt – eine leere Antwort. Am realen
Korpus tritt der zweite Fall **null**-mal auf; die breitere Regel kostet also nichts und schließt
eine Lücke, bevor sie auftritt.

Die Belege stammen dann aus der Chunk-Suche **ohne** Paper-Filter – derselbe Pfad, den die Basic
Search nutzt (per Contract-Test belegt). Ausgewiesen wird das durch **ein** zusätzliches Feld
`fallback: bool` im Ergebnis; CLI und Werkzeug machen es sichtbar. Ein Router-artiges Trio aus
Konfidenz, Signalen und Begründung wäre überdimensioniert – es gibt genau **einen** Grund.

### 4. Ein defekter Index bleibt ein Fehler

Fehlt der Graph oder enthält der Index keine Communities, bleibt es bei `constraint_violation`.
Der Fallback ist eine Antwort auf **fehlende Übereinstimmung**, nicht auf einen **kaputten
Zustand** – sonst würde ein unvollständiger Index klammheimlich als „DRIFT ohne Community"
durchgehen.

### 5. Contract: `community` wird zu `communities`, plus `fallback`

`DriftSearchResult.community: CommunityMatch | None` wird zu
`communities: tuple[CommunityMatch, ...]`; neu ist `fallback: bool`. Spec-Version `0.1.0` →
`0.2.0`.

Der Bruch ist hier nicht Kosmetik, sondern eine **Provenienz-Frage** und damit vom Leitprinzip 1
des [CONTRIBUTING](../../CONTRIBUTING.md) gedeckt: Würde weiterhin nur die beste Community
ausgewiesen, während die Belege aus der Vereinigung von bis zu fünf stammen, behauptete die
Antwort eine Herkunft, die nicht stimmt. Die additive Variante (`community` bleibt als Top-1
stehen, `communities` tritt daneben) wurde deshalb verworfen: Sie hielte zwei Quellen für dieselbe
Information vor und lüde dazu ein, die falsche zu lesen.

### 6. Evaluation: der Fallback wird getrennt ausgewiesen

Das Diagnose-Vokabular der DRIFT-Ebene lautet künftig
`in_community | community_missed | fallback`. `no_community` entfällt dort, weil dieser Zustand
seit der Umstellung nicht mehr auftreten kann – für Global bleibt es unverändert. Damit zeigt der
Bericht unmittelbar, **wie viele Treffer aus dem Fallback stammen**, und die Aggregatzahl bleibt
interpretierbar, auch wenn V4 die Community-Auswahl später verändert.

### 7. Bewusst **keine** CLI-Option – vorerst

Anders als die Zahl der Local-Seeds (`--seeds`, [ADR 0021](0021-local-multi-seed-phase10.md))
bekommt `communities` **keinen** CLI-Schalter. Der Grund ist keine Prinzipienfrage, sondern eine
konkrete Fehlerquelle: Die Modi teilen sich in `generation/answer.py` **eine** Abbildung
`EVIDENCE_BUILDERS` mit positionaler Signatur. Ein zweiter Parameter desselben Typs (`int`)
direkt neben `seeds` wäre dort still vertauschbar – ein Fehler, den weder mypy noch ein Test
zuverlässig fängt. Die saubere Abhilfe wäre ein Options-Objekt statt einer wachsenden
Positionsliste; das ist ein Refactoring außerhalb des V2-Zuschnitts. Bis dahin bleibt der
Parameter der Python-API vorbehalten – die Asymmetrie ist bewusst und dokumentiert, kein
Versehen.

## Ergebnis nach der Umsetzung (realer Korpus)

Gemessen mit `python -m scripts.eval_retrieval --modi` gegen den Live-Index (145 Paper, 11 181
Chunks, 44 Communities, Gold-Set 1.2.0, Wertung `hybrid`):

| Ebene | vorher | nachher |
| --- | --- | --- |
| `primitive` | 0,882 / 0,650 | **unverändert** |
| `basic` | 0,882 / 0,650 | **unverändert** |
| `local` | 0,912 / 0,654 | **unverändert** |
| `global` | 0,353 / 0,269 | **unverändert** |
| `drift` | 0,235 / 0,235 — in_community 8, community_missed 14, no_community 12 | **0,647 / 0,525** — in_community **12**, community_missed 10, **fallback 12** |

Die realen Zahlen decken sich **exakt** mit der Vorabsimulation, inklusive der Diagnose-Zählung.
**Zu lesen ist die Zeile so:** Von den 22 Treffern stammen 11 aus dem Community-Pfad und 11 aus
dem Fallback – die Aggregatzahl ist damit **kein** DRIFT-Ergebnis allein.

**Der qid-genaue Nachweis** (`--check` gegen die alte Baseline, Fingerprint unverändert):
**0 Regressionen**, 14 Verbesserungen (allesamt „kein Treffer → Treffer"), **2 ausgewiesene
Verschlechterungen** (G13 und V12 jeweils Rang 1 → 2) – und **keine einzige** Abweichung auf den
Ebenen `primitive`, `basic`, `local`, `global`. Damit ist belegt, dass die Änderung ausschließlich
DRIFT betrifft.

Anschließend wurde `drift_n` in die Messparameter aufgenommen und die Baseline neu eingefroren;
ein `--check` direkt danach meldet **keine Abweichung** (Determinismus).

## Alternativen

| Alternative | Warum verworfen |
| --- | --- |
| ***m* = 8** (misst am besten) | Overfitting auf 34 Fragen und post-hoc gefundenes Raster; siehe Punkt 1. |
| ***m* = 2 oder 3** | Gewinnen eine Frage, **verschlechtern** aber den MRR gegenüber heute. |
| **Rang-Fusion je Community** statt Vereinigung | Bevorzugt kleine Communities systematisch; zweiter Ranking-Mechanismus ohne belegten Nutzen. |
| **Fallback nur bei fehlender Community** | Lässt den Fall „Community da, keine Belege" offen – derselbe sichtbare Defekt, ohne Gegenwert. |
| **Fallback im Router statt im Modus** | Ein expliziter Aufruf `--mode drift` kennt keinen Router; der Defekt bliebe dort bestehen. |
| **Fallback auch bei kaputtem Index** | Würde einen Fehlerzustand verschleiern (Punkt 4). |
| **Keine Änderung, erst V4 abwarten** | Die leere Antwort bei 12 von 34 Fragen ist ein realer Nutzungsdefekt; die Garantie bleibt auch nach V4 sinnvoll. |

## Konsequenzen

- **Positiv:** DRIFT liefert nie mehr eine leere Antwort, solange die Basic-Suche etwas findet.
  Die erreichbare Deckelung steigt von **8 auf 12**, die Treffer des Community-Pfades von
  **8 auf 11** – ohne eine einzige verlorene Frage.
- **Negativ / Aufwand:** Die **Hälfte** der Treffer stammt aus dem Fallback und damit aus Basic.
  Wer die Aggregatzahl ohne die Diagnose liest, überschätzt DRIFT.
- **Negativ / Aufwand:** Zwei Fragen verlieren einen Rang (G13, V12 – jeweils 1 → 2). Der Treffer
  bleibt erhalten; die Baseline weist die Verschiebung aus.
- **Negativ / Aufwand:** Die Eigenschaft „Treffer == Deckelung" aus
  [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md) ist aufgegeben (11 von 12).
- **Negativ / Aufwand:** Bruch des `search_drift`-Output-Schemas mit Nachzug in Spec, Modul-Doku,
  CLI, QS-Harness und Tests.
- **Folgeentscheidungen:** [ADR 0008](0008-retrieval-and-query-router-phase4.md) wird in der
  DRIFT-Definition abgelöst (Nachtrag dort). **V4** wird die hier gemessenen Zahlen verschieben,
  weil es dieselbe Community-Auswahl betrifft – deshalb die getrennte Ausweisung.

## Grenzen (offen ausgewiesen)

- **Der Engpass bleibt die Community-Auswahl.** Für 12 von 34 Fragen scort keine Community über
  0, für 7 weitere genau eine. V2 hebt die Deckelung, wo Spielraum besteht; den Spielraum selbst
  schafft erst V4.
- **Die Kandidatenmenge kann groß werden.** Im Mittel sind es rund zehn Paper, im Einzelfall
  (G15) **33** – dort scheitert die Verfeinerung erstmals trotz erreichter Deckelung.
- **Der Fallback ist Basic, nicht DRIFT.** Er behebt einen Nutzungsdefekt, keine
  Retrieval-Schwäche.
