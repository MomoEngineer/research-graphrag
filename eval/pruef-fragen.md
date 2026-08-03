# Prüf-Fragen-Set

Pragmatisches, festes Frageset zur Qualitätssicherung über alle **fünf Fragetypen** (siehe [README.md](../README.md)). Es dient als wiederholbare Stichprobe: Liefert der Assistent eine plausible Antwort **mit korrekter Provenienz** (Paper, Abschnitt, Seite/Chunk)?

> **Status Phase 4:** Konkrete, auf den migrierten Korpus (145 Paper) bezogene Fragen sind ergänzt und einmal über die CLI (`python -m scripts.ask "<frage>" [--mode …]`) durchgespielt. Die **Befund**-Spalte hält das Ergebnis der Stichprobe fest (Index-Stand: Schema 0.2.0 mit Abschnitts-Provenienz). Die Modi entsprechen [ADR 0008](../docs/adr/0008-retrieval-and-query-router-phase4.md); ab **Phase 5** werden dieselben Modi als MCP-Tools in Copilot geprüft.

> **Status Phase 6:** Dasselbe Set ist jetzt **wiederholbar** als QS-Harness `python -m scripts.qa` hinterlegt (Single Source of Truth: `QUESTIONS` in [scripts/qa.py](../scripts/qa.py)); ein struktureller Regressionstest ([tests/retrieval/test_qa.py](../tests/retrieval/test_qa.py)) sichert die Provenienz-Form. Erneuter Durchlauf am Korpus (Index-Schema **0.3.0**) liefert für **alle 10 Fragen belegte Provenienz (10/10)**; die Befunde decken sich mit Phase 4 (u. a. D1 → „Datasets and Evaluation Metrics", W1 → Community #0/„Overall Comparison (RQ1)", W2 → Community #11 „agentic/vectorrag"). Vereinzeltes **Abschnitts-Rauschen** einzelner Treffer (z. B. „20.09 20.15", OCR-Ligaturen) bleibt die bekannte Heuristik-Grenze ([ADR 0006](../docs/adr/0006-canonical-model-phase2-scope.md)), kein Retrieval-Fehler ([ADR 0010](../docs/adr/0010-drop-in-workflow-and-qa-phase6.md)).

> **Status Phase 7 / A3:** Nach der Chunking-Verfeinerung ([ADR 0013](../docs/adr/0013-chunking-refinement-phase7.md), Index-Schema **0.4.0**) liefert `python -m scripts.qa` weiterhin **10/10** belegte Antworten. Sichtbar geändert hat sich die **Provenienz-Form**: Chunks, die über einen Seitenumbruch laufen, werden als Range angezeigt („Seiten 10–11"); die Abschnittstitel sind spürbar sauberer (u. a. „Datasets and Evaluation Metrics", „Code Knowledge Base Construction", „Multi-path Code Retrieval"). Restliches Titel-Rauschen (z. B. „Gpt", „F1 =2 ·P ·R") bleibt der Keyword-/Titel-Bereinigung in **A5** vorbehalten.

> **Status Phase 7 / A4:** Dieses Set bleibt die **qualitative** Stichprobe (Provenienz-Sichtprüfung). Ergänzend gibt es jetzt eine **quantitative** Messung: das versionierte Gold-Set [`retrieval-gold.json`](retrieval-gold.json) (34 Fragen, Labels **mechanisch aus dem Chunk-Text abgeleitet** und über `python -m scripts.eval_retrieval --verify-labels` nachrechenbar) sowie der Harness `python -m scripts.eval_retrieval` (Hit@k/MRR je Wertung). Damit wurde die Hybrid-Wertung belegt: Hit@5 **0,735 → 0,882**, bei Fakt-Fragen **0,773 → 0,955** ([ADR 0014](../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)). `python -m scripts.qa` liefert unverändert **10/10** belegte Antworten. Der Harness misst die geteilte Chunk-Primitive, nicht die Modi als Ganzes – die Ausweitung bleibt **A6**.

> **Status Phase 7 / A5:** Nach der Rausch-Reduktion ([ADR 0015](../docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)) liefert `python -m scripts.qa` weiterhin **10/10** belegte Antworten. Das in A3 hier notierte Titel-Rauschen ist adressiert: Abschnittstitel mit URL-/DOI-Marken, `et al`, Code-Zeichen oder Satzpunkt-Ende gibt es nicht mehr (**267 → 0** verdächtige Titel), und OCR-Ligaturen sind repariert statt sichtbar. Community-Keywords enthalten kein `et`/`al`/`arxiv`/Jahreszahl-Rauschen mehr. **Ehrlich bleibt:** numerierte Fließtextreste ohne Rauschmerkmal überleben weiterhin als Abschnittstitel (z. B. „CODEBERT-RAG: Retrieves nodes using") – sie zu erkennen wäre eine semantische Prüfung. Das Gold-Set steht auf **1.2.0** (zwei Labels wurden neu abgeleitet, weil eine zuvor als Überschrift gelesene URL-Zeile wieder im durchsuchbaren Chunk-Text liegt).

> **Status Phase 7 / A6:** Die in A4 offen gebliebene Ausweitung auf die **Modi als Ganzes** ist umgesetzt ([ADR 0016](../docs/adr/0016-quantitative-retrieval-evaluation-phase7.md)): `python -m scripts.eval_retrieval --modi` misst zusätzlich Local (inkl. Baustein-Beitrag), die Community-Auswahl (Coverage **nur** mit Selektivität und Trivial-Baselines) und DRIFT (inkl. Deckelung). Dieses Set bleibt die **qualitative** Stichprobe; die quantitative Ergänzung läuft optional im selben Kommando (`python -m scripts.qa --quantitativ`) und meldet Regressionen **qid-genau** gegen [`retrieval-baseline.json`](retrieval-baseline.json). **Für die Sichtprüfung relevant:** Die Messung erklärt, warum die Local-Fragen (D1/D2/N1/N2) manchmal thematisch abdriften – das gesamte Bündel hängt an einem Top-1-Seed –, und dass die DRIFT-Fragen (W1/W2) an der **Community-Wahl** scheitern, nicht an der Verfeinerung. `python -m scripts.qa` liefert unverändert **10/10** belegte Antworten.

> **Status Phase 7 / A7:** Der **Auto-Router** trifft dieses Set jetzt vollständig ([ADR 0017](../docs/adr/0017-router-hardening-phase7.md)): Vor der Härtung wählte er nur bei **6 von 10** Fragen den vorgesehenen Modus – S2 („thematic clusters") und N2 („works relate to") fielen mangels Signal auf den Default, D1/D2 ebenso. Nach der Härtung sind es **10/10** im Sinne des README-Contracts (streng 8/10: D1/D2 landen auf `basic`, was die README für Detailfragen ausdrücklich zulässt – die `mode`-Angabe in [scripts/qa.py](../scripts/qa.py) ist eine **explizite** Vorgabe für die Stichprobe, kein Router-Label). Die Modus-Wahl ist jetzt nachvollziehbar: `python -m scripts.ask` nennt Modus, **Konfidenzstufe** und die auslösenden Signale. Gemessen wird der Router separat über `python -m scripts.eval_retrieval --router` gegen [`router-gold.json`](router-gold.json); dieses Set hier bleibt die qualitative Provenienz-Stichprobe.

> **Status Phase 10 / V1:** Die in A6 notierte Ursache des thematischen Abdriftens der Local-Fragen (D1/D2/N1/N2) ist behoben: Local verankert sein Ergebnis nicht mehr an **einem** Seed, sondern an den **Top-5** der Chunk-Wertung; die Chunk-Nachbarschaft entsteht je Seed und wird rang-fusioniert ([ADR 0021](../docs/adr/0021-local-multi-seed-phase10.md)). Der Modus liegt damit nicht mehr hinter Basic (Hit 0,618 → **0,912**, MRR 0,532 → **0,654**). Für die Sichtprüfung heißt das: Die Local-Antworten zeigen jetzt mehrere Anker-Passagen statt einer; die Fan-out-Nachbarn folgen weiterhin dem **ersten** Seed. `python -m scripts.qa` liefert unverändert **10/10** belegte Antworten.

> **Status Phase 10 / V2:** Auch die in A6 notierte Ursache der DRIFT-Fragen (W1/W2) ist adressiert: DRIFT sucht nicht mehr in **einer** Community, sondern in der **Vereinigung der Top-5**, und fällt bei fehlender Community sichtbar auf die corpusweite Suche zurück ([ADR 0022](../docs/adr/0022-drift-community-union-and-fallback-phase10.md)). Für die Sichtprüfung heißt das: Die DRIFT-Antworten nennen jetzt mehrere Communities als Kontext, und eine **leere** Antwort gibt es nicht mehr – dafür muss man auf den Hinweis „Rückfall auf die corpusweite Suche" achten, denn dort sind die Belege **nicht** auf Community-Mitglieder beschränkt. Hit 0,235 → **0,647**, MRR 0,235 → **0,525** – wovon allerdings die Hälfte der Treffer aus dem Fallback stammt. `python -m scripts.qa` liefert unverändert **10/10** belegte Antworten.

> **Status Phase 10 / V3:** Die Fragen des Abschnitts 3 (Zitations-/Methodennetze) sind jetzt auch **quantitativ** gedeckt – bislang war das der einzige Fragetyp ohne Kennzahl. `python -m scripts.eval_retrieval --zitationen` misst 44 Ankerpaper gegen die `CITES`-Kanten ([ADR 0023](../docs/adr/0023-multihop-citation-evaluation-phase10.md)). Zwei Dinge, die für die **Sichtprüfung** dieses Sets wichtig sind: (1) Der Hinweis unten – „Ähnlichkeit ≠ Zitation" – ist bestätigt, aber differenzierter als gedacht: Der Ähnlichkeitsgraph trifft die Zitationsnachbarschaft **achtmal** so oft wie eine Zufallsauswahl (Lift 8,20), er ersetzt `get_citations` aber nicht. (2) Wer eine Frage über den **Titel** eines Papers stellt, bekommt die zitierenden Paper häufig über deren **Literaturverzeichnis** geliefert – der Beleg steht dann im Abschnitt „References" und sagt inhaltlich wenig. Beim Gegenlesen der Provenienz lohnt daher der Blick auf den Abschnittsnamen.

Für jede Frage werden festgehalten:

- **Erwarteter Suchmodus** (gemäß Fragetyp-Mapping der README),
- **Erwartete Provenienz** (welche Quelle/Seite sollte belegt sein),
- **Befund** (bei der Durchführung: korrekt / teilweise / falsch + Notiz).

---

## 1. Präzise Detailfrage → Local + Basic

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| D1 | Which datasets are used to evaluate GraphRAG approaches? | Local + Basic | Paper mit GraphRAG-Evaluation, Abschnitt „Datasets/Evaluation" | ✅ korrekt · Local-Seed = *RAG vs. GraphRAG – A Systematic Evaluation*, **S. 7, Abschnitt „Datasets and Evaluation Metrics"** (nennt SQuALITY, QMSum, ODSum). |
| D2 | What are the key stages of the GraphRAG workflow? | Local + Basic | GraphRAG-Survey, Workflow-Abschnitt | ✅ korrekt · Beleg über Local-Fan-out = *A Survey of Graph RAG for Customized LLMs*, **Abschnitt „Workflow of GraphRAG"** (knowledge organization/retrieval/integration). |

## 2. Cross-Paper-Synthese / Themen → Global

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| S1 | Which research directions emerge across the corpus? | Global | mehrere Communities mit repräsentativen Papern | ✅ korrekt · Top-Community #9 (Keywords: code, flow, vulnerabilities, graph, traversals), Vertreter u. a. *A Toolkit for Generating Code Knowledge Graphs*, *Modeling and Discovering Vulnerabilities with Code Property Graphs*. |
| S2 | Which thematic clusters combine graphs and retrieval? | Global | GraphRAG-/KG-RAG-Community | ✅ teilweise · liefert die GraphRAG-Community (#0, 27 Paper, Keywords: graph, graphrag, retrieval, rag, entity); rein lexikalische Clusterbildung (kein semantischer Entitätsgraph, ADR 0008). |

## 3. Zitations-/Autoren-/Methodennetze → Local (Fan-out)

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| N1 | Which papers build on knowledge graph methods? | Local (Fan-out) | über Graph-Kanten verknüpfte Nachbarpaper | ✅ korrekt · Seed = *Structure-Grounded Knowledge Retrieval …*, Fan-out-Nachbar *A Survey of Graph RAG …* (Kantengewicht 0,46) mit belegtem Chunk. |
| N2 | Which works relate to knowledge-graph-based code generation? | Local (Fan-out) | thematisch benachbarte Code-KG-Paper | ✅ korrekt · Chunk-Nachbarschaft u. a. *Knowledge Graph Based Repository-Level Code Generation*, **Abschnitt „Approach"**. |

> **Hinweis (Phase 7 / A2):** Der Local-Fan-out folgt **Ähnlichkeits**-Kanten, nicht Zitationen. Fragen der Form „welche Paper bauen auf *diesem* Paper auf?" beantwortet der **Zitationsgraph** – `python -m scripts.citations <paper_id>` bzw. das MCP-Tool `get_citations` (Intra-Korpus, [ADR 0011](../docs/adr/0011-intra-corpus-citation-graph-phase7.md)).

## 4. Exakte Fakten → Basic

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| F1 | What F1 score is reported for the evaluation? | Basic | Paper mit Ergebnis-Tabelle/Abschnitt | ✅ korrekt (Auto-Router: „f1" → basic) · Top-Treffer *A-MEM – Agentic Memory for LLM Agents*, **S. 8**; zweiter *NetConfEval*, **S. 8 (F1-Score)**. |
| F2 | Which benchmarking datasets are named? | Basic | Paper mit Datensatz-Nennung | ✅ korrekt · Basic-Treffer verweisen auf konkrete Datensatz-Passagen mit Seiten-Provenienz (u. a. Summarization-Datensätze, siehe D1). |

## 5. Widersprüche & Vergleiche → DRIFT

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| W1 | Compare vector and graph retrieval approaches. | DRIFT | ≥ 2 Paper der passenden Community | ✅ korrekt · Community #0 (GraphRAG), lokale Belege *Do We Still Need GraphRAG?* **S. 6, Abschnitt „Overall Comparison (RQ1)"**, *From Local to Global* **S. 9**, *Graph RAG – A Survey* **S. 10, Abschnitt „Indexing"**. |
| W2 | How do RAG and GraphRAG differ for agentic search? | DRIFT | Community + gegenüberstellende Belege | ✅ korrekt (Auto-Router: „differ" → drift) · Community #11 (agentic, vectorrag, graphrag), lokaler Beleg *Agentic GraphRAG*, **S. 10**. |

---

## Durchführung

1. Voraussetzung: Index inkl. Graph/Communities vorhanden (`python -m scripts.ingest`, Phasen 2–3).
2. **Ganzes Set auf einmal** (Phase 6): `python -m scripts.qa` spielt alle Fragen je erwartetem Modus durch und druckt die Provenienz für die Stichprobe. Einzeln/explorativ: `python -m scripts.ask "<frage>" --mode <basic|local|global|drift>` oder ohne `--mode` (Heuristik-Router, `auto`).
3. Antwort **und** gelieferte Provenienz gegen die Erwartung prüfen, Befund eintragen.
4. Auffälligkeiten (fehlende/falsche Quelle) als Stichprobenfund notieren (siehe README, „Qualitätssicherung"). Ein schneller Index-/Konsistenz-Überblick liefert `python -m scripts.status`.

> **Beobachtung (ehrlich):** Die Abschnitts-Provenienz ist meist präzise (z. B. „Datasets and Evaluation Metrics", „Overall Comparison (RQ1)"), stellenweise aber verrauscht (die Phase-2-Heuristik übersegmentiert, z. B. „20.09 20.15" als Abschnitt) – bekannte Grenze aus [ADR 0006](../docs/adr/0006-canonical-model-phase2-scope.md), kein Retrieval-Fehler. Ab **Phase 5** wird dieselbe Stichprobe zusätzlich über die MCP-Tools in Copilot gefahren.

