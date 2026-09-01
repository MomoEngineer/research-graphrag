# Roadmap – Research-GraphRAG

Phasenweiser Umsetzungsplan für den persönlichen Scientific-GraphRAG-Assistenten. Der Plan ist **iterativ**: erst ein dünner, lauffähiger Durchstich, dann gezielte Ausbaustufen. **Bewusst ohne Zeitschätzungen** – Fortschritt wird über die „Definition of Done" (DoD) je Phase und über Meilensteine gemessen.

> Ergänzt die [README](README.md). **Die Phasen 0–8 sowie 11, 12, 13, 14 und 15 sind abgeschlossen**
> und hier nur noch als Ergebnis-Tabelle zusammengefasst; die vollständigen Status-Blockquotes mit
> allen Kennzahlen, korrigierten Annahmen und offen dokumentierten Abweichungen stehen wörtlich in
> der [Roadmap-Historie](docs/roadmap-historie.md). **Phase 13 steht weiterhin vollständig hier**,
> als einzige Ausnahme von dieser Regel – sie war die unmittelbare Grundlage von Phase 14 und
> bleibt aus Kontinuitätsgründen an Ort und Stelle, auch nachdem Phase 14 selbst archiviert ist.
> **Kein aktiver Plan derzeit:** Phase 15 (Skalierung, [Statusblock](docs/roadmap-historie.md#g0--alles-hinterfragen-und-messen-zwingend-zuerst))
> und Phase 14 (Referenz-Ernte, [Statusblock](docs/roadmap-historie.md#e0--alles-hinterfragen-und-messen-zwingend-zuerst))
> sind beide abgeschlossen; Phase 14 **entfällt in der geplanten Form** – E0 fand einen
> billigeren, gleichwertigen Weg über die bestehende Kette und führte ihn selbst vor. **Phase 9 /
> S2 ist jetzt ebenfalls umgesetzt** ([ADR 0035](docs/adr/0035-fulltext-download-phase9-s2.md)) –
> die ursprüngliche Zurückstellung wurde nicht durch eine neue Messung aufgelöst, sondern durch
> eine an die Datenlage angepasste Anforderung: Fehlt eine Lizenz aus der Whitelist, bleibt der
> Kandidat ein Link statt eines Download-Versuchs, das ist der gewollte Regelfall. **Mit
> [V4](#v4--global-community-ranking-über-die-mitglieds-chunks-erst-messen-dann-entscheiden) ist
> jetzt auch der letzte offene Restpunkt umgesetzt** ([ADR 0036](docs/adr/0036-global-community-ranking-over-member-chunks-phase10.md)):
> Der Community-Score aggregiert das Mittel der fünf höchsten Hybrid-Chunk-Scores der
> Mitgliederpaper statt eines separaten TF-IDF-Rankings über Keywords + Summary – Global-Hit@5
> steigt am 606-Paper-Korpus von 0,529 auf **1,000**, DRIFT profitiert automatisch mit (0,588 →
> **0,882**), weil beide Modi dieselbe Auswahlfunktion teilen. **Damit hat Roadmap.md aktuell
> keine offenen Phasen mehr** – jede hier geführte Phase (9, 10, 13) ist abgeschlossen; ein
> künftiger Bedarf entsteht erst wieder aus neuen Befunden, nicht aus einer Restarbeit dieses
> Dokuments.

---

## Leitprinzipien

- **Lean & container-frei:** reine Python-Umgebung, kein Docker-/DB-Server.
- **Provenienz zuerst:** jede Antwort ist auf Paper/Abschnitt/Seite rückführbar.
- **Inkrementell nutzbar:** neue PDFs per Drop-in-Ordner + Skript, ohne alles neu aufzusetzen.
- **Klein, aber wachstumsfähig:** **gemessene Auslegung (2026-09-01, [Phase 15 / G5](docs/roadmap-historie.md#g5--auslegung-neu-festschreiben)): ≤ 750 Volltexte / ≤ 1500 Gesamteinträge.** Die frühere Zahl „≤ 500 Paper" stammte aus der Zeit mit 145 Papern und war bei 468 bereits faktisch erreicht; die neue Zahl ist eine **direkt am Auslegungsstand nachgemessene** 5-s-Marke für eine kalte Einzelanfrage über **alle vier** Modi (nicht nur Basic) – Local reißt die Marke bereits zwischen 800 und 900 Papern, deutlich vor der aus G0.1 grob hergeleiteten 1000er-Zahl (siehe [ADR 0033](docs/adr/0033-response-latency-cache-and-persisted-tfidf-state-phase15.md) und den [G5-Statusblock](docs/roadmap-historie.md#g5--auslegung-neu-festschreiben)). Auch 750 ist eine **Marke, keine Wand für die Ewigkeit** – jenseits von 606 Papern sind Retrieval-Güte (G0.3) und Community-Lift (G0.4) nur strukturell, nicht inhaltlich validiert.
- **Offline zuerst:** umgesetzt ist die Offline-Variante (Option B, [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)); ein Netzzugriff bleibt eine **separat startbare Zusatzfunktion**, nie eine Voraussetzung.
- **Erst messen, dann bauen.** Das ist die wichtigste Lehre aus den Phase-7-Punkten und keine Floskel: In **A3** war die vermutete Ursache der `short_chunk`-Flut falsch (nicht die Seitengrenze, sondern die Überschriften-Heuristik), in **A4** bestätigte sich die Annahme „Fusion schlägt Einzelverfahren" nicht, in **A5** saß das Keyword-Rauschen nicht im Vektorraum, sondern in der Auswahlpolitik, in **A6** hätte eine nackte Coverage-Kennzahl die triviale Strategie gekürt, und in **A7** waren die vermuteten Signal-Konflikte mit 1 von 44 Fragen praktisch inexistent. Jede Ausbaustufe beginnt daher mit einer Wegwerf-Messung und einem **Abbruchkriterium**.
- **Präzision vor Recall**, wo Daten in den Korpus oder in den Graphen fließen ([ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)).

---

## Stand: Phasen 0–8, 11, 12, 13, 14 und 15 (abgeschlossen)

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
| **8** – Korpus-Zufluss & Intake      | dreistufige Dedup (`new_papers/` → `papers/`), Robustheits-Gate, atomarer Swap, append-only Übersicht (`Z`-IDs), `scripts.intake`; **M5** erreicht | [ADR 0019](docs/adr/0019-corpus-intake-new-papers-phase8.md)                                                                                    |
| **12** – Zitierfähigkeit            | `metadata/paper_metadata.json`, feldweise Auflösung (`manual > curated > resolved > extracted`), `get_reference`, Literaturangaben Harvard/APA; **M8** erreicht | [ADR 0025](docs/adr/0025-citable-paper-metadata.md) · [ADR 0026](docs/adr/0026-online-metadata-resolution.md)                                    |
| **9 / S0–S2** – Online-Kandidatensuche & Volltext-Download | arXiv + OpenAlex hinter injizierbarem Transport-Port, Dedup über die Intake-Logik, append-only Bericht; **M6** erreicht. **S2** (`--download`) lädt opt-in, nur bei Lizenz-Whitelist (CC0/CC-BY/CC-BY-SA, nur OpenAlex) und bestandenem Titel-Rückvergleich – alles andere bleibt ein Link | [ADR 0020](docs/adr/0020-online-candidate-search-phase9.md) · [ADR 0032](docs/adr/0032-system-proxy-autodetection.md) · [ADR 0035](docs/adr/0035-fulltext-download-phase9-s2.md) |
| **10 / V1–V4** – Retrieval-Vertiefung | Local mit fünf Seeds, DRIFT über die Community-Vereinigung mit Fallback, Multi-Hop gegen den Zitationsgraphen messbar, Global-Community-Ranking über die Mitglieds-Chunks; **M7** erreicht, **alle vier Punkte umgesetzt** | [ADR 0021](docs/adr/0021-local-multi-seed-phase10.md) · [ADR 0022](docs/adr/0022-drift-community-union-and-fallback-phase10.md) · [ADR 0023](docs/adr/0023-multihop-citation-evaluation-phase10.md) · [ADR 0036](docs/adr/0036-global-community-ranking-over-member-chunks-phase10.md) |
| **11** – Betrieb & Datensicherheit | Sicherungsweg (B1), nachführbare Messgrundlage (B5), Graph-Grad geprüft und **verworfen** (B6), Auto-Watcher gestrichen (B4). **Aufgelöst:** B2/B3 sind in [Phase 15](docs/roadmap-historie.md#phase-15--skalierung-den-wachsenden-bestand-tragen) übergegangen – [Archiv](docs/roadmap-historie.md#phase-11--betrieb-robustheit--datensicherheit) | [ADR 0027](docs/adr/0027-corpus-backup-phase11.md) · [ADR 0028](docs/adr/0028-similarity-graph-degree-phase11.md) |
| **13** – Referenz-Einträge ohne Volltext | `*.refjson`-Stubs aus DOI/arXiv, `document_kind` bis in jeden Beleg, Nachrangigkeits-Guardrail (13 → **3** Regressionen ohne Totalverlust); **M9** erreicht – [Details unten](#phase-13--referenz-einträge-ohne-volltext) | [ADR 0029](docs/adr/0029-reference-stub-resolution-phase13.md) · [ADR 0030](docs/adr/0030-reference-entries-in-corpus-phase13.md) · [ADR 0031](docs/adr/0031-reference-contract-and-guardrail-phase13.md) |
| **15** – Skalierung (G0–G5) | Aho-Corasick statt O(Paper²), Prozess-Cache mit persistiertem TF-IDF-Zustand (warm < 1 s), `Übersicht.md` abgelöst durch `metadata/curation.json`, Auslegung neu festgeschrieben (≤ 750 Volltexte / ≤ 1500 Gesamteinträge); **M11** erreicht – [Archiv](docs/roadmap-historie.md#phase-15--skalierung-den-wachsenden-bestand-tragen) | [ADR 0033](docs/adr/0033-response-latency-cache-and-persisted-tfidf-state-phase15.md) · [ADR 0034](docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md) |
| **14** – Referenz-Ernte (E0) | **Entfällt in der geplanten Form:** E0 fand einen billigeren, gleichwertigen Weg (bestehende Kette `resolve_references` → `intake` statt neuer Ernte-/Kurationswerkzeuge) und führte ihn selbst mit 15/15 echten Treffern vor; zwei bindende Auflagen für einen künftigen manuellen Harvest festgehalten; **M10** erreicht (angepasste Form) – [Archiv](docs/roadmap-historie.md#phase-14--referenz-ernte-externe-verweise-aus-dem-eigenen-bestand) | Kein ADR (E0 baut nichts) |

**Nicht umgesetzt aus Phase 7:** der Punkt **A8** (inkrementelles Update, Auto-Watcher). Er ist in dieser Fassung aufgelöst – das inkrementelle Update lebt über B2 in [Phase 15 / G1](docs/roadmap-historie.md#g1--aufnahmepfad-begradigen-die-quadratischen-stellen) weiter (dort ausdrücklich als **Frage**, siehe [G0.5](docs/roadmap-historie.md#g05--erübrigt-sich-das-inkrementelle-update)), der Auto-Watcher ist [bewusst gestrichen](docs/roadmap-historie.md#b4--auto-watcher-bewusst-gestrichen) und wird durch den manuellen Intake der [Phase 8](docs/roadmap-historie.md#phase-8--korpus-zufluss-new_papers--intake) ersetzt.

> **Warum die Kennzahlen hier fehlen:** Sie stehen in den ADRs und in der [Historie](docs/roadmap-historie.md) und veralten dort nicht. Den **aktuellen** Bestand zeigt `python -m scripts.status`, die aktuelle Retrieval-Güte `python -m scripts.eval_retrieval`.

---

## Offene Restpunkte (kein Reihenfolgekonflikt)

Mit Phase 9 / S2, 10 / V4, 14 und 15 abgeschlossen bleibt **kein** Restpunkt mehr offen. Der
letzte – **[V4 – Global-Ranking über die Mitglieds-Chunks](#v4--global-community-ranking-über-die-mitglieds-chunks-erst-messen-dann-entscheiden)**
(Phase 10) – war lange nachgelagert, weil die ursprüngliche Prämisse einen Referenz-Zufluss mit
hunderten einchunkigen Einträgen befürchtete; Phase 14s Ergebnis (E1/E2 werden nicht gebaut) hat
diese Prämisse entkräftet, und [ADR 0036](docs/adr/0036-global-community-ranking-over-member-chunks-phase10.md)
setzt den Punkt jetzt um.

**Zur Anordnung dieses Dokuments:** Abgeschlossene Phasen werden nicht umsortiert, sondern beim
Abschluss in die [Historie](docs/roadmap-historie.md) überführt – die Regel, nach der die Phasen
0–8, 11, 12, 14 und 15 dort stehen (Phase 13 bleibt als einzige Ausnahme vollständig hier, siehe
oben).

---

## Phase 9 – Online-Research-Modus (separat startbar)

> **Status: S0 beantwortet, S1 und S2 umgesetzt** ([ADR 0020](docs/adr/0020-online-candidate-search-phase9.md),
> [ADR 0035](docs/adr/0035-fulltext-download-phase9-s2.md)).
> Der folgende S0-Befund (Messung vom 2026-08-03) entstand bewusst **ohne ADR** – S0 baut nichts
> und entscheidet keine Architektur. Mit der Umsetzung von S1 ist der dort formulierte Vorbehalt
> eingelöst: Die Entscheidung über Transport, Quellen und Sicherheitsgrenze steht jetzt im ADR.
> **S2 ist seit 2026-09-01 ebenfalls umgesetzt** – nicht durch eine neue Messung, sondern durch
> eine angepasste Anforderung: Statt einer belastbaren Whitelist-Abdeckung abzuwarten, gilt jetzt
> „Lizenz aus der Whitelist und bestandene Inhaltsprüfung ⇒ Download, sonst Link" als der gewollte
> Regelfall (Details unten bei S2).
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

**Ziel:** Ein **manuell gestarteter, vom Kern getrennter** Modus, der zu einem Thema oder einem Seed-Paper neue Quellen im Netz sucht und – nur auf ausdrücklichen Wunsch – frei lizenzierte Volltexte nach `new_papers/` legt, wo [Phase 8](docs/roadmap-historie.md#phase-8--korpus-zufluss-new_papers--intake) sie übernimmt.

**Abgrenzung, die nicht verhandelbar ist:** Der Kern bleibt netzfrei. Ohne Internet funktioniert alles Bisherige unverändert. Insbesondere bekommt der MCP-Server **kein** Netz-Tool im ersten Schritt – er wird von Copilot autonom aufgerufen, und niemand soll durch eine beiläufige Frage ungewollten Netzverkehr auslösen.

### S0 – Recherche & Machbarkeit (zwingend zuerst, mit Abbruchkriterium)
_Modell-Tipp: Claude Opus 5._

Dieser Schritt ist der Grund, warum die Phase überhaupt so geschnitten ist: **Es ist offen, ob das hier sinnvoll und überhaupt möglich ist.** Zu klären, bevor eine Zeile Code entsteht:

1. **Erreichbarkeit messen, nicht annehmen.** Das Repo entstand in einem Umfeld **ohne PyPI-Zugang** ([ADR 0002](docs/adr/0002-venv-and-offline-dependency-strategy.md)) – daraus folgt *nicht*, dass fachliches HTTP blockiert ist, aber es ist unbewiesen. Zu prüfen sind je ein Minimal-Request gegen die Kandidaten (arXiv-API, Crossref, OpenAlex, Semantic Scholar, Unpaywall) inklusive Proxy- und TLS-Verhalten. Dieselbe Methodik wie bei [ADR 0005](docs/adr/0005-graphrag-index-backend-open.md), wo die Beschaffbarkeit empirisch geprüft und die Architektur danach ausgerichtet wurde.
2. **Werkzeuglage (bereits gemessen):** `requests` und `httpx` sind offline vorhanden, `urllib` ohnehin; `feedparser` fehlt – die Atom-Antwort der arXiv-API müsste also über `xml.etree` aus der Standardbibliothek gelesen werden. Ein Fremd-Wheel ist für diese Phase **nicht** nötig.
3. **Quellenauswahl nach harten Kriterien:** API-Schlüssel nötig? Rate-Limit? Abdeckung für einen arXiv-/CS-lastigen Korpus? Liefert sie Abstracts? Weist sie **Lizenz** und Volltext-Link aus? Was sagen die Nutzungsbedingungen zur automatisierten Abfrage?
4. **Die unbequeme Frage: Lohnt es sich?** Der Korpus ist **kuratiert** – `Übersicht.md` bewertet Relevanz und ordnet Sub-Forschungsfragen zu. Ein Automat, der pro Lauf 50 Kandidaten ausspuckt, erzeugt Kurationsarbeit, statt sie zu sparen. Zielgröße ist deshalb **Präzision der Vorschläge, nicht deren Menge** – gemessen an einer simplen Frage: Wie viele Vorschläge eines Laufs würde man tatsächlich in die Übersicht aufnehmen?

*Abbruchkriterium:* Ist keine Quelle erreichbar, ist die Rechtslage unklar, oder liefert eine Handprobe überwiegend Irrelevantes, **entfällt die Phase** – dokumentiert, wie in A5 die verworfene Seitenbereichs-Regel und die verworfene Stopword-Variante im Vektorraum.

### S1 – Kandidaten finden (Metadaten, kein Download)
_Modell-Tipp: Claude Opus 5._

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
_Modell-Tipp: Claude Opus 5._

> **Status: umgesetzt** ([ADR 0035](docs/adr/0035-fulltext-download-phase9-s2.md)) – mit einem
> **engeren** Lizenzumfang als unten vorgesehen und einer **zusätzlichen** Inhaltsprüfung.
>
> **Abweichungen von der Vorgabe unten, jeweils begründet:**
>
> * **Keine „arXiv-Lizenzen" in der Whitelist.** Die Vorgabe nannte sie neben CC0/CC-BY/CC-BY-SA,
>   aber arXiv weist im Atom-Feed nachweislich **keine** Lizenz aus (S0, erneut live geprüft am
>   2026-09-01) – es gibt nichts, das geprüft werden könnte. Die Whitelist ist deshalb exakt
>   `public-domain` (OpenAlex' Bezeichnung für CC0), `cc-by`, `cc-by-sa`, ausschließlich aus
>   OpenAlex' `primary_location.license`.
> * **Größengrenze neu bestimmt:** `MAX_RESPONSE_BYTES` (5 MB) des bestehenden Transport-Ports
>   war für Metadaten kalibriert, nicht für Volltexte. Der Port bekommt einen optionalen
>   `max_bytes`-Parameter; der Download-Pfad ruft mit 100 MiB auf (größte Korpus-Datei zum
>   Entscheidungszeitpunkt × 2, gerundet).
>
> **Über die Vorgabe hinaus** prüft der Lauf nicht nur Content-Type/Größe, sondern auch, ob der
> heruntergeladene Inhalt **nachweislich zum Kandidaten gehört**: mindestens zwei Seiten, Titel im
> PDF gegen den berichteten Titel abgeglichen – mit demselben Titel-Match-Mechanismus, den der
> Intake für seine eigene Titel-Verdachtsstufe nutzt (`TITLE_SIMILARITY = 0.85`), nur mit
> vertauschten Rollen. Ohne diese Prüfung würde ein falsch verlinktes PDF oder eine Landing-Page
> unbemerkt in `new_papers/` landen.
>
> **Akzeptanz erfüllt:** `--download` bleibt ein optionales Flag an `scripts.discover`, nie
> Standard; ein nicht whitelisted lizenzierter oder inhaltlich nicht passender Treffer wird
> nachweislich nicht geladen (Testfälle je Ausschlussgrund); ein Netzfehler hinterlässt keine
> halbe Datei (atomares Schreiben über `.tmp` + `os.replace`); jeder Kandidat trägt im Bericht
> einen Status samt Begründung, Identifikator und Link bleiben unabhängig davon immer sichtbar.

- **Nur mit explizitem Flag** (`--download`), nie als Standard.
- **Nur bei frei lizenzierten Quellen** (Whitelist, z. B. CC0/CC-BY/CC-BY-SA und die arXiv-Lizenzen). Alles andere wird **nicht** geladen, sondern nur als Link berichtet. Eine Umgehung von Bezahlschranken ist ausgeschlossen.
- **Ziel ist ausschließlich `new_papers/`**; die Übernahme in den Korpus macht Phase 8. Es gibt genau **einen** Weg in den Korpus, nicht zwei.
- **Sicherheitsauflagen – heruntergeladene PDFs sind nicht vertrauenswürdiger Input:** Content-Type und Größe werden vor dem Schreiben geprüft; der Dateiname wird **selbst erzeugt** (aus Identifikator/Titel, nie aus der Serverantwort → kein Pfad-Traversal); ein Request pro Datei mit Rate-Limit, Timeout und identifizierendem User-Agent; kein Bulk-Crawl. Das Robustheits-Gate aus Phase 8 fängt anschließend defekte oder textlose Dateien ab.
- *Akzeptanz:* Eine geladene Datei durchläuft den Intake regulär; ein nicht frei lizenzierter Treffer wird nachweislich **nicht** geladen; ein Netzfehler hinterlässt keine halbe Datei.

### Bewusst ausgeschlossen

Vollautomatischer Dauerbetrieb, Hintergrund-Suche, automatische Übernahme ohne Sichtung, Umgehung von Zugangsbeschränkungen. Der Mensch entscheidet, was in den Korpus kommt – andernfalls verliert die kuratierte Übersicht ihren Sinn und der Korpus seine Qualität.

### Definition of Done

S0 ist beantwortet und dokumentiert (auch ein „lohnt sich nicht" ist ein gültiges Ergebnis). S1 liefert einen belegten, deduplizierten Kandidaten-Bericht; S2 ist umgesetzt und bleibt **opt-in und lizenzgebunden** – ohne `--download` ändert sich nichts.

---

## Phase 10 – Retrieval-Vertiefung (die belegten Befunde abarbeiten)

**Ziel:** Die drei Schwachstellen beheben, die [ADR 0016](docs/adr/0016-quantitative-retrieval-evaluation-phase7.md) **belegt, aber bewusst nicht behoben** hat. Diese Punkte sind die am besten begründeten im ganzen Repo: Der Messapparat existiert bereits (`--modi`, eingefrorene Baseline, qid-genauer `--check` mit Fingerprint-Guard), also ist jede Änderung **vor** dem Bauen abschätzbar und **nach** dem Bauen gegen Regression abgesichert.

### V1 – Local: mehrere Seeds statt eines
_Modell-Tipp: Claude Opus 5._

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
_Modell-Tipp: Claude Opus 5._

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
_Modell-Tipp: Claude Opus 5._

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
> (siehe [B3](docs/roadmap-historie.md#phase-11--betrieb-robustheit--datensicherheit)). Kein Schema-Eingriff, **kein Re-Ingest**, und
> **keine** Retrieval-Änderung: Die Messung bestätigt den Contract, statt ihn zu widerlegen.

*Lücke:* Das Gold-Set enthält ausschließlich **lexikalisch verankerte** Fragen. Der Fragetyp „Zitations-/Methodennetze (Multi-Hop)" aus dem README-Contract ist damit **überhaupt nicht gemessen** – obwohl mit **382 `CITES`-Kanten** und **44 Papern mit ≥ 3 zitierenden Quellen** eine objektive, **nicht-lexikalische** Labelquelle bereitsteht. A6 hat genau diesen Schritt als „naheliegendsten nächsten ohne Subjektivität" benannt und die Architektur dafür vorbereitet: `GoldQuestion` weist die **Label-Quelle** aus, damit weitere Quellen additiv danebentreten können.

*Zusatznutzen – und der eigentliche Grund für die hohe Priorität:* [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md) belegt ausdrücklich nur die **Präzision** des Zitationsgraphen (alle Kanten mechanisch im Referenztext belegt, Stichproben durchweg korrekt) und lässt den **Recall offen**. Mit Multi-Hop-Labels wird dieser blinde Fleck erstmals sichtbar. Zugleich löst der Punkt den in A6 zurückgestellten Wunsch nach „inhaltlich statt lexikalisch" abgeleiteten Labels auf – **ohne** die Nachrechenbarkeit aufzugeben, denn die Kanten sind mechanisch verifizierbar.

*Akzeptanz:* neue Label-Quelle neben der mechanischen; Fragen deterministisch aus dem Graphen erzeugt („welche Paper bauen auf *X* auf?"); `--verify-labels` prüft sie gegen `citation_edges`; gemessen werden `get_citations` und der Local-Fan-out; die Baseline wird um diese Ebene erweitert.

### V4 – Global: Community-Ranking über die Mitglieds-Chunks (erst messen, dann entscheiden)
_Modell-Tipp: Claude Opus 5._

> **Status (2026-09-01): umgesetzt** ([ADR 0036](docs/adr/0036-global-community-ranking-over-member-chunks-phase10.md))
> – die Vorgabe war korrekt, ihr Akzeptanzkriterium brauchte aber eine zusätzliche Messung.
>
> **Die vorab formulierte Frage („hebt die Aggregation Lift und Coverage bei gleicher
> Selektivität?") lässt sich nicht direkt am Produktivwert `n=5` beantworten**, weil dort mit
> jedem getesteten Kandidaten auch die Selektivität mitwächst (0,037 → 0,16–0,28) – eine
> Nachbarschaft mit vielen positiv scorenden Chunks lässt sich nicht bei gleichzeitig
> unveränderter Selektivität abfragen, wenn `n` fix bleibt. Erst das Herunterfahren von `n`, bis
> die Selektivität wieder bei 0,037 liegt, beantwortet die Frage **wörtlich**: Bei `n=1`
> (Selektivität 0,036 statt 0,037) steigen sowohl Coverage (0,173 → **0,301**) als auch Lift
> (4,67 → **8,29**) deutlich. Der niedrigere Lift bei `n=5` (3,41) ist damit kein
> Rankingrückschritt, sondern der Preis der breiteren, jetzt sinnvoll nutzbaren Auswahl.
>
> **Gewählt ist das Mittel der `MEMBER_TOP_K = 5` höchsten Hybrid-Chunk-Scores** je Community
> (`TfidfIndex.score_chunks_by_paper`, neu) – eine **Summe** wurde gemessen und verworfen, weil
> sie große Communities strukturell bevorzugt (Selektivität 0,276, Lift bricht auf 1,91 ein,
> exakt die Falle, vor der A6 für die triviale „größte Communities"-Strategie bereits gewarnt
> hatte). `MEMBER_TOP_K = 5` statt eines separat getunten Werts folgt der bestehenden
> `k`-Konvention der übrigen Modi – die Kandidaten 3/5/10 unterscheiden sich am Gold-Set um
> höchstens eine Frage.
>
> **Ergebnis am realen Korpus** (606 Paper, Gold-Set 1.5.0): Global Hit@5 **0,529 → 1,000**, MRR
> **0,435 → 0,860**; DRIFT profitiert automatisch mit (Hit **0,588 → 0,882**), weil beide Modi
> dieselbe Funktion `rank_communities` teilen. DRIFTs alter Fallback-Auslöser („Community-Pfad
> leer trotz echtem Basic-Treffer", [ADR 0022](docs/adr/0022-drift-community-union-and-fallback-phase10.md))
> tritt am realen Korpus praktisch nicht mehr auf (0 von 34 statt 12 von 34) – ein zugehöriger
> Test musste deshalb umgebaut werden, weil sein bisheriges Szenario strukturell unerreichbar
> wurde. **Eine Regression bleibt offen ausgewiesen:** DRIFT verliert Frage G15 (Rang 4 → kein
> Treffer) – dieselbe, in ADR 0022 bereits benannte Schwäche der lokalen Verfeinerung bei
> wachsender Kandidatenmenge, hier durch mehr positiv scorende Communities ausgelöst statt nur
> beobachtet. `--check` bestätigt **0 Abweichungen** auf `primitive`/`basic`/`local`.
>
> Kein Schema-Eingriff, **kein Re-Ingest**, kein Contract-Bruch (`score` bleibt ein `float`, nur
> seine Herkunft ändert sich). Beide Baselines sind neu eingefroren.

*Befund:* Global erreicht **0,353 / 0,269** bei einem Lift von **3,55** gegen ≈ **1,0** bei beiden Trivial-Baselines – die Auswahl ist also klar besser als Zufall, die Coverage bleibt mit **0,248** aber niedrig. *Verdacht:* Das Ranking vergleicht die Frage gegen einen sehr **dünnen** Text – zehn Keywords plus eine extraktive Zusammenfassung je Community. Die eigentliche Textmasse der Mitglieder bleibt ungenutzt.

*Vorschlag:* Den Community-Score aus den Chunk-Scores der Mitglieder aggregieren (die Hybrid-Wertung existiert bereits); Keywords und Zusammenfassung bleiben für die Darstellung.

*Akzeptanz – bewusst als Frage formuliert:* Hebt die Aggregation Lift **und** Coverage bei gleicher Selektivität? Falls nein, wird der Punkt **verworfen und der Befund dokumentiert** – genau so, wie in A5 die naheliegende Variante „Stopwords in den Vektorraum" nach der Messung verworfen wurde, weil sie den Graphen ohne belegbaren Nutzen verschoben hätte.

---

## Phase 13 – Referenz-Einträge ohne Volltext

> **Status: R0 beantwortet, R1 und R2 umgesetzt** (Messung vom 2026-08-09, bewusst **ohne ADR** –
> R0 baut nichts und entscheidet keine Architektur; dieselbe Handhabung wie bei [S0](#s0--recherche--machbarkeit-zwingend-zuerst-mit-abbruchkriterium)
> und [B6](docs/roadmap-historie.md#b6--grad-des-ähnlichkeitsgraphen-geprüft-verworfen)). Gemessen wurde gegen den
> Korpusstand **373 Paper / 26 003 Chunks / 118 Communities / 1481 `CITES`-Kanten**. Kein
> Produktivcode, kein Schema-Eingriff, kein Re-Ingest; die Wegwerf-Skripte sind gelöscht, die
> Rohantworten liegen unter `data/online_probe/` (nicht versioniert). Die Umsetzungen stehen in
> [ADR 0029](docs/adr/0029-reference-stub-resolution-phase13.md) und
> [ADR 0030](docs/adr/0030-reference-entries-in-corpus-phase13.md) samt den Statusblöcken bei
> [R1](#r1--auflösung--stub-erzeugung-kein-volltext-download) und
> [R2](#r2--intake--index-der-zweite-dokumenttyp); **R3 ist offen.**
>
> **Ergebnis: die Phase entfällt nicht, aber ihr Zuschnitt ändert sich an einer Stelle** – die
> Guardrail aus [R3](#r3--wirkung-sichern-contract-baselines-guardrail) ist **nicht länger
> bedingt, sondern gesetzt.**
>
> **Validitätsanker zuerst** (Pflicht seit V1): Der Nachbau der Zitationskanten aus
> `data/canonical/` liefert **1481 von 1481** Kanten identisch zum Index. Erst damit sind die
> daraus abgeleiteten Zahlen belastbar.
>
> **1. Ausbeute – die Vorgabe war zu pessimistisch, weil sie die falsche Quelle unterstellte.**
> Die Roadmap leitete ihre Skepsis aus **Crossref** ab („Abstracts nur bei rund einem Drittel").
> Gemessen wurde der Weg, den [R1](#r1--auflösung--stub-erzeugung-kein-volltext-download)
> tatsächlich nähme – **OpenAlex** (DOI direkt bzw. über den DataCite-DOI) mit dem arXiv-Feed als
> Rückfall. Von **60** abgefragten Kennungen sind 4 unbrauchbare Extraktionsartefakte (siehe
> Punkt 2); von den **56 gültigen** löste OpenAlex/arXiv **56** auf und lieferte für **52 = 93 %**
> einen Abstract. Entscheidend ist die Untergruppe, um die es der Phase geht: Bei den Werken mit
> echter Bezahlschranke (`oa_status = closed`) sind es **6 von 7**. Die vier Fehlschläge verteilen
> sich auf `closed`, `green` und **zweimal `gold`** – die Abstract-Verfügbarkeit hängt also
> **nicht** am Zugang zum Volltext. Die 50-%-Schwelle ist damit deutlich übertroffen: Die
> Online-Auflösung bleibt der **Hauptweg**, der manuelle Weg die Ausnahme. *Offen ausgewiesen:*
> **8 der 52** Abstracts sind mit unter 60 Wörtern (Minimum 28) eher Fragment als Abstract –
> überwiegend Einträge der ACL Anthology.
>
> **2. Nutzen für den Zitationsgraphen – das stärkste Argument der Phase hält, aber erst nach drei
> Korrekturen.** Roh gezählt tragen die Referenzabschnitte 3634 verschiedene DOI-/arXiv-Werte, die
> auf kein Korpus-Paper zeigen. Diese Zahl ist **zu hoch**, und zwar aus drei mechanisch
> nachweisbaren Gründen: **95** DOIs sind am Zeilenumbruch **abgeschnitten** (`10.18653/v1/` ist
> ein Präfix jedes ACL-Eintrags – solche Rümpfe passen auf viele Einträge und werden dadurch in
> der Häufigkeitsliste nach **oben** gespült, genau dort, wo man sie am wenigsten vermutet),
> **127** sind DataCite-Dubletten (`10.48550/arXiv.X` **und** `X`), und **42** treffen doch ein
> Korpus-Paper, dessen Identifikator nur den Frontmatter-Guard aus
> [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md) nicht passiert hat. Bereinigt
> bleiben **3371** tote Identifikatoren (1106 DOI / 2265 arXiv), davon **702** von mindestens
> **zwei** und **349** von mindestens **drei** Korpus-Papern zitiert. Beide vorab fixierten
> Schwellen sind damit klar übertroffen (gefordert: ≥ 50 mehrfach zitierte Werte und ≥ 10 % des
> Kantenbestands).
>
> | Aufgenommene Referenz-Einträge | Neue `CITES`-Kanten | gemessen am Bestand 1481 |
> | --- | --- | --- |
> | Top 10 | 307 | +21 % |
> | Top 25 | 505 | +34 % |
> | Top 50 | 742 | +50 % |
> | Top 100 | 1074 | +73 % |
> | alle 3371 | 5333 | +360 % |
>
> Die Kurve ist die eigentliche Aussage: Der Nutzen konzentriert sich stark – schon **zehn**
> Einträge bringen 307 Kanten, danach fällt der Ertrag je Eintrag von 30,7 auf 1,6. Die Phase
> lohnt sich also **kuratiert**, nicht als Massenimport. *Präzision der Zählung:* 40 Treffer im
> Referenzkontext von Hand geprüft – arXiv **10/10**, DOI **27/30** (die drei Fehler sind
> Abschneide- und Anklebefehler wie `10.3390/electronics14112102vol`). Dieser Defekt ist
> **selbstkorrigierend**: Ein kaputter Identifikator lässt sich online nicht auflösen und fällt in
> R1 als Befund auf, statt still eine falsche Kante zu erzeugen.
>
> **3. Verdrängung – das Abbruchkriterium ist verfehlt, und das ist das wichtigste Ergebnis der
> Messung.** Gemessen wurde an Index-Kopien (Methodik wie B6): **A** unverändert als Kontrolle,
> **B_real** mit den 52 echten Abstracts aus Punkt 1, **B_adv** mit 34 adversarialen Stubs (je
> Gold-Frage die ersten 200 Wörter des **gewinnenden** Chunks). Verglichen wurde qid-genau über
> **alle zehn Ebenen** beider Gold-Sets.
>
> | | Regressionen | Verbesserungen | wo |
> | --- | --- | --- | --- |
> | **B_real** (52 echte Abstracts) | **13** | 3 | ausschließlich Multi-Hop |
> | **B_adv** (34 adversariale Stubs) | **86** | 6 | Primitive/Basic/Local je 28, DRIFT 2 |
>
> Bemerkenswert ist die **Trennschärfe**: Bei den realistischen Stubs bleiben Primitive, Basic,
> Global und DRIFT **unverändert**, Local verbessert sich sogar leicht (0,824 → 0,853) – der
> Schaden entsteht ausschließlich bei den **Multi-Hop-Fragen** (`basic_title` 4, `local_title` 5,
> `basic_topic` 1, `local_topic` 3), zweimal davon als vollständiger Verlust aus den Top 5
> (C50, C35). Das ist plausibel und nicht zufällig: Eine Multi-Hop-Frage nennt einen **Titel**,
> und ein Stub besteht praktisch nur aus Titel und Abstract – die BM25-Längennormalisierung tut
> dann genau das, was die Roadmap befürchtet hat. Die adversariale Variante beziffert die
> Obergrenze des Effekts: Hit@5 fällt nur 0,824 → 0,794, der **MRR@5 aber halbiert sich**
> 0,730 → 0,366, weil fast jeder Rang 1 auf Rang 2 rutscht. Damit ist auch belegt, dass ein
> bestandenes Veto nicht trivial gewesen wäre.
>
> **Warum das A/B-Verfahren nötig war (und das wörtliche `--check` untauglich):** Beide Baselines
> sind auf **341** Paper eingefroren, der Korpus steht bei **373**. Die Kontrollkopie A gegen die
> eingefrorenen Stände gehalten (Fingerprint-Guard bewusst umgangen) ergibt **12 + 15 = 27**
> Regressionen allein aus dem Korpuswachstum – **doppelt so viele wie der Stub-Effekt**. Ein
> `--check` der Stub-Kopie gegen die alte Baseline hätte die 13 aussagekräftigen Abweichungen in
> 27 nichtssagenden ertränkt. *Folgepunkt für [B5](docs/roadmap-historie.md#b5--messgrundlage-nachführbar-halten)/R3:* Der
> quantitative Regressionsschutz ist derzeit außer Betrieb; das Neu-Einfrieren gehört an den
> Anfang von R3, nicht in diese Messung.
>
> **4. Handprobe – der Nutzen ist belegt: 10 von 10.** Zehn Fragen, deren Antwort ausschließlich
> im Abstract eines Stubs steht (Datensätze von `k-isomorphism`, die *heavy-edge*-Heuristik von
> METIS, 67,6 % von Flan-PaLM auf MedQA, die NP-Vollständigkeit beliebiger Waypoints …) werden
> **alle auf Rang 1** gefunden; ohne den Stub liefert der Korpus in acht von zehn Fällen etwas
> thematisch Fremdes, in zwei Fällen ein benachbartes Paper, aber nie die gefragte Tatsache.
> **Der unbequeme Teil davon:** Nutzen und Schaden haben **dieselbe** Ursache – der Stub gewinnt,
> weil er kurz ist. Eine Guardrail, die Referenz-Einträge grundsätzlich ausschließt, würde den
> Nutzen mit vernichten; richtig ist die **Nachrangigkeit gegenüber Volltext-Treffern**, denn in
> genau diesen zehn Fragen gibt es keinen konkurrierenden Volltext-Treffer.
>
> **Konsequenzen für R1–R3:** R1 bleibt wie geplant (Online-Auflösung als Hauptweg, manueller Weg
> als Ausnahme). R2 bleibt unverändert. In R3 wird die Guardrail **gebaut**, nicht erwogen – die
> Bedingung „nur, falls R0 sie erzwingt" ist eingetreten. Vor dem qid-genauen Nachweis in R3 sind
> **beide Baselines neu einzufrieren**.

**Ziel:** Ein Paper, von dem nur der Abstract öffentlich zugänglich ist, wird über seine **DOI oder arXiv-ID** zu einem vollwertigen, aber **ausdrücklich unvollständigen** Korpus-Eintrag – auffindbar, zitierfähig und als Ziel von Zitationskanten verfügbar, ohne je den Eindruck zu erwecken, es liege ein Volltext vor.

### Warum das nötig ist (und was heute fehlt)

Zwei Lücken; die zweite wiegt schwerer als die naheliegende erste.

1. **Der Fund verfällt.** Ein hinter einer Bezahlschranke gelesener Abstract ist heute nur über [`Übersicht.md`](Übersicht.md) zu sichern – und die ist eine kuratierte **Tabelle**, kein Index. Der Inhalt ist damit weder über `search_basic` auffindbar noch als Beleg zitierbar noch Teil irgendeines Graphen.
2. **Referenzen zeigen ins Leere.** Der Intra-Korpus-Zitationsgraph bildet ausschließlich Kanten, deren **Ziel bereits im Korpus liegt** ([ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)). Jede Referenz auf ein nicht beschaffbares Paper verpufft folgenlos – auch dann, wenn ein Dutzend Korpus-Paper dieselbe Arbeit zitieren. Referenz-Einträge verwandeln genau diese toten Verweise in echte `CITES`-Ziele. Das ist der strukturelle Gewinn der Phase, und anders als die Auffindbarkeit ist er **vorab bezifferbar** (siehe [R0](#r0--ausbeute-nutzen-und-verdrängung-messen-zwingend-zuerst-mit-abbruchkriterium)).

Mechanisch fehlt heute alles Nötige: Der Intake liest ausschließlich `*.pdf` und verlangt die `%PDF-`-Signatur, `pipeline.ingest` iteriert `papers/*.pdf`, die `paper_id` ist der sha256 der **Datei**, jeder `Citation` trägt eine Seitenangabe als Pflichtfeld, und `quality.assess` kennt nur Dokumente mit Volltext.

### Vier Festlegungen, die vorab getroffen sind

| Festlegung | Begründung |
| --- | --- |
| **Keine synthetische PDF** | Strukturierte Daten in ein PDF schreiben, um sie anschließend per Heuristik wieder herauszuparsen, ist ein Verlustkanal ohne Gegenwert – und `reportlab` ist heute reine Test-Abhängigkeit. Erzeugt wird eine **native Stub-Datei** (`.refjson`), die ein zweiter Extraktions-Adapter direkt in ein `CanonicalPaper` überführt. Eigene Endung, damit `papers/*.pdf`-Globs unberührt bleiben und die Datei nie mit `data/canonical/*.json` verwechselt wird. |
| **„Unvollständig" ist kein Qualitäts-Flag** | Flags sind Befunde über *misslungene* Extraktion. Hier ist es eine **Eigenschaft des Dokuments** – also ein Feld `document_kind` (`full` / `reference`) im Canonical- und im Index-Schema. Nur so können Retrieval, Evaluation und Antwortsynthese darauf reagieren, statt es bloß anzuzeigen. |
| **Genau ein Weg in den Korpus** | Das Skript schreibt nach `new_papers/`, nie nach `papers/`. Die Übernahme macht der Intake aus [Phase 8](docs/roadmap-historie.md#phase-8--korpus-zufluss-new_papers--intake) – mitsamt Duplikatprüfung. Ein zweiter Einlassweg wäre eine Fehlerquelle, wie schon in [S2](#s2--volltext-holen-opt-in-lizenz-whitelist) festgehalten. |
| **Kein MCP-Werkzeug** | Der Lauf benötigt Netz **und** schreibt Dateien. Copilot ruft Werkzeuge autonom auf; beides gehört daher nicht in Agent-Reichweite (gleiche Begründung wie beim Intake, [ADR 0019](docs/adr/0019-corpus-intake-new-papers-phase8.md), und bei `scripts.resolve_metadata`, [ADR 0026](docs/adr/0026-online-metadata-resolution.md)). |

### R0 – Ausbeute, Nutzen und Verdrängung messen (zwingend zuerst, mit Abbruchkriterium)
_Modell-Tipp: Claude Opus 5._

> **Beantwortet am 2026-08-09** – die Zahlen und die korrigierten Annahmen stehen im Statusblock
> am [Anfang dieser Phase](#phase-13--referenz-einträge-ohne-volltext). Kurzfassung: Ausbeute
> **93 %** (Schwelle 50 %), Nutzen **702** mehrfach zitierte tote Verweise und bis zu **5333**
> mögliche neue Kanten (Schwelle deutlich übertroffen), Verdrängung **13 qid-Regressionen**
> (Abbruchkriterium 0 → **verfehlt**, die Guardrail aus R3 ist damit gesetzt), Handprobe
> **10/10**.

Wie in S0, V1–V3 und B6 beginnt die Phase mit einer Wegwerf-Messung, nicht mit Code. Drei Fragen, jede mit **vorab fixierter** Schwelle:

1. **Liefern die Quellen überhaupt einen Abstract?** Gemessen an **mindestens 20 echten DOIs/arXiv-IDs** aus der eigenen Recherche. Die S0-Erhebung legt Skepsis nahe: Crossref führt Abstracts nur bei rund einem Drittel der Einträge, und gerade Closed-Access-Verlage liefern sie oft nicht. *Konsequenz statt Abbruch:* Liegt die Ausbeute unter **50 %**, wird der manuelle Weg (Abstract selbst einfügen) zum **Hauptweg** und die Online-Auflösung zur Bequemlichkeit – der Zuschnitt von R1 ändert sich damit, die Phase kippt nicht.
2. **Wie groß ist der Gewinn für den Zitationsgraphen?** Read-only aus dem bestehenden Index: Wie viele Referenz-Einträge des Korpus tragen einen DOI-/arXiv-artigen Wert, der auf **kein** Korpus-Paper zeigt, und wie oft wiederholt sich derselbe Wert über mehrere Paper hinweg? Das beziffert erstmals, wie viele tote Verweise durch Referenz-Einträge zu Kanten werden könnten. *Abbruchkriterium:* Sind es praktisch keine, verliert die Phase ihr stärkstes Argument und wird auf reine Auffindbarkeit zurückgestutzt – mit entsprechend kleinerem Umfang.
3. **Verdrängen kurze Stubs echte Evidenz?** BM25 normalisiert auf die Dokumentlänge; ein 200-Wort-Abstract bekommt bei Term-Treffern **strukturell Auftrieb** gegenüber einem 20 000-Wort-Paper. Gemessen wird an einer **Index-Kopie** (der Live-Index bleibt unberührt, Methodik wie in B6): simulierte Stubs einspielen, dann `--check` gegen **beide** eingefrorenen Baselines. *Abbruchkriterium:* **0 qid-Regressionen**. Tritt eine auf, wird sie nicht wegdiskutiert, sondern zieht die Guardrail aus [R3](#r3--wirkung-sichern-contract-baselines-guardrail) nach sich.

**Die Grenze dieser Messung wird offen ausgewiesen, nicht kaschiert.** Die Gold-Labels stammen mechanisch aus `chunks.text`; ein Stub ist damit **nie** ein Gold-Ziel und kann in der Messung ausschließlich schaden. Punkt 3 taugt deshalb – wie das End-to-End-Maß in [A7](docs/adr/0017-router-hardening-phase7.md) – nur als **Veto**, niemals als Nutzennachweis. Der eigentliche Nutzen ist mit den bestehenden Gold-Sets prinzipiell nicht messbar. Daneben tritt daher eine **Handprobe**: rund zehn Fragen, deren Antwort ausschließlich im Abstract eines Stubs steht – findet das Retrieval sie, ist der Nutzen belegt; findet es sie nicht, ist die Phase auch bei bestandenem Veto wertlos.

### R1 – Auflösung & Stub-Erzeugung (kein Volltext-Download)
_Modell-Tipp: Claude Opus 5._

> **Status: umgesetzt** (2026-08-09, [ADR 0029](docs/adr/0029-reference-stub-resolution-phase13.md)).
> Neu sind `src/research_graphrag/online/references.py`, das dünne `scripts/resolve_references.py`
> und das append-only Protokoll `data/references_log.md`. **Kein** Schema-Eingriff, **kein**
> Re-Ingest, **kein** MCP-Werkzeug (der Server bleibt bei neun), kein Contract berührt.
>
> **Zwei Vorgaben wurden präzisiert, beide aus R0 begründet:**
>
> **1. Ein Titel ist Pflicht, ein Abstract nicht.** Die Vorgabe regelt den Fall „kein Abstract"
> (Datei entsteht trotzdem, Abstract wird von Hand nachgetragen) – **nicht** den Fall „Kennung
> gar nicht auflösbar". Ohne Titel entsteht deshalb **keine** Datei, nur ein Befund: Ein solcher
> Eintrag wäre weder zitierfähig noch als Ziel einer Titel-Kante brauchbar (er unterschreitet
> `MIN_TITLE_CHARS`/`MIN_TITLE_WORDS`) und ergäbe in R2 ein sinnloses Korpus-Paper. R0 hat
> gezeigt, dass der Fall real ist: **4 von 60** geprüften Kennungen waren abgeschnittene
> Extraktionsartefakte.
>
> **2. Der Dateiname trägt ein sprechendes Wort.** Die Vorgabe verlangt einen Namen „deterministisch
> aus dem Identifikator, nie aus einer Serverantwort". Die Sicherheitsauflage dahinter – kein
> Pfad-Traversal – bleibt vollständig gewahrt: Der Name wird **erzeugt**, nicht übernommen, und
> zwar über eine **Whitelist** (`a`–`z`, `0`–`9`) mit Längengrenze. Die Kennung bleibt der
> eindeutige Anker (`ref-graphrag-arxiv-2404.16130.refjson`). Die eigentliche Funktion der
> Vorgabe – Idempotenz – wird **strenger** erfüllt als gefordert: **inhaltsbasiert** statt über
> den Namen, sodass auch eine von Hand umbenannte Stub-Datei wiedererkannt wird.
>
> **Über die Vorgabe hinaus** geht der Auflösungsweg an einer Stelle: Der arXiv-Feed ist nicht nur
> Rückfall, wenn OpenAlex nichts kennt, sondern auch **Abstract- und Autoren-Quelle**, wenn
> OpenAlex zwar Metadaten, aber keinen Abstract liefert. Genau diese Kombination hat R0 gemessen –
> ohne sie wäre die dort belegte Ausbeute von 93 % nicht reproduzierbar.
>
> **Ein echter Defekt kam erst im realen Lauf ans Licht** – ein Beleg dafür, dass der
> Offline-Nachweis allein nicht genügt hätte: Der arXiv-Feed wurde bislang über
> `search_query=all:"…"` abgefragt, also über den **Volltextindex**. Nach einer Kennung gesucht
> liefert das zuverlässig ein *fremdes* Paper (`1706.03762` → `2002.05202`); der Rückfall war
> damit praktisch wirkungslos. Neu sind deshalb `sources.arxiv_id_url` und
> `sources.fetch_arxiv_by_id` (`id_list`). **Derselbe Defekt steckt in `metadata._by_arxiv_feed`**
> (Phase 12 / K2) – dort ohne Schaden, weil die Identitätsprüfung den Fehltreffer verwirft, aber
> ebenso wirkungslos. Er wird hier **bewusst nicht mitkorrigiert** (Verhalten außerhalb dieses
> Schnitts); der Befund ist im ADR notiert.
>
> **Realer Nachweis** (373-Paper-Korpus, über den Unternehmens-Proxy): 3 Kennungen abgefragt,
> **2 Stub-Dateien mit vollständigem Abstract** (`ref-attention-is-all-arxiv-1706.03762.refjson`
> mit 8 Autoren aus dem Feed, `ref-identity-anonymization-graphs-doi-10.1145_1376616.1376629.refjson`
> von OpenAlex); die absichtlich abgeschnittene DOI `10.18653/v1/` wird als **Befund** gemeldet
> statt still eine falsche Kante zu stiften – der in R0 vorhergesagte selbstkorrigierende Effekt.
> Der zweite Lauf übersprang die bereits erzeugte Datei ohne Abfrage.
>
> **Akzeptanz erfüllt** (offline nachgewiesen, 67 neue Tests, Gesamtstand **852**): Ein Lauf
> erzeugt für jede auflösbare Kennung genau eine Stub-Datei; ein zweiter Lauf erzeugt **keine**
> und stellt **keine** Abfrage (geprüft über einen zählenden Client und real bestätigt); ohne
> Netz endet der Lauf mit `dependency_error` statt in einem Stacktrace; die Liste ist danach
> **byte-identisch**. `--dry-run` erzeugt nicht einmal einen Client. Vorgezogen aus R3 ist die
> Sicherung: `new_papers/referenzen.txt` und `data/references_log.md` stehen im Umfang aus
> [B1](docs/roadmap-historie.md#b1--sicherung-des-korpus) (Nachtrag in [ADR 0027](docs/adr/0027-corpus-backup-phase11.md)).
>
> **Ehrlich dazu:** Bis R2 sind die erzeugten `.refjson`-Dateien **wirkungslos** – der Intake
> liest weiterhin nur `*.pdf`. Das ist der Preis des inkrementellen Schnitts und in der Anleitung
> ausdrücklich vermerkt. Ebenfalls ausgewiesen: Die Korpus-Prüfung nutzt den **gehärteten**
> Schlüsselsatz, ein Paper mit nicht frontmatter-belegtem Identifikator würde also erneut als
> Stub vorgeschlagen – dieselbe bewusst getragene Grenze wie in
> [ADR 0020](docs/adr/0020-online-candidate-search-phase9.md); die Absicherung ist der Intake.

- **Eingabe** ist `new_papers/referenzen.txt`: **eine Kennung je Zeile**, zulässig sind **DOI und arXiv-ID**; `#` leitet einen Kommentar ein, Leerzeilen werden ignoriert. Beide Abfragewege existieren bereits in `online/metadata.py` (DOI direkt, arXiv über den DataCite-DOI) – neu ist im Wesentlichen, dass `abstract_inverted_index` mit angefordert und über das vorhandene `sources._restore_abstract` zurückgebaut wird.
- **Logik im Paket, Skript dünn** (Repo-Konvention): ein Modul unter `src/research_graphrag/online/`, dazu `scripts/resolve_references.py`. Der Netzzugang läuft **ausschließlich** über den injizierbaren Port aus [ADR 0020](docs/adr/0020-online-candidate-search-phase9.md); alles Übrige bleibt offline testbar. Fremde Titel und Abstracts sind **nicht vertrauenswürdige Eingaben** und werden wie in S1 entschärft, bevor sie in eine Datei gelangen.
- **Ausgabe** ist je Kennung **eine** Stub-Datei in `new_papers/`. Der Dateiname wird **selbst erzeugt** – deterministisch aus dem Identifikator, nie aus einer Serverantwort (kein Pfad-Traversal, gleiche Auflage wie in S2).
- **Der manuelle Weg führt über die erzeugte Datei, nicht über eine zweite Eingabeform.** Liefert keine Quelle einen Abstract, entsteht die Stub-Datei trotzdem – mit leerem Abstract-Feld und einem Befund im Bericht. Der Abstract wird dann von Hand hineinkopiert, bevor der Intake läuft. Das ist bewusst **eine** Stelle statt zweier konkurrierender Eingabeformate; die Konsequenz (Bearbeiten ändert den Hash und damit die künftige `paper_id`) ist vor dem Intake folgenlos und danach ein regulärer „Datei geändert"-Fall der Pipeline.
- **Idempotenz gegen drei Zustände.** Phase 12 / K2 hat gezeigt, wie leicht das schiefgeht: Dort las die Zielauswahl den **Index**, während der Lauf eine **Datei** schrieb – ein zweiter Lauf vor dem nächsten `ingest` fragte dieselben Paper erneut ab. Hier muss vor jeder Abfrage gegen **drei** Zustände geprüft werden: den Korpus-Index, die bereits erzeugten Stub-Dateien im Eingang und die Quarantäne `new_papers/_duplikate/`. Die Liste selbst bleibt dabei **unverändert** – sie ist ein kuratiertes Dokument, kein Arbeitsvorrat, den ein Skript abräumt.
- **Determinismus.** Die Stub-Datei **ist** die eingefrorene Antwort: Das Netz wird genau einmal befragt, die spätere Extraktion daraus ist deterministisch. Der enthaltene Abrufzeitpunkt dient der Provenienz und hat die ausgewiesene Folge, dass ein erneuter Abruf eine andere Datei mit anderem Hash ergibt – abgefangen von der Idempotenzprüfung und, als Rückfall, von Stufe 2 des Intake.
- **`--dry-run`** zeigt die geplanten Abfragen und Dateien, ohne Netz zu berühren und ohne Kontingent zu verbrauchen (Muster von `scripts.discover`).
- *Akzeptanz:* Ein Lauf über eine reale Liste erzeugt für jede auflösbare Kennung genau eine Stub-Datei; ein zweiter Lauf erzeugt **keine** und stellt **keine** Abfrage; ohne Netz endet der Lauf mit `dependency_error` und handlungsleitender Meldung statt in einem Stacktrace; die Liste ist danach byte-identisch.

### R2 – Intake & Index: der zweite Dokumenttyp
_Modell-Tipp: Claude Opus 5._

> **Status: umgesetzt** (2026-08-09, [ADR 0030](docs/adr/0030-reference-entries-in-corpus-phase13.md)).
> Neu sind `src/research_graphrag/extraction/refstub.py`, `pipeline.forget_source`,
> `overview.drafts.retarget_overview_row` und der zweite Zweig im Intake. **Schema-Anhebung**
> Canonical **0.4.0 → 0.5.0** und Index **0.4.0 → 0.5.0**; ein voller Re-Extract war damit
> erzwungen und ist byte-genau nachgewiesen. Kein Contract berührt, **kein** MCP-Werkzeug (der
> Server bleibt bei neun).
>
> **Zwei Vorgaben wurden präzisiert, beide aus dem Bestand begründet:**
>
> **1. Der Dateiname bleibt die einzige Titelquelle.** Die Vorgabe sagt „Titel und Identifikatoren
> eines Stubs kommen aus der Datei selbst" – im Repo entsteht der Titel aber überall aus dem
> **Dateinamen** (`title_from_uri`), und daran hängen Titel-Match, Intake-Stufe 3,
> `metadata_index` und die Übersichtszeile. Gelöst ist das nicht durch ein zweites Titelfeld,
> sondern durch **Umbenennen beim Übernehmen**: Der Stub heißt danach `<Titel>.refjson`. Ein
> `title`-Feld im Canonical wäre im Datenmodell sauberer, schüfe aber zwei Titelquellen – genau
> die Dualität, die dieses Repo vermeidet.
>
> **2. „Die Seitenangabe entfällt" ist ohne Contract-Bruch lösbar.** Die Vorgabe legt
> `page_label` in R2, den Contract-Bruch aber in R3 – `page_label` kennt `document_kind` also
> gar nicht. Der Referenz-Chunk trägt deshalb `page_number = 0`: Die fehlende Seite steht damit
> im **Datenmodell** statt im Contract, und R3 bleibt unangetastet.
>
> **Zwei Befunde, die erst die Umsetzung sichtbar gemacht hat – beide behoben:**
>
> **(a) Der Frontmatter-Guard hätte den Hauptnutzen der Phase vernichtet.** Er verlangt, dass ein
> Identifikator im **Titelseiten-Text** vorkommt (Präzisions-Härtung aus
> [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md)). Bei einem Stub steht die DOI
> aber im **Feld**, nicht im Text – der Eintrag wäre damit weder als Duplikat erkennbar noch als
> **Ziel** von `CITES`-Kanten erreichbar, also genau der in R0 bezifferte Gewinn (bis zu 5333
> Kanten) verfehlt. `front_matter_text` nimmt für Referenz-Einträge jetzt die eigenen
> Identifikatoren hinzu; die Kopie dieses Guards im Intake ist zugleich entfallen (eine Wahrheit
> statt zweier).
>
> **(b) Der Upgrade ließ eine Waise zurück.** Nach „Volltext schlägt Referenz-Eintrag" blieben
> Manifest-Eintrag und Canonical des Stubs liegen – das Paper erschien nach dem Re-Index
> **doppelt**. Neu ist `pipeline.forget_source`; ein Regressionstest hält den Fall fest.
>
> **Die Übersichtszeile wird umgebogen, nicht dupliziert.** Die Vorgabe sagt nur „nicht
> dupliziert" – dann zeigte die vorhandene `Z`-Zeile aber auf eine gelöschte Datei. Geändert
> werden ausschließlich `Name` und `Interner Link`; die wertenden Spalten und **alle anderen
> Zeilen** bleiben byte-identisch. Das ist die einzige Ausnahme von der append-only-Regel aus
> [ADR 0019](docs/adr/0019-corpus-intake-new-papers-phase8.md), und sie trifft nur eine Zeile,
> die das Werkzeug selbst erzeugt hat.
>
> **Akzeptanz erfüllt** (47 neue Tests, Gesamtstand **899**): Eine Stub-Datei durchläuft
> `scripts.intake` regulär und landet in Index und Übersicht; `--dry-run` verändert nachweislich
> nichts (Hash-Abbild des Baums identisch); ein Stub zu einem vorhandenen Paper wird als Duplikat
> erkannt; ein Volltext-PDF zu einem vorhandenen Stub wird **übernommen** statt quarantäniert –
> mit eigener Protokollzeile samt Hash; die Qualitäts-Flags der Volltext-Paper bleiben
> **unverändert**.
>
> **Betriebsregel bis R3, ausdrücklich:** Ein Referenz-Eintrag ist jetzt auffindbar, aber in den
> Ausgaben **noch nicht** als unvollständig ausgewiesen – genau den Zustand beendet R3. Bis dahin
> gehören keine Stubs in den Produktivkorpus; der Nachweis dieser Phase lief deshalb auf
> Miniatur-Korpora, der Produktivkorpus bekam nur den erzwungenen Re-Extract.

- **Der Intake wird dokumententyp-fähig.** Er nimmt neben `*.pdf` auch `*.refjson` an; die `%PDF-`-Signaturprüfung und das Lesen der Titelseite über `pypdf` gelten nur noch für den PDF-Zweig. Titel und Identifikatoren eines Stubs kommen aus der Datei selbst – damit ist die Eingangsseite **genauer** als bei einem PDF, nicht ungenauer.
- **Alle drei Prüfstufen gelten unverändert weiter.** sha256, gehärteter Identifikator-Vergleich und Titel-Ähnlichkeit sind dateiformatunabhängig; eine zweite Dedup-Logik entsteht nicht.
- **`document_kind` wird im Canonical- und im Index-Schema geführt** (Schema-Anhebung, damit ein Re-Extract erzwungen wird). Ein Referenz-Eintrag hat genau einen Chunk – den Abstract – und keine Referenz-Sektion.
- **Qualitäts-Gates werden typabhängig.** `missing_abstract`, `missing_references` und `no_chunks` sind für einen Referenz-Eintrag entweder sinnlos oder falsch; ungeprüft würde jeder Stub zwei bis drei Flags auslösen und den Report verrauschen, der in A3/A5 mühsam von 3074 auf 316 gedrückt wurde. Neu ist stattdessen genau ein sinnvoller Befund: **ein Referenz-Eintrag ohne Abstract**.
- **Die Seitenangabe entfällt.** Ein Abstract-Stub hat keine Seite 7; „Seite 1" wäre eine **falsche Aussage über die Herkunft**. `page_label` liefert für Referenz-Einträge eine eigene Kennzeichnung, und die Provenienz nennt den Abstract als das, was er ist.
- **Upgrade-Pfad Stub → Volltext.** Der Fall, dass das echte PDF später doch auftaucht, ist der gefährlichste der ganzen Phase: Ohne Regel greift Stufe 2 des Intake, erkennt die gleiche DOI und schiebt das **echte Paper** in die Quarantäne – genau verkehrt herum. Deshalb gilt ausdrücklich **„Volltext schlägt Referenz-Eintrag"**: Das PDF wird übernommen, der Stub tritt zurück. Das ist auch die einzige Löschung im Repo, die **konstruktionsbedingt** unbedenklich ist – ein Stub lässt sich aus `referenzen.txt` jederzeit neu erzeugen, ein PDF nie. Die Übersichtszeile wird dabei nicht dupliziert, und der Vorgang steht im Protokoll `data/intake_log.md`.
- **Übersicht.** Referenz-Einträge bekommen wie jedes neue Paper eine Entwurfszeile mit `Z`-ID, sichtbar als Referenz-Eintrag gekennzeichnet; die wertenden Spalten bleiben `(manuell)`.
- *Akzeptanz:* Eine Stub-Datei durchläuft `scripts.intake` regulär; `--dry-run` verändert nichts; ein Stub zu einem bereits vorhandenen Paper wird als Duplikat erkannt; ein Volltext-PDF zu einem vorhandenen Stub wird **übernommen** statt quarantäniert; die Qualitäts-Flags der Volltext-Paper bleiben gegenüber heute **unverändert**.

### R3 – Wirkung sichern: Contract, Baselines, Guardrail
_Modell-Tipp: Claude Opus 5._

> **Status (2026-08-09): umgesetzt.** `document_kind` ist Pflichtbestandteil jeder Ausgabe, der
> Zitier-Contract nennt die Unvollständigkeit, die Gold-Ableitung schließt Referenz-Einträge aus,
> beide Baselines sind neu eingefroren, und die Guardrail steht – **gemessen, nicht vermutet**
> ([ADR 0031](docs/adr/0031-reference-contract-and-guardrail-phase13.md)).
>
> **Die Messung kam zuerst, und sie hat sich selbst geprüft.** Der R0-Aufbau wurde vollständig
> reproduziert (52 echte Abstracts, dieselben zehn Ebenen, dasselbe Gold). Der eingebaute
> Selbsttest: **Kontrolle A gegen R0 = 0 abweichende qid-Ränge, B_real gegen R0 = 0 abweichende
> qid-Ränge.** Damit ist belegt, dass weder die Rekonstruktion der Stubs noch der
> Schema-Wechsel `0.4.0 → 0.5.0` noch die Beschleunigung der Messung einen einzigen Rang bewegt
> hat – erst danach waren die Varianten vergleichbar.
>
> **Die Entscheidungsregel stand vor der Messung fest** („die meisten der 13 Regressionen
> beheben, ohne einen Handproben-Treffer aus den Top 5 zu verlieren; bei Gleichstand die
> einfachere"), und sie hat die naheliegende Lösung **verworfen**:
>
> | Variante | Regressionen (davon Totalverlust) | Handprobe |
> | --- | --- | --- |
> | ohne Guardrail (= R0) | 13 (2) | 10/10 |
> | **Umsortieren (gewählt)** | **3 (0)** | **10/10** |
> | Auswahl: Volltext zuerst befüllen | 0 (0) | **0/10** |
> | Kontingent ⌈k/5⌉ | 39 (5) | 10/10 |
>
> Die harte Nachrangigkeit hätte die Messwerte gerettet, indem sie den gemessenen Gegenstand
> entfernt: **keine einzige** der zehn Handproben-Fragen findet ihren Referenz-Eintrag noch. Das
> Kontingent wiederum reserviert einen Platz, statt nur zu begrenzen, und verdrängt dadurch
> Volltext-Treffer – es misst schlechter als **gar keine** Guardrail. Gewählt ist deshalb die
> schmalste Regel: `demote_references` sortiert Referenz-Einträge stabil hinter die
> Volltext-Treffer und lässt die **Auswahl** unangetastet. Sie hat **keinen Parameter** und wirkt
> in einem stubfreien Korpus als Identität – deshalb bewegt sie die Baselines nicht.
>
> **Beide Totalverluste sind behoben** (`C50` 1 → None wird 1 → 3, `C35` 1 → None wird 1 → 2);
> die drei verbleibenden Befunde sind Rangverschiebungen um ein bis zwei Plätze. **Ehrlich
> dazu:** In der Handprobe rutschen alle zehn Treffer von Rang 1 auf Rang 5 (MRR 1,000 → 0,200).
> Rang 1 hatten sie nur, weil vier thematisch unpassende Volltext-Chunks schwächer bewertet
> wurden – gefunden werden sie weiterhin vollständig.
>
> **Der Contract-Bruch geht über die Vorgabe hinaus.** Neben `Citation` (12 → 13 Schlüssel),
> `PaperRef` (5 → 6) und `EvidenceItem` (7 → 8) trägt auch `PaperDetail` (8 → 9) das Feld: Dort
> sähen `n_pages = 0` und `n_chunks = 1` sonst nach **defekter Extraktion** aus statt nach einem
> bewusst unvollständigen Eintrag. `get_reference` bleibt dagegen bei `0.1.0` – die
> Literaturangabe ist von der Verfügbarkeit des Volltextes unabhängig, und genau das ist ihre
> Aussage. Sieben Spezifikationen steigen (`search_local`/`search_drift` auf `0.3.0`, die übrigen
> auf `0.2.0`).
>
> **Der Beleg wird zweifach kenntlich:** als Feld `document_kind` für maschinelle Auswerter und
> als Klartext „Referenz-Eintrag ohne Volltext" im Provenienz-Label – die wirksame Stelle, denn
> nur das Label steht im Prompt-Kontext. Der `citation_contract` verlangt zusätzlich, die
> Einschränkung im Antworttext zu **benennen**, ohne den Marker wörtlich zu zitieren (sonst
> stünde derselbe Text an zwei Orten).
>
> **Beide Gold-Sets und Baselines sind neu abgeleitet und eingefroren.** Retrieval-Gold `1.4.0`
> (34 Fragen, 11 mit geänderten Zielen), Multi-Hop-Gold **121 Anker** (vorher 113) – der
> quantitative Regressionsschutz ist damit nach dem Korpuswachstum 341 → 373 wieder in Betrieb.
> Beide `--check`-Läufe melden **„Keine Abweichung – alle Ränge unverändert"** (Exit 0).
>
> | Ebene | Hit@5 / MRR@5 | | Multi-Hop-Ebene | Hit@5 / MRR@5 |
> | --- | --- | --- | --- | --- |
> | `primitive` | 0.824 / 0.745 | | `graph` | 0.612 / 0.480 |
> | `basic` | 0.824 / 0.745 | | `basic_title` | 0.661 / 0.625 |
> | `local` | 0.824 / 0.745 | | `local_title` | 0.876 / 0.782 |
> | `global` | 0.529 / 0.412 | | `basic_topic` | 0.140 / 0.136 |
> | `drift` | 0.559 / 0.458 | | `local_topic` | 0.653 / 0.504 |
>
> **Die Realprobe zeigt Contract und Guardrail in einem Bild.** Auf einer Index-Kopie mit den 52
> echten Abstracts liefert die Handproben-Frage nach `k-isomorphism` den Referenz-Eintrag auf
> **Rang 5** – obwohl er mit `0.0328` den **höchsten** Score der Liste trägt. Er wird also
> zurückgesetzt, aber nicht entfernt, und trägt in jeder Ausgabe seine Kennzeichnung:
>
> ```text
> 5. Paper 5dd6ce89fed00513 · ohne Seite (Abstract) · Abschnitt Abstract · Score 0.0328
>    · Referenz-Eintrag ohne Volltext
> ```
>
> Über den In-Memory-MCP-Client gegengeprüft: `search_basic` weist `document_kind` je Zitat aus,
> `get_paper` meldet `reference` bei `n_pages = 0`, `get_citations` ebenso, und in
> `answer_question` trägt der Beleg den Marker im Label, während der `citation_contract` die
> Benennung im Antworttext verlangt.
>
> **Akzeptanz erfüllt** (13 neue Tests, Gesamtstand **912**): Jede Ausgabe weist einen
> Referenz-Eintrag aus, `--check` meldet nach dem Neu-Einfrieren 0 Abweichungen, und die
> Handprobe aus R0 findet die Abstracts.
>
> **Betriebsregel, weiterhin bewusst:** Der Produktivkorpus bleibt vorerst **stubfrei**. Die
> neuen Baselines beschreiben damit einen sauberen Referenzzustand; die Aufnahme echter
> Referenz-Einträge ist eine eigene Entscheidung, deren Wirkung der nächste `--check` sauber
> anzeigt.

- **Der Contract wird bewusst gebrochen.** `document_kind` wird als **Pflichtfeld** bis in `Citation`, `PaperRef` und `EvidenceItem` durchgereicht, die betroffenen Tool-Specs steigen in der Version. Die Begründung ist dieselbe wie bei `LocalSearchResult.seeds` und `DriftSearchResult.communities` in [V1](#v1--local-mehrere-seeds-statt-eines)/[V2](#v2--drift-community-auswahl-statt-top-1-mit-rückfallebene): Ein stiller Zustand wäre eine **falsche Provenienz-Behauptung**. Ein optionales Feld würde jede konsumierende Stelle zwingen, die Abwesenheit richtig zu deuten – und irgendwann zitiert `answer_question` einen Abstract, als stamme er aus dem Volltext.
- **Der Zitier-Contract nennt die Unvollständigkeit.** Ein Beleg aus einem Referenz-Eintrag ist im Antworttext als solcher erkennbar; die Literaturangabe selbst bleibt vollständig (Harvard/APA, [ADR 0025](docs/adr/0025-citable-paper-metadata.md)) – zitiert wird schließlich das Paper, nicht der Abstract.
- **Referenz-Einträge werden von der Label-Ableitung ausgeschlossen.** `--write-gold` leitet die mechanischen Labels aus dem Chunk-Text ab; ein Stub würde sonst **still zum Gold-Ziel** und die Messung damit selbstbezüglich. Der Ausschluss ist Voraussetzung dafür, dass die Kennzahlen vor und nach dieser Phase überhaupt vergleichbar bleiben.
- **Beide Baselines werden neu eingefroren** – zweistufig wie in V1/V2: erst der qid-genaue Nachweis mit unverändertem Fingerprint, danach das Einfrieren. Der Werkzeugweg dafür existiert seit [B5](docs/roadmap-historie.md#b5--messgrundlage-nachführbar-halten); genau deshalb ist der Zeitpunkt für diese Phase günstig.
- **Guardrail nur, falls R0 sie erzwingt.** Zeigt die Verdrängungsmessung Regressionen, werden Referenz-Einträge in der Chunk-Suche **nachrangig** behandelt (sie erscheinen, wenn Volltext-Treffer fehlen oder hinter diesen). Diese Mechanik wird **nicht auf Verdacht** gebaut – das wäre genau der Fehler, den A3 („die Seitengrenze ist schuld"), A5 („das Rauschen sitzt im Vektorraum") und B6 („die Schwelle ist zu hoch") jeweils vorgeführt haben.
  > **R0-Ergebnis: die Bedingung ist eingetreten** – 13 qid-Regressionen mit **echten** Abstracts,
  > alle in den Multi-Hop-Ebenen, zwei davon als vollständiger Verlust aus den Top 5. Die
  > Guardrail wird also gebaut. Sie muss **nachrangig** wirken, nicht ausschließend: Die Handprobe
  > findet ihre zehn Fragen ausgerechnet deshalb auf Rang 1, weil ein Stub kurz ist – Nutzen und
  > Schaden teilen sich die Ursache.
- **Sicherung.** `new_papers/referenzen.txt` wird in den Sicherungsumfang aus [B1](docs/roadmap-historie.md#b1--sicherung-des-korpus) aufgenommen: Die Liste ist kuratiert und aus keiner Quelle rekonstruierbar. Die Stub-Dateien selbst liegen in `papers/` und sind damit bereits erfasst.
- *Akzeptanz:* Jede Ausgabe, die einen Referenz-Eintrag enthält, weist ihn aus – CLI, MCP-Werkzeuge und `answer_question`; `--check` meldet nach dem Neu-Einfrieren 0 Abweichungen; die Handprobe aus R0 findet die Abstracts.

### Bewusst ausgeschlossen

Kein Volltext-Download (das ist eine eigene Fähigkeit – [S2](#s2--volltext-holen-opt-in-lizenz-whitelist), separat über `scripts.discover --download`), keine Umgehung von Bezahlschranken, keine automatische Übernahme ohne Sichtung, **keine LLM-gestützte Anreicherung** eines Abstracts zu etwas, das wie ein Volltext aussieht – das wäre Scheinsicherheit in Reinform –, kein MCP-Werkzeug und keine zweite Duplikatlogik neben der aus Phase 8.

### Definition of Done

- DOI/arXiv-Liste in `new_papers/referenzen.txt` → **ein** Befehl → Stub-Dateien liegen im Eingang → `python -m scripts.intake` → die Paper sind auffindbar, zitierfähig, im Graphen verknüpft und **überall als unvollständig ausgewiesen**.
- R0 ist beantwortet und dokumentiert – auch ein „lohnt sich nicht" ist ein gültiges Ergebnis, wie bei [B6](docs/roadmap-historie.md#b6--grad-des-ähnlichkeitsgraphen-geprüft-verworfen).
- Ein zweiter Lauf des Auflösungsskripts stellt keine Abfrage und erzeugt keine Datei; `--dry-run` verändert nachweislich nichts.
- Ein später eintreffendes Volltext-PDF ersetzt seinen Referenz-Eintrag, statt in der Quarantäne zu landen.
- **Anleitung in der [README](README.md)** inklusive des manuellen Abstract-Wegs und des Upgrade-Pfads; **ADR** bei der Umsetzung (Dateiformat, `document_kind`, Contract-Bruch, Upgrade-Regel).
- Tests: Auflösung mit/ohne Abstract, Idempotenz gegen alle drei Zustände, Intake eines Stubs, Stub-Duplikat, Volltext schlägt Stub, typabhängige Qualitäts-Flags, Ausweisung in allen Ausgaben, Gold-Ableitung ohne Stubs.

---

## Zielbild – erst bei belegter Beschaffbarkeit

Diese Punkte bleiben das **Zielbild** und werden erst umgesetzt, wenn die nötigen Wheels/Modelle/Runtimes offline verfügbar werden ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)); sie sind aktuell **empirisch nicht beschaffbar**.

- **Domain-/Zitationsgraph mit Kuzu (embedded) + Text2Cypher** für deterministische Cypher-Graphfragen und Multi-Hop-Netze (baut auf dem Intra-Korpus-Graphen aus [ADR 0011](docs/adr/0011-intra-corpus-citation-graph-phase7.md) auf).
- **GROBID** für präzises Parsing **externer** Referenzen und Zitationskontexte (benötigt Docker/Java).
- **Microsoft GraphRAG / Docling / LanceDB** als vollwertiges Zielbild (LLM-gestützte Entitäts-/Community-Reports, Bounding-Box-Provenienz). Damit käme auch der **Domain Graph** in Reichweite: Von den in der [README](README.md) skizzierten Kantentypen ist bislang nur `CITES` umgesetzt; `USES_METHOD`, `EVALUATES_ON` und `SUPPORTED_BY` brauchen Entitätsextraktion.
- **Hybrid-Suche mit dedizierten Vektor-/Suchmaschinen** und **Skalierung Richtung Qdrant/Weaviate/Neo4j**. *Dieser Punkt ist seit [Phase 15](docs/roadmap-historie.md#phase-15--skalierung-den-wachsenden-bestand-tragen) nicht mehr die Antwort auf Wachstum:* Die dort bezifferten Wände sind Implementierungsdetails im eigenen Code, keine Grenzen des Speichermodells – ein fremdes Backend bliebe für einen vierstelligen Bestand überzogen und ist offline ohnehin nicht beschaffbar. Der Punkt bleibt stehen, aber erst jenseits der in [G5](docs/roadmap-historie.md#g5--auslegung-neu-festschreiben) neu festgeschriebenen Auslegung.

---

## Literaturübersicht & Arbeitsteilung

- **Rollen-Trennung:** [`Übersicht.md`](Übersicht.md) = *welche* Quellen es gibt und wie relevant sie sind; der GraphRAG-Index = *was* inhaltlich darin steht.
- **Laufende Pflege:** Die Ingestion erzeugt Entwurfszeilen; die wertenden Spalten (`Relevanz fuer Expose`, `SRQ-Zuordnung`) bleiben menschlich kuratiert. Der `Themenfokus` kann an den GraphRAG-Communities ausgerichtet werden.
- **Ab Phase 8** schreibt der Intake die Entwurfszeilen direkt in die Übersicht (append-only, wertende Spalten leer) – umgesetzt, siehe [ADR 0019](docs/adr/0019-corpus-intake-new-papers-phase8.md). `data/overview_drafts.md` ist damit abgelöst; auch `scripts/update_overview.py` schreibt jetzt in die Übersicht.
- **Diese Arbeitsteilung endet mit [G4](docs/roadmap-historie.md#g4--zuflussregel-und-ablösung-der-übersicht).** Gemessen am 2026-08-28 sind von 482 Tabellenzeilen nur noch **131 kuratiert**; 351 sind unbearbeitete `Z`-Entwurfszeilen. Als Landkarte ist die Tabelle damit bereits heute entwertet, und der geplante Zufluss macht es schlimmer. Abgelöst wird das **Format**, nicht die **Aussage**: Die 131 Wertungen sind aus keiner Quelle reproduzierbar und werden maschinenlesbar gerettet, bevor die Datei außer Dienst geht.

---

## Querschnittsthemen: Risiken & Gegenmaßnahmen

| Risiko                                                                        | Gegenmaßnahme                                                                                                                                                                                                                                        |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PDF-Extraktionsrauschen (Layout, Formeln, Scans)                              | Qualitäts-Gates, Provenienz zum Original, Stichproben; Textnormalisierung ([ADR 0015](docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md)); Docling/Marker als späterer Ausbau ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)). |
| **Datenverlust durch den Intake** (hartes Löschen)                     | `--dry-run`, Bericht mit Hash je gelöschter Datei, Sicherungsweg aus [B1](docs/roadmap-historie.md#b1--sicherung-des-korpus).                                                                                                                                               |
| **Unkuratierte PDFs aus dem Netz** (Scans, Fehlerseiten, Schadinhalte)  | Lizenz-Whitelist, Content-Type-/Größenprüfung, selbst erzeugte Dateinamen, Robustheits-Flag für chunk-lose Dokumente.                                                                                                                             |
| **Verwässerung des kuratierten Korpus** durch automatische Vorschläge | Vorschläge landen im Bericht, nie automatisch im Korpus; Zielgröße ist Präzision, nicht Menge.                                                                                                                                                    |
| **Abstract-Stubs verdrängen Volltext-Evidenz** (BM25-Längennormalisierung)    | `document_kind` als Pflichtfeld in jedem Beleg, Ausschluss aus der Gold-Ableitung, Verdrängung vorab an einer Index-Kopie gemessen, Nachrangigkeit **nur** bei belegter Regression – **R0 hat sie belegt** (13 qid-Regressionen, alle in den Multi-Hop-Ebenen), die Guardrail ist damit gesetzt ([Phase 13](#phase-13--referenz-einträge-ohne-volltext)).       |
| Entity Resolution (Synonyme, gleichnamige Autoren)                            | leichte Alias-/Synonym-Kuratierung; bei kleinem Korpus manuell handhabbar.                                                                                                                                                                            |
| Scheinsicherheit durch Summaries                                              | Antworten immer mit Quellenankern/Original-TextUnits; für Fakten Basic/Local bevorzugen.                                                                                                                                                             |
| Inkonsistenz bei inkrementellen Updates                                       | Standard bleibt der volle Re-Index; inkrementell nur mit Identitäts-Nachweis ([G1](docs/roadmap-historie.md#g1--aufnahmepfad-begradigen-die-quadratischen-stellen)).                                                                                                                |
| Kosten/Datenschutz eines Index-LLM                                            | entschärft durch Option B:**kein** Index-LLM (offline, TF-IDF/BM25); ein LLM kommt nur zur Abfragezeit über die Bridge ([ADR 0005](docs/adr/0005-graphrag-index-backend-open.md)).                                                             |
| **Der Bestand wächst über die Auslegung hinaus** – Antwortzeit, Speicher und Aufnahmedauer laufen weg | Beziffert statt vermutet ([G0](docs/roadmap-historie.md#g0--alles-hinterfragen-und-messen-zwingend-zuerst)), begradigt an den drei belegten Stellen ([G1](docs/roadmap-historie.md#g1--aufnahmepfad-begradigen-die-quadratischen-stellen), [G2](docs/roadmap-historie.md#g2--antwortzeit-den-vektorraum-nicht-bei-jeder-frage-neu-bauen)), und die Auslegung wird danach **schriftlich neu festgeschrieben** ([G5](docs/roadmap-historie.md#g5--auslegung-neu-festschreiben)) statt still zu veralten. |
| **Beschleunigung zerstört still die Messgrundlage** – ein anderes Ranking wirkt wie eine Verbesserung | Jede Maßnahme in [G2](docs/roadmap-historie.md#g2--antwortzeit-den-vektorraum-nicht-bei-jeder-frage-neu-bauen) liefert entweder **bit-identische** Ergebnisse (qid-genau belegt) oder weist ihren Bruch aus und friert beide Baselines neu ein; die Entscheidungsregel dafür steht **vor** der Messung fest ([G0.6](docs/roadmap-historie.md#g06--was-kostet-bit-identität)). |
| **Das kuratierte Relevanzurteil geht beim Abschalten der Übersicht verloren** | Es ist aus keiner Quelle reproduzierbar und wird deshalb **zuerst** maschinenlesbar überführt, erst danach wird das Format abgelöst ([G4](docs/roadmap-historie.md#g4--zuflussregel-und-ablösung-der-übersicht)); der Sicherungsumfang aus [B1](docs/roadmap-historie.md#b1--sicherung-des-korpus) wird entsprechend nachgezogen. |
| **Massenzufluss von Referenz-Einträgen** (Phase 14) verwässert Korpus, Übersicht und Community-Struktur | Ernte **schlägt vor**, sie übernimmt nicht; harte Obergrenze aus einer gestaffelten Vorabmessung ([E0.2](docs/roadmap-historie.md#e02--skaliert-die-guardrail-das-schärfste-abbruchkriterium)); Wirkung auf Ähnlichkeitsgraph und Übersicht vorab beziffert ([E0.3](docs/roadmap-historie.md#e03--was-macht-der-ähnlichkeitsgraph-mit-vielen-einchunkigen-papern), [E0.5](docs/roadmap-historie.md#e05--verträgt-die-kuratierte-übersicht-den-zufluss)). |
| **Selbstbezügliche Messung** – geerntete Stubs werden zu Multi-Hop-Gold-Ankern und heben die Kennzahl ohne echten Gewinn | Ankerwahl auf `document_kind = 'full'` beschränken; Referenz-Einträge bleiben **Ziele**, werden aber keine **Anker** – vorab zu belegen ([E0.4](docs/roadmap-historie.md#e04--die-zirkularitätsfalle-der-multi-hop-messung)), analog zum lexikalischen Ausschluss aus [ADR 0031](docs/adr/0031-reference-contract-and-guardrail-phase13.md). |

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
- **M9 – Auch das Unerreichbare zählt:** ✅ erreicht – ein Paper, von dem nur der Abstract öffentlich ist, ist über seine DOI auffindbar, zitierfähig und als Ziel von `CITES`-Kanten verknüpft – und in **jeder** Ausgabe als unvollständig ausgewiesen (Phase 13). **Ehrlich dazu:** Der Produktivkorpus ist bewusst noch stubfrei; der Nachweis lief auf Index-Kopien mit **52 echten** Abstracts, deren Handprobe **10/10** trifft. Die Nachrangigkeits-Guardrail senkt die in R0 belegten 13 qid-Regressionen auf **3 ohne Totalverlust** – gemessen, nicht geschätzt, und gegen zwei besser klingende Varianten verteidigt.
- **M10 – Der Korpus kennt seine eigenen Ränder:** ✅ erreicht **in angepasster Form** (2026-09-01) – [E0](docs/roadmap-historie.md#e0--alles-hinterfragen-und-messen-zwingend-zuerst) fand einen billigeren, gleichwertigen Weg und führte ihn selbst vor: 15 der häufigsten externen Zitations-Kandidaten wurden über die **bestehende** Kette `resolve_references` → `intake` real aufgelöst (15/15 Treffer), ohne ein neues Ernte- oder Kurationswerkzeug zu bauen. Die Handprobe bestätigt den Nutzen (9/10, Schwelle ≥ 7/10); zwei bindende Auflagen für einen künftigen manuellen Harvest stehen fest (Multi-Hop-Anker bleiben auf `document_kind = 'full'` beschränkt, jeder Batch wird vorab mit einer Guardrail-Regression geprüft). **Ehrlich dazu:** Ein automatisiertes Ernte-/Kurationswerkzeug (E1/E2) wurde **nicht** gebaut – „lohnt sich nicht in der geplanten Form" war das durch E0 begründete, zulässige Ergebnis (Phase 14).
- **M11 – Der Bestand darf wachsen:** ✅ erreicht (2026-09-01, Phase 15). Der Aufnahmepfad hat keine in der Paperzahl quadratische Stelle mehr, warme Anfragen liegen bei Median 0,169 s (Marke < 1 s), die kuratierten Wertungen sind maschinenlesbar gerettet (`metadata/curation.json`) und die Auslegung ist mit **Messdatum** neu festgeschrieben (≤ 750 Volltexte / ≤ 1500 Gesamteinträge, 2026-09-01) statt aus der Zeit mit 145 Papern fortgeschrieben. Beide `--check`-Läufe melden 0 Abweichungen; die Handprobe aus [G0.7](docs/roadmap-historie.md#g07--handprobe-bleibt-das-werkzeug-im-alltag-brauchbar) hält 9 von 10 (Schwelle ≥ 8/10).

