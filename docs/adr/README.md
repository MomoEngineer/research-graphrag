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
| [0017](0017-router-hardening-phase7.md) | Router-Härtung (Phase 7 / A7): Wortgrenzen, ausgewiesene Konfidenz & Fallback | Akzeptiert |
| [0018](0018-code-documentation-architecture.md) | Code-Dokumentations-Architektur: Feature-Landkarte, Konzeptdokument & Modul-Dokus | Akzeptiert |
| [0019](0019-corpus-intake-new-papers-phase8.md) | Korpus-Zufluss über `new_papers/` (Phase 8): gestufter Intake, Quarantäne statt Löschen, `Übersicht.md` als einzige Senke | Akzeptiert |
| [0020](0020-online-candidate-search-phase9.md) | Online-Kandidatensuche (Phase 9 / S1): injizierbarer Transport-Port, Metadaten ohne Download | Akzeptiert |
| [0021](0021-local-multi-seed-phase10.md) | Local Multi-Seed (Phase 10 / V1): Top-*m*-Seeds, fusionierte Nachbarschaft, `seed` → `seeds` | Akzeptiert |
| [0022](0022-drift-community-union-and-fallback-phase10.md) | DRIFT (Phase 10 / V2): Vereinigung der Top-5 Communities, sichtbarer Basic-Fallback, `community` → `communities` | Akzeptiert |
| [0023](0023-multihop-citation-evaluation-phase10.md) | Multi-Hop-Evaluation (Phase 10 / V3): zweite Label-Quelle aus dem Zitationsgraphen, strukturelle Ebene, eigenes Baseline-Artefakt | Akzeptiert |
| [0025](0025-citable-paper-metadata.md) | Zitierfähige Paper-Metadaten (Phase 12 / K1): eigene versionierte Quelle, feldweise Autoritätskette, Durchreichung bis in jeden Beleg | Akzeptiert |
| [0026](0026-online-metadata-resolution.md) | Online-Auflösung der Zitationsdaten (Phase 12 / K2): automatische Übernahme mit ausgewiesener Belegstärke, separater Lauf statt Ingest | Akzeptiert |
| [0027](0027-corpus-backup-phase11.md) | Sicherung des Korpus (Phase 11 / B1): nur die Quelle sichern, Abgeleitetes bewusst weglassen, idempotenter Lauf mit Prüfnachweis | Akzeptiert |
| [0028](0028-similarity-graph-degree-phase11.md) | Grad des Ähnlichkeitsgraphen (Phase 11 / B6): `DEFAULT_K = 8` bleibt – geprüft und **verworfen**, weil ein dichterer Graph die Community-Ebene messbar verwässert | Akzeptiert |

> **Lücke bei 0024:** Die Nummer war für einen Stand zur visuellen Korpus-Exploration vergeben,
> von dem im Arbeitsverzeichnis nur noch Bytecode unter `src/research_graphrag/viz/__pycache__/`
> liegt – Quellen, Notebook und ADR fehlen. Die Nummer bleibt deshalb **unbesetzt**, statt sie
> neu zu vergeben.

---

## 5. Offene/geplante ADRs

