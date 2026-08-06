# 0027 – Sicherung des Korpus: Quelle sichern, Ableitung verwerfen

- **Status:** Akzeptiert
- **Datum:** 2026-08-06

## Kontext

Der gesamte Bestand des Werkzeugs hängt an zwei Ordnern **einer** Maschine: `papers/` und `data/`
sind bewusst nicht versioniert (`.gitignore`). Drei Entwicklungen haben das Risiko seit der
Festlegung dieses Punktes in der [Roadmap](../../Roadmap.md) verschärft:

1. **Phase 8 löscht.** Der Intake entfernt bei einem bitgenauen sha256-Treffer die eingehende
   Datei unwiderruflich ([ADR 0019](0019-corpus-intake-new-papers-phase8.md)).
2. **Phase 9 lässt den Bestand wachsen.** Die Online-Kandidatensuche führt systematisch neue
   Paper zu ([ADR 0020](0020-online-candidate-search-phase9.md)).
3. **Phase 12 erzeugt handgepflegte Daten.** Einträge der Herkunft `manual` in
   `metadata/paper_metadata.json` sind aus **keiner** anderen Quelle wiederherstellbar
   ([ADR 0025](0025-citable-paper-metadata.md)).

Hinzu kommt eine Erfahrung aus dem Repository selbst: Zweimal sind bereits vollständige
Arbeitsstände verschwunden – die erste Fassung der LLM-Bridge und der Stand zur visuellen
Korpus-Exploration, von dem nur noch Bytecode existiert (im
[ADR-Register](README.md) als Lücke bei `0024` vermerkt). Beide Male traf es Dateien, die noch
nicht committet waren.

### Gemessene Ausgangslage statt Vermutung

Nach der in [ADR 0013](0013-chunking-refinement-phase7.md) und
[ADR 0021](0021-local-multi-seed-phase10.md) etablierten Reihenfolge stand die Messung **vor**
der Entscheidung (realer Stand 2026-08-06, 341 Paper).

**Befund 1 – der Wert liegt fast vollständig in den PDFs.**

| Artefakt | Größe | rekonstruierbar aus |
| --- | --- | --- |
| `papers/` (341 PDFs) | **712,4 MB** | **nichts** |
| `data/canonical/` | 34,2 MB | `papers/` (deterministisch) |
| `data/index/` | 34,5 MB | `data/canonical/` (deterministisch) |
| `data/manifest.json` | 71 KB | `papers/` (Neuberechnung der Hashes) |
| `data/intake_log.md` | 74 KB | **nichts** (Protokoll der Löschungen) |
| `data/metadata_log.md` | 151 KB | nur mit Netz |
| `data/online_candidates.md` | 851 KB | nur mit Netz |
| [`Übersicht.md`](../../Übersicht.md) | 221 KB | **nichts** (kuratierte Wertung) |
| `metadata/paper_metadata.json` | 222 KB | `manual`-Felder: **nichts** |

Die abgeleiteten Anteile (`canonical/` + `index/`) machen 68,7 MB aus – **8,7 %**. Sie
wegzulassen ist damit **kein Platzargument**.

**Befund 2 – die zweite Hälfte der Akzeptanz ist bereits erfüllt.** Die Roadmap verlangt „ein
`--dry-run` überall dort, wo gelöscht wird". Ein Scan aller löschenden Aufrufe unter
`src/research_graphrag/` ergibt genau vier Stellen mit Nutzerwirkung – alle vier in
`intake.py` (zwei `unlink`, zwei `shutil.move`), und `scripts.intake` besitzt `--dry-run`
bereits seit Phase 8. Die übrigen Treffer sind Temporärdateien atomarer Schreibvorgänge
(`os.replace`-Muster) sowie das Verwerfen **abgeleiteter** Artefakte (veraltetes Canonical in
`pipeline._remove_stale_canonical`, Index-Datei beim vollen Re-Build). Für B1 ist hier **nichts
zu bauen**, nur nachzuweisen.

## Entscheidung

**1. Zwei Klassen statt eines Ordner-Abbilds.** Gesichert wird ausschließlich, was **Quelle**
ist; alles deterministisch Ableitbare bleibt draußen. Der Sicherungsumfang ist damit:

| Gesichert | Begründung |
| --- | --- |
| `papers/**` | die Quelle von allem |
| [`Übersicht.md`](../../Übersicht.md) | kuratierte Wertung, nicht reproduzierbar |
| `metadata/paper_metadata.json` | Herkunft `manual` ist nicht reproduzierbar |
| `data/manifest.json` | Dedup-Grundlage des Intake |
| `data/intake_log.md` | Protokoll der unwiderruflichen Löschungen |
| `data/metadata_log.md`, `data/online_candidates.md` | append-only Berichte eines vergangenen Netzzustands |

