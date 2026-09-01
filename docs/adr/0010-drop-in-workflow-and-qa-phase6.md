# 0010 – Drop-in-Workflow & Qualitätssicherung (Phase 6)

- **Status:** Akzeptiert
- **Datum:** 2026-07-31

## Kontext

[Roadmap.md](../../Roadmap.md) beschreibt für **Phase 6** einen reibungslosen „ablegen → nutzen"-
Kreislauf mit drei Bausteinen und der DoD *„neue PDF ablegen → `ingest.py` → sofort in Copilot
abfragbar; unveränderte PDFs übersprungen"*:

1. `ingest.py` bündelt Extraktion-Dedup + Index-Aktualisierung zu **einem** Befehl (voller
   Re-Index Standard; inkrementelles Update dokumentiert).
2. Der MCP-Server liest **stets die aktuellen** Artefakte (Reload/On-Read).
3. **Pragmatische QS:** Prüf-Fragen durchspielen, Provenienz-Stichproben, einfaches Logging/Status.

**Bestandsaufnahme vor Umsetzung:** Die Bausteine 1 und 2 sind durch die Phasen 2–5 bereits
faktisch erfüllt. `research_graphrag.pipeline.ingest` bündelt Extraktion, Dedup (`manifest.json`),
Index- und Graph-Bau samt Qualitätsreport in einem Schritt ([ADR 0007](0007-graphrag-index-phase3-option-b.md));
`scripts/ingest.py` ist der eine Befehl. Der MCP-Server hält **keinen** In-Memory-Cache: jedes Tool
ruft `TfidfIndex.load(db_path)` bzw. `load_communities(db_path)` **pro Anfrage** frisch auf
([ADR 0009](0009-mcp-server-stdio-phase5.md)) – On-Read ist damit bereits per Konstruktion gegeben.
Das echte Delta der Phase 6 ist daher **Verifizieren + Härten + gezielte QS-Ergänzungen**, nicht ein
Neubau. Rahmenbedingung bleibt das **Offline-Firmenumfeld** ([ADR 0002](0002-venv-and-offline-dependency-strategy.md))
und der Charakter als **persönliches, right-sized Werkzeug** ([CONTRIBUTING.md](../../CONTRIBUTING.md),
Abschnitt 5).

## Entscheidung

1. **On-Read beibehalten (kein Cache) und um einen atomaren Index-Swap härten.** Für die Garantie
   *„stets frische **und** vollständige Antwort"* wird der reine On-Read-Zugriff um einen atomaren
   Wechsel ergänzt: `pipeline.ingest` baut Index **und** Graph vollständig nach `index.sqlite.tmp`
   und verschiebt die Datei erst nach Erfolg per `os.replace` **atomar** an die Zielstelle
   (`_build_index_atomically`). Ein `os.replace` auf demselben Dateisystem ist atomar; ein zuvor
   laufender On-Read-Aufruf sieht daher **entweder** den alten **oder** den neuen, aber nie einen
   halbfertigen Index. Schlägt der Bau fehl, bleibt der bestehende Index **unangetastet**
   (Crash-Sicherheit); eine etwaige Temporärdatei wird stets entfernt.

