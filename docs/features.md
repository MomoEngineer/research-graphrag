# Features

Dieses Dokument ist die **funktionale Landkarte** des Repositories: Welche Fähigkeit gibt es,
über welchen Einstiegspunkt ist sie erreichbar, und in welchen Modulen ist sie verbaut. Das
**Warum** steht nicht hier, sondern im jeweils verlinkten ADR.

> **Abgrenzung (bewusst redundanzfrei, [ADR 0018](adr/0018-code-documentation-architecture.md)):**
> Zielbild und Projektstatus stehen in [README.md](../README.md), der weitere Plan in
> [Roadmap.md](../Roadmap.md) und die Chronologie der abgeschlossenen Phasen in der
> [Roadmap-Historie](roadmap-historie.md), die Ordnerstruktur in
> [repository-structure.md](repository-structure.md), Begriffe im [Glossar](glossary.md), die
> Bedienung der Kommandozeile in [scripts/README.md](../scripts/README.md) und die Verträge der
> MCP-Werkzeuge in deren [Spezifikationen](../src/research_graphrag/mcp_server/specs).
> Korpus- und Messzahlen werden hier **nicht** wiederholt – sie stehen in den ADRs und sind über
> `python -m scripts.status` bzw. `python -m scripts.eval_retrieval` reproduzierbar.
>
> Wie die Features **funktionieren**, erklärt [funktionsweise.md](funktionsweise.md) im
> Zusammenhang und die Modul-Doku unter `src/research_graphrag/<paket>/doc/` im Detail.

**Legende der Spalten:** *Einstiegspunkt* = CLI-Kommando, MCP-Werkzeug oder – bei interner
Mechanik – die Stelle, an der das Feature wirkt. *Verbaut in* verlinkt die Modul-Doku.
*Grundlage* verlinkt den ADR mit der Begründung.

---

## A. Korpus-Aufnahme

Alles, was aus einer PDF-Datei ein durchsuchbares, belegfähiges Artefakt macht.

