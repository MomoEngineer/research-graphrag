# 0028 – Grad des Ähnlichkeitsgraphen: `DEFAULT_K = 8` bleibt

- **Status:** Akzeptiert (geprüft und **verworfen** – keine Code-Änderung)
- **Datum:** 2026-08-06

## Kontext

Der Paper-Ähnlichkeitsgraph verbindet jedes Paper über *mutual top-k* mit höchstens
`DEFAULT_K = 8` Nachbarn ([ADR 0007](0007-graphrag-index-phase3-option-b.md)). Dieser Wert stammt
aus einer Zeit, in der der Korpus 145 Paper umfasste; inzwischen sind es **341**.

Bei dieser Dichte hat der Graph **85 isolierte Paper** (24,9 %) – für sie liefert der Fan-out der
Local Search nichts, und in der Community-Ebene erscheinen sie als Einzel-Community. Die Vermutung
lag nahe, dass `k = 8` zu klein geworden ist. Sie stammte aus einem verlorenen Arbeitsstand zur
visuellen Korpus-Exploration (im [ADR-Register](README.md) als Lücke bei `0024` vermerkt) und war
dort als offener Punkt notiert, aber nie gegen die Kennzahlen geprüft.

### Gemessene Ausgangslage statt Vermutung

Nach dem Muster von [ADR 0021](0021-local-multi-seed-phase10.md) und
[ADR 0022](0022-drift-community-union-and-fallback-phase10.md) stand die Messung **vor** der
Entscheidung, und die Entscheidungsregel stand **vor** der Messung.

**Validitätsanker.** Der Paper-Vektorraum wurde aus dem Index rekonstruiert und mit `k = 8` neu
verkantet: 439 Kanten, 115 Communities, 85 Singletons – **exakt** der Live-Index. Erst damit sind
die übrigen Varianten belastbar.

**Befund 1 – die Ähnlichkeitsschwelle ist nicht die Ursache.** **339 von 341** Papern (99,4 %)
haben einen Nachbarn mit Kosinus ≥ 0,10; der Median der besten Ähnlichkeit liegt bei **0,372**.
Eine Änderung der Schwelle von 0,04 auf 0,15 bewegt die Kantenzahl nur von 442 auf 426. Die
Isolation entsteht also **allein durch die Verdrängung im mutual top-k**.

**Befund 2 – k wirkt stark auf die Struktur.**

| k | Kanten | Communities | isoliert | größte Community | Modularität |
| --- | --- | --- | --- | --- | --- |
| **8** (heute) | 439 | 115 | 85 (24,9 %) | 32 (9,4 %) | 0,843 |
| 12 | 735 | 83 | 65 (19,1 %) | 44 (12,9 %) | 0,784 |
| 16 | 1032 | 61 | 45 (13,2 %) | 51 (15,0 %) | 0,728 |
| 20 | 1339 | 46 | 33 (9,7 %) | 66 (19,4 %) | 0,697 |
| 24 | 1643 | 37 | 27 (7,9 %) | 75 (22,0 %) | 0,672 |
| 32 | 2290 | 25 | 16 (4,7 %) | 95 (27,9 %) | 0,621 |

### Vorab fixierte Entscheidungsregel

Gewählt wird das **kleinste** k, das **alle drei** Bedingungen erfüllt:

1. **Keine Verschlechterung.** Auf **beiden** Gold-Sets sinkt weder Hit@k noch MRR@k einer Ebene
   gegenüber `k = 8`.
2. **Spürbare Wirkung.** Die Zahl der isolierten Paper wird mindestens **halbiert** (85 → ≤ 42).
3. **Keine Verwässerung.** Die größte Community bleibt unter **20 %** des Korpus – sonst verliert
   die Community-Ebene die Trennschärfe, von der Global und DRIFT leben.

Erfüllt kein Kandidat alle drei, wird der Punkt **verworfen** und der Befund dokumentiert – wie in
[ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md) die Variante „Stopwords in den
Vektorraum".

Nach der Struktur allein scheiden `k = 16` an Bedingung 2 (45 > 42) und `k = 24` an Bedingung 3
(22,0 %) aus. Gemessen wurden dennoch beide verbliebenen Nachbarn `k = 16` und `k = 20`, damit
Bedingung 1 nicht nur am rechnerischen Sieger geprüft wird. Der Live-Index blieb dabei unberührt:
Je Kandidat entstand eine Kopie, in der ausschließlich die Graph-Tabellen neu gebaut wurden.

## Messergebnis

**Retrieval-Gold-Set 1.3.0, 34 Fragen, hybrid, k = 5:**

| Ebene | k = 8 | k = 16 | k = 20 |
| --- | --- | --- | --- |
| basic / local | 0,824 / 0,736 | 0,824 / 0,736 | 0,824 / 0,736 |
| global | **0,559** / 0,412 | 0,529 / 0,476 | 0,529 / 0,462 |
| drift | 0,588 / 0,472 | 0,706 / 0,604 | 0,706 / 0,633 |
| **Lift der Community-Auswahl** | **5,80** | 3,29 | **2,96** |
| `no_community` | 2 | 8 | 9 |
| `fallback` (DRIFT) | 2 | 8 | 9 |

**Bedingung 1 ist bei beiden Kandidaten verletzt:** Global verliert Hit@5 (0,559 → 0,529). Drei
Beobachtungen erklären, warum das kein Rundungsrauschen ist:

- **Der Lift halbiert sich** (5,80 → 2,96). Die nackte Coverage steigt zwar (0,254 → 0,313), die
  Selektivität aber stärker (0,044 → 0,106). Die Auswahl wird also **größer, nicht besser** –
  genau die Verwechslung, gegen die [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md)
  den Lift eingeführt hat. Zur Einordnung: Die triviale Strategie „nimm die fünf größten
  Communities" liegt bei k = 20 mit Lift 0,87 bereits **unter** Zufallsniveau.
