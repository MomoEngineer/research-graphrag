# 0023 – Multi-Hop-Evaluation gegen den Zitationsgraphen (Phase 10 / V3): zweite Label-Quelle, strukturelle Ebene, eigenes Baseline-Artefakt

- **Status:** Akzeptiert
- **Datum:** 2026-08-03

## Kontext

[ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md) hat die quantitative Evaluation
etabliert, dabei aber zwei Punkte ausdrücklich **zurückgestellt**: inhaltlich abgeleitete Labels
und fehlende Fragen-*Klassen*. Beides hängt an derselben Lücke: Das Gold-Set
[eval/retrieval-gold.json](../../eval/retrieval-gold.json) enthält ausschließlich **lexikalisch
verankerte** Fragen. Der Fragetyp „Zitations-/Methodennetze (Multi-Hop)" aus dem
README-Contract ist damit **überhaupt nicht gemessen** – obwohl mit den 382 `CITES`-Kanten aus
[ADR 0011](0011-intra-corpus-citation-graph-phase7.md) eine objektive, **nicht-lexikalische** und
mechanisch nachrechenbare Labelquelle bereitliegt. `GoldQuestion` weist seit A6 bewusst die
**Label-Quelle** aus, damit genau solche Quellen additiv danebentreten können.

Die [Roadmap.md](../../Roadmap.md) führt diesen Punkt als **V3**.

### Gemessene Ausgangslage statt Vermutung

Wie in A3–A7 und V1/V2 entstand **vor jeder Code-Änderung** eine Wegwerf-Messung, die zuerst
den **Validitätsanker** reproduzieren musste (145 Paper, 11 181 Chunks, 44 Communities, 382
Kanten, `primitive` 0,882 / 0,650, 65 Zitationsziele, 44 Ziele mit ≥ 3 Zitierenden). Erst danach
wurden die Varianten gemessen. Sechs Befunde prägen die Entscheidungen:

| Befund | Messung | Konsequenz |
| --- | --- | --- |
| **Der Ähnlichkeitsgraph trägt Zitationsnähe.** | Coverage 0,181 bei Selektivität 0,022 ⇒ **Lift 8,20**; zufällige fünf Paper 0,98 | Der Graph-Fan-out ist erstmals **strukturell** beziffert – achtmal treffsicherer als Zufall |
| **Das Ankerpaper verfälscht jede Textmessung.** | MRR 0,428 → **0,701** (Basic/Titel) bzw. 0,449 → **0,821** (Local/Titel), sobald das Ankerpaper aus dem Bündel entfällt | Anker wird **fest** entfernt: Er ist per Konstruktion nie ein erwartetes Paper (keine Selbstzitate), besetzt aber Rang 1 ff. |
| **Die Titel-Anfrage nimmt eine lexikalische Abkürzung.** | **22 von 33** Basic-Treffern und **26 von 42** Local-Treffern stammen aus **Referenz-Chunks** | Die Abkürzung wird nicht versteckt, sondern als **Diagnose** ausgewiesen (`…:ref` / `…:body`) |
| **Die Themen-Anfrage ist die saubere Gegenprobe.** | **0** Treffer aus Referenz-Chunks, dafür deutlich schwerer (Basic 0,250) | Beide Anfrageformen bleiben – die eine misst den Kurzschluss, die andere seine Abwesenheit |
| **Der Fan-out trägt hier real.** | **13 von 28** Treffern der Themen-Anfrage kommen aus dem Fan-out | Der A6-Befund „der Fan-out rettet 1 von 34" war eine Eigenschaft des **fakt-orientierten** Gold-Sets, nicht des Fan-outs |
| **Die Referenz-Diagnose braucht keine Canonical-Dateien.** | `detect_heading(section_title).kind == references` stimmt am realen Korpus **exakt** mit der Canonical-Wahrheit überein (2357 = 2357 Chunks, 11 181/11 181 Übereinstimmung) | Die Evaluation bleibt allein auf `index.sqlite` angewiesen |

**Vorab fixiertes Abbruchkriterium** (nach dem Muster V1/V2): Liefert die strukturelle Ebene nur
Zufallsniveau (Lift ≈ 1,0) **und** stammen über 80 % der Titel-Treffer aus Referenz-Chunks, wird
V3 nicht eingefroren, sondern als dokumentierter Befund abgeschlossen. Gemessen: Lift **8,20**
und 66,7 % / 57,1 % ⇒ das Kriterium **greift nicht**.

