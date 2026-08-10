# `new_papers/` – Eingangsordner für den Korpus-Zufluss

Dieser Ordner ist der **Eingang** des Korpus (Roadmap-Phase 8). Neue PDFs werden hier abgelegt und
mit **einem** Befehl übernommen:

```powershell
python -m scripts.intake --dry-run   # zeigt jede geplante Aktion, verändert nichts
python -m scripts.intake
```

Der Intake prüft in drei Stufen mit fallender Sicherheit und handelt entsprechend
([ADR 0019](../docs/adr/0019-corpus-intake-new-papers-phase8.md)):

| Stufe | Kriterium | Konsequenz |
| --- | --- | --- |
| 1 | **sha256** identisch zu einem Paper im Korpus | Datei wird **gelöscht** (byte-identische Kopie existiert nachweislich) |
| 2 | **DOI/arXiv** identisch zu einem gehärteten Korpus-Schlüssel | Datei wandert nach `_duplikate/` (umkehrbar) |
| 3 | **Titel-Ähnlichkeit** ≥ 0,85 | Datei **bleibt liegen**, Befund im Bericht |
| – | kein Treffer | Datei wandert nach `papers/`, Index und Übersicht werden nachgezogen |

> **Achtung:** Stufe 1 löscht **unwiderruflich**. Vor dem ersten Lauf immer `--dry-run` nutzen.
> Eine **neuere Version** eines vorhandenen Papers gilt als Duplikat (gleiche Identifikator-Wurzel)
> und landet in `_duplikate/` – wer ersetzen will, löscht zuerst die alte Datei in `papers/`.

---

## Referenz-Einträge ohne Volltext (`referenzen.txt`)

Ein Paper, von dem nur der Abstract öffentlich ist, kommt über seine **DOI oder arXiv-ID** in den
Eingang. Die kuratierte Liste dafür ist `referenzen.txt` – eine Kennung je Zeile:

```powershell
python -m scripts.resolve_references --dry-run   # zeigt die geplanten Abfragen, verändert nichts
python -m scripts.resolve_references
```

Der Lauf legt je Kennung **eine** Stub-Datei `ref-<wort>-<kennung>.refjson` ab: Titel, Autoren,
Jahr, Venue, Identifikatoren und – der eigentliche Zweck – den **Abstract**
([ADR 0029](../docs/adr/0029-reference-stub-resolution-phase13.md)).

### Welche Schreibweisen die Liste versteht

`#` leitet einen Kommentar ein – auch **hinter** einer Kennung, damit notiert werden kann, warum
ein Eintrag dort steht. Leerzeilen werden übergangen, eine nicht deutbare Zeile ist ein Befund im
Protokoll und **kein** Abbruch. Erkannt werden:

| Art | Beispiele |
| --- | --- |
| DOI | `10.1145/3696410.3714748` · `doi:10.1145/…` · `https://doi.org/10.1145/…` |
| arXiv (neu) | `2404.16130` · `arXiv:2404.16130` · `arXiv:2404.16130v3` |
| arXiv (alt) | `cs/0501001` · `arXiv:cs/0501001v1` |
| arXiv als Link | `https://arxiv.org/abs/2404.16130` · `https://arxiv.org/pdf/2404.16130v2` |
| arXiv als DataCite-DOI | `10.48550/arXiv.2404.16130` (wird zu `2404.16130` normalisiert) |

```text
# Paper hinter einer Bezahlschranke – von mehreren Korpus-Papern zitiert
10.1145/3696410.3714748   # Grundlagenarbeit zu Community-Reports
arXiv:2404.16130
```

### Was man dazu wissen muss

- **Ein zweiter Lauf ist folgenlos.** Vor jeder Abfrage wird gegen drei Zustände geprüft: den
  Korpus, die bereits erzeugten Stub-Dateien hier und die Quarantäne `_duplikate/`. Erledigte
  Einträge dürfen in der Liste stehen bleiben – sie ist ein kuratiertes Dokument, kein
  Arbeitsvorrat. Der Lauf verändert sie **nie**.
- **Ohne Abstract entsteht die Datei trotzdem** – mit leerem `abstract`-Feld und einem Hinweis im
  Protokoll. Der Abstract wird dann von Hand **in diese Datei** kopiert (letztes Feld), bevor der
  Intake läuft.
- **Ohne Titel entsteht keine Datei.** Eine kaputte oder unbekannte Kennung wird als Befund
  gemeldet, statt einen wertlosen Eintrag zu erzeugen.
- **Netz nötig.** Führt der Weg nach außen über einen Proxy, wird er aus der
  Windows-Konfiguration ermittelt – auch aus einer PAC-Datei
  ([ADR 0032](../docs/adr/0032-system-proxy-autodetection.md)); `RESEARCH_GRAPHRAG_PROXY=host:port`
  oder `--proxy` überschreiben das (siehe
  [docs/online-recherche.md](../docs/online-recherche.md)). Ohne Netz endet der Lauf mit
  `dependency_error` – ohne Stacktrace und ohne halbe Datei.
- **Der Intake übernimmt sie regulär.** `python -m scripts.intake` liest neben `*.pdf` auch
  `*.refjson`, prüft dieselben drei Stufen und benennt die Datei beim Übernehmen nach ihrem
  **Titel** ([ADR 0030](../docs/adr/0030-reference-entries-in-corpus-phase13.md)). Taucht später
  das echte PDF auf, wird es übernommen und der Referenz-Eintrag abgelöst – **Volltext schlägt
  Referenz-Eintrag**.
Jeder Lauf steht append-only in `data/references_log.md`.

---

Die PDFs selbst sind – wie `papers/` – **nicht versioniert**; versioniert sind nur diese README
und die kuratierte Liste `referenzen.txt`. Der Unterordner `_duplikate/` wird vom Intake angelegt
und muss gelegentlich manuell geleert werden. Jede Intake-Entscheidung steht zusätzlich
append-only in `data/intake_log.md`.
