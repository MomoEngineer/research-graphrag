# 0031 – Referenz-Einträge in Contract und Ranking (Phase 13 / R3): Pflichtfeld, Zitier-Contract, Guardrail

- **Status:** Akzeptiert
- **Datum:** 2026-08-09

## Kontext

[ADR 0029](0029-reference-stub-resolution-phase13.md) erzeugt Stub-Dateien `*.refjson`,
[ADR 0030](0030-reference-entries-in-corpus-phase13.md) bringt sie als zweiten Dokumenttyp in
Intake, Extraktion und Index. Damit **existieren** Referenz-Einträge – wirksam werden sie erst
hier. Bis R3 gilt:

1. **Sie sind nach außen unsichtbar.** `document_kind` endet in der Tabelle `papers`; weder ein
   `Hit` noch ein `Citation`, `PaperRef` oder `EvidenceItem` trägt es. Ein Beleg aus einem
   Abstract sieht in jeder Ausgabe aus wie ein Volltext-Beleg.
2. **Sie könnten die Messgrundlage verfälschen.** `derive_expected_papers` leitet die Gold-Labels
   mechanisch aus `chunks.text` ab. Ein Stub-Chunk aus Titel und Abstract kann die Suchstrings
   zufällig enthalten und würde damit **still** zum erwarteten Paper – obwohl er die Frage nicht
   belegen kann.
3. **Sie verdrängen belegfähige Treffer.** Die Vormessung R0 hat das an 52 echten Abstracts
   beziffert: **13 qid-Regressionen**, alle in den Multi-Hop-Ebenen, davon **zwei
   Totalverluste** aus den Top 5.
4. **Beide Baselines sind außer Betrieb.** Sie stehen auf 341 Papern und Index-Schema `0.4.0`,
   der Korpus auf 373 und `0.5.0`. Jeder `--check` endet mit Exit-Code 2 – der quantitative
   Regressionsschutz misst derzeit nichts.

Der Zielkonflikt der Guardrail ist die eigentliche Entscheidung dieses ADR. Dieselbe Eigenschaft,
die den Schaden verursacht – ein Stub ist **kurz** und wird von den längennormierenden Wertungen
bevorzugt –, stiftet auch den Nutzen: In der Handprobe aus R0 fanden **10 von 10** Fragen ihren
Referenz-Eintrag auf **Rang 1**, weil kein Volltext des Korpus die Frage beantworten konnte.

## Entscheidung

### 1. `document_kind` wird Pflichtbestandteil des Contracts

Das Feld wird von der Tabelle `papers` bis in jede Ausgabe durchgereicht:

| Typ | Wirkung | Spec |
| --- | --- | --- |
| `Hit`, `_ChunkRef` | Quelle aller Chunk-Belege | – |
| `Citation` | 12 → **13** Schlüssel | `search_basic`, `search_local`, `search_drift` |
| `PaperRef` | 5 → **6** Schlüssel | `search_global`, `search_drift`, `get_citations` |
| `EvidenceItem`, `EvidenceSource` | 7 → **8** Schlüssel | `answer_question` |
| `PaperDetail` | 8 → **9** Schlüssel | `get_paper` |

`CitationLink` erbt das Feld über `PaperRef.to_dict()`.

**`PaperDetail` steht zusätzlich zur Roadmap-Vorgabe auf der Liste.** Dort ist das Feld sogar
besonders nötig: Ein Referenz-Eintrag meldet `n_pages = 0` und `n_chunks = 1` – ohne die
Dokumentart sähe das nach einer **misslungenen Extraktion** aus statt nach einem bewusst
unvollständigen Eintrag.

**`get_reference` bleibt unverändert** (Version `0.1.0`). Die Literaturangabe ist von der
Verfügbarkeit des Volltextes unabhängig; sie bleibt vollständig, und genau das ist die Aussage.

Die Spec-Versionen steigen entsprechend: `search_basic`, `search_global`, `get_paper`,
`get_citations`, `answer_question` auf `0.2.0`; `search_local` und `search_drift` auf `0.3.0`.

**Das Feld trägt einen Default (`full`) statt Pflicht im Konstruktor zu sein.** Ein Feld ohne
Default müsste in `Hit` vor den bestehenden Default-Feldern stehen und würde jeden
Positionsaufruf brechen. Der Preis – ein vergessener Aufruf fiele auf `full` zurück – wird durch
Contract-Tests abgedeckt, die einen echten Referenz-Eintrag durch alle Stufen verfolgen. Es ist
dieselbe Handhabung wie bei `CanonicalPaper.document_kind` in
[ADR 0030](0030-reference-entries-in-corpus-phase13.md).

### 2. Der Zitier-Contract nennt die Unvollständigkeit – die Literaturangabe bleibt vollständig