2. **Qualitätssicherung als wiederholbares Skript + struktureller Regressionstest, ohne Scoring.**
   `scripts/qa.py` spielt das **feste** Prüf-Fragen-Set (`QUESTIONS`, Single Source of Truth über
   [eval/pruef-fragen.md](../../eval/pruef-fragen.md)) je erwartetem Modus (Basic/Local/Global/DRIFT)
   durch und druckt die **belegte Provenienz** für die menschliche Stichprobe. Der Regressionstest
   (`tests/retrieval/test_qa.py`) prüft nur das **deterministisch Prüfbare** – Modus-Dispatch und
   wohlgeformte Provenienz (existierende `paper_id`, Seite ≥ 1, `file:`-Quelle) – ohne den
   Antwort-*Inhalt* zu bewerten. Eine automatische Bewertung (LLM-Judge/Scoring) wird **verworfen**:
   offline gibt es kein Ground-Truth-Label und keinen Judge; sie erzeugte hohen Pflegeaufwand bei
   trügerischer Genauigkeit (Risiko „Scheinsicherheit", siehe Roadmap-Querschnittsthemen).

3. **Read-only Status-/Logging-Kommando `scripts/status.py`.** Es liest ausschließlich (kein
   TF-IDF-Rebuild, keine Schreibzugriffe) und zeigt Index-Schema/-Kennzahlen (Paper/Chunks/
   Communities), Qualitäts-Flags aus `quality_report.json`, die Identifier-Abdeckung (DOI/arXiv)
   sowie einen **Konsistenz-Check** zwischen `papers/`, `manifest.json` und `canonical/`
   (nicht ingestete, verwaiste oder fehlende Artefakte).

4. **Standard bleibt der volle (atomare) Re-Index; inkrementelles Update bleibt dokumentiert/
   optional.** Bei ≤ 500 Papern ist der volle Re-Index günstig und konsistent (Roadmap); ein
   inkrementelles `graphrag update` ist eine spätere Optimierung (Phase 7).

5. **DoD-Nachweis über Tests plus realen Korpuslauf.** Wie in den Phasen 3–5 (kein steuerbarer
   Copilot-Client) belegen ein **Freshness-Regressionstest** (`tests/integration/test_phase6_freshness.py`:
   neue PDF → `ingest` → dieselbe On-Read-Kette liefert das neue Paper; unveränderte übersprungen;
   Fehler lässt Altindex intakt) und die QS-Harness die DoD; die manuelle Stichprobe über die 145
   Paper wird in [eval/pruef-fragen.md](../../eval/pruef-fragen.md) festgehalten.

Die Status-/QS-Logik lebt bewusst in **Dev-Hilfsskripten** (`scripts/`, Muster
`scripts/graph_info.py`) statt in `src/` oder als MCP-Tool – right-sized für ein persönliches
Werkzeug; ein späterer Umzug nach `src/` (falls als Tool benötigt) bleibt offen.

## Alternativen

- **mtime-basierter oder In-Memory-Index-Cache im Server.** Verworfen: eine reine
  **Performance**-Optimierung, die bei fehlerhafter Invalidierung **neue** Staleness-Risiken
  einführt – gegenläufig zum Ziel „beste, stets frische Antwort". Bei ≤ 500 Papern ist der
  On-Read-Neuaufbau des TF-IDF-Raums unkritisch; ein Cache bleibt Phase-7-Kandidat.
- **In-place-Re-Index ohne atomaren Swap (bisheriges Verhalten).** Verworfen: ein On-Read-Aufruf
  während des Neuaufbaus könnte einen halbfertigen Index sehen; zudem keine Crash-Sicherheit.
- **Vollautomatische Evaluation mit Scoring/LLM-Judge.** Verworfen (Punkt 2): offline kein
  Ground-Truth/Judge; hoher Pflegeaufwand und Scheinpräzision.
- **Status/QS als `src`-Modul + eigenes MCP-Tool.** Für Phase 6 verworfen (YAGNI/right-sized);
  Dev-Skripte genügen dem Zweck der pragmatischen QS.

## Konsequenzen

- **Positiv:** Antworten sind stets **frisch und vollständig**, ohne Server-Neustart; der
  Index-Neuaufbau ist **crash-sicher**; die QS ist **wiederholbar** (Skript + Regressionstest); ein
  Kommando gibt einen schnellen **Konsistenz-Überblick**; die DoD ist testgestützt.
- **Negativ / Aufwand:** On-Read rekonstruiert den TF-IDF-Raum **pro Anfrage** (bei ≤ 500 Papern
  vertretbar; Optimierung = Phase 7); der atomare Swap benötigt kurzzeitig **doppelten
  Plattenplatz** (Temporärdatei) beim Re-Index.
- **Folgeentscheidungen:** Performance-Cache und inkrementelles `graphrag update` sind Kandidaten
  für Phase 7 ([Roadmap.md](../../Roadmap.md)); solange der On-Read-Zugriff bleibt, ist dafür kein
  neuer ADR nötig.

## Nachtrag (2026-09-01, Phase 15 / G5)

Punkt 1 der Entscheidung („On-Read beibehalten, **kein Cache**") und die Begründung „bei ≤ 500
Papern vertretbar" sind durch [ADR 0033](0033-response-latency-cache-and-persisted-tfidf-state-phase15.md)
überholt: Seit Phase 15 / G2 gibt es einen Prozess-Cache über den Dateizustand der Index-Datei
(Weg C) plus einen persistierten TF-IDF-Zustand (Weg A) – die On-Read-Frische aus Punkt 1 bleibt
dabei **wörtlich** erhalten (ein atomarer Swap invalidiert den Cache-Eintrag), nur der wiederholte
Neubau des Vektorraums entfällt. Die Korpus-Auslegung „≤ 500 Paper" ist durch die gemessene
Auslegung aus [Roadmap.md, G5](../../Roadmap.md#g5--auslegung-neu-festschreiben) ersetzt:
**≤ 750 Volltexte / ≤ 1500 Gesamteinträge (2026-09-01)**. Die Zahl ist niedriger als die aus G0.1
hergeleitete erste Marke (1000), weil eine direkte Nachmessung am Auslegungsstand zeigte, dass
Local (nicht Basic oder DRIFT) die 5-s-Marke schon zwischen 800 und 900 Papern reißt – siehe
G5-Statusblock in der Roadmap. Punkte 2–5 dieses ADRs (QS-Skript,
`scripts.status`, voller atomarer Re-Index als Standard) bleiben unverändert gültig.