- **Der scheinbare DRIFT-Gewinn ist erkauft.** Hit steigt von 0,588 auf 0,706, aber `fallback`
  steigt gleichzeitig von 2 auf 9: DRIFT liefert häufiger schlicht das Basic-Ergebnis. Dass
  [ADR 0022](0022-drift-community-union-and-fallback-phase10.md) den Fallback **getrennt**
  ausweist, macht das sichtbar; ohne diese Trennung hätte die Zahl einen Fortschritt vorgetäuscht.
- **`no_community` steigt trotz mehr Kanten** (2 → 9). Das ist kontraintuitiv und der Kern des
  Problems: Weniger, dafür größere Communities bedeuten weniger Community-Dokumente mit
  generischeren Keywords. Das Community-Dokument besteht aus zehn Keywords und einer extraktiven
  Zusammenfassung; je heterogener die Mitglieder, desto unschärfer wird es. Der dichtere Graph
  schadet damit **genau der Ebene, die von ihm lebt**.

**Multi-Hop-Gold-Set, 113 Anker** – die Gegenseite, also das, was ein dichterer Graph einbringen
würde: MESSPLATZHALTER

## Entscheidung

**`DEFAULT_K` bleibt bei 8.** Kein Kandidat erfüllt die vorab fixierte Regel; der Punkt wird
verworfen. Es gibt **keine** Code-Änderung, keinen Schema-Eingriff, keinen Re-Ingest und keine
neue Baseline.

Damit bleibt bestehen: 85 Paper (24,9 %) haben keinen Fan-out. Das ist eine **bewusst getragene
Grenze**, keine übersehene Lücke – der Preis für ihre Beseitigung wäre eine messbar schlechtere
Community-Ebene, und die trägt zwei der vier Retrieval-Modi.

Zwei Dinge werden ausdrücklich festgehalten, damit die Frage nicht ein drittes Mal aus derselben
Vermutung heraus gestellt wird:

1. **Die Ähnlichkeitsschwelle ist als Stellschraube erledigt.** Sie bewegt bei dieser Verteilung
   praktisch nichts (442 → 426 Kanten über den gesamten sinnvollen Bereich).
2. **Der Graph ist nicht „zu dünn".** Er trägt Zitationsnähe im gewachsenen Korpus **besser** als
   zuvor: Lift 8,20 → **15,09** ([ADR 0023](0023-multihop-citation-evaluation-phase10.md),
   Nachtrag). Wer aus „Local ist auf dem fakt-orientierten Gold-Set nicht besser als Basic" auf
   einen defekten Graphen schließt, sitzt einem Artefakt der Label-Regel auf.

## Alternativen

**`k` erhöhen und die Community-Erkennung nachziehen** (höhere Louvain-Auflösung, damit die
Communities trotz dichterem Graphen klein bleiben). Verworfen als **Tuning auf 34 Fragen**: Zwei
gekoppelte Parameter gleichzeitig auf ein Gold-Set dieser Größe zu optimieren, ist genau das
Overfitting, das schon in [ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md) und
[ADR 0022](0022-drift-community-union-and-fallback-phase10.md) abgelehnt wurde.

**Die Schwelle senken statt `k` zu erhöhen.** Verworfen, weil gemessen wirkungslos (Befund 1).

**`k` relativ zur Korpusgröße wählen** (etwa `k = ⌈√n⌉`). Verworfen: Eine solche Formel wäre aus
**einem** Datenpunkt abgeleitet und suggeriert eine Gesetzmäßigkeit, für die es keinen Beleg gibt.
Wird der Korpus deutlich größer, ist diese Messung zu wiederholen – das ist billiger und ehrlicher
als eine geratene Skalierung.

**Den Fan-out für isolierte Paper aus dem Zitationsgraphen speisen.** Nicht verworfen, sondern
**außerhalb dieses Punktes**: Das wäre eine fachliche Erweiterung der Local Search (Ähnlichkeit
*oder* Zitation als Nachbarschaftsquelle), kein Parameterwechsel. Sie bräuchte einen eigenen ADR
und eine eigene Messung – der Contract-Unterschied „Ähnlichkeit ≠ Zitation" ist in
[eval/pruef-fragen.md](../../eval/pruef-fragen.md) bewusst herausgestellt.

## Konsequenzen

- **Positiv:** Eine plausible, aber unbelegte Annahme ist widerlegt, bevor sie Code geworden ist.
  Die eingefrorenen Baselines bleiben gültig, es entsteht kein Re-Ingest.
- **Positiv:** Der Zusammenhang „dichterer Graph → unschärfere Community-Dokumente → mehr Fragen
  ohne Community" ist jetzt beziffert. Er ist zugleich ein Argument für den zurückgestellten
  Roadmap-Punkt **V4** (Community-Ranking über die Mitglieds-Chunks statt über zehn Keywords):
  Wäre das Community-Dokument nicht so dünn, könnte ein dichterer Graph seine Wirkung überhaupt
  erst entfalten.
- **Negativ / Aufwand:** Ein Viertel der Paper bleibt ohne Fan-out. Wer zu einem solchen Paper
  verwandte Arbeiten sucht, ist auf `get_citations` und die Chunk-Suche angewiesen.
- **Folgeentscheidungen:** keine. Die Messung ist über den Wegwerf-Aufbau reproduzierbar
  beschrieben; bei deutlich gewachsenem Korpus ist sie zu wiederholen.