| Feature | Was es leistet | Einstiegspunkt | Verbaut in | Grundlage |
| --- | --- | --- | --- | --- |
| **Drop-in-Ingestion** | PDF ablegen, ein Befehl, fertig: Extraktion, Index, Graphen und Qualitätsreport in einem Lauf | `python -m scripts.ingest` | [pipeline](../src/research_graphrag/doc/pipeline.md) | [0005](adr/0005-graphrag-index-backend-open.md) |
| **Korpus-Intake mit Duplikatprüfung** | Eingangsordner `new_papers/`: prüft in drei Stufen (Hash, DOI/arXiv, Titel), übernimmt Neues und indiziert – mit wirksamem `--dry-run`; `Übersicht.md` bekommt seit Phase 15 / G4 keine neue Zeile mehr | `python -m scripts.intake` | [intake](../src/research_graphrag/doc/intake.md) | [0019](adr/0019-corpus-intake-new-papers-phase8.md), [0034](adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md) |
| **Online-Kandidatensuche** | Separat startbar: sucht bei arXiv und OpenAlex zu einer Anfrage **aus dem eigenen Bestand**, dedupliziert mit der Intake-Logik gegen den Korpus und schreibt einen append-only Bericht – kein MCP-Werkzeug | `python -m scripts.discover` | [online/search](../src/research_graphrag/online/doc/search.md), [online/sources](../src/research_graphrag/online/doc/sources.md), [online/candidates](../src/research_graphrag/online/doc/candidates.md), [online/report](../src/research_graphrag/online/doc/report.md) | [0020](adr/0020-online-candidate-search-phase9.md) |
| **Volltext-Download (opt-in)** | `--download` lädt automatisch, aber nur bei einer Lizenz aus der Whitelist (CC0/CC-BY/CC-BY-SA, ausschließlich aus OpenAlex) **und** bestandenem Titel-Rückvergleich gegen den Inhalt; alles andere bleibt ein Link – ausschließlich nach `new_papers/`, kein zweiter Weg in den Korpus | `python -m scripts.discover --download` | [online/download](../src/research_graphrag/online/doc/download.md) | [0035](adr/0035-fulltext-download-phase9-s2.md) |
| **Netzzugang hinter einem Port** | Die einzige Stelle mit Netzverbindung: CONNECT-Tunnel mit Proxy-Authentifizierung, certifi-Verifikation, Größen- und Schema-Grenzen | `RESEARCH_GRAPHRAG_PROXY` | [online/transport](../src/research_graphrag/online/doc/transport.md) | [0020](adr/0020-online-candidate-search-phase9.md) |
| **Proxy ohne Einrichtung** | Fehlt die ausdrückliche Angabe, wird der Endpunkt je Zielhost aus der Windows-Konfiguration ermittelt – einschließlich der Auswertung einer **PAC-Datei** durch Windows selbst; ohne Fund wird direkt verbunden | – (greift automatisch) | [online/systemproxy](../src/research_graphrag/online/doc/systemproxy.md) | [0032](adr/0032-system-proxy-autodetection.md) |
| **Metadaten-Auflösung** | Separat startbar: beschafft Autoren, Venue und Publikationsjahrgang über OpenAlex (Rückfall arXiv), übernimmt automatisch und weist die Belegstärke aus – der Ingest bleibt netzfrei | `python -m scripts.resolve_metadata` | [online/metadata](../src/research_graphrag/online/doc/metadata.md), [bibliography/store](../src/research_graphrag/bibliography/doc/store.md) | [0026](adr/0026-online-metadata-resolution.md) |
| **Referenz-Einträge ohne Volltext** | Separat startbar: macht aus einer kuratierten DOI-/arXiv-Liste je Kennung eine Stub-Datei `*.refjson` im Eingang (Titel, Autoren, Jahr, Venue, **Abstract**) – **kein** Volltext-Download, kein MCP-Werkzeug; ein zweiter Lauf ist folgenlos | `python -m scripts.resolve_references` | [online/references](../src/research_graphrag/online/doc/references.md), [online/report](../src/research_graphrag/online/doc/report.md) | [0029](adr/0029-reference-stub-resolution-phase13.md) |
| **Zweiter Dokumenttyp im Korpus** | Ein Referenz-Eintrag durchläuft denselben Intake wie ein PDF, wird nach seinem Titel benannt, trägt `document_kind` in Canonical und Index und wird von einem später eintreffenden **Volltext abgelöst** | `python -m scripts.intake` | [extraction/refstub](../src/research_graphrag/extraction/doc/refstub.md), [intake](../src/research_graphrag/doc/intake.md), [overview/drafts](../src/research_graphrag/overview/doc/drafts.md) | [0030](adr/0030-reference-entries-in-corpus-phase13.md) |
| **Unvollständigkeit ist sichtbar** | `document_kind` ist Pflichtbestandteil jeder Ausgabe (Zitat, Paper-Referenz, Beleg, Paper-Detail); ein Abstract-Beleg trägt den Klartext-Zusatz „Referenz-Eintrag ohne Volltext", und der Zitier-Contract verlangt, das im Antworttext zu benennen | alle `search_*`, `get_paper`, `get_citations`, `answer_question`, `scripts.ask` | [retrieval/provenance](../src/research_graphrag/retrieval/doc/provenance.md), [generation/evidence](../src/research_graphrag/generation/doc/evidence.md) | [0031](adr/0031-reference-contract-and-guardrail-phase13.md) |
| **Nachrangigkeits-Guardrail** | Referenz-Einträge stehen in der Chunk-Suche **hinter** den Volltext-Treffern – sie werden umsortiert, nicht aussortiert; ohne Volltext-Konkurrenz bleiben sie vorn | in `TfidfIndex.search` und `neighbors_of_chunk` | [indexing/tfidf_index](../src/research_graphrag/indexing/doc/tfidf_index.md) | [0031](adr/0031-reference-contract-and-guardrail-phase13.md) |
| **Dedup über Datei-Hash** | Nur neue oder geänderte PDFs werden neu extrahiert; ein Schema-Wechsel erzwingt die Neu-Extraktion trotz unveränderter Datei | `data/manifest.json` | [pipeline](../src/research_graphrag/doc/pipeline.md) | [0006](adr/0006-canonical-model-phase2-scope.md) |
| **PDF → Canonical JSON** | Seitentext, Abschnitte, Chunks, Identifikatoren und Qualitäts-Flags in einem versionierten Zwischenformat | `extract_pdf` | [extraction/pdf](../src/research_graphrag/extraction/doc/pdf.md), [extraction/model](../src/research_graphrag/extraction/doc/model.md) | [0005](adr/0005-graphrag-index-backend-open.md), [0006](adr/0006-canonical-model-phase2-scope.md) |
| **Textnormalisierung** | Repariert Ligaturen, die Wörter unauffindbar machen, und entfernt nicht dekodierbare Glyph-Artefakte | in `extract_pdf` vor der Strukturanalyse | [extraction/normalization](../src/research_graphrag/extraction/doc/normalization.md) | [0015](adr/0015-noise-reduction-keywords-and-sections-phase7.md) |
| **Abschnitts-Erkennung** | Erkennt Überschriften, verwirft Bibliografie- und Tabellenzeilen und absorbiert zu kleine Abschnitte in ihren Vorgänger | in `extract_pdf` | [extraction/structure](../src/research_graphrag/extraction/doc/structure.md) | [0006](adr/0006-canonical-model-phase2-scope.md), [0013](adr/0013-chunking-refinement-phase7.md), [0015](adr/0015-noise-reduction-keywords-and-sections-phase7.md) |
| **Größenbasiertes Chunking** | Bildet Chunks entlang von Abschnitt und Größe statt entlang der Seite; die Seite bleibt als **Provenienz-Range** erhalten | in `extract_pdf` | [extraction/chunking](../src/research_graphrag/extraction/doc/chunking.md) | [0013](adr/0013-chunking-refinement-phase7.md) |
| **Qualitäts-Gates** | Markiert fehlenden Abstract, fehlende Referenzen, OCR-Rauschen, verdächtige Tabellen, Chunk-Ausreißer und chunk-lose Dokumente | `data/quality_report.json` / `.md` | [extraction/quality](../src/research_graphrag/extraction/doc/quality.md) | [0006](adr/0006-canonical-model-phase2-scope.md), [0013](adr/0013-chunking-refinement-phase7.md), [0019](adr/0019-corpus-intake-new-papers-phase8.md) |
| **Atomarer Index-Swap** | Der Index wird in eine temporäre Datei gebaut und erst am Ende umgehängt: ein Fehler lässt den bisherigen Index intakt | in `ingest` | [pipeline](../src/research_graphrag/doc/pipeline.md) | [0010](adr/0010-drop-in-workflow-and-qa-phase6.md) |

