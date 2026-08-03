# 0020 – Online-Kandidatensuche (Phase 9 / S1): injizierbarer Transport-Port, Metadaten ohne Download

- **Status:** Akzeptiert
- **Datum:** 2026-08-03

## Kontext

Der Korpus wächst bisher ausschließlich über den manuellen Zufluss aus
[ADR 0019](0019-corpus-intake-new-papers-phase8.md): PDF nach `new_papers/`, dann
`python -m scripts.intake`. Woher die PDF stammt, ist ungelöst – die Suche nach neuer Literatur
findet vollständig außerhalb des Werkzeugs statt, und damit auch die Frage, ob ein gefundenes
Paper überhaupt neu ist.

Der vorgeschaltete Machbarkeits-Schritt **S0** ist beantwortet (Statusblock in
[Roadmap.md](../../Roadmap.md), Messung vom 2026-08-03) und hat die Ausgangslage in drei Punkten
präzisiert:

1. **Netz ist erreichbar – aber nicht direkt.** Externes DNS ist tot, ausgehendes TCP und UDP/53
   sind blockiert. Der einzige Weg nach außen ist ein Unternehmens-Proxy, der auf `CONNECT` mit
   **HTTP 407** und `Proxy-Authenticate: Negotiate, NTLM` antwortet. Über ihn liefern arXiv,
   Crossref und OpenAlex reguläre Antworten.
2. **Von fünf Kandidatenquellen sind zwei praktisch nutzbar.** Semantic Scholar antwortet ohne
   API-Schlüssel mit **429**, Unpaywall verlangt zwingend eine Kontakt-E-Mail (**422**), Crossref
   rankt sichtbar schlechter und liefert Abstracts nur lückenhaft (1 von 3 Treffern).
3. **Die Vorschlagsqualität trägt.** Eine Handprobe mit drei Anfragen aus dem eigenen Bestand
   ergab 51 Kandidaten; **13** lagen bereits im Korpus und wurden von der Logik aus ADR 0019
   erkannt, **ohne** ein Korpus-Paper zu übersehen. Der wirksamste Rauschfilter war das
   **Publikationsjahr** – es fängt 6 von 8 thematisch korpusfremden Treffern, weil OpenAlex nach
   Zitationszahl rankt und dadurch alte Klassiker hochspült.

Daraus folgt die eigentliche Schwierigkeit dieser Ausbaustufe: Ein bislang **vollständig
netzfreies** System (Leitprinzip 4 in [CONTRIBUTING.md](../../CONTRIBUTING.md)) bekommt seine
erste Netzkomponente – und zwar eine, die sich in dieser Umgebung nicht mit
Standard-HTTP-Bibliotheken bedienen lässt und offline nicht testbar ist.

## Entscheidung

### 1. Der Netzzugang liegt hinter einem injizierbaren Port

Neues Paket `src/research_graphrag/online/`. Das Modul `transport.py` definiert das Protocol
`HttpClient` mit genau einer Methode (`get`) und dem Ergebnistyp `HttpResponse`. Alles Übrige –
Anfragebildung, Quellen-Adapter, Deduplikation, Bericht – arbeitet **ausschließlich gegen diesen
Port** und ist damit netzfrei und vollständig testbar.

Das ist dasselbe Muster, mit dem [ADR 0004](0004-llm-bridge-via-mcp-sampling.md) und
[ADR 0012](0012-llm-bridge-and-answer-synthesis-phase7.md) den Modellzugriff gekapselt haben: Die
nicht testbare Außenanbindung sitzt an **einer** Stelle, die Kernlogik bleibt synchron und
deterministisch prüfbar.

### 2. Der Proxy-Transport ist plattformgebunden und wird nie im Repo konfiguriert

`ProxyHttpClient` baut den `CONNECT`-Tunnel selbst auf: Negotiate-Token aus dem bestehenden
Windows-Anmeldekontext über `sspi` (pywin32), danach TLS mit dem **certifi**-Bundle.

- **Der Proxy-Endpunkt kommt ausschließlich aus der Umgebungsvariablen
  `RESEARCH_GRAPHRAG_PROXY`** (Form `host:port`). Ein Unternehmens-Hostname ist ein Firmeninternum
  und gehört nicht in ein Repository.