### Eine Vorgabe der Roadmap ist logisch nicht erfüllbar

Die Roadmap begründet die hohe Priorität unter anderem damit, V3 mache den in
[ADR 0011](0011-intra-corpus-citation-graph-phase7.md) offen gelassenen **Recall** des
Zitationsgraphen erstmals sichtbar. Das ist **nicht haltbar**: Labels, die *aus* `citation_edges`
abgeleitet sind, können eine **fehlende** Kante nicht aufdecken – sie fehlt in Labels und Messung
gleichermaßen. Belastbarer Recall bräuchte eine unabhängige Wahrheit (Handsichtung von
Referenzabschnitten), die nicht Teil dieses Punktes ist.

## Entscheidung

V3 wird als **zweite, bewusst getrennte Messung** umgesetzt – additiv, deterministisch, offline,
ohne neue Abhängigkeit, **ohne Eingriff in den Retrieval-Contract**, ohne Schema-Änderung und
**ohne Re-Ingest**. Vorbild ist die Router-Messung aus
[ADR 0017](0017-router-hardening-phase7.md): eigenes Gold-Set, eigene Ebenen, eigener Bericht.

### 1. Eigenes Gold-Set mit der Label-Quelle `citation_graph`

- Neues Artefakt [eval/citation-gold.json](../../eval/citation-gold.json), **deterministisch aus
  dem Index erzeugt**: Anker sind alle Paper mit **≥ 3 zitierenden Korpus-Papern** (44 Stück;
  `min_citing` ist Parameter, nicht Zufall), aufsteigend nach `paper_id`, IDs `C01`, `C02`, …
- `expected_paper_ids` = die zitierenden Paper. **Nicht-lexikalisch und nicht kuratiert.**
- Die Fragen werden **nicht** in [eval/retrieval-gold.json](../../eval/retrieval-gold.json)
  aufgenommen. Sonst wanderten sie in die Aggregate von `primitive`/`basic`/`local`/`global`/
  `drift` und die seit [ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md) fortgeschriebene
  Hit/MRR-Reihe wäre nicht mehr vergleichbar.
- **Regenerierbar statt handgepflegt:** `derive_questions` erzeugt das Gold-Set,
  `verify_questions` vergleicht das eingefrorene mit dem neu abgeleiteten. Die CLI bietet beides
  an (`--write-gold`, `--verify-labels`). Ein Gold-Set, das nach einem Korpuszuwachs nicht
  reproduzierbar wäre, würde still verrotten.

### 2. Zwei Anfrageformen aus demselben Rahmen – die eine misst den Kurzschluss, die andere seine Abwesenheit

Beide Formen nutzen denselben Rahmen `Which papers build on {…}?`; **nur die Nutzlast**
unterscheidet sich, damit der Vergleich genau diesen einen Unterschied isoliert:

| Form | Nutzlast | Herleitung |
| --- | --- | --- |
| `title` | der Titel des Ankerpapers | `title_from_uri(source_uri)` – dieselbe Funktion, die auch der Zitationsgraph und der Online-Modus nutzen |
| `topic` | die sechs Top-Terme des Ankerpapers | `keyword_table` aus [overview/drafts.py](../../src/research_graphrag/overview/drafts.py) über den Per-Paper-Korpus – **kein zweiter Keyword-Mechanismus** |

Die Titel-Form ist die realistische Nutzerfrage, nimmt aber nachweislich die Abkürzung über die
Bibliografie der zitierenden Paper. Die Themen-Form vermeidet sie vollständig. Beide zusammen
sind aussagekräftiger als jede allein – deshalb werden **beide** gemessen und die Herkunft jedes
Treffers ausgewiesen.

### 3. Fünf Ebenen plus ein Contract-Test – `get_citations` ist keine Kennzahl

| Ebene | Bündel | Misst |
| --- | --- | --- |
| `graph` | `load_neighbors(Anker)[:k]` – **ohne Textanfrage** | Trägt der Paper-Ähnlichkeitsgraph Zitationsnähe? |
| `basic_title` / `basic_topic` | Zitate der Basic Search | lexikalische Vergleichsbasis |
| `local_title` / `local_topic` | Seeds → Nachbarschaft → Fan-out | der Pfad, den der README-Contract für Multi-Hop vorsieht |

