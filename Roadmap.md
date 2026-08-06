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

| Phase                                       | Ergebnis                                                                                                               | Entscheidung                                                                                                                                                                                 |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **0** – Fundament & Durchstich       | `pip install -e .`, Ingestion (`pypdf` → TF-IDF/SQLite), belegte Antwort; **M1** erreicht                   | [ADR 0002](docs/adr/0002-venv-and-offline-dependency-strategy.md) · [ADR 0003](docs/adr/0003-offline-test-and-coverage-tooling.md) · [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md) |
| **1** – Migration                    | 145 Paper nach`papers/`, [`Übersicht.md`](Übersicht.md) portiert (reduzierter Umfang: `recherche/` ausgelassen) | –                                                                                                                                                                                           |
| **2** – Ingestion & Canonical Model  | Canonical-Schema, Section-Heuristik, Chunking, DOI/arXiv, Qualitätsreport, Übersicht-Entwürfe                       | [ADR 0006](docs/adr/0006-canonical-model-phase2-scope.md)                                                                                                                                     |
| **3** – GraphRAG-Index               | Paper-Ähnlichkeitsgraph (TF-IDF,*mutual top-k*) + Louvain-Communities + extraktive Zusammenfassungen                | [ADR 0007](docs/adr/0007-graphrag-index-phase3-option-b.md)                                                                                                                                   |
| **4** – Retrieval & Router           | Basic/Local/Global/DRIFT + Heuristik-Router + Provenienz-Assembler                                                     | [ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md)                                                                                                                                |
| **5** – MCP-Server (stdio)           | Tools für Copilot, Fehlerübersetzung an der Grenze;**M2** erreicht                                             | [ADR 0009](docs/adr/0009-mcp-server-stdio-phase5.md)                                                                                                                                          |
| **6** – Drop-in & QS                 | atomarer Index-Swap,`scripts.status`, `scripts.qa`; **M3** erreicht                                          | [ADR 0010](docs/adr/0010-drop-in-workflow-and-qa-phase6.md)                                                                                                                                   |
| **7 / A1** – LLM-Bridge & Synthese   | `generation/`, nummerierte Evidenz mit Zitier-Contract, Tool `answer_question` (Sampling opt-in)                   | [ADR 0012](docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md)                                                                                                                           |
| **7 / A2** – Zitationsgraph          | deterministische`CITES`-Kanten aus dem Referenzabschnitt, `get_citations`                                          | [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)                                                                                                                               |
| **7 / A3** – Chunking-Verfeinerung   | Reject-Regeln + Section-Absorption, Seite als Provenienz-**Range** statt Grenze                                  | [ADR 0013](docs/adr/0013-chunking-refinement-phase7.md)                                                                                                                                       |
| **7 / A4** – Hybrid-Retrieval        | handimplementiertes BM25 + TF-IDF per Rang-Fusion; Gold-Set und Harness entstehen                                      | [ADR 0014](docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)                                                                                                                               |
| **7 / A5** – Rausch-Reduktion        | Textnormalisierung, Bibliografie-Reject-Regeln, Keyword-Politik                                                        | [ADR 0015](docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)                                                                                                                     |
| **7 / A6** – Quantitative Evaluation | Modi-Ebene, Diagnosen, Lift, eingefrorene Baseline mit qid-genauem Regressions-Check                                   | [ADR 0016](docs/adr/0016-quantitative-retrieval-evaluation-phase7.md)                                                                                                                         |
| **7 / A7** – Router-Härtung         | Match-Art je Signal,`basic` als Rückfallebene, ausgewiesene Konfidenz und Signale                                   | [ADR 0017](docs/adr/0017-router-hardening-phase7.md)                                                                                                                                          |

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
  | Stufe | Kriterium                             | Grundlage                                                               | Konsequenz                                                                          |
  | ----- | ------------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
  | 1     | **sha256** identisch            | `data/manifest.json` (Beleg am Dateisystem nachgerechnet)             | sicheres Duplikat → Datei in`new_papers/` wird **gelöscht**               |
  | 2     | **DOI oder arXiv-ID** identisch | `extract_identifiers` (Phase 2) gegen `papers.identifiers` im Index | **umgesetzt abweichend:** Quarantäne statt Löschung, siehe Statusblock oben |
  | 3     | **Titel-Ähnlichkeit**          | normalisierter Titel/Dateiname-Stamm gegen den Korpus                   | **unsicher** → keine Löschung, Datei bleibt liegen, Befund im Bericht       |
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

