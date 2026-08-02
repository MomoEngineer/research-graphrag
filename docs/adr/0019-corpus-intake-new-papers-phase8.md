# 0019 – Korpus-Zufluss über `new_papers/` (Phase 8): gestufter Intake, Quarantäne statt Löschen, `Übersicht.md` als einzige Senke

- **Status:** Akzeptiert
- **Datum:** 2026-08-02

## Kontext

Der bisherige Drop-in-Workflow (PDF nach `papers/`, dann `python -m scripts.ingest`) dedupliziert
über `data/manifest.json` – und zwar **Dateiname → sha256**. Ein **inhaltsgleiches PDF unter einem
anderen Dateinamen** wird dadurch als neues Paper indiziert: eigene `paper_id`, eigene Knoten und
Kanten im Ähnlichkeitsgraphen, doppelte Belege in jeder Antwort und eine zweite Zeile in der
Literaturübersicht. Bei handverlesener Ablage ist das selten; sobald PDFs mit fremd vergebenen
Dateinamen kommen (Roadmap-Phase 9), wird es zum Regelfall.

Die [Roadmap](../../Roadmap.md) sieht dafür einen Eingangsordner `new_papers/` mit dreistufiger
Duplikatprüfung vor (sha256 → DOI/arXiv → Titel-Ähnlichkeit) und verlangt **hartes Löschen** auf
den ersten beiden Stufen. Weil dabei Dateien unwiderruflich vernichtet werden, wurde die Tragfähig-
keit der Kriterien **vor** der Umsetzung am realen Korpus (145 Paper) gemessen – gemäß dem
Leitprinzip „erst messen, dann bauen".

### Messbefunde (Wegwerf-Messung, 2026-08-02)

| # | Befund | Bedeutung |
| --- | --- | --- |
| **F1** | `doi:10.1145/nnnnnnn.nnnnnnn` steht bei **3** Papern – der unausgefüllte ACM-Vorlagen-Platzhalter | Ein DOI-Wert im Korpus ist **nicht** notwendig eindeutig; jedes weitere ACM-Vorlagen-Paper träfe denselben Schlüssel |
| **F2** | **14 von 155** Identifikatoren sind nicht auf der eigenen Titelseite belegt (der Volltext-Fallback der Extraktion greift *zitierte* fremde IDs) – darunter `arXiv:2108.07732` (MBPP), exakt der Falsch-Hub aus [ADR 0011](0011-intra-corpus-citation-graph-phase7.md) | Der Korpus enthält Identifikatoren, die auf das **falsche** Paper zeigen |
| **F3** | Paarweise Titel-Ähnlichkeit (`difflib` auf normalisierten Dateinamen-Stämmen) über alle 145 Paper: **≥ 0,85 → 0 Paare**; ≥ 0,80 → 4 Paare, alle davon echt verschiedene Arbeiten (z. B. *GraphCoder* ↔ *RepoCoder*) | Eine Schwelle von **0,85** erzeugt am realen Korpus keinen Fehlalarm |
| **F4** | Chunks je Paper: Minimum **19**, kein Paper mit 0 Chunks | Ein neues Flag `no_chunks` ändert am Bestand **nichts** ⇒ kein Schema-Bump, keine Re-Extraktion |

F1 und F2 sind entscheidend: Sie belegen, dass das Kriterium „gleiche DOI/arXiv-ID" bei **17 von
155** Identifikatoren des eigenen Korpus fehlleiten würde – **14**, weil sie nicht auf der eigenen
Titelseite belegt sind, und **3**, weil sie denselben Vorlagen-Platzhalter tragen. Ein Intake, der
darauf hin löscht, vernichtet unter realistischen Bedingungen legitime, nirgends sonst vorhandene
Dateien.

## Entscheidung

### 1. Gestufte Prüfung mit **abgestufter** Konsequenz