**Nicht** gesichert werden `data/canonical/`, `data/index/`, `data/quality_report.*` und
`data/online_raw/`. Der Grund ist **Korrektheit, nicht Platz**: Eine Sicherung, die einen
fertigen Index enthält, verleitet dazu, ihn zurückzuspielen – und damit einen Index, der nicht
zum wiederhergestellten `papers/` passen muss. Der Wiederherstellungsweg ist deshalb bewusst
**genau einer**: Dateien zurückkopieren, dann `python -m scripts.ingest`. Dass dieser Weg
deterministisch zum selben Ergebnis führt, ist in [ADR 0013](0013-chunking-refinement-phase7.md)
und [ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md) byte-genau belegt.

> Damit wird der Wortlaut der Roadmap („`papers/`, `Übersicht.md` und `data/manifest.json`")
> **präzisiert**: Er stammt aus der Zeit vor Phase 9 und Phase 12; die drei append-only
> Protokolle und die Zitationsdaten sind seither hinzugekommen und ebenfalls nicht
> reproduzierbar.

**2. Ein Kopierlauf mit Prüfsummen-Nachweis, kein Archivformat.** Ziel ist ein Verzeichnis, in
dem die Dateien unter ihren Originalpfaden liegen, plus ein `backup_manifest.json` mit sha256,
Größe und Zeitpunkt je Datei. Das erlaubt eine Wiederherstellung mit Bordmitteln (Kopieren) und
macht die Sicherung **prüfbar**.

**3. Der Lauf ist idempotent.** Eine Datei, die am Ziel bereits mit identischem sha256 liegt,
wird übersprungen. Ein zweiter Lauf kopiert daher nichts und ist in Sekunden fertig – das ist
die Voraussetzung dafür, dass die Sicherung regelmäßig läuft statt einmalig.

**4. Drei Betriebsarten.** `--dry-run` zeigt den Lauf, ohne zu schreiben; der Standardlauf
sichert; `--pruefen` rechnet die Prüfsummen des Ziels gegen das Manifest nach und meldet
Abweichungen mit Exit-Code `1`. Ein Sicherungsstand, der nie geprüft wurde, ist keine Sicherung.

**5. Das Ziel darf nicht im Repository liegen.** Ein Ziel innerhalb der Arbeitskopie führt zu
`invalid_input`. Andernfalls würde die Sicherung Teil des gesicherten Bestandes und bei jedem
Lauf wachsen.

**6. Kein MCP-Werkzeug.** Wie beim Intake ([ADR 0019](0019-corpus-intake-new-papers-phase8.md),
Abschnitt 7) gehört eine Operation, die massenhaft Dateien schreibt, nicht in die autonome
Reichweite eines Agenten. Der Server bleibt bei **neun** Werkzeugen.

**7. Kein Zeitplan, keine Rotation, kein Framework.** Wann gesichert wird, entscheidet der
Nutzer; eine Aufbewahrungslogik hätte ohne Automatisierung keinen Adressaten. Das entspricht dem
Right-sizing aus [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Alternativen

**Ein Archiv (ZIP/7z) statt eines Verzeichnisses.** Verworfen: PDFs sind bereits komprimiert, der
Gewinn wäre gering; dafür verliert man die Idempotenz (jeder Lauf schreibt 712 MB neu), die
Teilwiederherstellung einzelner Dateien und die Prüfbarkeit mit Bordmitteln.

**Den gesamten Ordner `data/` mitsichern.** Verworfen, siehe Entscheidung 1: Der Platzgewinn ist
mit 8,7 % nebensächlich, das Risiko eines zurückgespielten, nicht passenden Index dagegen real.

**`git-lfs` oder ein externes Sicherungswerkzeug.** Verworfen: Ohne PyPI-/Mirror-Zugang
([ADR 0002](0002-venv-and-offline-dependency-strategy.md)) ist nichts zu beschaffen, und 712 MB
Binärdaten gehören nicht in die Historie eines Repositories, das ansonsten aus Text besteht.

**Eine Wiederherstellungsfunktion (`--restore`) mitliefern.** Verworfen: Das Zurückkopieren ist
ein Einzeiler des Betriebssystems, aber ein automatisches Zurückschreiben **in** `papers/` wäre
eine zweite überschreibende Operation. Der Weg wird stattdessen in
[data/README.md](../../data/README.md) beschrieben.

## Konsequenzen

- **Positiv:** Der nicht reproduzierbare Teil des Bestandes (712 MB PDFs plus 1,6 MB kuratierte
  und protokollierte Daten) ist mit einem Befehl sicherbar und mit einem zweiten prüfbar. Die
  Trennung Quelle/Ableitung macht zugleich sichtbar, was das System eigentlich besitzt.
- **Positiv:** Die Sicherung ist idempotent und damit wiederholbar, ohne jedes Mal den vollen
  Bestand zu schreiben.
- **Negativ / Aufwand:** Die Sicherung läuft **nicht** automatisch. Wird sie nicht gestartet,
  schützt sie nicht. Das ist eine bewusste Right-sizing-Entscheidung, kein Versehen.
- **Negativ / Aufwand:** Nach einer Wiederherstellung muss `python -m scripts.ingest` laufen
  (Größenordnung Minuten), bevor gesucht werden kann.
- **Folgeentscheidungen:** keine. Der Punkt berührt weder ein Schema noch einen Contract; es gibt
  **keinen** Re-Ingest und keine Änderung an einem Werkzeug.