> **Status: S0 beantwortet, S1 umgesetzt** ([ADR 0020](docs/adr/0020-online-candidate-search-phase9.md)).
> Der folgende S0-Befund (Messung vom 2026-08-03) entstand bewusst **ohne ADR** – S0 baut nichts
> und entscheidet keine Architektur. Mit der Umsetzung von S1 ist der dort formulierte Vorbehalt
> eingelöst: Die Entscheidung über Transport, Quellen und Sicherheitsgrenze steht jetzt im ADR.
> **S2 bleibt zurückgestellt.**
>
> **Ergebnis: die Phase entfällt nicht.** Beide Abbruchkriterien wurden geprüft und **nicht**
> ausgelöst. Wie in den Punkten A3–A7 und in Phase 8 hat die Messung die Vorgabe aber korrigiert.
>
> **1. Erreichbarkeit – die erste Messung hätte fehlgeleitet.** Ohne Proxy scheitert jede Anfrage
> bereits an der Namensauflösung (externes DNS tot, UDP/53 und ausgehendes TCP blockiert). Erst
> die Gegenprüfung fand die per **PAC-Datei** konfigurierte Proxy-Lage, die `urllib.getproxies()`
> nicht liest. Über den Proxy antworten: **arXiv 200** (nur mit `certifi` – die CA „Certainly"
> fehlt im Windows-Zertifikatsspeicher), **OpenAlex 200** (Kreditmodell: 1000 Einheiten, 10 je
> Anfrage ≈ 100 Abfragen), **Crossref 200** (1 Anfrage/s), **Semantic Scholar 429** (ohne
> API-Schlüssel unbrauchbar), **Unpaywall 422** (verlangt zwingend eine Kontakt-E-Mail, hier
> bewusst nicht gesetzt). Die offene Frage der Vorgabe ist damit beantwortet: Fachliches HTTP ist
> **nicht** blockiert – aber an eine **Proxy-Authentifizierung** gebunden (Negotiate/NTLM).
> `requests` beherrscht sie nicht; im Spike war ein selbst gebauter CONNECT-Tunnel nötig
> (Windows-gebunden, über `pyspnego`/`pywin32`). Die PAC-Datei ist ohne JS-Engine nicht
> auswertbar (`pypac`/`dukpy`/`js2py` fehlen) – der Proxy-Host müsste fest konfiguriert werden
> und kann sich ändern.
>
> **2. Werkzeuglage bestätigt:** `requests`, `httpx`, `urllib3` und `certifi` sind vorhanden,
> **`feedparser` fehlt** – `xml.etree` genügt für den Atom-Feed (praktisch belegt). Ein
> Fremd-Wheel ist nicht nötig.
>
> **3. Sinnhaftigkeit – die vermutete Schwachstelle war die falsche.** Drei Anfragen aus dem
> eigenen Bestand (zwei Communities, ein Seed-Paper) ergaben 51 Kandidaten. **13 lagen bereits im
> Korpus** und wurden von der **bestehenden** Phase-8-Logik erkannt; die Gegenprüfung fand
> **0 False Negatives** – das Akzeptanzkriterium aus S1 ist damit vorab erfüllt. Aufnahmequote
> **31/38 = 81,6 %** nach dem Kriterium „publiziert in den letzten fünf Jahren", nach
> zusätzlicher thematischer Sichtung **29/38 = 76,3 %**; beides liegt weit über der vorab
> festgelegten Schwelle von 30 %. Die Vorgabe befürchtete zu viele irrelevante Vorschläge –
> gemessen ist das Gegenteil, und der **wirksamste Filter ist trivial**: Das Publikationsjahr
> fängt 6 der 8 korpusfremden Treffer, weil OpenAlex nach Zitationszahl rankt und alte Klassiker
> hochspült. Der Engpass ist die **Sichtung**, nicht das Finden.
>
> **Grenze dieser Zahl, offen ausgewiesen:** Sie beruht auf einer mechanischen Jahresregel, nicht
> auf inhaltlicher Kuratierung – also eine **Obergrenze**, kein bestätigter Kurationswert.
> Aufgedeckt wurden außerdem **3 Dubletten innerhalb** der Kandidatenliste (dasselbe Paper aus
> arXiv und OpenAlex unter verschiedenen Identifikatoren): Eine quellenübergreifende
> Titel-Deduplikation gehört in S1.
>
> **Empfehlung – engerer Zuschnitt als geplant:** **S1 umsetzen, aber nur mit arXiv + OpenAlex.**
> Crossref rankt schlechter und liefert Abstracts nur lückenhaft (1 von 3), Semantic Scholar
> braucht einen API-Schlüssel, Unpaywall eine Kontakt-E-Mail. Ein **Aktualitätsfilter** wird
> Default. **S2 (Volltext-Download) bleibt zurückgestellt:** Die geforderte Lizenz-Whitelist ist
> auf dieser Datenbasis nicht sauber bedienbar – arXiv weist im Feed **keine** Lizenz aus,
> OpenAlex nur bei 15 von 51 Treffern; der Volltext-Link im Bericht macht den manuellen Abruf
> ohnehin zu einem Klick.
>
> **Nebenbefund (datiert, unbewertet):** Über denselben authentifizierten Proxy antwortet auch
> **PyPI mit HTTP 200**. Die Grundannahme „kein PyPI-Zugang" aus
> [ADR 0002](docs/adr/0002-venv-and-offline-dependency-strategy.md) und
> [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md) gilt in dieser Form nicht mehr. Ob
> `pip` diesen Weg nutzen könnte (es beherrscht kein Negotiate) und ob das den
> Unternehmensrichtlinien entspricht, wurde **nicht** geprüft – es wurde nichts installiert.

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

> **Status: umgesetzt** ([ADR 0020](docs/adr/0020-online-candidate-search-phase9.md)) – mit einem
> **engeren Zuschnitt** als unten vorgesehen, entlang der S0-Messung.
>
> **Umgesetzt ist** das Paket `src/research_graphrag/online/` (fünf Module) plus das dünne
> `scripts/discover.py`. Der Netzzugang liegt hinter einem **injizierbaren Port**: Nur
> `transport.py` öffnet eine Verbindung, alles andere – Anfragebildung, Quellen-Adapter,
> Deduplikation, Bericht – ist netzfrei und offline getestet. Der Proxy-Endpunkt kommt
> ausschließlich aus `RESEARCH_GRAPHRAG_PROXY`; ein Unternehmens-Hostname gehört nicht ins
> Repository.
>
> **Abweichungen von der Vorgabe unten, jeweils aus S0 begründet:**
>
> * **Zwei Quellen statt fünf** – arXiv und OpenAlex. Crossref rankt schlechter und liefert
>   Abstracts nur lückenhaft, Semantic Scholar braucht einen API-Schlüssel, Unpaywall eine
>   Kontakt-E-Mail.
> * **Keine freie Suchanfrage** (Punkt c der Vorgabe). Der Wert des Modus liegt im Bezug zum
>   eigenen Bestand; eine freie Suche könnte eine gewöhnliche Websuche besser.
> * **Aktualitätsfilter als Default** (letzte fünf Jahre, per `--seit` übersteuerbar). In S0 war
>   das Publikationsjahr der **wirksamste** Rauschfilter – es fängt 6 von 8 korpusfremden
>   Treffern, weil OpenAlex nach Zitationszahl rankt und alte Klassiker hochspült.
>
> **Über die Vorgabe hinaus** schließt S1 eine in S0 aufgedeckte Lücke: Dasselbe Paper erscheint
> bei beiden Quellen unter **verschiedenen** Identifikatoren (3 von 51 Treffern). Kandidaten werden
> deshalb zusätzlich **quellenübergreifend** über den normalisierten Titel zusammengeführt.
>
> **Akzeptanz erfüllt:** Die Deduplikation nutzt die **bestehende** Intake-Logik (kein zweiter
> Mechanismus) und wies in S0 **null** bereits vorhandene Paper als neu aus; ohne Netz endet der
> Modus in `dependency_error` mit handlungsleitender Meldung statt in einem Stacktrace, und der
> Bericht nennt zu jedem Vorschlag die auslösende Anfrage. Weil Titel und Abstracts **nicht
> vertrauenswürdige** Fremdeingaben sind, werden sie vor dem Schreiben entschärft – ein Punkt, den
> die Vorgabe nicht nennt.

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

