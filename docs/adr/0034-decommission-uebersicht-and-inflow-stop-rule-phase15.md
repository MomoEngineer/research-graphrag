# 0034 – Übersicht.md außer Dienst: maschinenlesbares Relevanzurteil, Stoppregel des Zuflusses

- **Status:** Akzeptiert
- **Datum:** 2026-09-01

## Kontext

[`Übersicht.md`](../../Übersicht.md) ist seit Phase 1 die menschlich kuratierte Literaturübersicht
des Repos: Themencluster, Relevanz-Einschätzung und SRQ-Zuordnung. Seit Phase 8
([ADR 0019](0019-corpus-intake-new-papers-phase8.md)) hängt der Korpus-Intake für jedes neue
Paper eine **Entwurfszeile** (`Z1`, `Z2`, …) an; Phase 13
([ADR 0030](0030-reference-entries-in-corpus-phase13.md)) hat dasselbe für Referenz-Einträge
getan.

Gemessen am 2026-08-28 (Phase 15, G0) stehen in der Datei **482** Tabellenzeilen, davon **131
kuratiert** und **351** unbearbeitete `Z`-Entwurfszeilen (72,8 %) – am 2026-09-01 sind es bereits
**627** Zeilen bei unverändert **131** kuratierten. Als Landkarte ist die Tabelle damit bereits
entwertet, und der in [Phase 14](../../Roadmap.md#phase-14--referenz-ernte-externe-verweise-aus-dem-eigenen-bestand)
geplante Referenz-Zufluss macht es schlimmer, nicht besser: Er würde die Zahl der `Z`-Zeilen um
bis zu 3371 potenzielle Kandidaten erhöhen (siehe Phase 13 / R0).

**Ersatzlos löschen wäre der falsche Schluss.** Die 131 kuratierten Zeilen tragen das **einzige
menschliche Relevanzurteil** im gesamten Repo (`Themenfokus`, `Relevanz fuer Expose`,
`SRQ-Zuordnung`) – es ist aus **keiner** anderen Quelle rekonstruierbar, weshalb
[ADR 0027](0027-corpus-backup-phase11.md) die Datei ausdrücklich als nicht wiederherstellbar
sichert.

Zweitens fehlt dem geplanten Zufluss (Referenzen ernten → aufnehmen → aus neuen Volltexten wieder
ernten) ein eingebauter Endpunkt. Er ist zwar durch die manuelle Volltextbeschaffung gedeckelt
(ein Referenz-Eintrag hat selbst keinen Referenzabschnitt und erzeugt daher keine weitere Runde),
aber „gedeckelt durch Erschöpfung" ist keine Regel, die vor dem ersten Lauf schriftlich steht.

## Entscheidung

### 1. Das kuratierte Relevanzurteil wird verlustfrei nach `metadata/curation.json` überführt

Neues Modul `src/research_graphrag/overview/curation.py` (Parser, analog zu
`bibliography.curated`, aber für die **wertenden** statt der bibliografischen Spalten) und
`scripts/migrate_curation.py` (Migration + `--check`-Verifikation). Zielort ist `metadata/`, nicht
`data/`: Derselbe Grund wie bei `paper_metadata.json` – der Ordner ist für **nicht
rekonstruierbare** Daten reserviert
([ADR 0025](0025-citable-paper-metadata.md)).

**Verlustfrei heißt wörtlich, nicht kategorisiert.** Jede kuratierte Zelle wird als Freitext
übernommen (`Relevanz fuer Expose` bleibt z. B. „Hoch (State-Diff-Reconciliation als Leitkonzept
für Rekonstruktion)", nicht nur „Hoch"); nur `SRQ-Zuordnung` wird zusätzlich in einzelne
Kennungen zerlegt, weil das die einzige Spalte ist, die tatsächlich eine Liste ist. Die
Zuordnung läuft über den Dateinamen (`Interner Link`) → `paper_id`, aus den Canonical-Papern
via `title_from_uri` – dieselbe Technik wie `bibliography.curated.records_from_curated`.

**Der Nachweis ist Zeile für Zeile geführt, nicht behauptet:** `scripts.migrate_curation --check`
parst `Übersicht.md` frisch und vergleicht jeden migrierten Datensatz gegen die geschriebene
Datei. Realer Lauf (2026-09-01, 606-Paper-Korpus): **131 kuratierte Zeilen, 131 einem
Korpus-Paper zugeordnet, 0 Abweichungen.**

Ein generischer Baustein (`column_index`, Kopfzellen-Suche über den Anfang des Labels) wandert
dabei von `bibliography.curated` nach `overview.drafts`, wo bereits `split_row`/`link_column`
liegen – sonst gäbe es eine **dritte** Implementierung derselben Tabellen-Kopfzeilen-Suche
(`bibliography.curated` importiert sie seither von dort, unverändertes Verhalten).

### 2. Der Intake schreibt keine neuen Zeilen mehr; `Übersicht.md` bleibt als historischer Stand erhalten

`intake.py` ruft `append_overview_rows` nicht mehr auf. `scripts/update_overview.py` verweigert
den Lauf standardmäßig (Exit 1, Hinweistext auf `metadata/curation.json`) und braucht das
ausdrückliche `--force` als Notfall-Fluchtweg. Die zugrundeliegende Funktion
`append_overview_rows` selbst bleibt **unverändert und vollständig getestet** – sie wird nicht
gelöscht, nur nicht mehr automatisch aufgerufen.

**Eine bestehende Zeile darf weiterhin umgebogen werden.** Löst ein eintreffender Volltext einen
Referenz-Eintrag ab (`docs/adr/0030`), bleibt `retarget_overview_row` aktiv: Eine **existierende**
Zeile auf einen neuen Dateinamen umzubiegen ist Konsistenzpflege am eingefrorenen historischen
Stand, kein neuer Eintrag. Trifft der Upgrade künftig einen Stub, für den nie eine Zeile
entstanden ist (weil er nach G4 aufgenommen wurde), bleibt das Umbiegen ein wirkungsloser
No-Op – kein Fehler, aber auch keine neue Information, die verloren ginge.

`Übersicht.md` selbst wird **nicht gelöscht oder gekürzt**. Sie bleibt als historischer Stand
bestehen (weiterhin durch [ADR 0027](0027-corpus-backup-phase11.md) gesichert) – ihr Inhalt ist
nach der Migration vollständig **reproduzierbar aus zwei Quellen** (`data/canonical/` für die
`Z`-Zeilen, `metadata/curation.json` für die kuratierten Werturteile), verliert aber ihre Rolle
als aktiv gepflegte, einzige Senke.

### 3. Stoppregel für den geplanten Referenz-Zufluss (Phase 14)

Drei Festlegungen, bevor Phase 14 den ersten Kandidaten übernimmt:

1. **Obergrenze je Runde.** Jeder Ernte-Lauf (`scripts.harvest_references --uebernehmen`, geplant
   in Phase 14 / E2) trägt eine harte Obergrenze `--limit`, deren Vorgabewert die in E0.2
   gemessene größte Menge ohne Guardrail-Totalverlust ist. G4 präzisiert: Diese Obergrenze ist ein
   **Maximum je Runde**, keine Empfehlung – sie darf nicht durch eine manuelle Übersteuerung nach
   oben umgangen werden, nur nach unten.
2. **Nutzenschwelle je Runde.** Nach jeder Runde wird ihr **Ertrag** gemessen: neue `CITES`-Kanten
   geteilt durch Zahl der in dieser Runde aufgenommenen Referenz-Einträge. Phase 13 / R0 hat
   bereits gezeigt, dass dieser Ertrag mit sinkender Priorität stark fällt (Top 10: 30,7
   Kanten/Eintrag; Top 100: 10,74; danach: 1,6) – eine **relative** statt einer absoluten
   Schwelle bleibt über wachsende Korpusgrößen hinweg gültig: **Eine Runde gilt als nicht mehr
   lohnend, wenn ihr eigener Ertrag unter 10 % des Ertrags der ersten (dichtesten) Runde des
   jeweiligen Korpusstands fällt.**
3. **Ausgewiesener Endzustand.** Der Bestand gilt als „vollständig genug für seine
   Fragestellung", sobald (a) **zwei aufeinanderfolgende Runden** die Nutzenschwelle verfehlen
   **oder** (b) eine Runde nicht einmal die harte Obergrenze erreicht, weil der Vorrat an
   lohnenden, noch nicht aufgenommenen Kandidaten selbst erschöpft ist. Beides wird mit Datum und
   den gemessenen Zahlen im E4-Statusblock von Phase 14 festgehalten – nicht stillschweigend
   angenommen. Ein späterer neuer Anlauf bleibt möglich, wächst der Korpus durch andere Zuflüsse
   (Phase 9, manuelle Ablage) weiter.

## Alternativen

- **`Übersicht.md` löschen oder auf die 131 kuratierten Zeilen kürzen.** Verworfen: Die `Z`-Zeilen
  sind zwar mechanisch reproduzierbar, ihr Verlust wäre aber ein unnötiger, destruktiver Schritt
  ohne Gegenwert – die Datei bleibt lesbarer historischer Kontext, ihre Rolle als aktive Senke
  endet trotzdem.
- **`append_overview_rows` vollständig entfernen statt nur ungenutzt zu lassen.** Verworfen: Die
  Funktion ist vollständig (11 Tests) abgesichert und ein legitimes, seltenes Notfall-Werkzeug
  (z. B. ein Fork mit fortgesetzt kuratierter Übersicht) – Löschen wäre Zerstörung ohne Nutzen für
  dieses Repo, während `--force` den Normalfall bereits verhindert.
- **Absolute Nutzenschwelle (feste Kantenzahl je Eintrag) statt relativer.** Verworfen: Eine feste
  Zahl (z. B. „< 5 Kanten/Eintrag") überfährt bei einem kleineren Korpus zu früh und bei einem
  sehr großen zu spät – die relative Schwelle (10 % der ersten Runde) skaliert mit dem
  tatsächlich gemessenen Ertragsverlauf.
- **`curation.json` unter `data/` statt `metadata/`.** Verworfen: `data/` ist als „abgeleitet,
  regenerierbar" definiert; das Relevanzurteil ist das Gegenteil.

## Konsequenzen

- **Positiv:** Das einzige menschliche Relevanzurteil ist maschinenlesbar, versioniert und
  Zeile-für-Zeile gegen den historischen Stand verifiziert; der Intake verliert eine
  Nebenwirkung (Schreiben in eine Datei, die ohnehin nicht mehr aktiv gepflegt wird); Phase 14
  bekommt eine geschriebene, falsifizierbare Stoppregel statt „bis es sich erschöpft".
- **Negativ / Aufwand:** `Übersicht.md` bleibt als (nun größtenteils historischer) Datenbestand
  im Repo liegen; ein zukünftiger Verbraucher von `metadata/curation.json` (Phase 14s
  Auswahlregel) muss erst noch gebaut werden – G4 liefert nur die Datenquelle, nicht die
  Auswahlregel selbst.
- **Folgeentscheidungen:** [ADR 0019](0019-corpus-intake-new-papers-phase8.md) (Übersicht als
  „einzige Senke" gilt nur noch für den historischen Bestand), [ADR 0027](0027-corpus-backup-phase11.md)
  (Sicherungsumfang um `metadata/curation.json` erweitert), [ADR 0030](0030-reference-entries-in-corpus-phase13.md)
  (Referenz-Einträge bekommen ebenfalls keine neue Zeile mehr) – alle drei per Nachtrag ergänzt,
  nicht stillschweigend umgangen.
