# scripts/

Entwickler-Hilfsskripte (kein MCP-Server). Aufruf stets über `python -m scripts.<name>`
vom Repository-Wurzelverzeichnis (WinPython-Konsolenskripte liegen nicht im `PATH`).

| Skript | Zweck |
| --- | --- |
| `coverage_offline.py` | Offline-Coverage-Gate: Zeilenabdeckung je Kernmodul via stdlib `trace` ([ADR 0003](../docs/adr/0003-offline-test-and-coverage-tooling.md)). Aufruf: `python -m scripts.coverage_offline`. |
| `ingest.py` | Drop-in-Ingestion: `papers/*.pdf` → Canonical JSON → TF-IDF/SQLite-Index **+ Paper-Ähnlichkeitsgraph mit Louvain-Communities** (Option B, [ADR 0007](../docs/adr/0007-graphrag-index-phase3-option-b.md)) **+ Intra-Korpus-Zitationsgraph** ([ADR 0011](../docs/adr/0011-intra-corpus-citation-graph-phase7.md)). Aufruf: `python -m scripts.ingest`. |
| `ask.py` | Frage über die Retrieval-Modi (Basic/Local/Global/DRIFT) mit Provenienz beantworten; `--mode auto` routet heuristisch ([ADR 0008](../docs/adr/0008-retrieval-and-query-router-phase4.md)); `--synthese` bereitet die Belege nummeriert über die LLM-Bridge auf (CLI ohne Modell → sichtbarer Noop-Fallback, [ADR 0012](../docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md)); `--scoring` wählt die Wertung `hybrid`/`tfidf`/`bm25` ([ADR 0014](../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)). Aufruf: `python -m scripts.ask "<Frage>" [--mode …] [--scoring …] [--synthese]`. |
| `graph_info.py` | Read-only-Übersicht der Graph-Communities (Keywords, Vertreter, Auszug); Phase-3-Nachweis ([ADR 0007](../docs/adr/0007-graphrag-index-phase3-option-b.md)). Aufruf: `python -m scripts.graph_info`. |
| `citations.py` | Read-only-Übersicht der Intra-Korpus-Zitationen eines Papers (`cites`/`cited_by` mit Quelle und Match-Kriterium doi/arxiv/title, [ADR 0011](../docs/adr/0011-intra-corpus-citation-graph-phase7.md)). Aufruf: `python -m scripts.citations <paper_id>`. |
| `update_overview.py` | Übersicht-Entwürfe: deterministische, extraktive Entwurfszeilen **append-only** nach `data/overview_drafts.md` (kuratierte `Übersicht.md` bleibt unangetastet, [ADR 0006](../docs/adr/0006-canonical-model-phase2-scope.md)); die Keyword-Spalte durchläuft die kuratierte Keyword-Politik ([ADR 0015](../docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)). Aufruf: `python -m scripts.update_overview`. |
| `status.py` | Read-only-Status von Index/Korpus (Schema, Paper/Chunks/Communities/Zitationskanten, Qualitäts-Flags, Identifier-Abdeckung) + Konsistenz-Check `papers/ ↔ manifest ↔ canonical`; pragmatische QS ([ADR 0010](../docs/adr/0010-drop-in-workflow-and-qa-phase6.md)). Aufruf: `python -m scripts.status`. |
| `qa.py` | QS-Harness: spielt das feste Prüf-Fragen-Set je erwartetem Modus (Basic/Local/Global/DRIFT) durch und zeigt die belegte Provenienz ([ADR 0010](../docs/adr/0010-drop-in-workflow-and-qa-phase6.md)). Aufruf: `python -m scripts.qa`. |
| `eval_retrieval.py` | Quantitative Retrieval-Evaluation: rechnet **Hit@k** und **MRR** gegen das versionierte Gold-Set [`eval/retrieval-gold.json`](../eval/retrieval-gold.json), dessen Labels mechanisch aus dem Chunk-Text abgeleitet sind; `--scoring` vergleicht die Wertungen, `--verify-labels` rechnet die Labels gegen den Index nach ([ADR 0014](../docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)). Aufruf: `python -m scripts.eval_retrieval [--k …] [--scoring …]`. |

Damit `python -m scripts.…` funktioniert, enthält der Ordner ein `__init__.py`.