| Stufe | Kriterium | Konsequenz | Begründung |
| --- | --- | --- | --- |
| 1 | **sha256** identisch zu einem Eintrag in `data/manifest.json` **und** am Dateisystem nachgerechnet | Datei wird **gelöscht** | Eine **byte-identische** Kopie existiert nachweislich in `papers/`; es geht kein Bit verloren |
| 2 | **DOI oder arXiv-ID** identisch zu einem *gehärteten* Korpus-Schlüssel | Datei wandert nach **`new_papers/_duplikate/`** (Quarantäne); gelöscht wird nur mit `--delete-identifier-duplicates` | Die Datei ist **nicht** identisch (andere Fassung, anderes Layout, ggf. neuere Version), und das Kriterium ist heuristisch (F1/F2) |
| 3 | **Titel-ähnlichkeit** ≥ 0,85 | Datei **bleibt liegen**, Befund im Bericht | Verdacht, kein Beweis – die Entscheidung gehört zum Menschen |

Die Roadmap-Vorgabe „Stufe 2 löscht" wird damit bewusst **abgeschwächt**: Die Datei verlässt den
Eingangsordner (das Ziel „kein Doppelbestand" ist erreicht), aber der Vorgang bleibt umkehrbar.

**Der Beleg der Löschung wird nachgerechnet.** Ein Manifest-Treffer allein genügt nicht: Wird eine
PDF aus `papers/` entfernt, ohne neu zu indizieren, zeigt der Eintrag ins Leere – und die einzige
verbliebene Kopie würde vernichtet. Vor dem Löschen wird deshalb geprüft, ob unter dem genannten
Namen **tatsächlich** eine Datei mit genau diesem Hash liegt; andernfalls durchläuft die Datei die
übrigen Stufen und bleibt erhalten. Erst damit stimmt die Begründung in der Tabelle wortwörtlich.

### 2. Härtung des Identifikator-Vergleichs (Stufe 2)

Ein Korpus-Identifikator zählt nur als Duplikat-Schlüssel, wenn **beide** Bedingungen gelten:

1. **Frontmatter-Beleg** – der Wert ist in einem Chunk mit `page_end ≤ 2` **außerhalb** des
   Referenzabschnitts belegt. Das ist exakt der Guard aus
   [ADR 0011](0011-intra-corpus-citation-graph-phase7.md) (dort gegen falsche `CITES`-Kanten,
   hier gegen falsche Löschungen) – er entwertet die 14 Fälle aus **F2**.
2. **Eindeutigkeit** – der Wert zeigt auf **genau ein** Korpus-Paper. Werte mit mehreren
   Trägern (Vorlagen-Platzhalter, **F1**) sind kein Duplikat-Kriterium.

Auf der Eingangsseite wird symmetrisch verfahren: Aus der neuen Datei werden Identifikatoren
**ausschließlich** von den ersten zwei Seiten gelesen – **ohne** den Volltext-Fallback der
regulären Extraktion, der die Fehlerklasse F2 überhaupt erst erzeugt.

### 3. Titel-Verdacht (Stufe 3)

Verglichen wird der normalisierte **Dateiname-Stamm** *und* ein aus den ersten zwei Seiten
gelesener **Titelkandidat** gegen die normalisierten Dateiname-Stämme des Korpus
(`difflib.SequenceMatcher`, Schwelle **0,85** nach **F3**). Der Titelkandidat ist nötig, weil
heruntergeladene Dateien oft `2310.11511v1.pdf` heißen – dann trägt der Stamm keine Information.
Die Kandidaten unterliegen denselben Mindestmaßen wie das Titel-Matching des Zitationsgraphen
(`MIN_TITLE_CHARS`, `MIN_TITLE_WORDS`), damit Kopfzeilen und Datumsangaben nicht als Titel gelten.

Die **Namenskollision** (`papers/<name>` existiert bereits mit anderem Inhalt) wird **vor** dieser
Stufe geprüft: Sie ist eine Tatsache über den Zielort, keine Vermutung, und sie ist die
handlungsleitendere Meldung.

*Gemessene Trefferquote (25 reale Paper, künstlich umbenannt):* **22 von 25** werden am
Seitentitel wiedererkannt, **kein einziger** zeigt auf das falsche Paper. Die drei Fehlanzeigen
sind Arbeiten, deren Titel über viele Zeilen läuft. Stufe 3 ist damit belegt ein **Verdacht** und
keine Garantie – was genau der Grund ist, warum sie folgenlos bleibt.

### 4. `Übersicht.md` wird die **einzige** Senke der Entwurfszeilen

Die Phase-2-Festlegung aus [ADR 0006](0006-canonical-model-phase2-scope.md) („die kuratierte
`Übersicht.md` bleibt unangetastet, Entwürfe gehen nach `data/overview_drafts.md`") wird
**abgelöst**. Neu hängen **beide** Einstiegspunkte – der Intake und `scripts/update_overview.py` –
ihre Entwurfszeilen an `Übersicht.md` an. Es gibt damit **eine** Zeilenbau-, **eine** Idempotenz-
und **eine** ID-Logik (`overview/drafts.py`); die Staging-Datei wird nicht mehr beschrieben.

Verbindliche Eigenschaften des Anhangs:

- **Append-only und byte-erhaltend.** Der bestehende Dateiinhalt wird **binär** übernommen und um
  neue Zeilen ergänzt (Zeilenende der Datei wird beibehalten); geschrieben wird über eine
  Temporärdatei mit `os.replace` – dasselbe Atomaritäts-Muster wie beim Index-Swap
  ([ADR 0010](0010-drop-in-workflow-and-qa-phase6.md)). Kein Umsortieren, kein Ändern
  bestehender Zellen.
- **Idempotent.** Erkennung über die internen Links (`parse_internal_links`, seit Phase 2); ein
  zweiter Lauf erzeugt keine zweite Zeile.
- **Wertende Spalten bleiben leer** (`(manuell)`): `Relevanz fuer Expose`, `SRQ-Zuordnung`,
  `Themenfokus`. Die Kuratierung bleibt beim Menschen.
- **Eigene ID-Reihe `Z1`, `Z2`, …**, fortlaufend aus dem höchsten bereits vorhandenen `Z`-Wert.
  Die kuratierten IDs sind Themencluster (`A1`, `B2`, …), die ein Automat nicht vergeben kann.
- **Migrationsschutz:** Eine noch vorhandene `data/overview_drafts.md` wird weiterhin **gelesen**
  und ihre Einträge gelten als bekannt, damit ein nicht übernommener Altbestand nicht doppelt in
  der Übersicht landet.

### 5. Robustheits-Gate für unkuratierte PDFs

- Neues Qualitäts-Flag **`no_chunks`**: Ein Dokument mit Seitentext, aber ohne Fließtext erzeugt
  bisher **null Chunks und kein Flag** – die in [ADR 0013](0013-chunking-refinement-phase7.md)
  dokumentierte bekannte Grenze. Das Flag schließt sie mechanisch (keine geratene Schwelle). Wegen
  **F4** ändert sich am bestehenden Korpus nichts ⇒ **kein Canonical-Schema-Bump, keine
  Re-Extraktion**.
- **`%PDF-`-Signaturprüfung** im Intake: Eine Datei ohne PDF-Signatur (z. B. eine als `.pdf`
  gespeicherte HTML-Fehlerseite) wird **nicht** übernommen, bleibt liegen und erscheint als Befund.
- Beides führt zu **keiner stillen Ablehnung**: Angenommene Paper werden im Bericht mit ihren
  Qualitäts-Flags ausgewiesen.

### 6. `--dry-run` und Protokoll

- **`--dry-run` ist Pflichtbestandteil** und verändert **nichts**: kein Löschen, kein Verschieben,
  kein Ingest, kein Schreiben in `Übersicht.md` und kein Protokolleintrag.
- **Vorbedingungen werden vorab geprüft.** Eingangsordner, `papers/` und die Zieldatei der
  Übersicht (Existenz *und* Spaltenlayout) werden geprüft, **bevor** die erste Datei bewegt wird.
  Ein Werkzeug mit Löschbefugnis darf keinen halb erledigten Zustand hinterlassen.
- Zusätzlich zum Bericht auf stdout schreibt ein Lauf **append-only** nach `data/intake_log.md`:
  Zeitstempel, Aktion, Dateiname, **sha256** und Grund. Das ist die einzige forensische Spur der
  einzigen Operation im Repo, die Dateien vernichtet, und erfüllt die Auflage aus dem
  Roadmap-Betriebspunkt B1 („Bericht mit Hash je gelöschter Datei").

### 7. Einordnung in die bestehende Pipeline

Der Intake ist eine **vorgelagerte** Schicht: Nach dem Verschieben ruft er unverändert
`pipeline.ingest` auf (voller Re-Index mit atomarem Swap). Weder das Index-Schema noch ein
Retrieval-Contract wird berührt; die Logik liegt in `src/research_graphrag/intake.py`, das Skript
`scripts/intake.py` bleibt dünn (Konvention aus
[docs/repository-structure.md](../repository-structure.md)).

**Der Intake wird bewusst *nicht* als MCP-Werkzeug registriert.** Der Server bleibt bei seinen acht
lesenden Werkzeugen. Ein Werkzeug, das **Dateien löscht und den Korpus verändert**, darf nicht von
einem Agenten autonom ausgelöst werden können – Copilot entscheidet selbständig über Werkzeugaufrufe,
und eine beiläufige Frage dürfte niemals eine unumkehrbare Operation anstoßen. Das ist dieselbe
Haltung, mit der Roadmap-Punkt B4 den Auto-Watcher streicht: Der Zufluss soll **angestoßen und
beobachtet** werden, nicht beiläufig geschehen.

## Alternativen

- **Hartes Löschen auch auf Stufe 2 (Roadmap-Wortlaut).** Verworfen: F1 und F2 belegen, dass das
  Kriterium im eigenen Korpus bei 17 von 155 Identifikatoren fehlleitet. Eine Quarantäne erreicht dasselbe operative Ziel
  (kein Doppelbestand, Eingangsordner leert sich), ist aber umkehrbar. Wer das Verhalten will,
  bekommt es explizit über `--delete-identifier-duplicates`.
- **Auch Stufe 1 nur quarantänisieren.** Verworfen: Bei identischem sha256 existiert die Datei
  bitgenau bereits in `papers/`; eine Quarantäne würde nur Speicher belegen und Handarbeit
  erzeugen, ohne irgendein Risiko zu senken.
- **Duplikatprüfung über den Volltext (Chunk-Ähnlichkeit) statt über Identifikatoren.** Verworfen
  für Phase 8: Sie erfordert eine vollständige Extraktion **vor** der Entscheidung, führt eine
  weitere Schwelle ein und ist nicht mechanisch nachrechenbar. Die drei Stufen decken die realen
  Fälle ab; ein inhaltlicher Vergleich bliebe eine spätere, eigenständig zu messende Ausbaustufe.
- **Zwei Senken beibehalten** (Intake → `Übersicht.md`, `update_overview.py` → Staging). Verworfen:
  Zwei Wege mit identischer Semantik driften auseinander, und ein Paper könnte in beiden Dateien
  erscheinen. Eine Senke mit zwei Einstiegspunkten ist die kleinere Angriffsfläche.
- **`scripts/update_overview.py` ersatzlos streichen.** Verworfen: Das Skript bleibt der Nachpflege-
  Pfad für PDFs, die direkt in `papers/` abgelegt wurden – dieser Weg existiert weiter.
- **Zusätzliches Flag `few_chunks:<n>` mit Schwelle.** Verworfen: Jede Zahl wäre ungemessen
  geraten. Das Repo-Prinzip verlangt Messung vor Schwelle; `no_chunks` ist mechanisch definiert.
- **Auto-Watcher auf `new_papers/`.** Bleibt gestrichen (Roadmap B4): Der Intake verändert den
  Korpus und löscht Dateien – das soll angestoßen und beobachtet werden, nicht im Hintergrund
  geschehen.
- **Intake als MCP-Werkzeug.** Verworfen: Copilot ruft Werkzeuge autonom auf; eine löschende,
  korpusändernde Operation gehört nicht in diese Reichweite. Der Server bleibt lesend.

## Konsequenzen

- **Positiv:** Ein Befehl übernimmt neue PDFs samt Duplikatprüfung, Index-Neubau und Übersicht-
  Zeile. Die beiden belegten Fehlerquellen des Identifikator-Vergleichs sind entschärft; die einzige
  unwiderrufliche Aktion ist an einen **bitgenauen** Beweis gebunden. Entwurfszeilen haben genau
  ein Ziel und eine Implementierung. Die bekannte Grenze „0 Chunks, kein Flag" ist geschlossen.
- **Negativ / Aufwand:** `new_papers/_duplikate/` muss gelegentlich manuell geleert werden. Eine
  **neuere Version** eines vorhandenen Papers gilt weiterhin als Duplikat (gleiche
  Identifikator-Wurzel) – sie landet in der Quarantäne statt im Korpus; wer ersetzen will, löscht
  zuerst die alte Datei in `papers/` (in der README dokumentiert). Der Intake schreibt in eine
  **versionierte, kuratierte** Datei; abgesichert ist das über Byte-Erhalt, atomares Schreiben und
  einen Regressionstest, nicht über Versionsverwaltung. Stufe 3 kann bei sehr ähnlichen Titeln
  einen Fehlverdacht melden – die Konsequenz ist eine Zeile im Bericht, kein Datenverlust.
- **Folgeentscheidungen:** Der Download-Pfad aus Roadmap-Phase 9 liefert ausschließlich nach
  `new_papers/` – es bleibt bei **einem** Weg in den Korpus. Der Sicherungsweg (B1) und das
  inkrementelle Update (B2) bleiben eigenständige Betriebspunkte.

---

## Nachweis am realen Korpus (2026-08-02)

**Härtung (read-only gegen die 145 Canonical-Paper):** Von **155** Identifikatoren überleben
**138** als Löschschlüssel; **17** werden verworfen (14 ohne Frontmatter-Beleg, 3 Träger des
mehrdeutigen ACM-Platzhalters). Gegenprobe: Weder `doi:10.1145/nnnnnnn.nnnnnnn` noch
`arXiv:2108.07732` sind Schlüssel. **142 von 145** Dateiname-Stämmen erfüllen die Titel-Mindestmaße.

**End-to-End (vollständige Kopie des Korpus, fünf Eingangsdateien):** Alle fünf Wege wurden
einmal durchlaufen – byte-identische Kopie → *gelöscht* (Hash im Protokoll), arXiv-Variante mit
geändertem Hash → *Quarantäne*, umbenanntes Korpus-Paper → *Titel-Verdacht* (Ratio 1,00, Datei
bleibt liegen), HTML-Fehlerseite mit `.pdf`-Endung → *liegen geblieben*, echtes neues Paper →
*übernommen* (Index 145 → 146 Paper, Übersicht + 1 Zeile `Z1`). Belegt wurden dabei:

- `--dry-run` verändert nichts (Hash-Abbild des gesamten Baums vor/nach identisch),
- die kuratierten Übersicht-Zeilen bleiben **byte-identisch** (die neue Datei beginnt exakt mit
  dem alten Inhalt), keine `.tmp`-Reste,
- der zweite Lauf ist **idempotent** (keine zweite Zeile),
- die Qualitäts-Flags der übernommenen Paper erscheinen im Bericht.

> **Verhältnis zu [ADR 0006](0006-canonical-model-phase2-scope.md):** Dieser ADR löst dort die
> Festlegung „Entwurfszeilen gehen ausschließlich append-only nach `data/overview_drafts.md`, die
> kuratierte `Übersicht.md` bleibt unangetastet" ab. Der übrige Umfang von ADR 0006 (heuristische
> Sections, keine Bounding-Boxes, kein tiefes Referenz-/Tabellen-Parsing) gilt unverändert weiter;
> der Flag-Katalog wird um `no_chunks` **ergänzt**, nicht geändert.
