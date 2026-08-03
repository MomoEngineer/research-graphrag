# Anleitung: Online-Recherche

Diese Seite beschreibt **Schritt für Schritt**, wie der Online-Modus benutzt wird: von der
Einrichtung über den ersten Lauf bis zu der Frage, wie aus einem Vorschlag ein Paper im Korpus
wird.

> **Abgrenzung.** *Warum* der Modus so gebaut ist, steht in
> [ADR 0020](adr/0020-online-candidate-search-phase9.md); *wie* er intern arbeitet, in den
> [Modul-Dokus](../src/research_graphrag/online/doc/search.md); der konzeptionelle Ablauf in
> [funktionsweise.md](funktionsweise.md). Hier geht es ausschließlich um die **Bedienung**.

---

## 1. Was der Modus tut – und was nicht

| Er tut | Er tut **nicht** |
| --- | --- |
| Bei arXiv und OpenAlex nach Literatur suchen | PDFs herunterladen |
| Die Anfrage aus dem **eigenen Korpus** ableiten | Frei im Web suchen |
| Treffer gegen den Korpus abgleichen | Etwas in den Korpus schreiben |
| Vorschläge in einen Bericht schreiben | Von selbst laufen oder von Copilot aufgerufen werden |

Der Modus wird **immer von Hand gestartet**. Er ist bewusst kein MCP-Werkzeug – Netzverkehr soll
eine beobachtete Handlung bleiben.

---

## 2. Einrichtung (einmalig)

### 2.1 Ohne Proxy

Besteht direkter Internetzugang, ist **nichts** einzurichten. Weiter bei Abschnitt 3.

### 2.2 Mit Unternehmens-Proxy

Der Proxy-Endpunkt wird über die Umgebungsvariable `RESEARCH_GRAPHRAG_PROXY` bekannt gemacht –
er steht bewusst nirgends im Repository. So ermittelst du ihn unter Windows:

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
| `--proxy host:port` | Überschreibt `RESEARCH_GRAPHRAG_PROXY` für diesen Lauf | – |
| `--ohne-rohdaten` | Legt die Rohantworten nicht ab | Rohantworten werden abgelegt |
| `--index` / `--data` | Abweichende Pfade | `data/index/index.sqlite`, `data/` |

**Zwei praktische Hinweise:**

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

Der Modus lädt **nichts** herunter. Der vollständige Weg:

1. **Vorschlag prüfen.** Abstract im Bericht lesen; bei Bedarf dem Volltext-Link folgen.
2. **PDF selbst laden.** Die Lizenz beachten – der Bericht weist sie aus, wenn die Quelle sie
   nennt. Bei arXiv steht sie nicht im Feed; sie ist auf der Abstract-Seite des Papers vermerkt.
3. **Datei nach `new_papers/` legen.**
4. **Erst trocken prüfen:** `python -m scripts.intake --dry-run`
5. **Übernehmen:** `python -m scripts.intake`

Damit greift die reguläre Duplikatprüfung des Korpus-Zuflusses – sie ist die eigentliche
Absicherung gegen Doppelbestand und prüft bitgenau. Die Prüfung im Online-Modus erspart dir nur
das Herunterladen von Bekanntem.

> **Wenn ein Paper doch doppelt vorgeschlagen wird:** Ein Korpus-Paper mit sehr kurzem Titel und
> ohne Identifikator kann der Online-Prüfung entgehen. Der Intake fängt es beim Übernehmen
> zuverlässig ab.

---

## 7. Wenn etwas nicht funktioniert

| Meldung | Ursache | Lösung |
| --- | --- | --- |
| `Bitte mindestens --community oder --seed angeben.` | Kein Anfrageweg gewählt | Abschnitt 3 |
| `[dependency_error] Keine direkte Verbindung zu … Falls ein Proxy nötig ist …` | Kein Netz oder Proxy nicht gesetzt | `RESEARCH_GRAPHRAG_PROXY` setzen (Abschnitt 2.2) |
| `[dependency_error] Proxy … nicht erreichbar` | Falscher Endpunkt oder Tippfehler | Endpunkt erneut aus der PAC-Datei ermitteln |
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
