# Roadmap – Research-GraphRAG

Phasenweiser Umsetzungsplan für den persönlichen Scientific-GraphRAG-Assistenten. Der Plan ist **iterativ**: erst ein dünner, lauffähiger Durchstich, dann gezielte Ausbaustufen. **Bewusst ohne Zeitschätzungen** – Fortschritt wird über die „Definition of Done" (DoD) je Phase und über Meilensteine gemessen.

> Ergänzt die [README](README.md). **Die Phasen 0–7 sind abgeschlossen** und hier nur noch als Ergebnis-Tabelle zusammengefasst; die vollständigen Status-Blockquotes mit allen Kennzahlen, korrigierten Annahmen und offen dokumentierten Abweichungen stehen wörtlich in der [Roadmap-Historie](docs/roadmap-historie.md). **Phase 8 ist umgesetzt** (Statusblock dort); aktiv geplant sind die **Phasen 9–11**.

---

## Leitprinzipien

- **Lean & container-frei:** reine Python-Umgebung, kein Docker-/DB-Server.
- **Provenienz zuerst:** jede Antwort ist auf Paper/Abschnitt/Seite rückführbar.
- **Inkrementell nutzbar:** neue PDFs per Drop-in-Ordner + Skript, ohne alles neu aufzusetzen.
- **Klein, aber wachstumsfähig:** optimiert für ≤ 500 Paper, mit klaren Erweiterungspfaden.
- **Offline zuerst:** umgesetzt ist die Offline-Variante (Option B, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)); ein Netzzugriff bleibt eine **separat startbare Zusatzfunktion**, nie eine Voraussetzung.
- **Erst messen, dann bauen.** Das ist die wichtigste Lehre aus den Phase-7-Punkten und keine Floskel: In **A3** war die vermutete Ursache der `short_chunk`-Flut falsch (nicht die Seitengrenze, sondern die Überschriften-Heuristik), in **A4** bestätigte sich die Annahme „Fusion schlägt Einzelverfahren" nicht, in **A5** saß das Keyword-Rauschen nicht im Vektorraum, sondern in der Auswahlpolitik, in **A6** hätte eine nackte Coverage-Kennzahl die triviale Strategie gekürt, und in **A7** waren die vermuteten Signal-Konflikte mit 1 von 44 Fragen praktisch inexistent. Jede Ausbaustufe beginnt daher mit einer Wegwerf-Messung und einem **Abbruchkriterium**.
- **Präzision vor Recall**, wo Daten in den Korpus oder in den Graphen fließen ([ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)).

---

## Stand: Phasen 0–7 (abgeschlossen)

| Phase | Ergebnis | Entscheidung |
| --- | --- | --- |
| **0** – Fundament & Durchstich | `pip install -e .`, Ingestion (`pypdf` → TF-IDF/SQLite), belegte Antwort; **M1** erreicht | [ADR 0002](docs/adr/0002-venv-and-offline-dependency-strategy.md) · [ADR 0003](docs/adr/0003-offline-test-and-coverage-tooling.md) · [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md) |
| **1** – Migration | 145 Paper nach `papers/`, [`Übersicht.md`](Übersicht.md) portiert (reduzierter Umfang: `recherche/` ausgelassen) | – |
| **2** – Ingestion & Canonical Model | Canonical-Schema, Section-Heuristik, Chunking, DOI/arXiv, Qualitätsreport, Übersicht-Entwürfe | [ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md) |
| **3** – GraphRAG-Index | Paper-Ähnlichkeitsgraph (TF-IDF, *mutual top-k*) + Louvain-Communities + extraktive Zusammenfassungen | [ADR 0007](docs/adr/0007-graphrag-index-phase3-option-b.md) |
| **4** – Retrieval & Router | Basic/Local/Global/DRIFT + Heuristik-Router + Provenienz-Assembler | [ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md) |
| **5** – MCP-Server (stdio) | Tools für Copilot, Fehlerübersetzung an der Grenze; **M2** erreicht | [ADR 0009](docs/adr/0009-mcp-server-stdio-phase5.md) |
| **6** – Drop-in & QS | atomarer Index-Swap, `scripts.status`, `scripts.qa`; **M3** erreicht | [ADR 0010](docs/adr/0010-drop-in-workflow-and-qa-phase6.md) |
| **7 / A1** – LLM-Bridge & Synthese | `generation/`, nummerierte Evidenz mit Zitier-Contract, Tool `answer_question` (Sampling opt-in) | [ADR 0012](docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md) |
| **7 / A2** – Zitationsgraph | deterministische `CITES`-Kanten aus dem Referenzabschnitt, `get_citations` | [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md) |
| **7 / A3** – Chunking-Verfeinerung | Reject-Regeln + Section-Absorption, Seite als Provenienz-**Range** statt Grenze | [ADR 0013](docs/adr/0013-chunking-refinement-phase7.md) |
| **7 / A4** – Hybrid-Retrieval | handimplementiertes BM25 + TF-IDF per Rang-Fusion; Gold-Set und Harness entstehen | [ADR 0014](docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md) |
| **7 / A5** – Rausch-Reduktion | Textnormalisierung, Bibliografie-Reject-Regeln, Keyword-Politik | [ADR 0015](docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md) |
| **7 / A6** – Quantitative Evaluation | Modi-Ebene, Diagnosen, Lift, eingefrorene Baseline mit qid-genauem Regressions-Check | [ADR 0016](docs/adr/0016-quantitative-retrieval-evaluation-phase7.md) |
| **7 / A7** – Router-Härtung | Match-Art je Signal, `basic` als Rückfallebene, ausgewiesene Konfidenz und Signale | [ADR 0017](docs/adr/0017-router-hardening-phase7.md) |

