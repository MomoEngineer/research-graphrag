# 0037 – Obergrenze für MCP-Tool-Antworten (`list_topics`-Neuschnitt, geteilte Trefferzahl-Grenze, Byte-Sicherheitsnetz)

- **Status:** Akzeptiert
- **Datum:** 2026-09-16

## Kontext

Der MCP-Transport bricht eine Werkzeug-Antwort über **1 MB** mit einer nicht diagnostizierbaren
Meldung ab (`Tool result is too large. Maximum size is 1MB`). Eine Messung gegen den realen
lokalen Index (siehe unten) bestätigt einen konkreten, strukturellen Auslöser statt einer
Vermutung:

| Werkzeug | Serialisierte Größe (gemessen) |
| --- | --- |
| `list_topics` (alle Communities, volle `members`-Liste) | **555.037 Byte** |
| `search_basic` k=5 (Default) | 3.828 Byte |
| `search_basic` k=200 | 148.757 Byte |
| `search_local` Defaults | 11.637 Byte |
| `search_local` k=50, fan_out=50 | 46.011 Byte |
| `search_global` n=5 (Default) | 7.934 Byte |
| `search_global` n=50 | 72.356 Byte |
| `search_drift` Defaults | 12.299 Byte |
| `get_paper`/`get_citations` (größtes Paper) | 8.256 / 16.124 Byte |
| `answer_question` Defaults | 8.743 Byte |

`list_topics` nimmt **keinen Parameter** entgegen und liefert unbedingt jede Community des
Korpus inklusive der vollständigen `members`-Liste (Paper-IDs). Der reale Index enthält aktuell
**3.461 Paper / 220.964 Chunks / 1.170 Communities**, davon **951 Singleton-Communities** der
Größe 1. Eine Aufschlüsselung zeigt, dass nicht die `members`-Liste den Hauptanteil trägt, sondern
`keywords`/`summary` **je Community** – bei 1.170 (größtenteils bedeutungslosen Ein-Paper-)
Communities addiert sich das:

| Variante | Größe |
| --- | --- |
| alle 1.170 Communities, mit `members` (heutiger Zustand) | 555.037 Byte |
| alle 1.170 Communities, ohne `members` | 470.607 Byte |
| nur Communities mit `size >= 2` (219 Stück), ohne `members` | 92.889 Byte |
| größte Einzelcommunity (105 Mitglieder) inkl. voller `members`-Liste | 2.554 Byte |

Alle acht übrigen Werkzeuge prüfen bei `k`/`n`/`fan_out`/`communities`/`seeds` nur die
Untergrenze (`> 0`), nie eine Obergrenze – bei heutigen Defaults unauffällig, aber eine offene
Lücke im Vertrag: Ein hinreichend großer Parameter treibt jede dieser Antworten unbegrenzt nach
oben. `get_citations` hat strukturell dieselbe Eigenschaft wie `list_topics` (kein
größenbegrenzender Parameter überhaupt), ist aber am realen Korpus noch klein (16 KB beim
meistzitierten gemessenen Paper).