- Derzeit sind **keine** ADR-pflichtigen Entscheidungen offen: [ADR 0005](0005-graphrag-index-backend-open.md) wurde nach einem empirischen Beschaffbarkeits-Test auf **Option B (Offline-Hybrid)** entschieden; [ADR 0006](0006-canonical-model-phase2-scope.md) grenzt den Heuristik-Umfang der Phase-2-Extraktion ab (Bounding-Boxes zurückgestellt); [ADR 0007](0007-graphrag-index-phase3-option-b.md) legt den Paper-Ähnlichkeitsgraphen mit Louvain-Communities für Phase 3 fest (Chunk-/Entitäts-Ebene zurückgestellt); [ADR 0008](0008-retrieval-and-query-router-phase4.md) legt die Offline-Semantik der Retrieval-Modi und des Query-Routers für Phase 4 fest (echtes DRIFT/Entitätsgraph zurückgestellt) und erweitert den Index additiv um die Abschnitts-Provenienz; [ADR 0009](0009-mcp-server-stdio-phase5.md) legt den stdio-MCP-Server (FastMCP) für Phase 5 fest (kein serverseitiges Sampling, `get_paper` aus dem Index, additive `identifiers`-Spalte); [ADR 0010](0010-drop-in-workflow-and-qa-phase6.md) härtet den Drop-in-Workflow der Phase 6 (On-Read + atomarer Index-Swap) und ergänzt die pragmatische QS (Prüf-Fragen-Harness, read-only Status-Kommando); [ADR 0011](0011-intra-corpus-citation-graph-phase7.md) legt den Intra-Korpus-Zitationsgraphen (Phase 7 / A2) fest (deterministisches DOI-/arXiv-/Titel-Matching, additive `citation_edges`-Tabelle, Präzision vor Recall); [ADR 0012](0012-llm-bridge-and-answer-synthesis-phase7.md) realisiert die LLM-Bridge (Phase 7 / A1) im Code und führt `answer_question` mit **opt-in** Sampling ein (Evidenz-Tools bleiben modellfrei); [ADR 0013](0013-chunking-refinement-phase7.md) stellt die Chunking-Verfeinerung (Phase 7 / A3) auf die **gemessene** Ursache um (Section-Absorption gegen Übersegmentierung) und führt die Seiten-Range `page_end` ein – zwei Festlegungen aus [ADR 0006](0006-canonical-model-phase2-scope.md) werden dadurch abgelöst (dort als Nachtrag vermerkt); [ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md) führt für Phase 7 / A4 die handimplementierte **BM25**-Wertung und die **Rang-Fusion** mit TF-IDF als Standard der Chunk-Modi ein (Laufzeit-Schema `Citation` um Teil-Scores erweitert, Index-Schema unverändert).
- Ergänzend für Phase 7 / A5: [ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md) normalisiert den extrahierten Seitentext (Ligatur-Reparatur, Entfernen der `/uniXXXXXXXX`-Glyphen), verwirft Bibliografie-Zeilen in der Überschriften-Erkennung (inklusive Referenzkontext) und führt eine kuratierte **Keyword-Politik** als Nachfilter ein; der Vektorraum des Ähnlichkeitsgraphen bleibt bewusst unangetastet (Canonical-Schema **0.4.0**, Index-Schema unverändert).
- Ergänzend für Phase 7 / A6: [ADR 0016](0016-quantitative-retrieval-evaluation-phase7.md) weitet die quantitative Retrieval-Evaluation von der geteilten Chunk-Primitive auf die **Modi als Ganzes** aus (Local-Komponentenbeitrag, Community-Auswahl, DRIFT-Deckelung), misst Global nur zusammen mit **Selektivität und Trivial-Baselines** (der Lift ordnet, die nackte Coverage nicht) und ergänzt einen **qid-genauen Regressions-Check** mit Fingerprint-Guard; die Logik zieht dafür als Paket nach `src/research_graphrag/evaluation/`. Zwei Roadmap-Punkte (inhaltliche Labels, breiteres Fragenset) bleiben begründet zurückgestellt.
- Ergänzend für Phase 7 / A7: [ADR 0017](0017-router-hardening-phase7.md) härtet den Query-Router: Die Match-Art wird **je Signal deklariert** (Wortgrenze/Wortanfang für Englisch, Teilwort nur für deutsche Stämme), `basic` wird vom gleichrangigen Modus zur **Rückfallebene**, Gleichstand fällt sichtbar auf sie zurück (Konfidenzstufe `weak`), und die Entscheidung wird als `routing` in `answer_question` **ausgewiesen** statt still getroffen. Die feste Präzedenz aus [ADR 0008](0008-retrieval-and-query-router-phase4.md) wird dadurch abgelöst (dort als Nachtrag vermerkt). Neu ist ein **Router-Gold-Set** mit aus der README abgeleiteten Contract-Labels; kein Schema-Eingriff, kein Re-Ingest.
- Ergänzend für Phase 8: [ADR 0019](0019-corpus-intake-new-papers-phase8.md) legt den Korpus-Zufluss über den Eingangsordner `new_papers/` fest: dreistufige Duplikatprüfung mit **abgestufter** Konsequenz (nur der bitgenaue sha256-Treffer löscht, der Identifikator-Treffer wandert in eine Quarantäne, der Titel-Verdacht bleibt folgenlos), Härtung des Identifikator-Vergleichs gegen zwei am Korpus **gemessene** Fehlerquellen (nicht belegte und nicht eindeutige Identifikatoren), `Übersicht.md` als **einzige** Senke der Entwurfszeilen (löst eine Festlegung aus [ADR 0006](0006-canonical-model-phase2-scope.md) ab, dort als Nachtrag vermerkt) sowie ein Robustheits-Gate (`no_chunks`-Flag, `%PDF-`-Signaturprüfung). Kein Schema-Eingriff, kein Re-Ingest.
- Ergänzend für Phase 9 / S1: [ADR 0020](0020-online-candidate-search-phase9.md) zieht die **erste Netzkomponente** in das bislang netzfreie System – hinter einem **injizierbaren Transport-Port**, so dass Anfragebildung, Quellen-Adapter, Deduplikation und Bericht ohne Netz testbar bleiben. Der Proxy-Endpunkt kommt ausschließlich aus einer Umgebungsvariablen, die TLS-Verifikation nutzt das certifi-Bundle, und die Duplikatprüfung wird aus [ADR 0019](0019-corpus-intake-new-papers-phase8.md) **wiederverwendet** statt nachgebaut. Gesucht wird nur bei arXiv und OpenAlex; Volltext-Downloads (S2) bleiben zurückgestellt, weil die Lizenzangaben der Quellen keine belastbare Whitelist tragen. Der Modus ist bewusst **kein** MCP-Werkzeug und schreibt ausschließlich einen append-only Bericht – kein Schema-Eingriff, **kein Re-Ingest**.
- Ergänzend für Phase 10 / V1: [ADR 0021](0021-local-multi-seed-phase10.md) beseitigt die Sollbruchstelle der Local Search – statt eines Seed-Chunks tragen die **Top-5 der Hybrid-Wertung** das Ergebnis, die Chunk-Nachbarschaft entsteht je Seed und wird per Reciprocal Rank Fusion zusammengeführt. Der Fan-out bleibt am Ankerpaper, weil die gemessene Erweiterung auf null von 34 Gold-Fragen wirkt; die naheliegende Variante „Seeds aus verschiedenen Papern" misst besser und wird trotzdem verworfen, weil die paper-basierten Labels ihren Preis nicht abbilden können. `LocalSearchResult.seed` wird zu `seeds` (Spec `0.2.0`) – ein bewusster Contract-Bruch; ein neuer Aufrufer-Parameter am MCP-Werkzeug entsteht **nicht**. Kein Schema-Eingriff, **kein Re-Ingest**; eine Festlegung aus [ADR 0008](0008-retrieval-and-query-router-phase4.md) wird abgelöst (dort als Nachtrag vermerkt).
- Ergänzend für Phase 10 / V2: [ADR 0022](0022-drift-community-union-and-fallback-phase10.md) hebt DRIFTs Deckelung, indem die Kandidatenmenge aus den **Top-5 Communities** vereinigt wird (der Default der Global Search – bewusst **nicht** der am besten messende Wert 8, siehe Overfitting-Argument aus [ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md)), und macht die leere Antwort unmöglich: Liefert der Community-Pfad keine Belege, fällt DRIFT sichtbar auf die Chunk-Suche ohne Paper-Filter zurück (`fallback`-Feld). Ein **defekter** Index bleibt dagegen ein Fehler. `DriftSearchResult.community` wird zu `communities` (Spec `0.2.0`) – der Bruch ist eine Provenienz-Frage, weil die Belege sonst eine falsche Herkunft behaupteten. Der Fallback-Beitrag wird in der Evaluation **getrennt** ausgewiesen (Diagnose `fallback`), weil er Basic ist und nicht DRIFT. Kein Schema-Eingriff, **kein Re-Ingest**; eine weitere Festlegung aus [ADR 0008](0008-retrieval-and-query-router-phase4.md) wird abgelöst.
- Ergänzend für Phase 10 / V3: [ADR 0023](0023-multihop-citation-evaluation-phase10.md) erschließt mit den `CITES`-Kanten die **zweite und einzige nicht-lexikalische** Label-Quelle des Repos und misst damit erstmals den Fragetyp „Zitations-/Methodennetze". Neu ist eine **strukturelle** Ebene, die den Paper-Ähnlichkeitsgraphen ganz ohne Textanfrage gegen die Zitationsnachbarschaft prüft. Zwei Anfrageformen aus einem gemeinsamen Rahmen isolieren den gemessenen **Bibliografie-Kurzschluss** (Treffer aus dem Literaturverzeichnis werden als `:ref` ausgewiesen statt als Erfolg verbucht), das Ankerpaper verlässt jedes Bündel, und `get_citations` bleibt als tautologischer Oberwert ausdrücklich **keine** Kennzahl. Der Recall-Anspruch der Roadmap wird als logisch nicht erfüllbar **korrigiert** und durch mechanische Schranken ersetzt (dort in [ADR 0011](0011-intra-corpus-citation-graph-phase7.md) als Nachtrag vermerkt). Gold-Set und Baseline sind eigene Artefakte, damit der Retrieval-Check kurz bleibt; kein Schema-Eingriff, **kein Re-Ingest**, keine Retrieval-Änderung.
- Ergänzend für Phase 12 / K1: [ADR 0025](0025-citable-paper-metadata.md) schließt die Lücke zwischen „Identifikator vorhanden" und „zitierfähig": Die Zitationsdaten bekommen eine **eigene, versionierte** Quelle außerhalb des regenerierbaren `data/`, werden **feldweise** nach der Kette `manual > curated > resolved > extracted` aufgelöst und weisen je Feld die gewinnende Herkunft aus. Grundlage ist eine Messung, die zwei Dinge belegt: Nur eines von acht Werkzeugen lieferte überhaupt einen Identifikator, und die extrahierten Werte sind für Zitationszwecke nicht verlässlich genug (29 von 129 kuratierten Angaben weichen ab, teils legitim als Publisher-DOI, teils als echter Extraktionsfehler). Neu sind das Paket `bibliography/`, die additive Index-Tabelle `paper_metadata`, das neunte Werkzeug `get_reference` und `python -m scripts.cite`; `Citation`, `PaperRef` und `EvidenceItem` werden **additiv** breiter. Kein Re-Extract, voller Re-Index genügt.
- Ergänzend für Phase 12 / K2: [ADR 0026](0026-online-metadata-resolution.md) beschafft die lokal nicht gewinnbaren Felder (Autoren, Venue, Publikationsjahrgang) über OpenAlex mit arXiv als Rückfall – als **separat startbarer** Lauf, damit der Ingest netzfrei und deterministisch bleibt. Der Zielkonflikt „Automatik oder Bestätigung?" wird nicht über die Übernahme gelöst, sondern über die **Belegstärke**: Übernommen wird jeder belegte Treffer, aber ein nicht eindeutiger Beleg trägt `confidence = weak` bis in `get_reference` hinein und steht im Protokoll. Die Titel-Schwelle ist die am Korpus kalibrierte aus [ADR 0019](0019-corpus-intake-new-papers-phase8.md); kuratierte und von Hand gepflegte Werte können durch die Auflösungskette nicht überschrieben werden. Der Lauf ist bewusst **kein** MCP-Werkzeug (schreibend und netzgebunden), der Server bleibt bei **neun** Werkzeugen.
- Geplant: **Umstieg auf `uv`** (sobald ein Mirror/Netz verfügbar ist) – löst [ADR 0002](0002-venv-and-offline-dependency-strategy.md) teilweise ab; **Option C** (pluggable Backends) als Folge-ADR, falls Teile des MS-GraphRAG-Stacks beschaffbar werden.