- **Ohne die Variable** wird direkt verbunden. Das hält den Code an anderen Standorten brauchbar
  und macht den Proxy zur Ausnahme, nicht zur Voraussetzung.
- **Warum certifi statt des Windows-Speichers:** arXiv wird von der CA „Certainly" ausgestellt,
  deren Wurzelzertifikat im gemessenen Windows-Speicher fehlt (`certificate verify failed`). Mit
  certifi antwortet dieselbe Anfrage mit HTTP 200. Die Verifikation wird **nicht** abgeschaltet.

### 3. Nur arXiv und OpenAlex

Crossref, Semantic Scholar und Unpaywall entfallen mit der in S0 gemessenen Begründung. Der
Atom-Feed von arXiv wird mit `xml.etree` aus der Standardbibliothek gelesen – `feedparser` ist
offline nicht verfügbar und auch nicht nötig.

### 4. Die Deduplikation wird wiederverwendet, nicht nachgebaut

Der Abgleich gegen den Korpus nutzt die Bausteine aus ADR 0019 (`_load_corpus`,
`best_title_match`, `normalize_title`) über die neue öffentliche Funktion `intake.load_corpus`.
Ein zweiter Dedup-Mechanismus wäre eine Fehlerquelle mit zwei divergierenden Wahrheiten.

**Ergänzt** wird eine in S0 aufgedeckte Lücke: Dasselbe Paper erscheint bei arXiv und OpenAlex
unter **verschiedenen** Identifikatoren (3 Fälle in 51 Treffern). Kandidaten werden deshalb
zusätzlich **quellenübergreifend** über den normalisierten Titel zusammengeführt.

### 5. Ausgabe: append-only Bericht, kein Weg in den Korpus

Der Lauf schreibt nach `data/online_candidates.md` (append-only) und legt die Rohantworten
datiert unter `data/online_raw/<Zeitstempel>/` ab (Reproduzierbarkeit, Leitprinzip 3).

**Der Bericht ist eine Empfehlung, kein Bestand.** Es wird weder nach `papers/` noch nach
`new_papers/` geschrieben und – anders als beim Intake – **nicht** in
[`Übersicht.md`](../../Übersicht.md). Der einzige Weg in den Korpus bleibt ADR 0019.

Weil Titel und Abstracts **nicht vertrauenswürdige externe Daten** sind, werden sie vor dem
Schreiben entschärft: Tabellen-Pipes, Zeilenumbrüche und Steuerzeichen werden neutralisiert,
Längen begrenzt, und Verweise werden nur als Klartext-URL mit `http(s)`-Schema ausgegeben – nie
als Markdown-Link mit fremdbestimmtem Ziel.

### 6. Aktualitätsfilter als Default

Kandidaten älter als **fünf Jahre** entfallen; die Grenze ist per CLI übersteuerbar. Grundlage ist
die S0-Messung, nicht eine Annahme.

### 7. Kein MCP-Werkzeug, kein Download

Der Modus wird **ausschließlich** über `python -m scripts.discover` gestartet. Er wird bewusst
**nicht** als MCP-Tool registriert: Copilot ruft Werkzeuge autonom auf, und niemand soll durch
eine beiläufige Frage ungewollten Netzverkehr auslösen. Der Server bleibt bei **acht**
Werkzeugen und netzfrei.

Der Volltext-Download (S2 der Roadmap) bleibt **zurückgestellt**: arXiv weist im Feed keine Lizenz
aus, OpenAlex nur bei 15 von 51 gemessenen Treffern – eine belastbare Lizenz-Whitelist ist auf
dieser Datenbasis nicht führbar. Der Bericht nennt den Volltext-Link, der Abruf bleibt manuell.

### 8. Abhängigkeiten: zwei explizite Pins, kein neues Paket