**Zur Korpusgröße:** README.md/CONTRIBUTING.md dokumentieren eine gemessene Auslegung von
**≤ 750 Volltexte / ≤ 1500 Gesamteinträge** (Stand 2026-09-01, aus einer Latenzmessung zu Local
Search, [Roadmap-Historie, G5](../roadmap-historie.md#g5--auslegung-neu-festschreiben)). Der reale
Bestand liegt mit 3.461 Papern bereits beim **4,6-Fachen** dieser Ceiling. Diese Diskrepanz ist
real und wird hier zur Kenntnis genommen und für die **Bemessung der in diesem ADR gewählten
Grenzwerte** zugrunde gelegt – eine Korrektur der G5-Auslegung selbst setzte eine eigene,
gleichwertige Latenzmessung voraus (Local Search riss die 5-s-Marke laut G5 bereits zwischen 800
und 900 Papern) und ist **nicht** Gegenstand dieses ADR.

## Entscheidung

### 1. `list_topics` liefert standardmäßig eine gefilterte, membergelöste Übersicht

Spezifikation `0.1.0 → 0.2.0` (bewusster Bruch, Präzedenzfall `search_local` `0.1.0 → 0.2.0`):

- Die Standardantwort verliert das Feld `members` (Größe, Keywords, Summary und Vertreter bleiben
  – sie decken den Übersichts-Zweck ab, ohne mit dem Korpus linear mitzuwachsen).
- Neuer Parameter `min_size` (Default `2`): blendet Singleton-Communities aus, die keine
  cross-paper-Synthese tragen (95.037 → 470.607 → 92.889 Byte allein durch dieses Filterkriterium
  am realen Korpus).
- Neuer Parameter `limit` (Default `50`, hart auf `MAX_RESULT_COUNT` = 50 gedeckelt): begrenzt die
  Trefferzahl unabhängig vom künftigen Korpuswachstum; sortiert wird dafür nach Größe absteigend
  (bedeutendste Themencluster zuerst) statt wie bisher aufsteigend nach `community_id`.
- Neuer Parameter `community_id`: liefert **eine** Community mit voller `members`-Liste (max.
  gemessen 2.554 Byte selbst bei der größten Community) – der Weg, um nach der Auswahl aus der
  Übersicht die vollständige Mitgliederliste zu bekommen. Unbekannte `community_id` → `not_found`.
- Die Antwort weist zusätzlich `total_matching` (Communities mit `size >= min_size` vor `limit`)
  und `truncated` (bool) aus – eine Kürzung ist damit **sichtbar**, nie stillschweigend, wie es
  auch der DRIFT-`fallback` bereits vorlebt.

Implementiert als eigenes Modul `retrieval/topics.py` (bisher lag `list_topics` als einzige
Ausnahme direkt im Server, ohne eigene Retrieval-Fachlogik – mit Filterung/Limit/Einzelabruf hat
es genug Fachlogik, um denselben dünnen-Wrapper-Grundsatz wie die übrigen acht Werkzeuge zu
verdienen).

### 2. Eine geteilte Obergrenze `MAX_RESULT_COUNT = 50` für alle Trefferzahl-Parameter

Ein neues, schmales Top-Level-Modul `research_graphrag/limits.py` (Querschnitt, wie `errors.py`
und `keywords.py`) definiert `MAX_RESULT_COUNT = 50` und eine Hilfsfunktion, die einen zu großen
Parameter als `invalid_input` ablehnt – **exakt dieselbe Fehlerkategorie**, mit der die bereits
bestehenden Untergrenzen (`k <= 0` usw.) abgelehnt werden. Genutzt an jeder Stelle, die heute schon
ihre Untergrenze prüft:

- `indexing/tfidf_index.py`: `TfidfIndex.search()` (deckt `search_basic`, `search_drift` und
  intern `search_local`s `seeds` ab) und `neighbors_of_chunk()` (deckt `search_local`s `k` ab).
- `retrieval/local.py::search_local()`: `fan_out`, `seeds`.
- `retrieval/global_search.py::rank_communities()`: `n`.
- `retrieval/drift.py::search_drift()`: `k`, `communities`.
- `retrieval/citations.py::get_citations()`: neuer Parameter `limit` (Default `MAX_RESULT_COUNT`),
  begrenzt `cites`/`cited_by` **je Richtung**; die Antwort weist zusätzlich `cites_total`/
  `cited_by_total` aus (dieselbe Transparenz-Regel wie bei `list_topics`).
- `retrieval/topics.py`: `limit` (s. o.).

**Harte Ablehnung statt stilles Kappen.** Ein zu großer Parameter wird mit einer benannten
`invalid_input`-Meldung abgelehnt statt intern auf `MAX_RESULT_COUNT` gekürzt zu werden. Ein still
gekürztes Ergebnis sähe für den aufrufenden Agenten wie eine vollständige Trefferliste aus – das
widerspricht den Leitprinzipien „Provenienz zuerst" und „Nachvollziehbarkeit vor Tempo"
(CONTRIBUTING.md, Abschnitt 1) ebenso wie dem etablierten Muster dieses Portfolios, jede Abweichung
sichtbar zu machen statt sie zu verstecken (DRIFTs `fallback`, `list_topics`s neues `truncated`).
`50` ist dabei reichlich bemessen: Jede gemessene Kombination aus der Tabelle oben bleibt bei
`MAX_RESULT_COUNT` weit unter 150 KB – auch bei mehrfacher gleichzeitiger Ausschöpfung (z. B.
`search_local` mit `k=50` **und** `fan_out=50`).

### 3. Byte-Sicherheitsnetz in `_guard` als letzte Absicherung – kein Abschneiden mitten in der Antwort

`server.py::_guard` ist laut eigener Modul-Doku bereits die „letzte Sicherung" gegen unerwartete
Fehler. Nach einem erfolgreichen `produce()` wird die Antwort **einmal** vollständig serialisiert
und ihre Byte-Länge gegen eine Sicherheitsschwelle (`_MAX_RESPONSE_BYTES = 900_000`, Marge unter
der 1-MB-Transportgrenze) geprüft. Wird sie überschritten, liefert `_guard` einen strukturierten
`constraint_violation`-Fehler statt der bereits serialisierten Antwort.

Die Antwort wird dabei **nie in der Mitte abgeschnitten**: Es gibt keinen Zwischenzustand, in dem
ein Teil einer Trefferliste ausgeliefert wird, ohne dass der Aufrufer das erkennen könnte. Entweder
die vollständige, unter der Schwelle liegende Antwort geht raus, oder ein Fehler – nie ein
unvollständiges Fragment. Dieses Netz soll im Normalfall **nie greifen**: Bei korrekt bemessenem
`MAX_RESULT_COUNT` bleibt jede reguläre Antwort weit darunter; es fängt ausschließlich
Unvorhergesehenes ab (z. B. eine künftige Erhöhung von `_SNIPPET_LIMIT`, ohne `MAX_RESULT_COUNT`
neu zu prüfen).

`constraint_violation` wird wiederverwendet statt einer neuen Fehlerkategorie: Die Situation ist
eine verletzte Invariante des Tool-Vertrags („die Antwort passt in die Sicherheitsschwelle"), keine
in Isolation ungültige Eingabe – dieselbe Einordnung wie bei „Index ohne Chunks" oder „kein Graph
gebaut". `docs/error-model.md` wird um dieses Beispiel ergänzt.

## Alternativen

- **Byte-basiertes Kappen als primärer Mechanismus** (Antwort iterativ verkleinern, bis sie unter
  1 MB passt). Verworfen: Die abgelieferte Trefferzahl hinge dann vom Zufall der Snippet-/
  Identifier-Länge ab statt vom Score – zwei identische Anfragen könnten unterschiedlich viele
  Treffer liefern. Das widerspricht dem in **jeder** Tool-Spec verankerten
  Determinismus-/Reproduzierbarkeit-Abschnitt. Zusätzlich bräuchte ein korrektes Kappen pro
  Werkzeug eine eigene Truncation-Reihenfolge (welche Liste zuerst kürzen?) – mehr Komplexität für
  einen Fall, den die Item-Count-Grenze aus Entscheidung 2 bereits mit großer Marge verhindert.
- **Stilles Kappen von `k`/`n`/… auf `MAX_RESULT_COUNT`** statt Ablehnung. Verworfen: siehe
  Begründung in Entscheidung 2 (Transparenzprinzip).
- **`list_topics` unverändert lassen, nur eine neue Fehlerschwelle einziehen.** Verworfen: Das
  Werkzeug bliebe strukturell unbrauchbar für seinen eigentlichen Zweck (Korpus-Überblick), sobald
  es regelmäßig `constraint_violation` statt einer Antwort liefert – das Problem wäre nur
  verschoben, nicht gelöst.
- **Eigene MCP-Tools pro Paginierungsseite** (z. B. `list_topics_page`). Verworfen: Parameter
  (`min_size`, `limit`, `community_id`) am bestehenden Werkzeug sind die kleinere,
  contract-konsistente Änderung; ein zusätzliches Werkzeug hätte die Portfolio-Größe ohne
  erkennbaren Zusatznutzen erhöht.
- **Die veraltete ≤750/≤1500-Ceiling in README/CONTRIBUTING jetzt korrigieren.** Zurückgestellt:
  Die Zahl ist das Ergebnis einer dedizierten Latenzmessung (G5); sie ohne erneute Messung zu
  überschreiben widerspräche demselben Prinzip, das dieses ADR befolgt. Empfohlen als **separate**
  Folgearbeit (G5-Neuvermessung inkl. Local-Search-Latenz bei 3.461 Papern) – umgesetzt in
  [ADR 0038](0038-corpus-ceiling-revision-local-search-latency.md).

## Konsequenzen

- **Positiv:** Jede gemessene Tool-Antwort bleibt mit großer Marge unter der 1-MB-Transportgrenze,
  auch bei künftigem Korpuswachstum (die dominanten Antwortgrößen hängen jetzt von `k`/`limit`
  ab, nicht mehr unbegrenzt vom Korpus). Abweichungen (Kürzung, Sicherheitsnetz) sind immer
  sichtbar (`truncated`, `total_matching`, `cites_total`/`cited_by_total`, strukturierter Fehler)
  statt stillschweigend. Eine einzige Konstante (`MAX_RESULT_COUNT`) ist die Quelle der Wahrheit
  für alle Trefferzahl-Grenzen.
- **Negativ / Aufwand:** `list_topics` ist ein **Breaking Change** (Output-Schema, Sortierreihenfolge
  von aufsteigend `community_id` zu absteigend `size`); ein Aufrufer, der bisher `members` gelesen
  hat, muss künftig `community_id` gezielt nachfragen. Ein zu großes `k`/`n`/`limit` endet jetzt als
  Fehler statt als (großes) Ergebnis – ein Aufrufer mit hartkodiertem `k > 50` muss angepasst
  werden. Der neue `retrieval/topics.py`-Layer ist zusätzlicher Code für ein zuvor triviales
  Werkzeug.
- **Folgeentscheidungen:** Eine Neuvermessung der ≤750/≤1500-Korpus-Ceiling (inkl.
  Local-Search-Latenz bei 3.461 Papern, siehe oben) bleibt offene, separate Folgearbeit –
  umgesetzt in [ADR 0038](0038-corpus-ceiling-revision-local-search-latency.md).