`get_citations` wird **nicht** als Kennzahl geführt: Das Werkzeug liest genau die Tabelle, aus der
die Labels stammen – jede Kennzahl wäre 1,000 *by construction*. Es wird stattdessen als
**Contract-Test** gesichert (Muster: `basic == primitive` aus
[ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md)), und im Bericht steht der triviale
Oberwert als Bezugsgröße.

**Das Ankerpaper wird aus jedem Bündel entfernt** – fest, nicht als Option. Es kann per
Konstruktion nie ein erwartetes Paper sein; es im Bündel zu lassen misst nur, wie weit der
Retriever seinen eigenen Anker vordrängt.

**Diagnose-Vokabular:** `neighbor` (strukturell) · `chunk:ref` / `chunk:body` (Basic) ·
`seed:*`, `neighborhood:*`, `fan_out*` (Local). Das Suffix trennt Belege aus einem
**Referenzabschnitt** von Belegen aus dem **Fließtext** und macht damit den lexikalischen
Kurzschluss sichtbar, statt ihn als Erfolg zu verbuchen.

Für die strukturelle Ebene gilt zusätzlich die Regel aus
[ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md): **Coverage nie ohne Selektivität und
nie ohne Trivial-Baseline**; ausgewiesen wird der **Lift** gegen eine gleich große Zufallsauswahl.

### 4. Eigenes Baseline-Artefakt – und ein Fail-fast, das exakter ist als ein Fingerprint-Feld