`certifi` und `pywin32` werden in `pyproject.toml` **explizit gepinnt**. Beide waren bereits
transitiv vorhanden (`mcp` → `httpx` → `certifi`; `mcp` → `pywin32` auf Windows) und werden nun
direkt importiert – exakt die Regel, die
[ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md) für `numpy` etabliert hat. Beide Pins
stehen bereits in `requirements.lock`; die Datei bleibt unverändert.

## Alternativen

| Verworfen | Grund |
| --- | --- |
| `requests`/`httpx` mit Proxy-Konfiguration | Gemessen: beide scheitern am 407, weil sie Proxy-**Negotiate** nicht beherrschen. `requests-negotiate-sspi` ist offline nicht verfügbar. |
| `pyspnego` für den Handshake | Gemessen entbehrlich: `sspi` aus pywin32 schließt den Handshake in **einer** Runde ab – und pywin32 ist auf Windows ohnehin schon da. Eine Abhängigkeit weniger. |
| Optionales Extra `[online]` in `pyproject.toml` | Es enthielte keine Abhängigkeit, die nicht ohnehin installiert ist – eine Trennung, die nichts bewirkt. Die Grenze wird stattdessen im Code gezogen (eigenes Paket, Import in `DomainError` übersetzt). |
| PAC-Datei automatisch auswerten | Erfordert eine JavaScript-Engine; `pypac`, `dukpy` und `js2py` fehlen offline. Eine eigene PAC-Auswertung wäre fehleranfällig und ohne Nutzen gegenüber einer Umgebungsvariablen. |
| TLS-Verifikation abschalten, um arXiv zu erreichen | Sicherheitsverstoß ohne Not – certifi löst dasselbe Problem korrekt. |
| Eigene Dedup-Logik für Metadaten | Zwei Wahrheiten über „ist das schon im Korpus" wären eine Fehlerquelle. ADR 0019 ist gemessen und getestet. |
| Kandidaten direkt in `Übersicht.md` schreiben | Die Übersicht ist die **kuratierte** Sicht. Ungeprüfte Netzvorschläge würden genau die Eigenschaft zerstören, die sie wertvoll macht. |
| Registrierung als MCP-Tool | Copilot ruft Tools autonom auf; Netzverkehr gehört nicht in Agent-Reichweite (dieselbe Erwägung wie beim Intake, ADR 0019 §7). |
| Crossref zusätzlich aufnehmen | Gemessen schlechteres Ranking und Abstracts nur bei 1 von 3 Treffern – mehr Rauschen bei mehr Netzverkehr. |

## Konsequenzen

- **Positiv:** Der Kern bleibt netzfrei – ohne die Umgebungsvariable und ohne Aufruf von
  `scripts.discover` ändert sich am bisherigen Verhalten nichts. Anfragebildung, Quellen-Adapter,
  Deduplikation und Bericht sind **ohne Netz** testbar (Fixtures aus realen, in S0 abgelegten
  Antworten). Die Deduplikation gegen den eigenen Korpus ist der belegte Mehrwert gegenüber einer
  gewöhnlichen Websuche.
- **Negativ / Aufwand:** `ProxyHttpClient` ist **Windows-gebunden** (SSPI) und lässt sich offline
  nicht testen – die Zeilenabdeckung dieses einen Moduls unterschreitet den Richtwert bewusst,
  wie schon bei `mcp_server/sampling.py`. Der Proxy-Endpunkt muss manuell gesetzt werden und kann
  sich ändern. Netzantworten sind nicht deterministisch; reproduzierbar ist der **Befund** über
  die abgelegten Rohantworten, nicht der Lauf.
- **Bekannte Grenze:** Die Titel-Zusammenführung über Quellen hinweg arbeitet auf normalisierten
  Zeichenketten. Stark abweichende Schreibweisen desselben Papers bleiben zwei Kandidaten – das
  ist der bewusste Preis für Präzision vor Recall (dieselbe Abwägung wie in
  [ADR 0011](0011-intra-corpus-citation-graph-phase7.md)).
- **Folgeentscheidungen:** S2 (Volltext-Download) bleibt zurückgestellt und bräuchte einen eigenen
  ADR – insbesondere für die Lizenzermittlung, die Prüfung von Content-Type und Größe sowie die
  selbst erzeugten Dateinamen.