## B. Index und Graphen

Die Artefakte, auf denen jede Antwort beruht – eine SQLite-Datei als alleinige Quelle der
Wahrheit.

| Feature | Was es leistet | Einstiegspunkt | Verbaut in | Grundlage |
| --- | --- | --- | --- | --- |
| **Chunk-Index** | Speichert Chunks samt Provenienz in SQLite und rekonstruiert den Vektorraum beim Laden deterministisch – ohne serialisierte Modelle | `TfidfIndex.load` | [indexing/tfidf_index](../src/research_graphrag/indexing/doc/tfidf_index.md) | [0005](adr/0005-graphrag-index-backend-open.md) |
| **Hybrid-Wertung** | BM25 und TF-IDF-Kosinus über **einer** Tokenisierung, verbunden per Reciprocal Rank Fusion; umschaltbar auf ein Einzelverfahren | `--scoring` bzw. Parameter `scoring` | [indexing/bm25](../src/research_graphrag/indexing/doc/bm25.md), [indexing/fusion](../src/research_graphrag/indexing/doc/fusion.md), [indexing/tfidf_index](../src/research_graphrag/indexing/doc/tfidf_index.md) | [0014](adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md) |
| **Paper-Ähnlichkeitsgraph** | Verbindet inhaltlich ähnliche Paper über wechselseitige Top-k-Kanten und gruppiert sie per Louvain in Communities mit extraktiver Zusammenfassung | `python -m scripts.graph_info` | [indexing/graph_index](../src/research_graphrag/indexing/doc/graph_index.md) | [0007](adr/0007-graphrag-index-phase3-option-b.md) |
| **Zitationsgraph (`CITES`)** | Leitet aus dem Referenzabschnitt gerichtete Zitationskanten **innerhalb des Korpus** ab (DOI, arXiv-ID, Titel) – Präzision vor Recall | `python -m scripts.citations`, `get_citations` | [indexing/citation_graph](../src/research_graphrag/indexing/doc/citation_graph.md) | [0011](adr/0011-intra-corpus-citation-graph-phase7.md) |
| **Zitierfähige Metadaten** | Führt vier Herkünfte (Handpflege, kuratierte Übersicht, Online-Auflösung, Extraktion) **feldweise** zusammen und weist je Feld aus, welche gewonnen hat | in `ingest`, Tabelle `paper_metadata` | [indexing/metadata_index](../src/research_graphrag/indexing/doc/metadata_index.md), [bibliography/resolve](../src/research_graphrag/bibliography/doc/resolve.md) | [0025](adr/0025-citable-paper-metadata.md) |
| **Keyword-Politik** | Filtert Rausch-Terme aus den extraktiven Keyword-Listen – als Nachfilter, damit der Vektorraum unberührt bleibt | Community-Keywords, Übersicht-Entwürfe | [keywords](../src/research_graphrag/doc/keywords.md) | [0015](adr/0015-noise-reduction-keywords-and-sections-phase7.md) |