Ein Beleg aus einem Referenz-Eintrag wird an **zwei** Stellen kenntlich:

- **Im Provenienz-Label** (`REFERENCE_EVIDENCE_MARKER`, Klartext „Referenz-Eintrag ohne
  Volltext"). Das ist die wirksame Stelle: Nur das Label steht im Prompt-Kontext, den das Modell
  sieht.
- **Im Datensatz** (`document_kind`), für Aufrufer, die maschinell auswerten.

Der `DEFAULT_SYSTEM_PROMPT` verlangt zusätzlich, diese Einschränkung **im Antworttext zu
benennen**. Er zitiert den Marker bewusst **nicht wörtlich**, sondern verweist auf die
Kennzeichnung im Label – sonst stünde derselbe Text an zwei Orten und könnte auseinanderlaufen.

Die fehlende Seite wird weiter über `page_label` als „ohne Seite (Abstract)" ausgewiesen
([ADR 0030](0030-reference-entries-in-corpus-phase13.md)); sie sagt, *wo* der Beleg herkommt,
der Marker sagt, dass der Volltext **fehlt**. Beides zusammen ist die vollständige Auskunft.

### 3. Referenz-Einträge werden von der mechanischen Gold-Ableitung ausgeschlossen

`derive_expected_papers` verbindet `chunks` mit `papers` und wertet nur `document_kind = 'full'`.
Damit kann ein Stub **nie** Gold-Ziel werden. Die Label-Regel in der Gold-Set-Datei nennt die
Ausnahme im Klartext, `INDEX_SCHEMA_VERSION` steigt auf `0.5.0`.

**Das Multi-Hop-Gold bleibt unangetastet.** Dort ist ein Referenz-Eintrag als **Ziel** genau der
gewollte Effekt: Die Frage „welche Paper bauen auf X auf?" ist korrekt beantwortet, wenn X ein
Paper ohne Volltext ist – das ist der bezifferte Hauptnutzen der Phase. Die Anker stammen aus dem
Zitationsgraphen, nicht aus dem Chunk-Text; der Zirkelschluss der lexikalischen Regel besteht
dort nicht.

### 4. Die Guardrail sortiert um, sie sortiert nicht aus

`demote_references` sortiert Referenz-Einträge **stabil hinter** die Volltext-Treffer derselben
Liste – in `TfidfIndex.search` **und** in `neighbors_of_chunk`. Die **Auswahl** der Top-k bleibt
unverändert; nur ihre **Reihenfolge** ändert sich.

Damit gilt beides gleichzeitig:

- Wo ein Volltext die Frage beantworten kann, steht er vorn.
- Wo keiner es kann, steht der Referenz-Eintrag weiterhin ganz oben – der Fall, für den er
  existiert.

Ein stubfreier Korpus merkt von der Regel nichts: Die Sortierung ist dann die Identität. Deshalb
bewegt die Guardrail die eingefrorenen Baselines nicht.

### 5. Beide Baselines werden neu eingefroren

Zweistufig wie in V1/V2: erst der qid-genaue Nachweis bei **unverändertem** Fingerprint, dann das
Einfrieren. Reihenfolge innerhalb von R3: **Messung zuerst** (siehe unten), dann Gold-Ausschluss
und Guardrail im Code, dann Gold-Neuableitung und Einfrieren, zuletzt `--check`.

## Die Messung, die die Guardrail bestimmt hat

Der Aufbau von R0 wurde vollständig reproduziert: 52 echte Abstracts in einer Index-Kopie,
dieselben zehn Ebenen, dasselbe Gold. Der **eingebaute Selbsttest**: Kontroll- und
Vergleichslauf mussten die gespeicherten R0-Ränge exakt treffen.

> **Reproduktion Kontrolle A gegen R0: 0 abweichende qid-Ränge.
> Reproduktion B_real gegen R0: 0 abweichende qid-Ränge.**

Damit ist belegt, dass die Rekonstruktion der Stubs, die Beschleunigung der Messung (gecachte
Ladepfade) und der zwischenzeitliche Schema-Wechsel `0.4.0 → 0.5.0` **keinen** Rang bewegt haben.

Die Regel für den Variantenentscheid stand **vor** der Messung fest: *Gewählt wird die Variante,
die die meisten der 13 R0-Regressionen behebt, ohne dass die Handprobe einen ihrer zehn Treffer
aus den Top 5 verliert; bei Gleichstand die einfachere.*

| Variante | Regel | Regressionen (davon Totalverlust) | Handprobe Hit@5 |
| --- | --- | --- | --- |
| *keine* (= R0 B_real) | – | 13 (2) | 10/10 |
| **v1 – Reihenfolge** | Umsortieren innerhalb der Top-k | **3 (0)** | **10/10** |
| v2 – Auswahl | Volltext zuerst befüllen, Stubs nur auf Restplätzen | 0 (0) | **0/10** |
| v3 – Kontingent | höchstens ⌈k/5⌉ Stub-Plätze, reserviert | 39 (5) | 10/10 |

**v1 gewinnt nach der vorab fixierten Regel.** Es behebt 10 der 13 Regressionen und – das ist
der wichtigere Teil – **beide Totalverluste**: `C50` (1 → None) landet wieder auf Rang 3, `C35`
(1 → None) auf Rang 2. Die drei verbleibenden Befunde sind reine Rangverschiebungen um ein bis
zwei Plätze; **kein** Treffer geht verloren.

**Warum v2 ausscheidet, obwohl es 0 Regressionen erreicht:** Es zerstört den Nutzen der Phase
vollständig – **0 von 10** Handproben-Fragen finden ihren Referenz-Eintrag noch in den Top 5.
Die Nebenbedingung der Entscheidungsregel greift genau hier: Eine Guardrail, die die Messwerte
rettet, indem sie den gemessenen Gegenstand entfernt, misst nur noch sich selbst.

**Warum v3 ausscheidet:** Das Kontingent wirkt in beide Richtungen – es begrenzt Stubs nicht nur
nach oben, es **reserviert** ihnen auch einen Platz. Bei `k = 5` verdrängt der reservierte Platz
den fünftbesten Volltext-Treffer, und zwar auch dann, wenn gar kein Stub in der Nähe ist. Das
Ergebnis ist mit 39 Regressionen und 5 Totalverlusten schlechter als **ohne** jede Guardrail.

**Der ausgewiesene Preis von v1:** In der Handprobe rutschen alle zehn Treffer von Rang 1 auf
Rang 5 (MRR 1,000 → 0,200). Das ist die unvermeidliche Kehrseite: Rang 1 hatten sie nur, weil
vier thematisch unpassende Volltext-Chunks schwächer bewertet wurden. Die Akzeptanzbedingung
lautet „die Handprobe findet die Abstracts", nicht „auf Rang 1" – gefunden werden sie
vollständig.

## Alternativen

- **Kein Contract-Bruch, nur ein Zusatz im Label.** Verworfen: Ein maschineller Aufrufer müsste
  dann einen Anzeigetext parsen, um eine strukturelle Eigenschaft zu erkennen.
- **Score-Abschlag statt Umsortierung** (Stub weicht, wenn ein Volltext „nah genug" scort).
  Verworfen ohne Messung: Ein Schwellenwert wäre an den 52 Stubs dieser einen Messung getunt –
  dieselbe Overfitting-Falle, die schon in A4 gegen kuratierte Labels sprach. Die gewählte Regel
  hat **keinen** Parameter.
- **Referenz-Einträge ganz aus dem Retrieval halten** (nur als Zitationsziele). Verworfen: Dann
  wäre die Handprobe ohne Ergebnis, und der einzige Grund für die Phase entfiele.
- **Stubs auch aus dem Multi-Hop-Gold ausschließen.** Verworfen, siehe Punkt 3.
- **Das Neu-Einfrieren ans Ende von R3 stellen** (Reihenfolge der Roadmap-Prosa). Verworfen: Die
  13 Regressionen aus R0 beziehen sich auf das **damalige** Gold. Nur eine Messung gegen genau
  diesen Stand ist mit R0 vergleichbar – deshalb Messung zuerst, Einfrieren danach. Der
  R0-Statusblock sagt dasselbe.

## Konsequenzen

- **Positiv:** Jede Ausgabe weist einen Referenz-Eintrag als solchen aus – CLI, MCP-Werkzeuge und
  `answer_question`. Die Messgrundlage kann durch Stubs nicht mehr still verfälscht werden. Der
  quantitative Regressionsschutz ist nach dem Neu-Einfrieren wieder in Betrieb. Der Nutzen der
  Phase bleibt vollständig erhalten (Handprobe 10/10).
- **Negativ / Aufwand:** Sieben Tool-Spezifikationen steigen in der Version; ein Aufrufer, der
  Ausgaben auf feste Schlüsselmengen prüft, muss nachziehen. Drei qid-Rangverschiebungen bleiben
  als bewusst akzeptierte Grenze bestehen. In der Handprobe fällt der MRR von 1,000 auf 0,200.
- **Folgeentscheidungen:** Ob und wann echte Referenz-Einträge in den Produktivkorpus aufgenommen
  werden, ist eine **Betriebsentscheidung** und nicht Teil dieses ADR. Die neuen Baselines
  beschreiben bewusst einen **stubfreien** Zustand; der nächste `--check` nach einer Aufnahme
  zeigt deren Wirkung dann sauber an.
