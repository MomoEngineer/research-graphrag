# 0040 – Explizites Leeren eines `manual`-Feldes (`clear_fields`)

- **Status:** Akzeptiert
- **Datum:** 2026-09-19

## Kontext

Die feldweise Auflösungskette `manual > curated > resolved > extracted`
([ADR 0025](0025-citable-paper-metadata.md)) gewinnt je Feld die erste Herkunft mit
**nicht-leerem** Wert (`MetadataRecord.has()`,
[bibliography/resolve.py](../../src/research_graphrag/bibliography/resolve.py)). Das setzt
voraus, dass ein leerer Wert immer "diese Quelle hat keine Meinung" bedeutet. Diese Annahme
trifft nicht mehr zu, sobald `manual` – die höchstrangige Herkunft – ein Feld absichtlich leer
lässt, weil eine niedrigerrangige Herkunft dort einen **geprüften Fehltreffer** trägt.

Konkret gemessen an Paper `01b44252fa9afbe4` (Harwardt & Prause, "Digitale Transformation durch
KI", Springer Gabler): Die `extracted`-Herkunft liest per Regex aus dem PDF-Volltext eine
arXiv-ID (`2406.12934`) – tatsächlich die ID eines **anderen**, im Buch zitierten Papers, nicht
des Buchs selbst (das als gedrucktes/eBook-Werk keine arXiv-ID hat). Eine `manual`-Korrektur mit
`apply_manual_correction` ([ADR 0039](0039-correction-tool-and-pdf-file-access.md)) kann Titel,
Autoren, Jahr, Venue, DOI und URL berichtigen – aber nicht `arxiv_id`, weil:

1. `_validate_fields` (heute `_validate_request`) einen leeren String für ein Textfeld als
   ungültige Eingabe ablehnt ("nicht leer, wenn gesetzt", siehe
   [specs/correct_paper_metadata.md](../../src/research_graphrag/mcp_server/specs/correct_paper_metadata.md),
   Abschnitt 2).
2. Selbst wenn man diese Prüfung umginge, würde `MetadataRecord.has("arxiv_id")` für einen
   `manual`-Record mit `arxiv_id=""` `False` liefern – "kein Wert" ist für `resolve.py` nicht von
   "kein *bekannter* Wert" unterscheidbar, die Auflösung fiele weiterhin auf `extracted` zurück.

Sichtbarer Effekt: `python -m scripts.cite 01b44252fa9afbe4` zeigt `arxiv_id=extracted` und die
Gesamtkonfidenz bleibt `weak` (die niedrigste beteiligte Herkunft zieht sie herunter,
[`lowest_confidence`](../../src/research_graphrag/bibliography/model.py)) – obwohl **jedes**
andere Feld bereits korrekt und `manual` ist. Die gerenderten Harvard/APA-Belege sind davon nicht
betroffen (DOI hat Vorrang vor arXiv in `PaperMetadata.preferred_url`), aber die ausgewiesene
Konfidenz und die Herkunfts-Übersicht sind irreführend.

[ADR 0039](0039-correction-tool-and-pdf-file-access.md), Abschnitt 5 ("Grenzen"), hält diese
Lücke bereits bewusst fest: *"Kein Zurücksetzen/Löschen eines Feldes auf dieser Schnittstelle
[…] Ein vollständiger Rückbau bleibt der Handbearbeitung von `metadata/paper_metadata.json`
vorbehalten."* Diese Grenze wird mit diesem ADR aufgehoben.

## Entscheidung

### 1. `MetadataRecord` bekommt `cleared_fields: frozenset[str]`

Ein additives Feld (Default `frozenset()`), das die Felder nennt, die diese Quelle
**ausdrücklich** als leer bestätigt hat – nicht bloß nie befüllt hat
([bibliography/model.py](../../src/research_graphrag/bibliography/model.py)). In der
Speicherform (`metadata/paper_metadata.json`) erscheint es als sortierte Liste
`"cleared_fields": ["arxiv_id"]`; fehlt der Schlüssel (jede vor diesem ADR geschriebene Zeile),
gilt ein leeres Frozenset – **keine Migration nötig**, das bisherige Verhalten bleibt exakt
erhalten. Der `SCHEMA_VERSION`-Wert von `bibliography/store.py` (`0.1.0`) bleibt deshalb bewusst
unverändert (siehe Alternativen).

### 2. `MetadataRecord.has()` liefert `True` für ein explizit geleertes Feld

```python
def has(self, name: str) -> bool:
    if name in self.cleared_fields:
        return True
    ...  # bisherige Prüfung auf nicht-leeren Wert
```

`has()` ist die **einzige** Stelle, an der die feldweise Auflösung
([resolve.py](../../src/research_graphrag/bibliography/resolve.py)) entscheidet, ob eine
Herkunft "eine Meinung" zu einem Feld hat. Die neue Semantik wirkt dort ohne weitere
Codeänderung. Ein zweiter, unabhängiger Konsument derselben Methode profitiert automatisch mit:
`online/metadata.py:filter_pending()` nutzt `has()` bereits, um zu entscheiden, ob ein Paper für
die nächste Online-Auflösung noch "offen" ist (`CITABLE_FIELDS`). Ein explizit geleertes Feld
gilt danach ebenfalls als "abgedeckt" – der Online-Lauf fragt kein bereits geprüftes,
absichtlich leeres Feld erneut ab. Beide Effekte folgen aus **einer** Änderung, nicht aus zwei
parallel gepflegten Prüfungen – dasselbe "eine Wahrheit"-Prinzip, das diesem Modul zugrunde
liegt (siehe Docstrings in `bibliography/model.py`).

### 3. `correct_paper_metadata` / `apply_manual_correction` bekommen `clear_fields`

Ein neuer, zu den sieben typisierten Feld-Parametern **orthogonaler** Parameter
`clear_fields: list[str]` (Namen aus `bibliography.model.METADATA_FIELDS`) statt einer
Zweitbedeutung von `None`:

- Ein Feld darf **nicht gleichzeitig** in einem Set-Parameter (z. B. `arxiv_id="…"`) und in
  `clear_fields` stehen – `invalid_input`.
- Mindestens **einer** der beiden Kanäle (gesetzte Felder oder `clear_fields`) muss nicht-leer
  sein (ersetzt die bisherige "mindestens ein Feld"-Prüfung, die nur gesetzte Felder kannte).
- Ein geleertes Feld wird auf seinen feldtyp-korrekten leeren Wert gesetzt (`""`/`()`/`0`) **und**
  in `cleared_fields` aufgenommen.
- Wird dasselbe Feld in einem **späteren** Aufruf gesetzt, verlässt es `cleared_fields` wieder –
  ein echter Wert dominiert immer, unabhängig vom bisherigen Cleared-Zustand.
- `data/corrections_log.md` zeigt für ein geleertes Feld den Klartext-Vermerk
  `(explizit geleert)` statt eines leeren Strings, damit ein Log-Leser eine bewusste Leerung
  nicht mit einem stillen Nulldiff verwechselt.

### 4. Tool-Version

[specs/correct_paper_metadata.md](../../src/research_graphrag/mcp_server/specs/correct_paper_metadata.md)
steigt von `0.1.0` auf `0.2.0` (abwärtskompatible Erweiterung, siehe
[docs/documentation-standards.md](../documentation-standards.md), Abschnitt 4.1): ein neuer
optionaler Parameter, ein neuer Ausgabeschlüssel (`record.cleared_fields`) – kein bestehendes
Verhalten ändert sich für Aufrufe ohne `clear_fields`.

## Alternativen

- **`null` als Sentinel in den bestehenden Feld-Parametern** (z. B. `arxiv_id: str | None = None`
  würde `None` zusätzlich für "explizit leeren" statt nur für "nicht angefasst" verwenden).
  Verworfen: bricht das dokumentierte Vertragsverhalten aller bisherigen Tools (`None` heißt
  überall "Parameter weggelassen") und wäre über die MCP-Tool-Schema-Serialisierung nicht
  zuverlässig von einem tatsächlich fehlenden Parameter unterscheidbar.
- **Eigener Drei-Zustands-Typ pro Feld** (`"unset" | "value" | "cleared"`) statt eines
  Frozenset über Feldnamen. Verworfen: verlangt sieben neue Parametertypen am Tool und einen
  Wrapper-Typ je Feld im Modell – unverhältnismäßig für ein Bit pro Feld; ein Set über
  `METADATA_FIELDS`-Namen ist grep-bar und passt zum bestehenden Stil (`ORIGIN_PRECEDENCE`,
  `CITABLE_FIELDS` sind ebenfalls einfache Tupel über Feldnamen).
- **`SCHEMA_VERSION`-Bump plus Migrationslauf.** Erwogen und verworfen: Die Erweiterung ist
  rückwärtskompatibel (fehlender Schlüssel ⇒ leeres Frozenset ⇒ unverändertes altes Verhalten,
  geprüft in `MetadataRecord.from_dict`); ein Versionssprung würde einen Migrationslauf ohne
  fachlichen Gegenwert erzwingen und widerspräche dem "right-sized"-Prinzip
  ([CONTRIBUTING.md](../../CONTRIBUTING.md), Abschnitt 5).
- **Status quo: Rückbau nur per Handbearbeitung von `metadata/paper_metadata.json`.** Verworfen –
  das ist exakt die in [ADR 0039](0039-correction-tool-and-pdf-file-access.md) §5 dokumentierte
  Lücke, die dieser ADR schließt: Ein Agent soll einen erkannten Regex-Fehltreffer selbst
  beheben können, ohne die versionierte Datei von Hand zu editieren (ADR 0039, Zweck).
- **`cleared_fields` nur in `corrections.py` auswerten, `has()` unverändert lassen.** Erwogen:
  Ein separater Check `if not record.has(name) and name not in record.cleared_fields: continue`
  direkt in `resolve.py` hätte `has()`s ursprüngliche, engere Bedeutung ("trägt einen
  nicht-leeren Wert") unangetastet gelassen. Verworfen, weil das den `filter_pending`-Nutzen aus
  Entscheidungspunkt 2 nicht automatisch mitgenommen hätte – zwei Stellen müssten dieselbe
  Zusatzbedingung duplizieren, mit dem Risiko, dass eine der beiden bei einer künftigen Änderung
  vergessen wird. Eine einzige, erweiterte `has()`-Semantik ist die schmalere Änderung.

## Konsequenzen

- **Positiv:** Schließt die in ADR 0039 dokumentierte Lücke; eine Korrektur kann jetzt jeden der
  sieben Fälle "Wert setzen" **und** "Wert explizit verneinen" abdecken. Kein Schema-Bruch, keine
  Migration, kein zusätzlicher Re-Ingest-Zwang (derselbe `python -m scripts.ingest`-Schritt wie
  bei jeder anderen Korrektur). Die Semantik wirkt konsistent an zwei Stellen (Präzedenzauflösung
  und Online-Resolution-Skip-Prüfung) über eine einzige geänderte Methode.
- **Negativ / Aufwand:** `MetadataRecord` trägt jetzt ein Feld, dessen Bedeutung nur im
  Zusammenspiel mit `has()` verständlich ist – dokumentiert im Docstring beider Symbole. Das
  Tool-Schema von `correct_paper_metadata` wächst um einen achten Parameter.
- **Folgeentscheidungen:** keine offenen. Die reale Korrektur an Paper `01b44252fa9afbe4`
  (`clear_fields=["arxiv_id"]`) ist eine Dateninstanz dieser Entscheidung, kein separater ADR.
