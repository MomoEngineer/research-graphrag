# Architecture Decision Records (ADRs)

Ein **Architecture Decision Record (ADR)** dokumentiert eine bedeutsame Architektur- oder Grundsatzentscheidung: den Kontext, die getroffene Entscheidung und die Konsequenzen. ADRs machen nachvollziehbar, **warum** das System so ist, wie es ist – zentral für die Nachvollziehbarkeit dieses Repos.

---

## 1. Wann ist ein ADR erforderlich?

Ein ADR wird angelegt bei u. a.:

- Einführung/Wechsel eines schweren Backends (Extraktion, Index, Vektor-Store).
- Wechsel der Extraktions-/Index-/Retrieval-Strategie.
- Wahl einer anderen Programmiersprache als Python für eine Komponente.
- Betrieb des Servers über HTTP/SSE statt `stdio`.
- Bewusst in Kauf genommener Redundanz.
- Jeder Entscheidung, die schwer umkehrbar ist oder mehrere Komponenten betrifft.

---

## 2. Prozess

1. Kopiere [templates/adr-template.md](../../templates/adr-template.md).
2. Nummeriere fortlaufend: `NNNN-kurzer-titel.md`.
3. Setze den Status auf `Vorgeschlagen`, während die Entscheidung diskutiert wird.
4. Nach Annahme: Status auf `Akzeptiert` setzen.
5. Wird eine Entscheidung später ersetzt: alten ADR auf `Ersetzt durch NNNN` setzen, nicht löschen.

---

## 3. Status-Werte

- **Vorgeschlagen** – zur Diskussion.
- **Akzeptiert** – in Kraft.
- **Abgelehnt** – verworfen, aber zur Nachvollziehbarkeit erhalten.
- **Ersetzt** – durch einen neueren ADR abgelöst (mit Verweis).

---

## 4. Verzeichnis der ADRs

| Nr. | Titel | Status |
| --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Architekturentscheidungen als ADR festhalten | Akzeptiert |
| [0002](0002-venv-and-offline-dependency-strategy.md) | venv- und Offline-Dependency-Strategie | Akzeptiert |
| [0003](0003-offline-test-and-coverage-tooling.md) | Offline-Test- und Coverage-Tooling | Akzeptiert |
| [0004](0004-llm-bridge-via-mcp-sampling.md) | LLM-Bridge über MCP-Sampling (Abfragezeit) | Akzeptiert |
| [0005](0005-graphrag-index-backend-open.md) | Index-Backend: Offline-Hybrid (Option B) | Akzeptiert |
| [0006](0006-canonical-model-phase2-scope.md) | Canonical-Modell Phase 2: Heuristik-Umfang & zurückgestellte Bounding-Boxes | Akzeptiert |
| [0007](0007-graphrag-index-phase3-option-b.md) | GraphRAG-Index Phase 3: Paper-Ähnlichkeitsgraph & Louvain-Communities (Option B) | Akzeptiert |
| [0008](0008-retrieval-and-query-router-phase4.md) | Retrieval & Query-Router Phase 4: Offline-Modi (Basic/Local/Global/DRIFT) & Router | Akzeptiert |
| [0009](0009-mcp-server-stdio-phase5.md) | MCP-Server (stdio) Phase 5: Retrieval-Tools & Copilot-Integration | Akzeptiert |
| [0010](0010-drop-in-workflow-and-qa-phase6.md) | Drop-in-Workflow & Qualitätssicherung (Phase 6): On-Read + atomarer Index-Swap, QS-Harness, Status | Akzeptiert |
| [0011](0011-intra-corpus-citation-graph-phase7.md) | Intra-Korpus-Zitationsgraph (Phase 7 / A2): deterministisches ID-/Titel-Matching | Akzeptiert |
| [0012](0012-llm-bridge-and-answer-synthesis-phase7.md) | LLM-Bridge & optionale Antwort-Synthese (Phase 7 / A1): Generierungs-Port, `answer_question` mit opt-in Sampling | Akzeptiert |
| [0013](0013-chunking-refinement-phase7.md) | Chunking-Verfeinerung (Phase 7 / A3): Section-Absorption & Seiten-Range statt harter Seitengrenze | Akzeptiert |
| [0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md) | Hybrid-Retrieval (Phase 7 / A4): BM25 + TF-IDF mit Reciprocal Rank Fusion | Akzeptiert |
| [0015](0015-noise-reduction-keywords-and-sections-phase7.md) | Rausch-Reduktion (Phase 7 / A5): Textnormalisierung, Bibliografie-Rejects & Keyword-Politik | Akzeptiert |
| [0016](0016-quantitative-retrieval-evaluation-phase7.md) | Quantitative Retrieval-Evaluation (Phase 7 / A6): Modus-Ebene, Trivial-Baselines & Regressions-Check | Akzeptiert |