## C. Retrieval

Vier Suchmodi über gemeinsamer Provenienz – jede Antwort ist auf Paper, Abschnitt und Seite
rückführbar.

| Feature | Was es leistet | Einstiegspunkt | Verbaut in | Grundlage |
| --- | --- | --- | --- | --- |
| **Basic Search** | Top-k-Passagen über die Hybrid-Wertung – der belegstärkste Modus für exakte Fakten | `search_basic`, `--mode basic` | [retrieval/basic](../src/research_graphrag/retrieval/doc/basic.md) | [0008](adr/0008-retrieval-and-query-router-phase4.md), [0014](adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md) |
| **Local Search** | Startet an den besten Passagen (Top-*m*-Seeds) und erweitert um ähnliche Chunks sowie um Nachbarpaper aus dem Ähnlichkeitsgraphen | `search_local`, `--mode local` | [retrieval/local](../src/research_graphrag/retrieval/doc/local.md) | [0008](adr/0008-retrieval-and-query-router-phase4.md) · [0021](adr/0021-local-multi-seed-phase10.md) |
| **Global Search** | Beantwortet corpusweite Fragen über die Community-Ebene statt über einzelne Passagen | `search_global`, `--mode global` | [retrieval/global_search](../src/research_graphrag/retrieval/doc/global_search.md) | [0008](adr/0008-retrieval-and-query-router-phase4.md) |
| **DRIFT Search** | Wählt die passenden Communities und verfeinert in der Vereinigung ihrer Mitglieder lokal; ohne passende Community sichtbarer Rückfall auf die corpusweite Suche | `search_drift`, `--mode drift` | [retrieval/drift](../src/research_graphrag/retrieval/doc/drift.md) | [0008](adr/0008-retrieval-and-query-router-phase4.md) · [0022](adr/0022-drift-community-union-and-fallback-phase10.md) |
| **Query-Router** | Ordnet eine Frage ohne Datenbankzugriff einem Modus zu und weist Konfidenzstufe, auslösende Signale und Begründung aus | `--mode auto` (Default), `answer_question` | [retrieval/router](../src/research_graphrag/retrieval/doc/router.md) | [0008](adr/0008-retrieval-and-query-router-phase4.md), [0017](adr/0017-router-hardening-phase7.md) |
| **Provenienz-Assembler** | Gemeinsame Zitat-Typen für alle Modi: Paper, Abschnitt, Seiten-Range, Chunk, Score und Teil-Scores | in jedem Modus | [retrieval/provenance](../src/research_graphrag/retrieval/doc/provenance.md) | [0008](adr/0008-retrieval-and-query-router-phase4.md), [0013](adr/0013-chunking-refinement-phase7.md), [0014](adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md) |
| **Paper-Detail** | Metadaten, Identifikatoren, Abschnittsfolge und Leit-Ausschnitt eines Papers – ausschließlich aus dem Index, ohne Dateizugriff | `get_paper` | [retrieval/paper](../src/research_graphrag/retrieval/doc/paper.md) | [0009](adr/0009-mcp-server-stdio-phase5.md) |
| **Zitationen abfragen** | Beide Richtungen der Zitationskanten eines Papers mit Paper-Provenienz und Match-Kriterium | `get_citations`, `python -m scripts.citations` | [retrieval/citations](../src/research_graphrag/retrieval/doc/citations.md) | [0011](adr/0011-intra-corpus-citation-graph-phase7.md) |
| **Literaturangabe** | Fertige Angabe in **Harvard** und **APA** samt Kurzbeleg, Herkunft je Feld und Diagnose fehlender Pflichtfelder | `get_reference`, `python -m scripts.cite` | [retrieval/reference](../src/research_graphrag/retrieval/doc/reference.md), [bibliography/styles](../src/research_graphrag/bibliography/doc/styles.md) | [0025](adr/0025-citable-paper-metadata.md) |
| **Identifikator an jedem Beleg** | Jedes Zitat und jede Paper-Referenz trägt DOI/arXiv/URL und einen Zitierschlüssel – der Beleg ist ohne Zusatzaufruf extern auflösbar | alle `search_*`, `answer_question` | [retrieval/provenance](../src/research_graphrag/retrieval/doc/provenance.md) | [0025](adr/0025-citable-paper-metadata.md) |