> **Status: umgesetzt** ([ADR 0021](docs/adr/0021-local-multi-seed-phase10.md)) – mit einem
> **größeren *m*** als hier vorgeschlagen und einer **verworfenen** Teilmaßnahme.
>
> Das Abbruchkriterium wurde geprüft und **nicht** ausgelöst: *m* = 3 hebt die erreichbare
> Deckelung von **17 auf 28** von 34 Gold-Fragen. Wie schon in den Punkten A3–A7 hat die
> Vorabmessung die Vorgabe aber korrigiert – gleich dreifach.
>
> **1. *m* = 3 genügt nicht.** Das volle Bündel erreicht bei *m* = 3 nur 0,853 / 0,642 und bei
> *m* = 4 nur 0,882 / **0,648** – beide bleiben unter Basics MRR von 0,650. Nach der **vorab**
> festgelegten Regel (kleinstes *m*, das auf **beiden** Kennzahlen nicht unterlegen ist) fällt die
> Wahl auf **`DEFAULT_SEEDS = 5`**: **0,912 / 0,654** gegen Basic 0,882 / 0,650. Die
> Diagnose-Verteilung verschiebt sich wie erwartet von seed **17** auf **30**.
>
> **2. Das Akzeptanzkriterium dieser Vorgabe misst weniger, als es verspricht.** „Local erreicht
> mindestens die Basic-Werte" ist bei *m* = *k* **definitorisch** erfüllt, weil Locals Bündel dann
> Basics Top-*k* enthält. Es taugt – wie das End-to-End-Maß in A7 – nur als **Veto**. Der
> substanzielle Nachweis ist deshalb ein anderer: **0 Regressionen** bei **13** qid-genauen
> Verbesserungen, und **eine** Frage (G11), die Local findet und Basic@5 verfehlt. Offen
> ausgewiesen bleibt, dass Nachbarschaft (1 Treffer) und Fan-out (0) zur Kennzahl kaum beitragen –
> ihr Wert ist Kontext, und der ist mit diesem Gold-Set nicht messbar.
>
> **3. Der Fan-out wurde erweitert gemessen und **nicht** erweitert.** Die naheliegende
> Vereinigung über alle Seed-Paper ändert bei *m* = 5 **keine** der 34 Fragen; er bleibt daher am
> Ankerpaper. Ebenfalls verworfen – obwohl **besser** messend (0,941 / 0,664) – ist die Variante
> „Seeds aus verschiedenen Papern": Die paper-basierten Labels bilden ihren Preis nicht ab, denn
> sie verdrängt die zweitbeste Passage **desselben** Papers, also genau die Evidenz einer
> Detailfrage.
>
> **Über die Vorgabe hinaus** ist der Contract ehrlich gemacht: `LocalSearchResult.seed` heißt
> jetzt `seeds` und ist eine Liste (Spec `0.2.0`, bewusster Bruch). Eine Festlegung aus
> [ADR 0008](docs/adr/0008-retrieval-and-query-router-phase4.md) ist damit abgelöst. Kein
> Schema-Eingriff, **kein Re-Ingest**; `--check` belegt qid-genau, dass Primitive, Basic, Global
> und DRIFT **unberührt** bleiben.

*Befund:* Local erreicht Hit@5 **0,618** / MRR **0,532**, Basic dagegen **0,882** / **0,650**. Der Modus, den der Fragetyp-Contract der README für **Detailfragen** vorsieht, ist damit schwächer als seine eigene Rückfallebene. Die Diagnose zeigt warum: Von den Treffern stammen **17** vom Seed, **3** aus der Chunk-Nachbarschaft und **1** aus dem Paper-Fan-out. Das ist kein Ranking-, sondern ein Strukturproblem – Nachbarschaft und Fan-out messen Ähnlichkeit **zum Seed**, nicht zur Frage. Ist der Top-1-Seed falsch, ist das ganze Bündel verloren.

*Vorschlag:* Statt eines Seeds die Top-*m* der Hybrid-Wertung verwenden, die Nachbarschaft je Seed bilden und die Teilrankings per **Reciprocal Rank Fusion** zusammenführen – der Baustein liegt seit A4 in `indexing/fusion.py`.

*Erst messen:* Vorab auszählen, in wie vielen Gold-Fragen das erwartete Paper unter den Top-*m* Seeds liegt. **Hebt `m = 3` die erreichbare Deckelung nicht, entfällt der Punkt.**

*Akzeptanz:* Local erreicht mindestens die Basic-Werte; die Diagnose-Verteilung verschiebt sich nachweisbar; `--check` meldet keine qid-Regression; Determinismus und `Citation`-Contract unverändert.

### V2 – DRIFT: Community-Auswahl statt Top-1, mit Rückfallebene

