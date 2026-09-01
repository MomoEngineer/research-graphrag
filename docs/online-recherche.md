# Anleitung: Online-Recherche

Diese Seite beschreibt **Schritt für Schritt**, wie der Online-Modus benutzt wird: von der
Einrichtung über den ersten Lauf bis zu der Frage, wie aus einem Vorschlag ein Paper im Korpus
wird.

> **Abgrenzung.** *Warum* der Modus so gebaut ist, steht in
> [ADR 0020](adr/0020-online-candidate-search-phase9.md) (Kandidatensuche) und
> [ADR 0035](adr/0035-fulltext-download-phase9-s2.md) (Volltext-Download); *wie* er intern
> arbeitet, in den [Modul-Dokus](../src/research_graphrag/online/doc/search.md). Hier geht es
> ausschließlich um die **Bedienung**. Die Abschnitte 1–8 beschreiben die **Kandidatensuche**
> samt dem opt-in Download (Abschnitt 6); der zweite Online-Lauf für Paper ohne Volltext steht in
> [Abschnitt 9](#9-der-zweite-online-lauf-paper-ohne-volltext).

---

## 1. Was der Modus tut – und was nicht

| Er tut | Er tut **nicht** |
| --- | --- |
| Bei arXiv und OpenAlex nach Literatur suchen | Ohne `--download` PDFs herunterladen |
| Die Anfrage aus dem **eigenen Korpus** ableiten | Frei im Web suchen |
| Treffer gegen den Korpus abgleichen | Etwas **in den Korpus** schreiben (auch mit `--download` nicht – nur nach `new_papers/`) |
| Vorschläge in einen Bericht schreiben | Von selbst laufen oder von Copilot aufgerufen werden |
| Mit `--download` frei lizenzierte Volltexte laden (opt-in, s. Abschnitt 6) | Bezahlschranken umgehen oder ohne Lizenznachweis laden |

Der Modus wird **immer von Hand gestartet**. Er ist bewusst kein MCP-Werkzeug – Netzverkehr soll
eine beobachtete Handlung bleiben.

---

## 2. Einrichtung (einmalig)

### 2.1 Im Regelfall: nichts einzurichten

Der Endpunkt wird in zwei Stufen bestimmt
([ADR 0032](adr/0032-system-proxy-autodetection.md)):

1. die ausdrückliche Angabe – `RESEARCH_GRAPHRAG_PROXY` oder `--proxy`,
2. andernfalls die **Windows-Systemkonfiguration**, einschließlich einer hinterlegten
   **PAC-Datei**.

Damit gilt: Wer über den Browser ins Netz kommt, kommt auch mit diesem Werkzeug ins Netz – ohne
Vorbereitung. Besteht direkter Internetzugang, ist ohnehin nichts einzurichten. Weiter bei
Abschnitt 3.

Was Windows für ein Ziel meldet, lässt sich jederzeit nachsehen:

```powershell
.\.venv\Scripts\python.exe -c "from research_graphrag.online.systemproxy import detect_system_proxy as d; print(d('https://api.openalex.org/'))"
```

### 2.2 Endpunkt ausdrücklich vorgeben

Nötig nur, wenn die Ermittlung nichts findet (Ausgabe `None`) oder ein **anderer** Endpunkt
genutzt werden soll. Der Endpunkt steht bewusst nirgends im Repository. So ermittelst du ihn
unter Windows von Hand:

```powershell
# 1. Ist eine automatische Proxy-Konfiguration (PAC) hinterlegt?
(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings').AutoConfigURL
```

Liefert das eine URL, lies die PAC-Datei aus und suche die Proxy-Einträge:

```powershell
# 2. PAC-Datei laden und die genannten Proxy-Endpunkte anzeigen
$pac = (Invoke-WebRequest -Uri '<AutoConfigURL aus Schritt 1>' -UseBasicParsing).Content
[regex]::Matches($pac, 'PROXY\s+([A-Za-z0-9_.\-]+:\d+)') |
    ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique
```

Wähle einen der ausgegebenen Endpunkte und setze ihn für die aktuelle Sitzung:

```powershell
$env:RESEARCH_GRAPHRAG_PROXY = "<host>:<port>"
```

Dauerhaft (gilt für neue Terminals):

```powershell
[Environment]::SetEnvironmentVariable("RESEARCH_GRAPHRAG_PROXY", "<host>:<port>", "User")
```

> **Zur Anmeldung:** Verlangt der Proxy eine Authentifizierung (`Negotiate`/`NTLM`), wird sie aus
> deiner bestehenden Windows-Anmeldung erzeugt. Es wird **kein Passwort abgefragt** und keines
> gespeichert.

---

## 3. Eine Anfrage wählen

Der Modus sucht nicht frei, sondern ausgehend von deinem Bestand. Es gibt zwei Wege.

### 3.1 Über eine Community („mehr zu diesem Themencluster")

Verschaffe dir zuerst einen Überblick über die Themencluster deines Korpus:

```powershell
python -m scripts.graph_info
```

Die Ausgabe nennt je Community eine Nummer, die Zahl der Paper und die Keywords. Wähle die
Nummer, deren Keywords zu deinem Interesse passen:

```powershell
python -m scripts.discover --community 2
```

### 3.2 Über ein Seed-Paper („mehr wie dieses")

Kennst du ein Paper, an dem du weiterarbeiten willst, brauchst du dessen `paper_id`. Sie steht in
der Provenienz jeder Antwort (`python -m scripts.ask …`) und in der Community-Übersicht
(Zeile „Vertreter"):

```powershell
python -m scripts.discover --seed 6a1ccc0a1fb6841b
```

Die Suchbegriffe entstehen dabei aus dem **Titel** des Papers.

### 3.3 Beides kombinieren

Beide Optionen sind mehrfach angebbar und lassen sich mischen – alle Anfragen laufen dann in
**einem** Bericht zusammen:

```powershell
python -m scripts.discover --community 2 --community 9 --seed 6a1ccc0a1fb6841b
```

---

## 4. Den Lauf steuern

| Option | Wirkung | Standard |
| --- | --- | --- |
| `--seit JAHR` | Frühestes Erscheinungsjahr | die letzten fünf Jahre |
| `--limit N` | Treffer je Quelle **und** Anfrage | 10 |
| `--begriffe N` | Wie viele Suchbegriffe aus Keywords bzw. Titel übernommen werden | 3 |
| `--dry-run` | Zeigt nur die gebildeten Anfragen – **ohne** Abfrage und **ohne** Bericht | Lauf wird ausgeführt |
| `--proxy host:port` | Überschreibt `RESEARCH_GRAPHRAG_PROXY` für diesen Lauf | – |
| `--ohne-rohdaten` | Legt die Rohantworten nicht ab | Rohantworten werden abgelegt |
| `--download` | Lädt frei lizenzierte Volltexte automatisch nach `new_papers/` (Abschnitt 6) | aus – nur Bericht |
| `--eingang` | Zielordner für `--download` | `new_papers/` |
| `--index` / `--data` | Abweichende Pfade | `data/index/index.sqlite`, `data/` |

**Drei praktische Hinweise:**

- **Erst schauen, dann suchen.** `--dry-run` zeigt, welche Suchbegriffe aus der Community bzw.
  dem Seed-Paper entstehen. Das lohnt sich, weil jeder echte Lauf Kontingent verbraucht und den
  Bericht verlängert – und weil sich die Nummer einer Community nach einem `intake`-Lauf auf ein
  anderes Thema beziehen kann.
- **Weniger Begriffe = mehr Treffer.** Die Suchbegriffe werden bei arXiv UND-verknüpft. Kommt
  wenig zurück, hilft `--begriffe 2`.
- **Ältere Literatur suchen:** `--seit 2015`. Ohne diese Angabe werden ältere Treffer verworfen
  und in der Bilanz als „vor \<Jahr\>" gezählt.

---

## 5. Das Ergebnis lesen

Die Konsolenausgabe endet mit einer Bilanz dieser Form:

```
[discover] 14 Treffer · 7 bereits im Korpus · 0 vor 2024 · 7 neu
```

| Angabe | Bedeutung |
| --- | --- |
| **Treffer** | Ergebnisse beider Quellen, nach Zusammenführung von Dubletten |
| **bereits im Korpus** | Von der Duplikatprüfung erkannt – erscheinen **mit Beleg** im Bericht, nicht als Vorschlag |
| **vor \<Jahr\>** | Durch den Aktualitätsfilter verworfen |
| **neu** | Die eigentlichen Vorschläge |

Ausführlich steht alles in [`data/online_candidates.md`](../data/README.md). Die Datei wächst
**append-only**: Jeder Lauf hängt einen Abschnitt an, nichts wird überschrieben. Je Vorschlag
findest du Identifikator, Jahr, Quellen, Lizenz, Volltext-Link, den Abstract-Auszug und die Zeile
„Vorgeschlagen wegen" – sie sagt, aus welcher Anfrage der Treffer stammt.

> **Warum die bereits bekannten Paper aufgeführt werden:** Nur so lässt sich nachprüfen, dass die
> Duplikatprüfung richtig entschieden hat. Jeder Eintrag nennt seinen Beleg (Identifikator oder
> Titelähnlichkeit).

---

## 6. Vom Vorschlag zum Paper im Korpus

Standardmäßig lädt der Modus **nichts** herunter. Mit `--download` versucht er es zusätzlich,
aber nur für Kandidaten mit einer Lizenz aus der Whitelist – alles andere bleibt ein Link
([ADR 0035](adr/0035-fulltext-download-phase9-s2.md)).

### 6.1 Automatisch (`--download`)

```powershell
python -m scripts.discover --community 2 --download
```

Geladen wird **nur**, wenn beides zutrifft:

1. **Lizenz aus der Whitelist** – `public-domain` (CC0), `cc-by` oder `cc-by-sa`, ausschließlich
   aus OpenAlex. arXiv weist im Feed **nie** eine Lizenz aus (siehe S0-Befund); ein arXiv-Treffer
   besteht die Whitelist deshalb nur, wenn OpenAlex denselben Kandidaten mit einer Lizenz
   beigesteuert hat.
2. **Inhalt passt zum Kandidaten** – mindestens zwei Seiten, und der Titel im PDF stimmt mit dem
   berichteten Titel überein. Ein falsch verlinktes PDF oder eine Landing-Page wird dadurch
   verworfen statt übernommen.

Jeder Kandidat trägt im Bericht anschließend eine Download-Zeile, z. B. „Download: geladen —
2345678 Bytes“ oder „Download: nicht geladen (Lizenz nicht in der Whitelist) — Lizenz
'cc-by-nc' nicht in der Whitelist“ – auch im Fehlschlag bleiben Identifikator und Link stehen,
damit der manuelle Weg (6.2) jederzeit offensteht. Geladene Dateien landen unter `--eingang`
(Standard: `new_papers/`), benannt nach dem Muster `online-<titelwort>-<identifikator>.pdf`.

### 6.2 Manuell (immer möglich, auch ohne `--download`)

1. **Vorschlag prüfen.** Abstract im Bericht lesen; bei Bedarf dem Volltext-Link folgen.
2. **PDF selbst laden.** Die Lizenz beachten – der Bericht weist sie aus, wenn die Quelle sie
   nennt. Bei arXiv steht sie nicht im Feed; sie ist auf der Abstract-Seite des Papers vermerkt.
3. **Datei nach `new_papers/` legen.**
4. **Erst trocken prüfen:** `python -m scripts.intake --dry-run`
5. **Übernehmen:** `python -m scripts.intake`

### 6.3 Gemeinsame Absicherung

Ob automatisch oder von Hand: Der Weg **in den Korpus** führt immer über `new_papers/` und den
Intake. Damit greift die reguläre Duplikatprüfung des Korpus-Zuflusses – sie ist die eigentliche
Absicherung gegen Doppelbestand und prüft bitgenau. Die Prüfung im Online-Modus erspart dir nur
das Herunterladen von Bekanntem, und die Inhaltsprüfung aus 6.1 nur das versehentliche Ablegen
eines falsch zugeordneten PDFs.

> **Wenn ein Paper doch doppelt vorgeschlagen wird:** Ein Korpus-Paper mit sehr kurzem Titel und
> ohne Identifikator kann der Online-Prüfung entgehen. Der Intake fängt es beim Übernehmen
> zuverlässig ab.

---

## 7. Wenn etwas nicht funktioniert

| Meldung | Ursache | Lösung |
| --- | --- | --- |
| `Bitte mindestens --community oder --seed angeben.` | Kein Anfrageweg gewählt | Abschnitt 3 |
| `[dependency_error] Keine direkte Verbindung zu …; die Windows-Proxy-Konfiguration nennt für dieses Ziel keinen Endpunkt` | Kein Netz, oder Windows kennt keinen zuständigen Proxy | Endpunkt von Hand setzen (Abschnitt 2.2) |
| `[dependency_error] Keine direkte Verbindung zu … Falls ein Proxy nötig ist …` | Ein gesetzter Endpunkt fehlt und die Ermittlung war abgeschaltet | `RESEARCH_GRAPHRAG_PROXY` setzen (Abschnitt 2.2) |
| `[dependency_error] Proxy … nicht erreichbar` | Falscher Endpunkt oder Tippfehler | Gesetzte Variable entfernen (dann greift die Ermittlung) oder Endpunkt erneut aus der PAC-Datei ermitteln |
| `[dependency_error] Proxy lehnt die Verbindung ab: … 407 …` | Anmeldung am Proxy gescheitert | Windows-Anmeldung prüfen (Sperrbildschirm, abgelaufenes Kerberos-Ticket) |
| `[dependency_error] … benötigt pywin32 (nur unter Windows verfügbar)` | Proxy-Anmeldung außerhalb von Windows | Ohne Proxy betreiben (Variable nicht setzen) |
| `[invalid_input] Proxy-Angabe muss die Form 'host:port' haben` | Schreibfehler, z. B. `http://` davor | Nur `host:port` angeben, ohne Schema |
| `[not_found] Community … ist im Index nicht vorhanden` | Nummer existiert nicht | `python -m scripts.graph_info` |
| `[not_found]` bei `--seed` | Unbekannte `paper_id` | ID aus `scripts.ask` oder `scripts.graph_info` übernehmen |
| `OpenAlex antwortete mit HTTP 429` | Tageskontingent erschöpft | Später erneut versuchen; arXiv liefert weiterhin |
| Wenige oder keine Treffer | Suchbegriffe zu eng verknüpft | `--begriffe 2`, `--seit` weiter fassen oder `--limit` erhöhen |

Der Lauf endet in **jedem** Fehlerfall mit einer benannten Kategorie und Rückgabewert 1 – ohne
Stacktrace und ohne halben Zustand. Fällt nur **eine** Quelle aus, läuft der Rest weiter; der
Status jeder Quelle steht im Bericht.

---

## 8. Betriebshinweise

- **Kontingent im Blick behalten.** OpenAlex weist ein Tageskontingent aus; der Lauf meldet den
  Rest als Hinweiszeile. Jede Anfrage kostet Kontingent, unabhängig von `--limit`.
- **Sparsam abfragen.** Der Modus stellt je Anfrage genau eine Abfrage pro Quelle. Wiederhole
  Läufe nicht ohne Grund – die Ergebnisse ändern sich von Tag zu Tag kaum.
- **Rohantworten aufräumen.** `data/online_raw/` wächst mit jedem Lauf. Die Ablage dient dazu,
  einen Befund später nachvollziehen zu können; alte Verzeichnisse können gelöscht werden.
- **Der Bericht wird nie aufgeräumt.** `data/online_candidates.md` ist append-only. Wenn er
  unübersichtlich wird, archiviere ihn von Hand – das Werkzeug löscht dort nichts.
- **Nichts davon ist versioniert.** `data/` steht in `.gitignore`; Bericht und Rohantworten sind
  lokale Arbeitsstände.

---

## 9. Der zweite Online-Lauf: Paper ohne Volltext

Dieselbe Einrichtung (Abschnitt 2) gilt für einen zweiten, ebenfalls separat startbaren Lauf.
Er richtet sich an Paper, deren Volltext gar nicht beschaffbar ist – nur der Abstract:

```powershell
python -m scripts.resolve_references --dry-run   # zeigt die geplanten Abfragen, verändert nichts
python -m scripts.resolve_references
```

Gelesen wird die kuratierte Liste `new_papers/referenzen.txt` (eine DOI oder arXiv-ID je Zeile),
geschrieben wird je Kennung **eine** Stub-Datei `*.refjson` im Eingangsordner. Welche
Schreibweisen die Liste versteht und was beim manuellen Nachtragen eines Abstracts zu tun ist,
steht in [`new_papers/README.md`](../new_papers/README.md); *warum* der Lauf so gebaut ist, in
[ADR 0029](adr/0029-reference-stub-resolution-phase13.md).

Drei Unterschiede zur Kandidatensuche sind wichtig:

| Kandidatensuche (`discover`) | Referenz-Einträge (`resolve_references`) |
| --- | --- |
| Anfrage aus dem eigenen Bestand, Ergebnis offen | Anfrage ist eine **konkrete Kennung**, die du gewählt hast |
| Schreibt nur einen **Bericht** | Schreibt **Dateien** in den Eingangsordner |
| Jeder Lauf fragt erneut | Ein zweiter Lauf fragt **nichts** erneut ab (Prüfung gegen Korpus, Eingang und Quarantäne) |

> **Noch wirkungslos:** Bis Phase 13 / R2 liest `python -m scripts.intake` ausschließlich
> `*.pdf` – die erzeugten Stub-Dateien bleiben bis dahin im Eingang liegen.

Das Protokoll dieses Laufs ist `data/references_log.md` (append-only). Anders als der Bericht der
Kandidatensuche ist die **Eingabeliste** versioniert und Teil des Sicherungsumfangs
([ADR 0027](adr/0027-corpus-backup-phase11.md)).