**Nicht umgesetzt aus Phase 7:** der Punkt **A8** (inkrementelles Update, Auto-Watcher). Er ist in dieser Fassung aufgelöst – das inkrementelle Update lebt als [B2](#b2--inkrementelles-update-statt-vollem-re-index) weiter, der Auto-Watcher ist [bewusst gestrichen](#b4--auto-watcher-bewusst-gestrichen) und wird durch den manuellen Intake der [Phase 8](#phase-8--korpus-zufluss-new_papers--intake) ersetzt.

> **Warum die Kennzahlen hier fehlen:** Sie stehen in den ADRs und in der [Historie](docs/roadmap-historie.md) und veralten dort nicht. Den **aktuellen** Bestand zeigt `python -m scripts.status`, die aktuelle Retrieval-Güte `python -m scripts.eval_retrieval`.

---

## Phase 8 – Korpus-Zufluss: `new_papers/` + Intake

> **Status: umgesetzt** ([ADR 0019](docs/adr/0019-corpus-intake-new-papers-phase8.md)) – mit
> **einer begründeten Abweichung** von der Vorgabe unten. Die Vorabmessung hat das Kriterium der
> Stufe 2 widerlegt: Im eigenen Korpus würden **17 von 155** Identifikatoren fehlleiten – der
> unausgefüllte ACM-Vorlagen-Platzhalter `10.1145/nnnnnnn.nnnnnnn` steht bei **drei** Papern, und
> **14** Werte stammen aus dem Volltext-Fallback der Extraktion und zeigen auf ein *zitiertes*
> fremdes Paper (darunter der Falsch-Hub aus [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)).
> Ein Intake, der darauf hin löscht, vernichtet unter realistischen Bedingungen legitime Dateien.
>
> Umgesetzt ist daher eine **abgestufte** Konsequenz: Stufe 1 (sha256) löscht wie geplant – dort
> ist bitgenau bewiesen, dass die Datei bereits im Korpus liegt. Stufe 2 verschiebt nach
> `new_papers/_duplikate/` (hartes Löschen nur per `--delete-identifier-duplicates`) und
> vergleicht nur noch **gehärtete** Schlüssel: belegt auf der eigenen Titelseite (Guard aus
> ADR 0011) **und** im Korpus eindeutig – von 155 Identifikatoren überleben **138**. Stufe 3
> (Schwelle **0,85**, am Korpus **ohne** Fehlalarm) bleibt folgenlos und erkennt **22 von 25**
> künstlich umbenannten Realpapern, keines davon falsch zugeordnet.
>
> Ebenfalls umgesetzt: das **Robustheits-Gate** (`no_chunks`-Flag – schließt die bekannte Grenze
> aus [ADR 0013](docs/adr/0013-chunking-refinement-phase7.md) – plus `%PDF-`-Signaturprüfung), die
> **Übersicht als einzige Senke** (append-only, byte-erhaltend, atomar, ID-Reihe `Z1`, `Z2`, …;
> löst eine Phase-2-Festlegung ab) und ein append-only **Protokoll** `data/intake_log.md` mit Hash
> je gelöschter Datei. Der Nachweis erfolgte end-to-end an einer **vollständigen Kopie** des
> 145-Paper-Korpus: alle fünf Wege einmal durchlaufen, `--dry-run` nachweislich wirkungslos
> (Hash-Abbild identisch), kuratierte Zeilen byte-identisch, zweiter Lauf idempotent. **436 Tests**
> grün, kein Schema-Eingriff, **kein Re-Ingest**.

**Ziel:** Ein einziger Befehl übernimmt neue PDFs aus einem Eingangsordner in den Korpus, verhindert dabei **Doppelbestand**, stößt die vollständige Pipeline an und pflegt die Literaturübersicht nach.

### Warum das nötig ist (und was heute fehlt)

Der bestehende Drop-in-Workflow (PDF nach `papers/` legen, `python -m scripts.ingest`) dedupliziert über `data/manifest.json` – und zwar **Dateiname → sha256**. Ein **inhaltsgleiches PDF unter einem anderen Dateinamen** wird dadurch als neues Paper indiziert: eigene `paper_id`, eigene Knoten und Kanten im Ähnlichkeitsgraphen, doppelte Belege in jeder Antwort und eine zweite Zeile in der Übersicht. Bei manueller Ablage passiert das selten; sobald PDFs aus dem Netz mit fremd vergebenen Dateinamen kommen ([Phase 9](#phase-9--online-research-modus-separat-startbar)), wird es zum Regelfall. Genau diese Lücke schließt der Intake.

### Umfang

- **Eingangsordner `new_papers/`** (nicht versioniert, wie `papers/` und `data/`).
- **Logik in `src/research_graphrag/intake.py`**, dünnes `scripts/intake.py` – konsistent zur Repo-Konvention „Logik im Paket, Skripte dünn" ([docs/repository-structure.md](docs/repository-structure.md)).
- **Drei Prüfstufen mit fallender Sicherheit** – die Konsequenz hängt an der Sicherheit, nicht am Verdacht:

  | Stufe | Kriterium | Grundlage | Konsequenz |
  | --- | --- | --- | --- |
  | 1 | **sha256** identisch | `data/manifest.json` (Beleg am Dateisystem nachgerechnet) | sicheres Duplikat → Datei in `new_papers/` wird **gelöscht** |
  | 2 | **DOI oder arXiv-ID** identisch | `extract_identifiers` (Phase 2) gegen `papers.identifiers` im Index | **umgesetzt abweichend:** Quarantäne statt Löschung, siehe Statusblock oben |
  | 3 | **Titel-Ähnlichkeit** | normalisierter Titel/Dateiname-Stamm gegen den Korpus | **unsicher** → keine Löschung, Datei bleibt liegen, Befund im Bericht |

- **Kein Treffer** → Datei wird nach `papers/` verschoben. Bei **Namenskollision mit abweichendem Hash** wird nichts überschrieben: Die Datei bleibt liegen und erscheint als Befund.
- Danach **ein** Ingest-Lauf (`pipeline.ingest`, voller Re-Index mit atomarem Swap – unverändert), anschließend die Übersicht-Zeilen (siehe unten).
- **Abschlussbericht:** übernommen / als Duplikat gelöscht (mit Hash und Fundstelle) / offen geblieben (mit Grund).

### Zwei bewusste Härten

1. **Löschen ist endgültig – deshalb ist `--dry-run` Pflichtbestandteil.** Der Lauf zeigt jede geplante Aktion an, ohne etwas zu verändern. Das ist die einzige Absicherung, die nicht auf einem Papierkorb beruht.
2. **Eine neuere Version zählt als Duplikat.** `arXiv:1234.5678v2` trägt dieselbe Identifikator-Wurzel wie `v1` und wird in Stufe 2 gelöscht. Das ist die logische Folge der gewünschten Regel und muss in der Anleitung stehen: **Wer ersetzen will, löscht zuerst die alte Datei in `papers/`** und lässt den Intake dann laufen.

### Übersicht-Pflege durch das Skript

Bisher schreibt `scripts/update_overview.py` **append-only** nach `data/overview_drafts.md`, und [`Übersicht.md`](Übersicht.md) bleibt unangetastet (Festlegung aus Phase 2). Neu soll der Intake die Entwurfszeile **direkt an die Tabelle in `Übersicht.md`** anhängen.

Akzeptanz dafür:

- **Append-only**: nur anhängen, nie umsortieren, nie eine bestehende Zelle ändern. Ein Regressionstest belegt, dass die kuratierten Zeilen **byte-identisch** bleiben.
- **Idempotent**: ein zweiter Lauf erzeugt keine zweite Zeile (die Erkennung über die internen Links existiert bereits in `overview/drafts.py`).
- **Wertende Spalten bleiben leer**: `Relevanz fuer Expose` und `SRQ-Zuordnung` werden als `(manuell)` eingetragen – die Kuratierung bleibt beim Menschen, sonst verliert die Tabelle ihre Rolle.
- **ID-Vergabe**: Die kuratierten IDs sind Themencluster (`A1`, `B2`, …), die ein Automat nicht vergeben kann. Neue Zeilen bekommen daher eine eigene Reihe (z. B. `Z1`, `Z2`, …) und werden beim Kuratieren umsortiert.
- **Diese Änderung löst eine Phase-2-Festlegung ab** und braucht bei der Umsetzung einen ADR (Verhältnis zu `data/overview_drafts.md`: bleibt der Pfad für `scripts/update_overview.py` oder wird er abgelöst?).

### Robustheits-Gate für unkuratierte PDFs

[ADR 0013](docs/adr/0013-chunking-refinement-phase7.md) dokumentiert eine bekannte Grenze: Ein Dokument mit Seitentext, aber ohne Fließtext erzeugt **null Chunks und kein Qualitäts-Flag**. Bei 145 handverlesenen Papern war das folgenlos; mit einem Eingangsordner – und erst recht mit Downloads – kommen reine Scans ohne Textebene, Cover-Seiten und HTML-Fehlerseiten mit `.pdf`-Endung ins System. Aus einer theoretischen Lücke wird damit ein realer Fall.

*Akzeptanz:* ein Flag für „zu wenige/keine Chunks", das im Intake-Bericht sichtbar wird. Die Datei wird trotzdem übernommen (keine stille Ablehnung) – aber der Befund ist sichtbar, statt lautlos einen leeren Korpus-Eintrag zu erzeugen.

### Definition of Done

- PDF nach `new_papers/` legen → **ein** Befehl → Duplikate sind entfernt, neue Paper liegen in `papers/`, Index/Ähnlichkeitsgraph/Zitationskanten sind aktualisiert, die Übersicht hat eine Entwurfszeile, der Bericht listet jede Entscheidung.
- `--dry-run` verändert nachweislich nichts.
- **Anleitung in der [README](README.md)**: Schritt-für-Schritt inklusive der Konsequenz des Löschens und des Versions-Sonderfalls.
- Tests: sha256-Treffer, Identifikator-Treffer, Titel-Verdacht (**darf nicht löschen**), Namenskollision, Idempotenz der Übersicht, Unverändertheit der kuratierten Zeilen, Bericht bei leerem Eingangsordner.

---

## Phase 9 – Online-Research-Modus (separat startbar)

**Ziel:** Ein **manuell gestarteter, vom Kern getrennter** Modus, der zu einem Thema oder einem Seed-Paper neue Quellen im Netz sucht und – nur auf ausdrücklichen Wunsch – frei lizenzierte Volltexte nach `new_papers/` legt, wo [Phase 8](#phase-8--korpus-zufluss-new_papers--intake) sie übernimmt.

**Abgrenzung, die nicht verhandelbar ist:** Der Kern bleibt netzfrei. Ohne Internet funktioniert alles Bisherige unverändert. Insbesondere bekommt der MCP-Server **kein** Netz-Tool im ersten Schritt – er wird von Copilot autonom aufgerufen, und niemand soll durch eine beiläufige Frage ungewollten Netzverkehr auslösen.

### S0 – Recherche & Machbarkeit (zwingend zuerst, mit Abbruchkriterium)

Dieser Schritt ist der Grund, warum die Phase überhaupt so geschnitten ist: **Es ist offen, ob das hier sinnvoll und überhaupt möglich ist.** Zu klären, bevor eine Zeile Code entsteht:

1. **Erreichbarkeit messen, nicht annehmen.** Das Repo entstand in einem Umfeld **ohne PyPI-Zugang** ([ADR 0002](docs/adr/0002-venv-and-offline-dependency-strategy.md)) – daraus folgt *nicht*, dass fachliches HTTP blockiert ist, aber es ist unbewiesen. Zu prüfen sind je ein Minimal-Request gegen die Kandidaten (arXiv-API, Crossref, OpenAlex, Semantic Scholar, Unpaywall) inklusive Proxy- und TLS-Verhalten. Dieselbe Methodik wie bei [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md), wo die Beschaffbarkeit empirisch geprüft und die Architektur danach ausgerichtet wurde.
2. **Werkzeuglage (bereits gemessen):** `requests` und `httpx` sind offline vorhanden, `urllib` ohnehin; `feedparser` fehlt – die Atom-Antwort der arXiv-API müsste also über `xml.etree` aus der Standardbibliothek gelesen werden. Ein Fremd-Wheel ist für diese Phase **nicht** nötig.
3. **Quellenauswahl nach harten Kriterien:** API-Schlüssel nötig? Rate-Limit? Abdeckung für einen arXiv-/CS-lastigen Korpus? Liefert sie Abstracts? Weist sie **Lizenz** und Volltext-Link aus? Was sagen die Nutzungsbedingungen zur automatisierten Abfrage?
4. **Die unbequeme Frage: Lohnt es sich?** Der Korpus ist **kuratiert** – `Übersicht.md` bewertet Relevanz und ordnet Sub-Forschungsfragen zu. Ein Automat, der pro Lauf 50 Kandidaten ausspuckt, erzeugt Kurationsarbeit, statt sie zu sparen. Zielgröße ist deshalb **Präzision der Vorschläge, nicht deren Menge** – gemessen an einer simplen Frage: Wie viele Vorschläge eines Laufs würde man tatsächlich in die Übersicht aufnehmen?

*Abbruchkriterium:* Ist keine Quelle erreichbar, ist die Rechtslage unklar, oder liefert eine Handprobe überwiegend Irrelevantes, **entfällt die Phase** – dokumentiert, wie in A5 die verworfene Seitenbereichs-Regel und die verworfene Stopword-Variante im Vektorraum.

### S1 – Kandidaten finden (Metadaten, kein Download)

- **Die Anfrage kommt aus dem eigenen Bestand**, nicht aus freier Eingabe allein: (a) Keywords einer Community aus `list_topics`, (b) Titel/Identifikator eines Seed-Papers im Sinne von „mehr wie dieses", (c) optional eine freie Suchanfrage.
- **Kandidaten werden gegen den eigenen Korpus dedupliziert** – mit **derselben** DOI-/arXiv-/Titel-Logik wie in Phase 8. Ein zweiter Dedup-Mechanismus wäre eine Fehlerquelle.
- **Ausgabe append-only** nach `data/online_candidates.md`: Titel, Quelle, Identifikator, Jahr, Abstract-Auszug, Lizenz, Link – und **warum** vorgeschlagen (welche Anfrage, welche Community). Ohne diese Begründung ist eine Empfehlung nicht prüfbar.
- **Reproduzierbarkeit:** Netzantworten sind nicht deterministisch. Die Rohantwort wird mit Zeitstempel abgelegt, damit ein Befund später nachvollziehbar bleibt (CONTRIBUTING, Leitprinzip „Reproduzierbarkeit").
- *Akzeptanz:* Ein Lauf gegen eine reale Community liefert plausible Kandidaten; in einer Stichprobe sind **null** bereits vorhandene Paper als „neu" ausgewiesen; ohne Netz bricht der Modus **sauber** ab (klare Meldung, kein Stacktrace, kein halber Zustand).

### S2 – Volltext holen (opt-in, Lizenz-Whitelist)

- **Nur mit explizitem Flag** (`--download`), nie als Standard.
- **Nur bei frei lizenzierten Quellen** (Whitelist, z. B. CC0/CC-BY/CC-BY-SA und die arXiv-Lizenzen). Alles andere wird **nicht** geladen, sondern nur als Link berichtet. Eine Umgehung von Bezahlschranken ist ausgeschlossen.
- **Ziel ist ausschließlich `new_papers/`**; die Übernahme in den Korpus macht Phase 8. Es gibt genau **einen** Weg in den Korpus, nicht zwei.
- **Sicherheitsauflagen – heruntergeladene PDFs sind nicht vertrauenswürdiger Input:** Content-Type und Größe werden vor dem Schreiben geprüft; der Dateiname wird **selbst erzeugt** (aus Identifikator/Titel, nie aus der Serverantwort → kein Pfad-Traversal); ein Request pro Datei mit Rate-Limit, Timeout und identifizierendem User-Agent; kein Bulk-Crawl. Das Robustheits-Gate aus Phase 8 fängt anschließend defekte oder textlose Dateien ab.
- *Akzeptanz:* Eine geladene Datei durchläuft den Intake regulär; ein nicht frei lizenzierter Treffer wird nachweislich **nicht** geladen; ein Netzfehler hinterlässt keine halbe Datei.

### Bewusst ausgeschlossen

Vollautomatischer Dauerbetrieb, Hintergrund-Suche, automatische Übernahme ohne Sichtung, Umgehung von Zugangsbeschränkungen. Der Mensch entscheidet, was in den Korpus kommt – andernfalls verliert die kuratierte Übersicht ihren Sinn und der Korpus seine Qualität.

### Definition of Done

S0 ist beantwortet und dokumentiert (auch ein „lohnt sich nicht" ist ein gültiges Ergebnis). Bei positivem Befund liefert S1 einen belegten, deduplizierten Kandidaten-Bericht; S2 bleibt opt-in und lizenzgebunden.

---

## Phase 10 – Retrieval-Vertiefung (die belegten Befunde abarbeiten)

**Ziel:** Die drei Schwachstellen beheben, die [ADR 0016](docs/adr/0016-quantitative-retrieval-evaluation-phase7.md) **belegt, aber bewusst nicht behoben** hat. Diese Punkte sind die am besten begründeten im ganzen Repo: Der Messapparat existiert bereits (`--modi`, eingefrorene Baseline, qid-genauer `--check` mit Fingerprint-Guard), also ist jede Änderung **vor** dem Bauen abschätzbar und **nach** dem Bauen gegen Regression abgesichert.

### V1 – Local: mehrere Seeds statt eines

*Befund:* Local erreicht Hit@5 **0,618** / MRR **0,532**, Basic dagegen **0,882** / **0,650**. Der Modus, den der Fragetyp-Contract der README für **Detailfragen** vorsieht, ist damit schwächer als seine eigene Rückfallebene. Die Diagnose zeigt warum: Von den Treffern stammen **17** vom Seed, **3** aus der Chunk-Nachbarschaft und **1** aus dem Paper-Fan-out. Das ist kein Ranking-, sondern ein Strukturproblem – Nachbarschaft und Fan-out messen Ähnlichkeit **zum Seed**, nicht zur Frage. Ist der Top-1-Seed falsch, ist das ganze Bündel verloren.

*Vorschlag:* Statt eines Seeds die Top-*m* der Hybrid-Wertung verwenden, die Nachbarschaft je Seed bilden und die Teilrankings per **Reciprocal Rank Fusion** zusammenführen – der Baustein liegt seit A4 in `indexing/fusion.py`.

*Erst messen:* Vorab auszählen, in wie vielen Gold-Fragen das erwartete Paper unter den Top-*m* Seeds liegt. **Hebt `m = 3` die erreichbare Deckelung nicht, entfällt der Punkt.**

*Akzeptanz:* Local erreicht mindestens die Basic-Werte; die Diagnose-Verteilung verschiebt sich nachweisbar; `--check` meldet keine qid-Regression; Determinismus und `Citation`-Contract unverändert.

### V2 – DRIFT: Community-Auswahl statt Top-1, mit Rückfallebene

*Befund:* DRIFT erreicht **0,235 / 0,235** – und die Diagnose ist ungewöhnlich eindeutig: Treffer (8) und erreichbare Deckelung (8) sind **identisch**. Die lokale Verfeinerung arbeitet also **fehlerfrei**; **100 %** der Fehlschläge entstehen davor, in der Community-Wahl: **12×** wurde gar keine Community gefunden, **14×** die falsche. Global erreicht mit fünf Communities **12** Fragen – die Beschränkung auf die Top-1-Community kostet DRIFT damit rund ein Drittel.

*Vorschlag:* (a) Kandidatenmenge aus den Top-*m* Communities vereinigen statt nur der besten; (b) wird **gar keine** Community gefunden, sichtbar auf Basic zurückfallen statt leer zu liefern – dasselbe Muster, das A7 im Router etabliert hat (Rückfallebene mit ausgewiesener Konfidenz, nicht stilles Scheitern).

*Akzeptanz:* Die erreichbare Deckelung steigt von 8 auf ≥ 12; die Diagnose `no_community` geht auf 0, und zwar durch einen **ausgewiesenen** Fallback, nicht durch Verstecken; Determinismus; `--check` ohne Regression.

### V3 – Multi-Hop-Fragen gegen den Zitationsgraphen messbar machen

*Lücke:* Das Gold-Set enthält ausschließlich **lexikalisch verankerte** Fragen. Der Fragetyp „Zitations-/Methodennetze (Multi-Hop)" aus dem README-Contract ist damit **überhaupt nicht gemessen** – obwohl mit **382 `CITES`-Kanten** und **44 Papern mit ≥ 3 zitierenden Quellen** eine objektive, **nicht-lexikalische** Labelquelle bereitsteht. A6 hat genau diesen Schritt als „naheliegendsten nächsten ohne Subjektivität" benannt und die Architektur dafür vorbereitet: `GoldQuestion` weist die **Label-Quelle** aus, damit weitere Quellen additiv danebentreten können.

*Zusatznutzen – und der eigentliche Grund für die hohe Priorität:* [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md) belegt ausdrücklich nur die **Präzision** des Zitationsgraphen (alle Kanten mechanisch im Referenztext belegt, Stichproben durchweg korrekt) und lässt den **Recall offen**. Mit Multi-Hop-Labels wird dieser blinde Fleck erstmals sichtbar. Zugleich löst der Punkt den in A6 zurückgestellten Wunsch nach „inhaltlich statt lexikalisch" abgeleiteten Labels auf – **ohne** die Nachrechenbarkeit aufzugeben, denn die Kanten sind mechanisch verifizierbar.

*Akzeptanz:* neue Label-Quelle neben der mechanischen; Fragen deterministisch aus dem Graphen erzeugt („welche Paper bauen auf *X* auf?"); `--verify-labels` prüft sie gegen `citation_edges`; gemessen werden `get_citations` und der Local-Fan-out; die Baseline wird um diese Ebene erweitert.

### V4 – Global: Community-Ranking über die Mitglieds-Chunks (erst messen, dann entscheiden)

*Befund:* Global erreicht **0,353 / 0,269** bei einem Lift von **3,55** gegen ≈ **1,0** bei beiden Trivial-Baselines – die Auswahl ist also klar besser als Zufall, die Coverage bleibt mit **0,248** aber niedrig. *Verdacht:* Das Ranking vergleicht die Frage gegen einen sehr **dünnen** Text – zehn Keywords plus eine extraktive Zusammenfassung je Community. Die eigentliche Textmasse der Mitglieder bleibt ungenutzt.

*Vorschlag:* Den Community-Score aus den Chunk-Scores der Mitglieder aggregieren (die Hybrid-Wertung existiert bereits); Keywords und Zusammenfassung bleiben für die Darstellung.

*Akzeptanz – bewusst als Frage formuliert:* Hebt die Aggregation Lift **und** Coverage bei gleicher Selektivität? Falls nein, wird der Punkt **verworfen und der Befund dokumentiert** – genau so, wie in A5 die naheliegende Variante „Stopwords in den Vektorraum" nach der Messung verworfen wurde, weil sie den Graphen ohne belegbaren Nutzen verschoben hätte.

---

## Phase 11 – Betrieb, Robustheit & Datensicherheit

### B1 – Sicherung des Korpus

*Lücke:* `papers/` und `data/` sind **nicht versioniert**. Der gesamte Bestand hängt damit an einem Ordner auf einer Maschine – während der Index jederzeit aus den PDFs reproduzierbar wäre. Phase 8 verschärft das gleich doppelt: Der Intake **löscht** Dateien unwiderruflich, und Phase 9 fügt automatisiert neue hinzu.

*Akzeptanz:* ein dokumentierter, einfacher Sicherungsweg – gesichert werden müssen nur `papers/`, [`Übersicht.md`](Übersicht.md) und `data/manifest.json`; alles Übrige ist rekonstruierbar. Dazu ein `--dry-run` überall dort, wo gelöscht wird. Bewusst **kein** eigenes Backup-Framework – das wäre für ein persönliches Werkzeug überzogen.

### B2 – Inkrementelles Update statt vollem Re-Index

*Lücke (bisher A8a):* Der volle Re-Index ist bei ~145 Papern günstig und konsistent, wächst aber linear mit dem Bestand – und Phase 9 lässt den Bestand systematisch wachsen (Auslegung bis ~500 Paper).

*Akzeptanz:* Nur neue/geänderte Paper extrahieren und indizieren, danach den Graphen neu bauen; das Ergebnis ist **nachweislich identisch** zum vollen Re-Index (Byte-Vergleich der Kanten, Communities und Zitationskanten – die Methodik ist in A3 und A5 etabliert). Der volle Re-Index bleibt Standard.

### B3 – Messung ohne Wartezeit

*Lücke:* Ein `--modi`-Lauf dauert mehrere Minuten, weil der Index je Ebene neu geladen wird (in A6 bewusst nicht optimiert, um keinen Contract anzufassen). Eine Messung, die man ungern startet, wird seltener gestartet – und genau diese Messungen haben in A3 bis A7 wiederholt die Annahmen korrigiert.

*Akzeptanz:* Index einmal laden und durchreichen, **ohne** Eingriff in einen Contract; die Ergebnisse sind bit-identisch zur eingefrorenen Baseline (`--check` ist der Beweis).

### B4 – Auto-Watcher: bewusst gestrichen

Der frühere Punkt A8b entfällt. `watchdog` ist offline **vorhanden** – technisch scheitert es also nicht. Die Entscheidung ist fachlich: Der Intake **löscht Dateien** und verändert den Korpus; beides soll beobachtet und angestoßen werden, nicht im Hintergrund passieren. Ein Watcher würde die einzige Stelle automatisieren, an der ein Mensch hinsehen soll.

---

## Zielbild (Option C, beschaffungsabhängig)

Diese Punkte bleiben das **Zielbild** und werden erst umgesetzt, wenn die nötigen Wheels/Modelle/Runtimes offline verfügbar werden ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)); sie sind aktuell **empirisch nicht beschaffbar**.

- **Domain-/Zitationsgraph mit Kuzu (embedded) + Text2Cypher** für deterministische Cypher-Graphfragen und Multi-Hop-Netze (baut auf dem Intra-Korpus-Graphen aus [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md) auf).
- **GROBID** für präzises Parsing **externer** Referenzen und Zitationskontexte (benötigt Docker/Java).
- **Microsoft GraphRAG / Docling / LanceDB** als vollwertiges Zielbild (LLM-gestützte Entitäts-/Community-Reports, Bounding-Box-Provenienz). Damit käme auch der **Domain Graph** in Reichweite: Von den in der [README](README.md) skizzierten Kantentypen ist bislang nur `CITES` umgesetzt; `USES_METHOD`, `EVALUATES_ON` und `SUPPORTED_BY` brauchen Entitätsextraktion.
- **Hybrid-Suche mit dedizierten Vektor-/Suchmaschinen** und **Skalierung Richtung Qdrant/Weaviate/Neo4j**, falls der Bestand deutlich über die ~500-Paper-Auslegung hinauswächst.

---

## Literaturübersicht & Arbeitsteilung

- **Rollen-Trennung:** [`Übersicht.md`](Übersicht.md) = *welche* Quellen es gibt und wie relevant sie sind; der GraphRAG-Index = *was* inhaltlich darin steht.
- **Laufende Pflege:** Die Ingestion erzeugt Entwurfszeilen; die wertenden Spalten (`Relevanz fuer Expose`, `SRQ-Zuordnung`) bleiben menschlich kuratiert. Der `Themenfokus` kann an den GraphRAG-Communities ausgerichtet werden.
- **Ab Phase 8** schreibt der Intake die Entwurfszeilen direkt in die Übersicht (append-only, wertende Spalten leer) – umgesetzt, siehe [ADR 0019](docs/adr/0019-corpus-intake-new-papers-phase8.md). `data/overview_drafts.md` ist damit abgelöst; auch `scripts/update_overview.py` schreibt jetzt in die Übersicht.

---

## Querschnittsthemen: Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| PDF-Extraktionsrauschen (Layout, Formeln, Scans) | Qualitäts-Gates, Provenienz zum Original, Stichproben; Textnormalisierung ([ADR 0015](docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)); Docling/Marker als späterer Ausbau ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)). |
| **Datenverlust durch den Intake** (hartes Löschen) | `--dry-run`, Bericht mit Hash je gelöschter Datei, Sicherungsweg aus [B1](#b1--sicherung-des-korpus). |
| **Unkuratierte PDFs aus dem Netz** (Scans, Fehlerseiten, Schadinhalte) | Lizenz-Whitelist, Content-Type-/Größenprüfung, selbst erzeugte Dateinamen, Robustheits-Flag für chunk-lose Dokumente. |
| **Verwässerung des kuratierten Korpus** durch automatische Vorschläge | Vorschläge landen im Bericht, nie automatisch im Korpus; Zielgröße ist Präzision, nicht Menge. |
| Entity Resolution (Synonyme, gleichnamige Autoren) | leichte Alias-/Synonym-Kuratierung; bei kleinem Korpus manuell handhabbar. |
| Scheinsicherheit durch Summaries | Antworten immer mit Quellenankern/Original-TextUnits; für Fakten Basic/Local bevorzugen. |
| Inkonsistenz bei inkrementellen Updates | Standard bleibt der volle Re-Index; inkrementell nur mit Identitäts-Nachweis ([B2](#b2--inkrementelles-update-statt-vollem-re-index)). |
| Kosten/Datenschutz eines Index-LLM | entschärft durch Option B: **kein** Index-LLM (offline, TF-IDF/BM25); ein LLM kommt nur zur Abfragezeit über die Bridge ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)). |

---

## Meilensteine

- **M0 – Migration:** ✅ erreicht – PDFs und `Übersicht.md` ins Repo übernommen (Phase 1).
- **M1 – Erster Durchstich:** ✅ erreicht – 1 PDF → Index → 1 Frage mit Quelle beantwortet (Phase 0b).
- **M2 – Copilot nutzt es:** ✅ erreicht – stdio-MCP-Server registriert, Werkzeuge mit Provenienz (Phase 5).
- **M3 – Drop & Use:** ✅ erreicht – Drop-in-Kreislauf mit atomarem Index-Swap und pragmatischer QS (Phase 6).
- **M4 – Belegte Qualität:** ✅ erreicht – Retrieval und Router sind **quantitativ** messbar (Gold-Sets, Baseline, Regressions-Check; A4/A6/A7).
- **M5 – Zufluss ohne Doppelbestand:** ✅ erreicht – neue PDFs gehen über `new_papers/` in den Korpus, Duplikate werden erkannt, die Übersicht wächst mit (Phase 8).
- **M6 – Online-Recherche entschieden:** S0 ist beantwortet – entweder liefert der Modus belegte Kandidaten, oder der Punkt ist dokumentiert verworfen (Phase 9).
- **M7 – Local schlägt Basic:** der für Detailfragen vorgesehene Modus ist nicht länger schwächer als seine Rückfallebene (Phase 10 / V1).
