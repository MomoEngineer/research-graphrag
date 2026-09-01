# 0035 – Volltext-Download (Phase 9 / S2): Lizenz-Whitelist, Inhaltsvalidierung statt reiner Content-Type-Prüfung

- **Status:** Akzeptiert
- **Datum:** 2026-09-01

## Kontext

[ADR 0020](0020-online-candidate-search-phase9.md) hat S1 (Kandidatensuche auf Metadatenebene)
umgesetzt und S2 (Volltext-Download) **bewusst zurückgestellt**: Die geforderte Lizenz-Whitelist
war auf der gemessenen Datenbasis nicht sauber bedienbar – arXiv weist im Atom-Feed **keine**
Lizenz aus, OpenAlex nur bei 15 von 51 gemessenen Treffern (≈ 29 %). Dieser Befund ist am
2026-09-01 erneut geprüft worden (Live-Abfrage von `export.arxiv.org/api/query` für ein reales
Paper) und weiterhin gültig: Der Atom-Feed enthält kein `<rights>`-, `<license>`- oder
`<arxiv:license>`-Element. Die vollständige OpenAlex-Lizenzvokabel wurde ebenfalls neu geprüft
(`help.openalex.org`/`developers.openalex.org`, Feld `primary_location.license`): mögliche Werte
sind u. a. `cc-by`, `cc-by-sa`, `cc-by-nc`, `cc-by-nc-sa`, `cc-by-nc-nd`, `cc-by-nd`,
`public-domain` (OpenAlex' Bezeichnung für CC0), `mit`, `apache-2-0`, `gpl-v2`/`gpl-v3`, `isc`,
`publisher-specific-oa`, `other-oa`.

**Die eigentliche Änderung gegenüber der Roadmap-Vorgabe ist keine neue Messung, sondern eine
Entscheidung** (mit dem Nutzer abgestimmt, 2026-09-01): Statt die Lücke durch eine bessere
Lizenzquelle zu schließen, wird die Anforderung angepasst. Fehlt eine belastbare Lizenz oder ist
sie nicht in der Whitelist, ist das **kein Fehlerfall und kein Grund, die Phase weiter
zurückzustellen**, sondern der reguläre, gewollte Ausgang: Der Kandidat wird mit Identifikator und
Direktlink berichtet, **nicht** geladen – der Mensch prüft und lädt bei Bedarf selbst. Damit
entfällt der ursprüngliche Blocker, ohne dass sich an der Datenlage etwas geändert hätte.

Ein zweiter, bisher nicht dokumentierter Befund kam bei der Vorbereitung dieses ADR hinzu: Der
bestehende `HttpClient`-Port (`transport.py`) begrenzt **jede** Antwort hart auf
`MAX_RESPONSE_BYTES = 5_000_000` (5 MB) – ausreichend für JSON-/Atom-Metadaten, aber zu eng für
Volltext-PDFs. Die größte Datei im aktuellen Korpus (`papers/Towards Understanding Refactoring
Engine Bugs.pdf`) ist bereits 53.374.046 Bytes groß.

Ein dritter Punkt aus der Abstimmung mit dem Nutzer: Eine heruntergeladene Datei muss **immer**
nachweislich ein wissenschaftliches Paper sein – Content-Type und PDF-Signatur allein belegen nur
„es ist ein PDF", nicht „es ist das gemeinte Werk". Es braucht eine Identitätsprüfung gegen die
Kandidaten-Metadaten.

Dieser ADR entscheidet ausschließlich S2. An S0/S1 ([ADR 0020](0020-online-candidate-search-phase9.md))
ändert sich nichts.

## Entscheidung

### 1. Lizenz-Whitelist: genau drei Werte, ausschließlich aus OpenAlex

```python
LICENSE_WHITELIST = frozenset({"public-domain", "cc-by", "cc-by-sa"})
```

Neues Modul `src/research_graphrag/online/download.py`. Geprüft wird ausschließlich
`Candidate.license` (bereits heute aus OpenAlex' `primary_location.license` befüllt,
`sources.py`). arXiv liefert nie eine Lizenz – ein arXiv-only-Kandidat besteht die Whitelist damit
grundsätzlich nicht, es sei denn, `merge_candidates` hat ihn mit einem OpenAlex-Treffer
zusammengeführt, der ein Lizenzfeld mitbringt (`_combine`: `license=first.license or
second.license`, bereits vorhanden – **kein** neuer Mechanismus). Alles außerhalb der drei Werte
(`cc-by-nc*`, `cc-by-nd`, `publisher-specific-oa`, leer, unbekannt …) gilt als „nicht
whitelisted" und wird nicht geladen.

### 2. Transport-Port: optionaler `max_bytes`-Parameter, rückwärtskompatibel

```python
class HttpClient(Protocol):
    def get(self, url: str, *, accept: str = "*/*", max_bytes: int = MAX_RESPONSE_BYTES) -> HttpResponse: ...
```

`ProxyHttpClient._read_limited` bekommt denselben Parameter statt der Konstante. Bestehende
Aufrufer (S1, Referenz-Auflösung, Metadaten-Auflösung) sind unverändert, weil der Default gleich
bleibt. Der Download-Pfad ruft mit einer eigenen, größeren Grenze auf:

```python
MAX_DOWNLOAD_BYTES = 104_857_600  # 100 MiB
```

Herleitung: größte Datei im Korpus (53.374.046 Bytes) × 2, gerundet auf 100 MiB – großzügig genug
für praktisch jedes wissenschaftliche Paper inkl. Supplementary Material, ohne dass ein einzelner
Download unbegrenzt Speicher binden kann.

### 3. Ablauf je Kandidat (nur mit `--download`, nur für `report.fresh`)

Reihenfolge so gewählt, dass aussichtslose Fälle **vor** dem Netzzugriff aussortiert werden (kein
Kontingent-Verbrauch für ohnehin verworfene Kandidaten):

1. **Lizenz-Check zuerst, ohne Netz.** Kein Lizenzwert oder nicht in `LICENSE_WHITELIST` →
   Outcome `no_license` bzw. `license_not_whitelisted` (der tatsächliche Wert steht im Grund,
   damit nachvollziehbar bleibt, warum). Kein GET.
2. **URL vorhanden und `http(s)`?** Sonst Outcome `no_url`.
3. **Ein GET** über denselben injizierten `HttpClient`, `max_bytes=MAX_DOWNLOAD_BYTES`,
   `accept="application/pdf"`. Statuscode ≠ 200 oder Netzfehler → Outcome `http_error` (Status im
   Grund).
4. **Signatur vor dem Header:** Rumpf muss mit `PDF_MAGIC = b"%PDF-"` beginnen (wiederverwendet
   aus `intake.py`) – der `Content-Type`-Header ist nur ein Zusatzsignal, weil manche Server
   `application/octet-stream` liefern. Keine Signatur → Outcome `not_a_pdf`.
5. **Inhaltsprüfung (die eigentliche „ist das ein wissenschaftliches Paper"-Prüfung):**
   - `pypdf.PdfReader`, mindestens 2 Seiten (`len(reader.pages) >= 2`) – ein einzelnes
     Abstract-Blatt ist kein Volltext. Sonst Outcome `too_short`.
   - `read_front_pages(raw)` aus `intake.py` liest die normalisierten ersten Seiten (**ohne**
     Volltext-Fallback – bewusst dieselbe, bereits gehärtete Funktion).
   - Titelkandidaten aus den Front-Pages bilden (`intake._title_candidates` wird dafür **öffentlich
     gemacht** – Umbenennung zu `title_candidates`, keine Verhaltensänderung) und gegen den
     Kandidaten-Titel prüfen: `best_title_match(guesses, {normalize_title(candidate.title):
     candidate.title})`, dieselbe Schwelle `TITLE_SIMILARITY = 0.85` wie beim Intake. Das ist
     **derselbe** Titel-Match-Mechanismus, nur mit vertauschten Rollen (viele Titelkandidaten aus
     dem PDF gegen **einen** bekannten Titel statt gegen viele Korpus-Titel). Kein Treffer →
     Outcome `title_mismatch`.
   - Bewusst **keine** volle `extract_pdf`-Kanonisierung (Chunking, Qualitäts-Gates): Das leistet
     der Intake ohnehin erneut, sobald die Datei aus `new_papers/` übernommen wird – ein zweiter
     voller Durchlauf wäre doppelte Arbeit ohne Gegenwert.
6. **Schreiben, wenn alles besteht.** Eigener Dateiname nach demselben Muster wie
   `references.stub_filename` (Titel-Slug über Whitelist-Zeichen + Identifikator, Kurz-Hash bei
   Überlänge) – neue, aber strukturgleiche Funktion `pdf_filename` in `download.py`, Präfix
   `online-` zur Unterscheidung von von Hand abgelegten PDFs, Endung `.pdf`. Atomar geschrieben
   (`.tmp` + `os.replace`, wie überall im Paket) nach `new_papers/`. Outcome `downloaded` mit Pfad.

### 4. Ein Request pro Datei, kein Bulk, Rate-Limit

`DOWNLOAD_DELAY_SECONDS = 1.0` zwischen aufeinanderfolgenden **Downloads** (nicht zwischen den
bestehenden Metadaten-Anfragen). Timeout und User-Agent unverändert aus `transport.py`. Kein
HEAD-Request zur Vorprüfung – ein zweiter Request pro Kandidat widerspräche „ein Request pro
Datei"; die Prüfung läuft nach dem einzigen GET, vor dem Schreiben.

### 5. `--download` erweitert `scripts.discover`, nie Standard

Ablauf im selben Lauf: Suche → Dedup/Aktualitätsfilter (wie bisher, unverändert) → **nur mit
`--download`** → Download-Versuch je frischem Kandidaten → ein gemeinsamer Bericht. Ohne das Flag
ändert sich am bestehenden Verhalten und Berichtsformat **nichts**.

### 6. Bericht zeigt den Download-Status, Identifikator und Link bleiben immer sichtbar

`DiscoveryReport` bekommt ein neues Feld `downloads: tuple[DownloadOutcome, ...] = ()` (leer, wenn
`--download` nicht gesetzt war). `_render_candidate` zeigt zusätzlich eine Zeile „Download:
\<Status\> – \<Grund\>", sobald ein Outcome vorliegt – Identifikator und Link stehen **davon
unabhängig** immer im Bericht, genau wie vom Nutzer gefordert.

### 7. Kein zweiter Weg in den Korpus, kein MCP-Werkzeug

Ziel bleibt ausschließlich `new_papers/`; die Übernahme bleibt Aufgabe des Intake (Phase 8)
mitsamt seinem Robustheits-Gate, das defekte oder textlose Dateien **zusätzlich und unabhängig**
von der hiesigen Inhaltsprüfung abfängt. `--download` bleibt Teil von `scripts.discover`, wird
**nicht** als MCP-Werkzeug registriert – dieselbe Begründung wie in ADR 0020 §7 (Netzverkehr und
Schreibzugriff gehören nicht in Agent-Reichweite).

## Alternativen

| Verworfen | Grund |
| --- | --- |
| Vorab eine S2.0-Messung (wie S0/E0/G0) | **Bewusste Nutzerentscheidung:** Das Verhalten bei fehlender/nicht gelisteter Lizenz ist bereits vollständig spezifiziert (Link statt Download). Eine Messung würde nur die ohnehin bekannte, geringe arXiv-/OpenAlex-Abdeckung erneut bestätigen, ohne die Entscheidung zu ändern. |
| Content-Type-Prüfung als alleiniger Nachweis „wissenschaftliches Paper" | Belegt nur „ist ein PDF", nicht „ist das gemeinte Werk"; ersetzt durch den Titel-Rückvergleich mit der bestehenden Intake-Logik. |
| Volle Canonical-Extraktion (`extract_pdf`) als Vorab-Check | Doppelte Arbeit – der Intake extrahiert das Paper ohnehin regulär, sobald es aus `new_papers/` übernommen wird. Ein schlanker, nur auf `read_front_pages` gestützter Check genügt für die Identitätsprüfung. |
| `MAX_RESPONSE_BYTES` unverändert lassen, PDFs separat unbegrenzt lesen | Ein unbegrenzter Lesevorgang wäre eine Ressourcen-Schwachstelle; stattdessen ein expliziter, optionaler Parameter am bestehenden Port. |
| Eigener, neuer Titel-Match-Mechanismus für den Download-Pfad | Zweite Wahrheit über „ist das dasselbe Werk" – exakt die Fehlerquelle, die [ADR 0019](0019-corpus-intake-new-papers-phase8.md) und [ADR 0020](0020-online-candidate-search-phase9.md) bereits vermeiden. |
| HEAD-Request vor dem GET zur Content-Type-Vorprüfung | Ein zweiter Request pro Kandidat widerspricht „ein Request pro Datei, kein Bulk-Crawl". |
| Whitelist um weitere Lizenzen erweitern (z. B. `cc-by-nc`) | Nicht Gegenstand dieses ADR – die Roadmap nennt ausdrücklich CC0/CC-BY/CC-BY-SA; eine Erweiterung bräuchte einen eigenen, begründeten Anlauf. |

## Konsequenzen

- **Positiv:** S2 wird umsetzbar, ohne dass die Lizenzlücke ein Blocker bleibt – die Anforderung
  ist an die real messbare Datenlage angepasst, nicht umgekehrt an sie herangemessen. Der Bericht
  bleibt in jedem Fall (mit oder ohne `--download`) die vollständige, manuell nutzbare Fundgrube:
  Identifikator und Link erscheinen unabhängig vom Lizenz- oder Download-Ergebnis. Die
  Inhaltsprüfung verhindert, dass ein falsch zugeordnetes PDF in `new_papers/` landet, ohne die
  Robustheits-Gate-Logik des Intake zu duplizieren – rund die Hälfte der Mechanik ist
  Wiederverwendung (`read_front_pages`, `title_candidates`, `best_title_match`,
  `TITLE_SIMILARITY`, `PDF_MAGIC` aus `intake.py`; `title_slug`-Muster aus `references.py`).
- **Negativ / Aufwand:** Auto-Download bleibt selten (nur OpenAlex-Treffer mit
  `public-domain`/`cc-by`/`cc-by-sa` **und** bestandener Titelprüfung) – das ist gewollt (Präzision
  vor Recall), aber im Betrieb sichtbar: Die meisten Treffer bleiben Links, genau wie vom Nutzer
  verlangt. Der zusätzliche `max_bytes`-Parameter am `HttpClient`-Port berührt (rückwärtskompatibel)
  alle bestehenden Aufrufer der Datei. Antworten bis 100 MiB werden vollständig in den Speicher
  gelesen statt gestreamt – für ein Einzelbenutzer-Werkzeug mit einem Request pro Datei akzeptiert,
  wie schon bei den bisherigen (kleineren) Antworten.
- **Bewusst getragene Grenze:** Die Titelprüfung schützt vor einer falschen Zuordnung, nicht vor
  einem inhaltlich fehlerhaften, aber korrekt zugeordneten PDF (z. B. einer beschädigten Datei mit
  zufällig passendem Titel-Text) – dafür bleibt das Robustheits-Gate des Intake zuständig, das
  ohnehin jede übernommene Datei prüft.
- **Coverage unverändert außerhalb der Norm:** `download.py` (94,2 %) und `report.py` (95,6 %)
  liegen über dem Richtwert; `transport.py` bleibt bei 69,6 % unterhalb – **unverändert**
  gegenüber dem in [ADR 0020](0020-online-candidate-search-phase9.md) begründeten Zustand
  (Windows-gebundener Proxy-/Socket-Pfad, offline nicht testbar). Der neue `max_bytes`-Parameter
  fügt dem Modul keine zusätzlich ungetestete Verzweigung hinzu.
- **Folgeentscheidungen:** keine bekannt. Eine spätere Erweiterung der Whitelist oder ein
  zusätzlicher Lizenzabgleich über eine weitere Quelle (z. B. Unpaywall) bräuchte einen eigenen,
  erneut gemessenen Anlauf – nicht Teil dieses ADR.