## D. Antwort und LLM-Bridge

Die Schicht, die Suchergebnisse in **eine** zitierfähige Antwort überführt – mit oder ohne
Sprachmodell.

| Feature | Was es leistet | Einstiegspunkt | Verbaut in | Grundlage |
| --- | --- | --- | --- | --- |
| **Nummerierte Evidenz** | Bildet alle vier Modi auf eine einheitliche, durchnummerierte Belegliste mit Zitier-Contract ab | `answer_question`, `--synthese` | [generation/synthesis](../src/research_graphrag/generation/doc/synthesis.md), [generation/evidence](../src/research_graphrag/generation/doc/evidence.md) | [0012](adr/0012-llm-bridge-and-answer-synthesis-phase7.md) |
| **Generierungs-Port** | Injizierbarer Anschluss für ein Sprachmodell; ohne Modell degradiert das Ergebnis **sichtbar**, statt die Belege zu verlieren | `GenerationProvider` | [generation/provider](../src/research_graphrag/generation/doc/provider.md) | [0004](adr/0004-llm-bridge-via-mcp-sampling.md), [0012](adr/0012-llm-bridge-and-answer-synthesis-phase7.md) |
| **Antwort in einem Aufruf** | Modus wählen, suchen, Evidenz aufbereiten, optional formulieren – als eine Operation für CLI und Werkzeug | `answer_question`, `python -m scripts.ask --synthese` | [generation/answer](../src/research_graphrag/generation/doc/answer.md) | [0012](adr/0012-llm-bridge-and-answer-synthesis-phase7.md), [0017](adr/0017-router-hardening-phase7.md) |
| **Sampling über den Client** | Holt die Formulierung per MCP-Sampling vom Modell des Clients – opt-in, ohne eigene Schlüssel, Fehler führen nie zum Abbruch | `answer_question(synthesize=true)` | [mcp_server/sampling](../src/research_graphrag/mcp_server/doc/sampling.md) | [0004](adr/0004-llm-bridge-via-mcp-sampling.md), [0012](adr/0012-llm-bridge-and-answer-synthesis-phase7.md) |