---

## 5. Offene/geplante ADRs

- Derzeit sind **keine** ADR-pflichtigen Entscheidungen offen: [ADR 0005](0005-graphrag-index-backend-open.md) wurde nach einem empirischen Beschaffbarkeits-Test auf **Option B (Offline-Hybrid)** entschieden; [ADR 0006](0006-canonical-model-phase2-scope.md) grenzt den Heuristik-Umfang der Phase-2-Extraktion ab (Bounding-Boxes zurückgestellt); [ADR 0007](0007-graphrag-index-phase3-option-b.md) legt den Paper-Ähnlichkeitsgraphen mit Louvain-Communities für Phase 3 fest (Chunk-/Entitäts-Ebene zurückgestellt); [ADR 0008](0008-retrieval-and-query-router-phase4.md) legt die Offline-Semantik der Retrieval-Modi und des Query-Routers für Phase 4 fest (echtes DRIFT/Entitätsgraph zurückgestellt) und erweitert den Index additiv um die Abschnitts-Provenienz; [ADR 0009](0009-mcp-server-stdio-phase5.md) legt den stdio-MCP-Server (FastMCP) für Phase 5 fest (kein serverseitiges Sampling, `get_paper` aus dem Index, additive `identifiers`-Spalte); [ADR 0010](0010-drop-in-workflow-and-qa-phase6.md) härtet den Drop-in-Workflow der Phase 6 (On-Read + atomarer Index-Swap) und ergänzt die pragmatische QS (Prüf-Fragen-Harness, read-only Status-Kommando); [ADR 0011](0011-intra-corpus-citation-graph-phase7.md) legt den Intra-Korpus-Zitationsgraphen (Phase 7 / A2) fest (deterministisches DOI-/arXiv-/Titel-Matching, additive `citation_edges`-Tabelle, Präzision vor Recall); [ADR 0012](0012-llm-bridge-and-answer-synthesis-phase7.md) realisiert die LLM-Bridge (Phase 7 / A1) im Code und führt `answer_question` mit **opt-in** Sampling ein (Evidenz-Tools bleiben modellfrei); [ADR 0013](0013-chunking-refinement-phase7.md) stellt die Chunking-Verfeinerung (Phase 7 / A3) auf die **gemessene** Ursache um (Section-Absorption gegen Übersegmentierung) und führt die Seiten-Range `page_end` ein – zwei Festlegungen aus [ADR 0006](0006-canonical-model-phase2-scope.md) werden dadurch abgelöst (dort als Nachtrag vermerkt); [ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md) führt für Phase 7 / A4 die handimplementierte **BM25**-Wertung und die **Rang-Fusion** mit TF-IDF als Standard der Chunk-Modi ein (Laufzeit-Schema `Citation` um Teil-Scores erweitert, Index-Schema unverändert).
- Ergänzend für Phase 7 / A5: [ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md) normalisiert den extrahierten Seitentext (Ligatur-Reparatur, Entfernen der `/uniXXXXXXXX`-Glyphen), verwirft Bibliografie-Zeilen in der Überschriften-Erkennung (inklusive Referenzkontext) und führt eine kuratierte **Keyword-Politik** als Nachfilter ein; der Vektorraum des Ähnlichkeitsgraphen bleibt bewusst unangetastet (Canonical-Schema **0.4.0**, Index-Schema unverändert).
- Ergänzend für Phase 7 / A6: [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md) weitet die quantitative Retrieval-Evaluation von der geteilten Chunk-Primitive auf die **Modi als Ganzes** aus (Local-Komponentenbeitrag, Community-Auswahl, DRIFT-Deckelung), misst Global nur zusammen mit **Selektivität und Trivial-Baselines** (der Lift ordnet, die nackte Coverage nicht) und ergänzt einen **qid-genauen Regressions-Check** mit Fingerprint-Guard; die Logik zieht dafür als Paket nach `src/research_graphrag/evaluation/`. Zwei Roadmap-Punkte (inhaltliche Labels, breiteres Fragenset) bleiben begründet zurückgestellt.
- Geplant: **Umstieg auf `uv`** (sobald ein Mirror/Netz verfügbar ist) – löst [ADR 0002](0002-venv-and-offline-dependency-strategy.md) teilweise ab; **Option C** (pluggable Backends) als Folge-ADR, falls Teile des MS-GraphRAG-Stacks beschaffbar werden.