> **Status: umgesetzt** ([ADR 0022](docs/adr/0022-drift-community-union-and-fallback-phase10.md)) –
> beide Maßnahmen wie vorgesehen, aber mit einer **korrigierten Lesart der Akzeptanzkriterien**.
>
> **1. Beide Kriterien unten sind rechnerisch vorbestimmt.** DRIFTs erreichbare Deckelung bei
> *m* Communities **ist** Globals `in_community` bei *n* = *m* – die geforderte „Deckelung ≥ 12"
> tritt allein dadurch ein, dass *m* = 5 gewählt wird; und „`no_community` geht auf 0" ist
> trivial, sobald ein Fallback existiert. Gemessen wurde deshalb an zwei anderen Fragen.
>
> **2. Die wichtigere Frage stand nicht in der Vorgabe – und ging gut aus.** Die heutige
> Fehlerfreiheit der Verfeinerung beruhte darauf, dass sie über **eine** Community rankt; mit der
> Vereinigung rankt sie über ein Vielfaches. Ergebnis: **keine** einzige zuvor gewonnene Frage
> geht verloren, zwei rutschen um einen Rang (G13, V12 – jeweils 1 → 2). Die Treffer des
> Community-Pfades steigen von **8 auf 11**, die Deckelung von **8 auf 12**. Bemerkenswert: *m* = 2
> und *m* = 3 gewinnen zwar eine Frage, **verschlechtern** aber den MRR – nur *m* = 5 verbessert
> beides. Ein am Gold-Set noch besseres *m* = 8 wurde **verworfen** (eine Frage von 34 =
> Overfitting; 5 ist zudem der Default der Global Search).
>
> **3. Der Fallback trägt die Hälfte der Treffer – und zwar als Basic.** Mit Fallback erreicht
> DRIFT **0,647 / 0,525**; er greift 12× und trifft dabei 11×. Von 22 Treffern stammen damit 11
> aus der corpusweiten Suche. Die Aggregatzahl wäre ohne diese Aufteilung irreführend, deshalb
> weist die Evaluation den Fallback als **eigene Diagnose** aus.
>
> **Zwei Befunde über die Vorgabe hinaus:** Die Vereinigung kann überhaupt nur bei **15 von 34**
> Fragen wirken (für 12 scort keine Community über 0, für 7 genau eine) – der Engpass ist das
> dünne Community-Dokument und damit **V4**. Und die in A6 gefeierte Eigenschaft
> „Treffer == Deckelung" ist **aufgegeben** (11 von 12): Bei G15 wächst die Kandidatenmenge auf 33
> Paper, und die Verfeinerung verfehlt das Ziel erstmals trotz erreichter Deckelung.
>
> `DriftSearchResult.community` heißt jetzt `communities` und ist eine Liste, neu ist `fallback`
> (Spec `0.2.0`, bewusster Bruch – sonst behäuptete die Antwort eine falsche Herkunft). Ein
> **defekter** Index bleibt ein Fehler. Kein Schema-Eingriff, **kein Re-Ingest**; `--check` belegt
> qid-genau, dass Primitive, Basic, Local und Global **unberührt** bleiben.

*Befund:* DRIFT erreicht **0,235 / 0,235** – und die Diagnose ist ungewöhnlich eindeutig: Treffer (8) und erreichbare Deckelung (8) sind **identisch**. Die lokale Verfeinerung arbeitet also **fehlerfrei**; **100 %** der Fehlschläge entstehen davor, in der Community-Wahl: **12×** wurde gar keine Community gefunden, **14×** die falsche. Global erreicht mit fünf Communities **12** Fragen – die Beschränkung auf die Top-1-Community kostet DRIFT damit rund ein Drittel.

*Vorschlag:* (a) Kandidatenmenge aus den Top-*m* Communities vereinigen statt nur der besten; (b) wird **gar keine** Community gefunden, sichtbar auf Basic zurückfallen statt leer zu liefern – dasselbe Muster, das A7 im Router etabliert hat (Rückfallebene mit ausgewiesener Konfidenz, nicht stilles Scheitern).

*Akzeptanz:* Die erreichbare Deckelung steigt von 8 auf ≥ 12; die Diagnose `no_community` geht auf 0, und zwar durch einen **ausgewiesenen** Fallback, nicht durch Verstecken; Determinismus; `--check` ohne Regression.

### V3 – Multi-Hop-Fragen gegen den Zitationsgraphen messbar machen