## E. Zugang

| Feature | Was es leistet | Einstiegspunkt | Verbaut in | Grundlage |
| --- | --- | --- | --- | --- |
| **MCP-Server (stdio)** | Stellt neun Werkzeuge für GitHub Copilot bereit und lädt den Index **pro Anfrage** frisch – neue Paper wirken ohne Neustart | `python -m research_graphrag.mcp_server` | [mcp_server/server](../src/research_graphrag/mcp_server/doc/server.md) | [0009](adr/0009-mcp-server-stdio-phase5.md), [0010](adr/0010-drop-in-workflow-and-qa-phase6.md) |
| **Fehlerübersetzung an der Grenze** | Übersetzt interne Fehler in eine strukturierte, kategorisierte Ausgabe; unerwartete Fehler werden nie durchgereicht | jedes Werkzeug | [errors](../src/research_graphrag/doc/errors.md), [mcp_server/server](../src/research_graphrag/mcp_server/doc/server.md) | [error-model.md](error-model.md), [0009](adr/0009-mcp-server-stdio-phase5.md) |
| **Kommandozeile** | Fünfzehn Skripte für Intake, Ingestion, Fragen, Zitation, Status, Sicherung, QS, Online-Recherche und Evaluation – der vollständige Funktionsumfang ohne Copilot | `python -m scripts.<name>` | [scripts/README.md](../scripts/README.md) | — |

### Die neun MCP-Werkzeuge

| Werkzeug | Fähigkeit | Spezifikation |
| --- | --- | --- |
| `search_basic` | Passagen-Suche für exakte Fakten | [search_basic.md](../src/research_graphrag/mcp_server/specs/search_basic.md) |
| `search_local` | Detailfrage mit Nachbarschaft und Fan-out | [search_local.md](../src/research_graphrag/mcp_server/specs/search_local.md) |
| `search_global` | Corpusweite Synthese über Communities | [search_global.md](../src/research_graphrag/mcp_server/specs/search_global.md) |
| `search_drift` | Community-Wahl mit lokaler Verfeinerung | [search_drift.md](../src/research_graphrag/mcp_server/specs/search_drift.md) |
| `get_paper` | Metadaten und Struktur eines Papers | [get_paper.md](../src/research_graphrag/mcp_server/specs/get_paper.md) |
| `get_citations` | Zitationen innerhalb des Korpus | [get_citations.md](../src/research_graphrag/mcp_server/specs/get_citations.md) |
| `get_reference` | Literaturangabe in Harvard und APA | [get_reference.md](../src/research_graphrag/mcp_server/specs/get_reference.md) |
| `list_topics` | Themenübersicht über alle Communities | [list_topics.md](../src/research_graphrag/mcp_server/specs/list_topics.md) |
| `answer_question` | Modus-Wahl, Evidenz und optionale Formulierung in einem Aufruf | [answer_question.md](../src/research_graphrag/mcp_server/specs/answer_question.md) |

## F. Qualitätssicherung und Evaluation

Der Teil, der Änderungen **messbar** statt nur plausibel macht.

