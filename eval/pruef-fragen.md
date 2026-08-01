# Prüf-Fragen-Set

Pragmatisches, festes Frageset zur Qualitätssicherung über alle **fünf Fragetypen** (siehe [README.md](../README.md)). Es dient als wiederholbare Stichprobe: Liefert der Assistent eine plausible Antwort **mit korrekter Provenienz** (Paper, Abschnitt, Seite/Chunk)?

> **Status Phase 4:** Konkrete, auf den migrierten Korpus (145 Paper) bezogene Fragen sind ergänzt und einmal über die CLI (`python -m scripts.ask "<frage>" [--mode …]`) durchgespielt. Die **Befund**-Spalte hält das Ergebnis der Stichprobe fest (Index-Stand: Schema 0.2.0 mit Abschnitts-Provenienz). Die Modi entsprechen [ADR 0008](../docs/adr/0008-retrieval-and-query-router-phase4.md); ab **Phase 5** werden dieselben Modi als MCP-Tools in Copilot geprüft.

> **Status Phase 6:** Dasselbe Set ist jetzt **wiederholbar** als QS-Harness `python -m scripts.qa` hinterlegt (Single Source of Truth: `QUESTIONS` in [scripts/qa.py](../scripts/qa.py)); ein struktureller Regressionstest ([tests/retrieval/test_qa.py](../tests/retrieval/test_qa.py)) sichert die Provenienz-Form. Erneuter Durchlauf am Korpus (Index-Schema **0.3.0**) liefert für **alle 10 Fragen belegte Provenienz (10/10)**; die Befunde decken sich mit Phase 4 (u. a. D1 → „Datasets and Evaluation Metrics", W1 → Community #0/„Overall Comparison (RQ1)", W2 → Community #11 „agentic/vectorrag"). Vereinzeltes **Abschnitts-Rauschen** einzelner Treffer (z. B. „20.09 20.15", OCR-Ligaturen) bleibt die bekannte Heuristik-Grenze ([ADR 0006](../docs/adr/0006-canonical-model-phase2-scope.md)), kein Retrieval-Fehler ([ADR 0010](../docs/adr/0010-drop-in-workflow-and-qa-phase6.md)).

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