> **Status: umgesetzt** ([ADR 0023](docs/adr/0023-multihop-citation-evaluation-phase10.md)) – mit
> **einem korrigierten Anspruch** und **einer entlarvten Vorgabe-Annahme**.
>
> Das vorab fixierte Abbruchkriterium (strukturelle Ebene auf Zufallsniveau **und** über 80 %
> der Titel-Treffer aus Referenz-Chunks) wurde geprüft und **nicht** ausgelöst. Wie in den
> Punkten A3–A7 und V1/V2 hat die Vorabmessung die Vorgabe aber an drei Stellen korrigiert.
>
> **1. Der Ähnlichkeitsgraph trägt Zitationsnähe – erstmals beziffert.** Die neue **strukturelle**
> Ebene fragt ohne jeden Text: Enthalten die Top-5-Nachbarn eines Ankerpapers die Paper, die es
> zitieren? Coverage **0,181** bei Selektivität **0,022** ergibt einen **Lift von 8,20** gegen
> **0,98** einer gleich großen Zufallsauswahl. Das ist die erste Zahl überhaupt zum
> GraphRAG-Anspruch des Paper-Graphen.
>
> **2. Die naheliegende Fragenform nimmt eine lexikalische Abkürzung.** „Welche Paper bauen auf
> *Titel* auf?" wird zu einem guten Teil über das **Literaturverzeichnis** der zitierenden Paper
> beantwortet – gemessen **22 von 33** Basic-Treffern und **26 von 42** Local-Treffern. Die
> Abkürzung wird nicht versteckt, sondern als Diagnose (`:ref` statt `:body`) ausgewiesen, und
> eine zweite Anfrageform aus den **Themen-Termen** des Ankers dient als Gegenprobe – sie kommt
> ohne einen einzigen Referenz-Treffer aus. Ebenso fest verdrahtet: Das **Ankerpaper verlässt
> jedes Bündel**, weil es per Konstruktion nie ein erwartetes Paper sein kann, aber die vorderen
> Ränge besetzt (MRR 0,428 → **0,701** allein dadurch).
>
> **3. Der Zusatznutzen unten ist logisch nicht erreichbar – und das ist der wichtigste Befund.**
> Aus `citation_edges` abgeleitete Labels können eine **fehlende** Kante nicht sichtbar machen;
> der offene Recall aus [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md) bleibt
> offen. Ausgewiesen werden stattdessen **mechanische Schranken**: 2 von 145 Papern ohne
> erkannten Referenzabschnitt, 3 mit zu kurzem Titel, 15 ohne frontmatter-belegten Identifikator
> – und damit **genau 1** Paper, das als Ziel strukturell unerreichbar ist. Eine obere Grenze
> der Vollständigkeit, kein gemessener Recall.
>
> **Ergebnis:** Auf dieser Ebene **schlägt Local den Basic-Modus deutlich** (0,955 vs. 0,750 bei
> der Titel-Form, 0,636 vs. 0,250 bei der Themen-Form) – die Struktur zahlt sich genau dort aus,
> wo der README-Contract sie vorsieht. Nebenbei ist ein Befund aus
> [ADR 0016](docs/adr/0016-quantitative-retrieval-evaluation-phase7.md) als Artefakt des
> fakt-orientierten Gold-Sets entlarvt: „Der Fan-out rettet 1 von 34 Fragen" – hier steuert er
> **13 von 28** Treffern der Themen-Anfrage bei.
>
> **Bewusst anders als unten:** `get_citations` wird **nicht** als Kennzahl geführt (es liest
> dieselbe Tabelle wie die Labels, jede Zahl wäre 1,000 by construction), sondern als
> Contract-Test und als ausgewiesener trivialer Oberwert. Gold-Set und Baseline sind **eigene**
> Artefakte statt einer Erweiterung der bestehenden – sonst mischten sich zwei unvergleichbare
> Fragetypen in dieselben Aggregate, und jeder Regressions-Check dauerte ein Vielfaches
> (siehe [B3](#b3--messung-ohne-wartezeit)). Kein Schema-Eingriff, **kein Re-Ingest**, und
> **keine** Retrieval-Änderung: Die Messung bestätigt den Contract, statt ihn zu widerlegen.

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

> **Status: umgesetzt** (2026-08-06, [ADR 0027](docs/adr/0027-corpus-backup-phase11.md)). Neu sind `backup.py` (Top-Level) und das dünne `scripts/backup.py` mit `--dry-run`, `--pruefen` und einem Fortschrittsbalken.
>
> **Der Umfang wurde gegenüber dieser Akzeptanz präzisiert**, weil sie aus der Zeit vor Phase 9 und Phase 12 stammt: Neben `papers/`, [`Übersicht.md`](Übersicht.md) und `data/manifest.json` sind auch `metadata/paper_metadata.json` (Herkunft `manual` ist aus **keiner** Quelle reproduzierbar) sowie die drei append-only Protokolle `data/intake_log.md`, `data/metadata_log.md` und `data/online_candidates.md` nicht rekonstruierbar. **Nicht** gesichert werden `data/canonical/`, `data/index/` und die Qualitätsberichte – und zwar aus **Korrektheits-, nicht aus Platzgründen**: Sie machen nur 8,7 % aus (68,7 MB von 788 MB), ein mitgesicherter Index verleitet aber dazu, ihn zurückzuspielen, obwohl er zum wiederhergestellten Korpus nicht passen muss. Der Weg zurück ist deshalb genau einer: zurückkopieren, dann `python -m scripts.ingest`.
>
> **Die zweite Hälfte der Akzeptanz war bereits erfüllt** – belegt statt gebaut: Ein Scan aller löschenden Aufrufe unter `src/research_graphrag/` ergab genau vier Stellen mit Nutzerwirkung, alle vier in `intake.py`, und `scripts.intake` besitzt `--dry-run` seit Phase 8. Die übrigen Treffer sind Temporärdateien atomarer Schreibvorgänge und das Verwerfen **abgeleiteter** Artefakte.
>
> **Realer Nachweis** (341 Paper): Vorschau und Lauf treffen dieselben Entscheidungen für **348 Dateien / 680,9 MiB**; der zweite Lauf kopiert **0** und ist nach 15 s fertig (Idempotenz über sha256); `--pruefen` bestätigt 348/348 mit Exit `0`, nach einer gezielten Manipulation meldet es die Datei namentlich mit Exit `1`. Der Sicherungsstand enthält nachweislich **kein** `canonical/` und **kein** `index/`. Kein Schema-Eingriff, kein Contract, kein neues MCP-Werkzeug (der Server bleibt bei **neun**).

### B2 – Inkrementelles Update statt vollem Re-Index

*Lücke (bisher A8a):* Der volle Re-Index ist bei ~145 Papern günstig und konsistent, wächst aber linear mit dem Bestand – und Phase 9 lässt den Bestand systematisch wachsen (Auslegung bis ~500 Paper).

*Akzeptanz:* Nur neue/geänderte Paper extrahieren und indizieren, danach den Graphen neu bauen; das Ergebnis ist **nachweislich identisch** zum vollen Re-Index (Byte-Vergleich der Kanten, Communities und Zitationskanten – die Methodik ist in A3 und A5 etabliert). Der volle Re-Index bleibt Standard.

### B3 – Messung ohne Wartezeit

*Lücke:* Ein `--modi`-Lauf dauert mehrere Minuten, weil der Index je Ebene neu geladen wird (in A6 bewusst nicht optimiert, um keinen Contract anzufassen). Eine Messung, die man ungern startet, wird seltener gestartet – und genau diese Messungen haben in A3 bis A7 wiederholt die Annahmen korrigiert.

*Akzeptanz:* Index einmal laden und durchreichen, **ohne** Eingriff in einen Contract; die Ergebnisse sind bit-identisch zur eingefrorenen Baseline (`--check` ist der Beweis).

### B4 – Auto-Watcher: bewusst gestrichen

Der frühere Punkt A8b entfällt. `watchdog` ist offline **vorhanden** – technisch scheitert es also nicht. Die Entscheidung ist fachlich: Der Intake **löscht Dateien** und verändert den Korpus; beides soll beobachtet und angestoßen werden, nicht im Hintergrund passieren. Ein Watcher würde die einzige Stelle automatisieren, an der ein Mensch hinsehen soll.

### B5 – Messgrundlage nachführbar halten

*Lücke (2026-08-06 aufgefallen, nachträglich aufgenommen):* Die Gold-Sets und Baselines waren auf den Stand von **145** Papern eingefroren, der Korpus ist auf **341** gewachsen. `--verify-labels` reproduzierte nur noch **1 von 34** Fragen, beide `--check`-Läufe verweigerten den Vergleich mit Exit `2`. Der Fingerprint-Guard hat damit korrekt gearbeitet – der quantitative Regressionsschutz war trotzdem faktisch außer Betrieb. Ursache war eine Werkzeuglücke: Für das Multi-Hop-Gold gab es einen reproduzierbaren Neuableitungs-Weg (`--zitationen --write-gold`), für das **Retrieval**-Gold nicht.

*Akzeptanz:* Ein Befehl leitet die mechanischen Labels aus dem aktuellen Index neu ab, ohne die Fragen anzufassen; das Ergebnis ist über `--verify-labels` vollständig nachrechenbar, und eine Frage ohne Ziel wird als Befund gemeldet statt still geschrieben.

> **Status: umgesetzt** (2026-08-06, Nachtrag in [ADR 0016](docs/adr/0016-quantitative-retrieval-evaluation-phase7.md)). Neu sind `relabel_gold_set`, `unlabelled_questions` und `save_gold_set` im Paket `evaluation` sowie `python -m scripts.eval_retrieval --write-gold` (mit `--gold-version` und `--notiz`).
>
> **Warum ein Gold-Set einen Korpuswechsel nicht überlebt:** Die Labels sind Paper-IDs, und eine `paper_id` ist der sha256-Hash der Datei. Ein durch eine neuere Fassung **ersetztes** PDF bekommt eine neue ID – das eingefrorene Label zeigt danach ins Leere, unabhängig davon, ob der Inhalt noch im Korpus steht. Genau das erklärt die 6 weggefallenen Alt-Ziele restlos: Sie gehören zu **4 Papern, die nicht mehr im Bestand sind**.
>
> **Gemessene Drift vor der Neuableitung:** 32 der 34 Fragen gewinnen Ziele hinzu, 2 bleiben gleich, keine verliert unterm Strich. Die Zielmenge wächst von **141 auf 355** (Faktor 2,52) bei einem Korpus-Faktor von 2,35 – die Label-Regel skaliert also proportional. Die breiteste Frage deckt **7,9 %** des Korpus ab, eine zufällige Fünferauswahl erreicht Hit@5 = **0,146**: Die Trennschärfe bleibt erhalten. Keine Frage steht ohne Ziel da.
>
> **Neuer Stand** (Gold-Set **1.3.0**, Fragen wortgleich, **34/34** Labels reproduzierbar; Multi-Hop-Gold **44 → 113** Anker, 113/113 geprüft): primitive/basic/local **0,824 / 0,736**, global **0,559 / 0,412**, drift **0,588 / 0,472**; Community-Auswahl Lift **5,80** gegen größte-5 1,04 und zufällig-5 0,94. Multi-Hop: graph **0,593 / 0,452**, basic_title **0,673 / 0,634**, local_title **0,858 / 0,768**, basic_topic **0,142 / 0,133**, local_topic **0,628 / 0,464**; strukturelle Auswahl Lift **15,09** gegen 1,03. Beide Baselines sind neu eingefroren, beide `--check`-Läufe melden 0 Abweichungen.
>
> **Ehrlich dazu:** Diese Zahlen sind mit den alten **nicht** vergleichbar – Korpus *und* Labels haben sich geändert. Belastbar ist allein das Verhältnis der Ebenen innerhalb eines Laufs. Global hat deutlich zugelegt (Lift 3,55 → 5,80), und auf dem fakt-orientierten Set liefert **Local exakt dasselbe wie Basic** – alle 28 Treffer aus den Seeds, null Beitrag von Nachbarschaft und Fan-out.
>
> **Der naheliegende Schluss daraus wäre falsch** und wurde durch die Multi-Hop-Messung desselben Korpus widerlegt: Dort steuert der Fan-out **44 von 71** Treffern der Themen-Anfrage bei, und die strukturelle Auswahl über den Ähnlichkeitsgraphen erreicht **Lift 15,09** (vorher 8,20) – der Graph ist also **besser** geworden, nicht schlechter. Damit bestätigt sich erneut, was schon [ADR 0023](docs/adr/0023-multihop-citation-evaluation-phase10.md) festgehalten hat: „Der Fan-out trägt kaum bei" ist eine Eigenschaft des **fakt-orientierten Gold-Sets**, dessen Labels mechanisch aus dem Chunk-Text stammen und deshalb die direkte Chunk-Suche strukturell bevorzugen. Die korrekte Aussage lautet: *Auf lexikalisch verankerten Faktfragen ist Local nicht besser als Basic.*

### B6 – Grad des Ähnlichkeitsgraphen (geprüft, verworfen)

*Lücke (2026-08-06 aufgefallen, nachträglich aufgenommen):* Der Ähnlichkeitsgraph verbindet jedes Paper über *mutual top-k* mit höchstens `DEFAULT_K = 8` Nachbarn – ein Wert aus der Zeit mit 145 Papern. Bei 341 Papern haben **85 Paper (24,9 %) keinen einzigen Nachbarn** und damit keinen Fan-out.

*Akzeptanz (vorab fixiert):* Das kleinste k, das (1) auf **beiden** Gold-Sets keine Kennzahl verschlechtert, (2) die isolierten Paper mindestens halbiert und (3) die größte Community unter 20 % des Korpus hält. Erfüllt kein Kandidat alle drei, wird der Punkt verworfen und der Befund dokumentiert.

> **Status: geprüft und verworfen** (2026-08-06, [ADR 0028](docs/adr/0028-similarity-graph-degree-phase11.md)). **Keine Code-Änderung**, kein Schema-Eingriff, kein Re-Ingest, keine neue Baseline.
>
> **Die Ursache ist nicht die Schwelle:** 339 von 341 Papern (**99,4 %**) haben einen Nachbarn ≥ 0,10, der Median der besten Ähnlichkeit liegt bei **0,372**. Eine Schwellenänderung von 0,04 auf 0,15 bewegt die Kantenzahl nur von 442 auf 426. Isolation entsteht **allein** durch die Verdrängung im mutual top-k. Damit ist die Schwelle als Stellschraube erledigt.
>
> **Gemessen wurde gegen Index-Kopien** (der Live-Index blieb unberührt), nachdem die Rekonstruktion mit `k = 8` den Live-Stand exakt reproduziert hatte (439 Kanten / 115 Communities / 85 Singletons):
>
> | Ebene | k = 8 | k = 16 | k = 20 |
> | --- | --- | --- | --- |
> | basic / local | 0,824 / 0,736 | 0,824 / 0,736 | 0,824 / 0,736 |
> | global | **0,559** / 0,412 | 0,529 / 0,476 | 0,529 / 0,462 |
> | drift | 0,588 / 0,472 | 0,706 / 0,604 | 0,706 / 0,633 |
> | **Lift der Community-Auswahl** | **5,80** | 3,29 | **2,96** |
> | `no_community` · `fallback` | 2 · 2 | 8 · 8 | 9 · 9 |
>
> **Bedingung 1 ist bei beiden Kandidaten verletzt** – Global verliert Hit@5. Drei Beobachtungen zeigen, dass das kein Rauschen ist: Der **Lift halbiert sich** (die Auswahl wird größer, nicht besser – die Coverage steigt, die Selektivität stärker); der **DRIFT-Gewinn ist erkauft**, weil `fallback` von 2 auf 9 steigt und DRIFT damit häufiger nur das Basic-Ergebnis liefert; und **`no_community` steigt trotz mehr Kanten** von 2 auf 9, weil weniger und größere Communities unschärfere Community-Dokumente ergeben. Der dichtere Graph schadet also genau der Ebene, die von ihm lebt.
>
> **Das ist zugleich ein Argument für [V4](#v4--global-community-ranking-über-die-mitglieds-chunks-erst-messen-dann-entscheiden):** Wäre das Community-Dokument nicht nur zehn Keywords plus Auszug, könnte ein dichterer Graph seine Wirkung überhaupt erst entfalten.
>
> **Bewusst getragene Grenze:** 85 Paper bleiben ohne Fan-out. Wer zu einem solchen Paper verwandte Arbeiten sucht, nutzt `get_citations` und die Chunk-Suche.

---

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

| Risiko                                                                        | Gegenmaßnahme                                                                                                                                                                                                                                        |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PDF-Extraktionsrauschen (Layout, Formeln, Scans)                              | Qualitäts-Gates, Provenienz zum Original, Stichproben; Textnormalisierung ([ADR 0015](docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)); Docling/Marker als späterer Ausbau ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)). |
| **Datenverlust durch den Intake** (hartes Löschen)                     | `--dry-run`, Bericht mit Hash je gelöschter Datei, Sicherungsweg aus [B1](#b1--sicherung-des-korpus).                                                                                                                                               |
| **Unkuratierte PDFs aus dem Netz** (Scans, Fehlerseiten, Schadinhalte)  | Lizenz-Whitelist, Content-Type-/Größenprüfung, selbst erzeugte Dateinamen, Robustheits-Flag für chunk-lose Dokumente.                                                                                                                             |
| **Verwässerung des kuratierten Korpus** durch automatische Vorschläge | Vorschläge landen im Bericht, nie automatisch im Korpus; Zielgröße ist Präzision, nicht Menge.                                                                                                                                                    |
| Entity Resolution (Synonyme, gleichnamige Autoren)                            | leichte Alias-/Synonym-Kuratierung; bei kleinem Korpus manuell handhabbar.                                                                                                                                                                            |
| Scheinsicherheit durch Summaries                                              | Antworten immer mit Quellenankern/Original-TextUnits; für Fakten Basic/Local bevorzugen.                                                                                                                                                             |
| Inkonsistenz bei inkrementellen Updates                                       | Standard bleibt der volle Re-Index; inkrementell nur mit Identitäts-Nachweis ([B2](#b2--inkrementelles-update-statt-vollem-re-index)).                                                                                                                |
| Kosten/Datenschutz eines Index-LLM                                            | entschärft durch Option B:**kein** Index-LLM (offline, TF-IDF/BM25); ein LLM kommt nur zur Abfragezeit über die Bridge ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)).                                                             |

---

## Phase 12 – Zitierfähigkeit: vom Identifikator zur Literaturangabe

> **Status: umgesetzt.** Beide Punkte sind erledigt – **K1** (netzfrei) und **K2** (Auflösung).
> Belegt am realen Korpus (341 Paper): **vollständig zitierfähig 0 → 336**, Paper mit
> Identifikator 329 → **339**, und die kuratierte Übersicht steuert erstmals maschinell
> **265 Feldwerte** bei (131 Titel, 91 arXiv-IDs, 35 DOIs, 8 Links), die zuvor ungenutzt in einer
> Markdown-Tabelle lagen ([ADR 0025](docs/adr/0025-citable-paper-metadata.md) ·
> [ADR 0026](docs/adr/0026-online-metadata-resolution.md)).

### Warum das nötig war (und was gemessen wurde)

Das Werkzeug begleitet eine wissenschaftliche Arbeit – aber bis Phase 11 lieferte **eines von
acht** Werkzeugen (`get_paper`) überhaupt einen extern auflösbaren Identifikator. Alle
Suchtreffer, alle Belege in `answer_question` und alle Community-Referenzen trugen ausschließlich
eine interne `paper_id` und einen lokalen Dateipfad. Der Zitier-Contract aus
[ADR 0012](docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md) verlangte Marken `[1]`,
`[2]` …, die auf nichts Zitierbares zeigten.

Die Vorabmessung korrigierte zugleich die naheliegende Annahme, die Extraktion sei „gut genug":

| Befund (341 Paper) | Wert |
| --- | --- |
| Paper mit mindestens einem extrahierten Identifikator | 329 (96,5 %) |
| davon **nicht** auf der eigenen Titelseite belegt | ≈ 45 |
| Identifikatoren mit mehr als einem Träger | 9 (u. a. der MBPP-Falsch-Hub, der ACM-Platzhalter) |
| kuratierte Übersichtszeilen mit externer Angabe | 129 von 131 |
| davon **abweichend** von der Extraktion | **29** |

Die 29 Abweichungen haben zwei Ursachen, und beide sind lehrreich: teils nennt die Übersicht
legitim den **Publisher-DOI**, wo die Extraktion die arXiv-ID liest; teils ist die Extraktion
schlicht **falsch**. Für Retrieval ist das gleichgültig, für eine Literaturangabe nicht – ein
falscher DOI ist schlimmer als kein DOI.

### K1 – Zitierfähige Metadaten, netzfrei

*Umgesetzt:* eigene **versionierte** Quelle `metadata/paper_metadata.json` (außerhalb des
regenerierbaren `data/`), **feldweise** Auflösung nach `manual > curated > resolved > extracted`
mit ausgewiesener Herkunft je Feld, additive Index-Tabelle `paper_metadata`, Durchreichung von
`identifiers` und `citation_key` bis in jeden Beleg, vollständige Literaturangaben (Harvard und
APA) in `answer_question`, `get_paper`, dem neunten Werkzeug `get_reference` und
`python -m scripts.cite`.

*Bewusst nicht:* die vollständige Angabe in **jedem** Chunk-Zitat (fünf Belege desselben Papers
trügen sie fünfmal) und ein Zugriffsdatum in der Literaturangabe (es wäre vom Ausführungstag
abhängig und bräche jeden Byte-Vergleich).

### K2 – Online-Auflösung der fehlenden Felder

*Umgesetzt:* `python -m scripts.resolve_metadata` löst Autoren, Venue und Publikationsjahrgang
über OpenAlex auf (Rückfall: arXiv-Feed), **automatisch** übernommen, aber mit ausgewiesener
Belegstärke: Identifikator-Treffer `strong`, nicht belegter Identifikator oder Titel-Ähnlichkeit
`weak`, unterhalb der Schwelle verworfen. Protokoll append-only in `data/metadata_log.md`.

*Bewusst nicht:* eine Auflösung **im Ingest** – der Kern bleibt netzfrei und deterministisch – und
**kein** MCP-Werkzeug, weil der Lauf schreibt und Netz benötigt.

### Ergebnis am realen Korpus

| Kennzahl | vorher | nachher |
| --- | --- | --- |
| vollständig zitierfähige Paper | 0 | **336** von 341 |
| Paper mit Identifikator | 329 | **339** |
| schwach belegte Datensätze | – | 66 (ausgewiesen) |
| Werkzeuge mit Identifikator in der Antwort | 1 von 8 | **9 von 9** |

Offen bleiben **5** Paper, für die keine Quelle einen Treffer liefert; sie sind über einen
`manual`-Eintrag zu pflegen.

---

## Meilensteine

- **M0 – Migration:** ✅ erreicht – PDFs und `Übersicht.md` ins Repo übernommen (Phase 1).
- **M1 – Erster Durchstich:** ✅ erreicht – 1 PDF → Index → 1 Frage mit Quelle beantwortet (Phase 0b).
- **M2 – Copilot nutzt es:** ✅ erreicht – stdio-MCP-Server registriert, Werkzeuge mit Provenienz (Phase 5).
- **M3 – Drop & Use:** ✅ erreicht – Drop-in-Kreislauf mit atomarem Index-Swap und pragmatischer QS (Phase 6).
- **M4 – Belegte Qualität:** ✅ erreicht – Retrieval und Router sind **quantitativ** messbar (Gold-Sets, Baseline, Regressions-Check; A4/A6/A7).
- **M5 – Zufluss ohne Doppelbestand:** ✅ erreicht – neue PDFs gehen über `new_papers/` in den Korpus, Duplikate werden erkannt, die Übersicht wächst mit (Phase 8).
- **M6 – Online-Recherche entschieden:** ✅ erreicht – S0 ist beantwortet: Die Quellen sind über den authentifizierten Unternehmens-Proxy erreichbar (arXiv/OpenAlex/Crossref mit HTTP 200), und die Handprobe liegt mit 76–82 % deutlich über der vorab festgelegten Schwelle von 30 %. Empfohlen ist ein **engerer Zuschnitt** als geplant: S1 nur mit arXiv + OpenAlex, S2 zurückgestellt (Phase 9).
- **M7 – Local schlägt Basic:** ✅ erreicht – der für Detailfragen vorgesehene Modus ist nicht länger schwächer als seine Rückfallebene (Hit 0,618 → **0,912**, MRR 0,532 → **0,654** gegen Basic 0,882 / 0,650). **Ehrlich dazu:** Der Zugewinn ist teilweise definitorisch, weil Locals Bündel mit fünf Seeds die Top-5 der Chunk-Suche enthält; belastbar sind die **13 qid-genauen Verbesserungen ohne Regression** (Phase 10 / V1).
- **M8 – Aus dem Fund wird eine Quelle:** ✅ erreicht – jeder Beleg trägt einen extern auflösbaren Identifikator, und aus einem Suchtreffer entsteht ohne Handarbeit eine korrekte Literaturangabe in Harvard und APA. **336 von 341** Papern sind vollständig zitierfähig (vorher **0**). **Ehrlich dazu:** 66 Datensätze beruhen auf einem nicht eindeutigen Beleg und sind als `weak` markiert; 5 Paper bleiben ohne Auflösung (Phase 12).