| Feature | Was es leistet | Einstiegspunkt | Verbaut in | Grundlage |
| --- | --- | --- | --- | --- |
| **Status und Konsistenz** | Read-only-Bild von Index und Korpus samt Abgleich `papers/ ↔ manifest ↔ canonical` | `python -m scripts.status` | [scripts/README.md](../scripts/README.md) | [0010](adr/0010-drop-in-workflow-and-qa-phase6.md) |
| **Prüf-Fragen-Harness** | Spielt ein festes Fragenset über alle Fragetypen durch und zeigt die belegte Provenienz | `python -m scripts.qa` | [eval/pruef-fragen.md](../eval/pruef-fragen.md) | [0010](adr/0010-drop-in-workflow-and-qa-phase6.md) |
| **Gold-Set und Kennzahlen** | Hit@k und MRR gegen ein versioniertes Fragenset, dessen Labels mechanisch nachrechenbar sind | `python -m scripts.eval_retrieval` | [evaluation/gold](../src/research_graphrag/evaluation/doc/gold.md), [evaluation/metrics](../src/research_graphrag/evaluation/doc/metrics.md) | [0014](adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md), [0016](adr/0016-quantitative-retrieval-evaluation-phase7.md) |
| **Labels nachführen** | Leitet die Labels nach einem Korpuswechsel neu aus dem Index ab, ohne die Fragen anzufassen, und meldet Fragen, die kein Ziel mehr haben | `python -m scripts.eval_retrieval --write-gold` | [evaluation/gold](../src/research_graphrag/evaluation/doc/gold.md) | [0016](adr/0016-quantitative-retrieval-evaluation-phase7.md) |
| **Modus-Diagnosen** | Trennt Auswahl- von Rankingfehlern und weist Community-Auswahl nie ohne Selektivität und Trivial-Baselines aus | `python -m scripts.eval_retrieval --modi` | [evaluation/runner](../src/research_graphrag/evaluation/doc/runner.md), [evaluation/report](../src/research_graphrag/evaluation/doc/report.md) | [0016](adr/0016-quantitative-retrieval-evaluation-phase7.md) |
| **Regressions-Check** | Vergleicht den aktuellen Stand **frage-genau** mit einer eingefrorenen Baseline; ein Fingerprint verweigert den Vergleich bei verändertem Korpus | `python -m scripts.eval_retrieval --check` | [evaluation/baseline](../src/research_graphrag/evaluation/doc/baseline.md) | [0016](adr/0016-quantitative-retrieval-evaluation-phase7.md) |
| **Router-Contract-Treue** | Misst ohne Index, ob der Router die Fragetyp-Tabelle der README einhält, und prüft die Abdeckung aller Signale | `python -m scripts.eval_retrieval --router` | [evaluation/routing](../src/research_graphrag/evaluation/doc/routing.md) | [0017](adr/0017-router-hardening-phase7.md) |
| **Multi-Hop gegen den Zitationsgraphen** | Misst den Fragetyp „Zitations-/Methodennetze" mit **nicht-lexikalischen** Labels aus den `CITES`-Kanten – strukturell (ohne Textanfrage) und mit zwei Anfrageformen, deren Belege nach Fliesstext und Literaturverzeichnis getrennt ausgewiesen werden | `python -m scripts.eval_retrieval --zitationen` | [evaluation/multihop](../src/research_graphrag/evaluation/doc/multihop.md) | [0023](adr/0023-multihop-citation-evaluation-phase10.md) |

## G. Querschnitt