- [eval/citation-baseline.json](../../eval/citation-baseline.json) statt Erweiterung der
  bestehenden Baseline. Grund: `compare` verlangt identische Ebenen-Mengen; ein gemeinsames
  Artefakt würde **jeden** `--check` um die vier Textebenen verlängern. Genau davor warnt
  Punkt B3 der Roadmap („eine Messung, die man ungern startet, wird seltener gestartet"). Die
  Roadmap-Formulierung „die Baseline wird um diese Ebene erweitert" wird damit bewusst
  **präzisiert**, nicht ignoriert: Die Ebene bekommt eine Baseline, nur eben ihre eigene.
- Der Fingerprint bleibt **unverändert im Format** (Gold-Set-Version, Index-Schema, Bestand,
  Parameter). Ergänzt wird stattdessen ein **fachlich exakterer Fail-fast**: Vor dem Messlauf
  werden die eingefrorenen Fragen gegen den Index nachgerechnet. Ändern sich die
  `CITES`-Kanten, ohne dass sich Paper- oder Chunk-Zahl ändert (etwa durch eine Änderung an
  `citation_graph.py`), meldet der Check **nicht vergleichbar** – eine Kantenzahl im Fingerprint
  wäre nur ein Näherungssignal gewesen.
- **`eval/retrieval-baseline.json` bleibt unangetastet.** Deshalb bekommt die neue Ebene eigene
  `MultiHopParameters`; `RunParameters` wird **nicht** erweitert, weil das den bestehenden
  Fingerprint invalidiert hätte.

### 5. Eine kleine Entkopplung in `baseline.py`

`read_fingerprint` nimmt statt `GoldSet` und `RunParameters` nur noch die **Gold-Set-Version**
und ein **Parameter-Mapping**. Damit ist `baseline.py` – wie `metrics.py` – frei von Abhängigkeiten
auf Gold-Set und Runner und für beide Messungen gleichermaßen nutzbar. Das **Dateiformat der
Baseline ändert sich nicht**; die eingefrorene Retrieval-Baseline bleibt gültig.

### 6. Der Recall-Anspruch wird korrigiert, nicht behauptet

Statt eines nicht erfüllbaren Recall-Nachweises weist die Messung **mechanische
Recall-Schranken** aus – die Menge, die als Kante **strukturell unerreichbar** ist:

| Schranke | real |
| --- | --- |
| Paper ohne erkannten Referenzabschnitt (können nicht zitieren) | 2 von 145 |
| Titel unter `MIN_TITLE_CHARS`/`MIN_TITLE_WORDS` (kein Titel-Schlüssel) | 3 von 145 |
| ohne frontmatter-belegten Identifikator (kein ID-Schlüssel) | 15 von 145 |
| **als Ziel unerreichbar** (weder Titel- noch ID-Schlüssel) | **1 von 145** |

Das einzige unerreichbare Paper ist `66816ebc0cb33ea9` („Modeling and Discovering
Vulnerabilities") – **dasselbe**, das die QA zu [ADR 0020](0020-online-candidate-search-phase9.md)
unabhängig als Grenze der Online-Deduplikation gefunden hat. Diese Schranken sind eine **obere
Grenze der Vollständigkeit**, kein gemessener Recall; das steht so im Bericht.

### 7. Bewusste Nicht-Ziele

- **Keine Retrieval-Änderung.** Die Messung *bestätigt* den README-Contract („Zitations-/
  Methodennetze → Local (Fan-out) + `get_citations`"): Local schlägt Basic auf dieser Ebene
  deutlich, und der Fan-out trägt messbar. Eine Änderung wäre Aktionismus.
- **Kein MCP-Werkzeug.** Evaluation ist ein Wartungsvorgang, kein Agenten-Werkzeug; der Server
  bleibt bei **acht** Werkzeugen.
- **Kein Tuning** von `k`, `fan_out`, `seeds` oder `min_citing` anhand dieser 44 Fragen
  ([ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md)).
- **Keine Beschleunigung.** Ein voller Zitations-Lauf lädt den Index je Aufruf neu (On-Read,
  [ADR 0010](0010-drop-in-workflow-and-qa-phase6.md)) und dauert dadurch mehrere Minuten. Das ist
  dieselbe bewusste Abwägung wie in [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md);
  die Abhilfe ist Punkt **B3** der Roadmap, nicht dieser Punkt.

## Alternativen

- **Fragen in `eval/retrieval-gold.json` aufnehmen** (wörtliche Roadmap-Lesart). Verworfen: Die
  Aggregate der fünf bestehenden Ebenen würden zwei unvergleichbare Fragetypen mischen und die
  seit A4 fortgeschriebene Kennzahlreihe entwerten.
- **Nur die Titel-Anfrage messen.** Verworfen – gemessen widerlegt: Zwei Drittel der Treffer
  stammen aus der Bibliografie. Die Zahl sähe gut aus und hieße wenig.
- **Nur die Themen-Anfrage messen.** Verworfen: Sie ist die sauberere, aber nicht die
  realistischere Frage. Erst der Kontrast zeigt, **wie viel** der Titel-Erfolg der Bibliografie
  verdankt.
- **`get_citations` als Kennzahl.** Verworfen: tautologisch (1,000 by construction).
- **Ankerpaper im Bündel belassen.** Verworfen – gemessen: kostet 0,27 bzw. 0,37 MRR, ohne je
  einen Treffer beitragen zu können.
- **Referenz-Diagnose aus `data/canonical/`.** Verworfen: Die Näherung über `section_title` ist am
  realen Korpus **exakt** und spart der Evaluation eine Abhängigkeit auf die Extraktionsartefakte.
- **Gemeinsame Baseline mit dem Retrieval-Stand.** Verworfen, siehe Punkt 4 (Laufzeit, B3).
- **`n_citation_edges` in den Fingerprint.** Verworfen zugunsten der exakten Label-Nachrechnung;
  außerdem hätte das Feld die bestehende Baseline-Datei ungültig gemacht.
- **Handgesichtete Multi-Hop-Labels.** Verworfen aus demselben Grund wie in
  [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md): Sie kosten die Nachrechenbarkeit.

## Konsequenzen

- **Positiv:** Der Fragetyp „Multi-Hop" ist erstmals gemessen, mit einer **nicht-lexikalischen**
  und trotzdem nachrechenbaren Labelquelle. Der Paper-Ähnlichkeitsgraph ist erstmals
  **strukturell** beziffert (Lift 8,20). Der A6-Befund „der Fan-out trägt kaum" ist als
  Artefakt des fakt-orientierten Gold-Sets entlarvt. Der lexikalische Kurzschluss über
  Bibliografien ist sichtbar statt versteckt. Zwei der drei in A6 zurückgestellten Punkte
  (inhaltliche Labels, fehlende Fragenklasse) sind eingelöst.
- **Negativ / Aufwand:** Ein weiteres Gold-Set und ein weiteres Baseline-Artefakt sind zu
  pflegen; nach jedem Korpuszuwachs sind beide bewusst neu zu erzeugen. Ein voller Lauf dauert
  mehrere Minuten. Die Kennzahlen der Themen-Form sind niedrig und dürfen nicht als
  Qualitätsurteil über das Retrieval gelesen werden – die Aussagegrenze steht im Bericht.
- **Folgeentscheidungen:** Der Recall des Zitationsgraphen bleibt **offen** (nur Schranken, kein
  Maß) – eine Handsichtung wäre ein eigener Punkt. Die Laufzeit adressiert **B3**. Eine
  Retrieval-Änderung ist bewusst **nicht** abgeleitet.

## Ergebnis nach der Umsetzung

Realer Lauf gegen den unveränderten Korpus (145 Paper, 11 181 Chunks, 382 `CITES`-Kanten),
`python -m scripts.eval_retrieval --zitationen --write-baseline`:

| Ebene | Hit@5 | MRR@5 | Diagnose |
| --- | --- | --- | --- |
| `graph` | 0,591 | 0,475 | neighbor 26 |
| `basic_title` | 0,750 | 0,701 | `chunk:ref` 22 · `chunk:body` 11 |
| `local_title` | **0,955** | **0,821** | Seeds 33 · Nachbarschaft 3 · Fan-out 6 |
| `basic_topic` | 0,250 | 0,239 | `chunk:body` 11 · **`chunk:ref` 0** |
| `local_topic` | 0,636 | 0,538 | Seeds 11 · Nachbarschaft 4 · **Fan-out 13** |

| Strategie | Coverage | Selektivität | Lift |
| --- | --- | --- | --- |
| Ähnlichkeitsgraph (Top-5) | 0,181 | 0,022 | **8,20** |
| zufällige 5 Paper | 0,034 | 0,034 | 0,98 |

Aufgeschlüsselt nach Zitationshäufigkeit des Ankers (Hit@5; Gruppengrößen 17 / 17 / 10):

| Ebene | zitiert 3–4 | zitiert 5–9 | zitiert 10+ |
| --- | --- | --- | --- |
| `graph` | 0,412 | 0,647 | 0,800 |
| `basic_title` | 0,647 | 0,706 | 1,000 |
| `local_title` | 0,941 | 0,941 | 1,000 |
| `basic_topic` | 0,235 | 0,118 | 0,500 |
| `local_topic` | 0,471 | 0,647 | 0,900 |

**Der wichtigste Einzelbefund** ist die Umkehrung gegenüber dem fakt-orientierten Gold-Set: Dort
war Local dem Basic-Modus unterlegen (A6) bzw. erst durch Multi-Seed gleichgezogen
([ADR 0021](0021-local-multi-seed-phase10.md)); auf der Multi-Hop-Ebene schlägt Local den
Basic-Modus deutlich (0,955 vs. 0,750 bei der Titel-Form, 0,636 vs. 0,250 bei der Themen-Form).
Die Struktur zahlt sich genau dort aus, wo der README-Contract sie vorsieht.

**Drei Einschränkungen, offen ausgewiesen:**

1. **Ein Teil des Titel-Erfolgs ist lexikalisch erkauft** – 22 von 33 Basic-Treffern stammen aus
   einem Referenzabschnitt der zitierenden Paper. Belastbar sind vor allem die **Themen-Form**
   (kein einziger Referenz-Treffer) und die **strukturelle Ebene** (gar keine Textanfrage).
2. **Alle Ebenen finden Hubs leichter.** Über die Gruppen steigt Hit@5 durchweg an, bei `graph`
   von 0,412 auf 0,800. Ein Verfahren, das nur stark zitierte Paper fände, sähe im Aggregat
   trotzdem passabel aus – deshalb steht die Aufschlüsselung im Bericht.
3. **Der Recall bleibt offen**, siehe Punkt 6. Die Schranken sind eine Obergrenze.

**Determinismus belegt:** Die Wegwerf-Vorabmessung und der Produktivlauf stimmen auf allen fünf
Ebenen bis auf die dritte Nachkommastelle überein; ein `--check` unmittelbar nach dem Einfrieren
meldet über alle 5 Ebenen und 44 Anker **keine einzige Abweichung**. Die eingefrorene
Retrieval-Baseline bleibt trotz der Signaturänderung an `read_fingerprint` gültig – auch das ist
per `--check` nachgewiesen.

**Umfang:** ein Modul (`evaluation/multihop.py`), ein Renderer, zwei Konstanten in `gold.py`,
zwei neue Artefakte unter `eval/` und vier CLI-Schalter; 36 zusätzliche Tests. Kein
Schema-Eingriff, kein Re-Ingest, keine neue Abhängigkeit, keine Änderung am Retrieval-Contract.
