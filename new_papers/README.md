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

Die PDFs selbst sind – wie `papers/` – **nicht versioniert**; nur diese README ist es. Der
Unterordner `_duplikate/` wird vom Intake angelegt und muss gelegentlich manuell geleert werden.
Jede Entscheidung steht zusätzlich append-only in `data/intake_log.md`.