| Feature | Was es leistet | Einstiegspunkt | Verbaut in | Grundlage |
| --- | --- | --- | --- | --- |
| **Übersicht-Entwürfe** | Seit Phase 15 / G4 außer Dienst (verweigert den Lauf ohne `--force`) – hängte zuvor Entwurfszeilen append-only, byte-erhaltend und atomar an die kuratierte `Übersicht.md` an | `python -m scripts.update_overview --force` (Notfall) | [overview/drafts](../src/research_graphrag/overview/doc/drafts.md) | [0006](adr/0006-canonical-model-phase2-scope.md), [0015](adr/0015-noise-reduction-keywords-and-sections-phase7.md), [0019](adr/0019-corpus-intake-new-papers-phase8.md), [0034](adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md) |
| **Kuratiertes Relevanzurteil** | Überführt die 131 kuratierten Übersicht-Zeilen (Themenfokus, Relevanz, SRQ-Zuordnung) verlustfrei nach `metadata/curation.json`; `--check` vergleicht Zeile für Zeile | `python -m scripts.migrate_curation` | [overview/curation](../src/research_graphrag/overview/doc/curation.md) | [0034](adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md) |
| **Sicherung des Bestandes** | Sichert idempotent nur das nicht Reproduzierbare (PDFs, Übersicht, kuratiertes Relevanzurteil, Zitationsdaten, Manifest, Protokolle) in ein Verzeichnis außerhalb der Arbeitskopie und rechnet den Stand auf Wunsch gegen sein Prüf-Manifest nach | `python -m scripts.backup --ziel <Pfad>` | [backup](../src/research_graphrag/doc/backup.md) | [0027](adr/0027-corpus-backup-phase11.md), [0034](adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md) |
| **Fehlertaxonomie** | Eine gemeinsame Fehlersprache für alle Schichten, die an der Serverkante ohne Übersetzungstabelle ausgegeben werden kann | `DomainError` | [errors](../src/research_graphrag/doc/errors.md) | [error-model.md](error-model.md) |

---

## Was es bewusst nicht gibt

Damit die Landkarte auch die Ränder zeigt – jeweils mit dem ADR, der die Abgrenzung festhält:

- **Kein Microsoft-GraphRAG, kein Docling, kein LanceDB.** Die Offline-Umgebung gibt sie nicht
  her; umgesetzt ist die Offline-Variante ([ADR 0005](adr/0005-graphrag-index-backend-open.md)).
- **Keine LLM-gestützte Entitätsextraktion.** Vom Domain-Graph ist allein `CITES` umgesetzt; die
  übrigen Kantentypen bleiben Zielbild
  ([ADR 0011](adr/0011-intra-corpus-citation-graph-phase7.md)).
- **Kein serverseitiges Modell.** Die Evidenz-Werkzeuge sind modellfrei; Formulierung entsteht
  nur auf ausdrückliche Anforderung über das Modell des Clients
  ([ADR 0009](adr/0009-mcp-server-stdio-phase5.md),
  [ADR 0012](adr/0012-llm-bridge-and-answer-synthesis-phase7.md)).
- **Kein inkrementelles Index-Update.** Der Index wird vollständig neu gebaut – bei dieser
  Korpusgröße günstiger und konsistenter ([ADR 0010](adr/0010-drop-in-workflow-and-qa-phase6.md)).
- **Keine Bounding-Boxen.** Provenienz endet bei Abschnitt und Seiten-Range
  ([ADR 0006](adr/0006-canonical-model-phase2-scope.md),
  [ADR 0013](adr/0013-chunking-refinement-phase7.md)).
- **Keine inhaltlichen Evaluations-Labels.** Gemessen wird ausschließlich mit mechanisch
  nachrechenbaren Labels ([ADR 0016](adr/0016-quantitative-retrieval-evaluation-phase7.md)).
- **Kein Netz im Kern.** Netzverkehr entsteht ausschließlich beim ausdrücklichen Aufruf von
  `python -m scripts.discover` (oder der übrigen Online-Läufe) und ist bewusst **kein**
  MCP-Werkzeug ([ADR 0020](adr/0020-online-candidate-search-phase9.md)). Der Volltext-Download ist
  seit Phase 9 / S2 möglich, aber **opt-in** (`--download`) und eng auf eine Lizenz-Whitelist
  begrenzt – ohne das Flag lädt der Modus wie zuvor nichts ([ADR 0035](adr/0035-fulltext-download-phase9-s2.md)).
