# 0025 – Zitierfähige Paper-Metadaten: eigene Quelle, Autoritätskette, Durchreichung

- **Status:** Akzeptiert
- **Datum:** 2026-08-05

## Kontext

Das Werkzeug wird begleitend zu einer wissenschaftlichen Arbeit genutzt. Zwei Anforderungen
folgen daraus, die bisher **nicht** erfüllt sind:

1. Ein Agent, der über den MCP-Server sucht, soll zu jedem Beleg einen **extern auflösbaren
   Identifikator** bekommen – nicht nur eine interne `paper_id` und einen lokalen Dateipfad.
2. Aus einem Fund soll sich **unmittelbar korrekt zitieren** lassen (Harvard und APA), ohne dass
   der Identifikator erst von Hand aufgelöst und die Literaturangabe manuell gebaut wird.

### Gemessene Ausgangslage statt Vermutung

Nach der in [ADR 0013](0013-chunking-refinement-phase7.md), [ADR 0015](0015-noise-reduction-keywords-and-sections-phase7.md)
und [ADR 0021](0021-local-multi-seed-phase10.md) etablierten Reihenfolge liefen **vor jeder
Code-Änderung** read-only Messungen gegen den realen Korpus (341 Paper, Stand 2026-08-05).

**Befund 1 – die Ausgabe deckt heute 1 von 8 Werkzeugen ab.** Nur `get_paper` liefert
`identifiers`. `Citation` (Basic/Local/DRIFT), `PaperRef` (Global), `CitationLink`
(`get_citations`) und `EvidenceItem` (`answer_question`) tragen ausschließlich `paper_id` und
`source_uri` – letzteres ein `file:`-Pfad. Der Zitier-Contract aus
[ADR 0012](0012-llm-bridge-and-answer-synthesis-phase7.md) verlangt Marken `[1]`, `[2]` …, die
damit auf nichts extern Auflösbares zeigen.

**Befund 2 – die Abdeckung ist hoch, die Verlässlichkeit ist ungemessen.**

| Kennzahl (341 Paper) | Wert |
| --- | --- |
| mit mindestens einem Identifikator | 329 (96,5 %) |
| ohne jeden Identifikator | 12 |
| auf der eigenen Titelseite belegt (Frontmatter-Guard aus [ADR 0011](0011-intra-corpus-citation-graph-phase7.md)) | ≈ 284 |
| **nicht belegt → Volltext-Fallback-Verdacht** | **≈ 45** |
| Identifikatoren mit mehr als einem Träger | 9, u. a. `2108.07732` (3×, der MBPP-Falsch-Hub), `10.1145/nnnnnnn.nnnnnnn` (2×, ACM-Vorlage) |

Dazu Präzisionsdefekte der Extraktions-Regex: abgeschnittene DOIs wie `10.1109/TKDE.2023`.

**Befund 3 – es gibt bereits eine bessere Quelle, die maschinell ungenutzt bleibt.** Die
kuratierte [Übersicht.md](../../Übersicht.md) trägt in der Spalte
`Externer Link/Indetifikator`:

| Herkunft der Zeile | mit externer Angabe | ohne |
| --- | --- | --- |
| **kuratiert** (Phase-1-Migration) | 129 | 2 |
| **Entwurf** (`Z…`, aus dem Intake) | 200 | 16 |

Die 200 Entwurfszeilen sind **keine** unabhängige Quelle – `overview/drafts._external_link`
schreibt dort die extrahierten Werte samt Fehlern hinein. Bei den 129 kuratierten Zeilen weichen
jedoch **29** von der Extraktion ab, und zwar aus zwei verschiedenen Gründen:

- **legitim:** Die Übersicht nennt den *Publisher*-DOI, die Extraktion die *arXiv*-ID desselben
  Papers (E1: `10.18653/v1/2025.findings-acl.373` vs. `arXiv:2503.06689`). Beide sind korrekt,
  aber für eine Literaturangabe ist der Publisher-DOI der richtige.
- **falsch:** E10 hat `2108.07732` extrahiert (wieder der MBPP-Hub) statt `2408.11081`; E8
  `1910.02216` statt `2401.03065`.

**Daraus folgt die Leitlinie dieses ADR:** Für Retrieval ist die Extraktion gut genug, für
Zitation nachweislich nicht. Ein *falscher* DOI in einer wissenschaftlichen Arbeit ist schlimmer
als *kein* DOI. Deshalb wird nicht die Extraktion „verbessert", sondern eine **zweite, bessere
Quelle** eingeführt und die Herkunft jedes Wertes **ausgewiesen**.

## Entscheidung

### 1. Eine eigene, versionierte Metadatenquelle: `metadata/paper_metadata.json`

Die Zitationsdaten liegen **nicht** unter `data/`. Dieser Ordner ist per `.gitignore` als
„abgeleitet, regenerierbar" definiert – Zitationsdaten sind es nicht: Sie enthalten kuratierte
und extern aufgelöste Wahrheit, die sich aus den PDFs **nicht** rekonstruieren lässt. Sie liegen
deshalb in einem eigenen, **versionierten** Ordner `metadata/`, analog zu `eval/`. Das schließt
zugleich die in [Roadmap-Punkt B1](../../Roadmap.md) benannte Lücke für genau diese Daten.

### 2. Getrennte Datensätze je Herkunft, ein aufgelöster Datensatz je Paper

Gespeichert wird **je Herkunft ein Datensatz** (`MetadataRecord`), nicht ein vermischter. Die
vier Herkünfte in absteigendem Vorrang:

| Herkunft | Quelle | Vertrauen |
| --- | --- | --- |
| `manual` | von Hand in `metadata/paper_metadata.json` gepflegt | höchste |
| `curated` | Spalte `Externer Link/Indetifikator` kuratierter Zeilen der Übersicht | hoch |
| `resolved` | Online-Auflösung ([ADR 0026](0026-online-metadata-resolution.md)) | mittel |
| `extracted` | Regex auf der Titelseite des PDF | niedrig |

Der **effektive** Datensatz (`PaperMetadata`) wird **feldweise** aufgelöst: je Feld gewinnt die
erste Herkunft mit nicht-leerem Wert. Das ist notwendig, weil die Quellen komplementär sind – die
Übersicht kennt den Publisher-DOI, aber weder Autoren noch Venue; die Online-Auflösung kennt
beides. Welche Herkunft je Feld gewonnen hat, wird in `origins` mitgeführt und ausgegeben
(Grundsatz „Provenienz zuerst", [CONTRIBUTING](../../CONTRIBUTING.md)).

Nur `curated`-Zeilen der Übersicht zählen als Quelle. Entwurfszeilen (`Z…`) werden **ignoriert**,
weil sie die Extraktion spiegeln und sonst eine Scheinbestätigung erzeugen würden.

### 3. Preprint und Version of Record werden beide geführt

`doi` und `arxiv_id` stehen nebeneinander; keiner verdrängt den anderen. Für die Literaturangabe
gilt eine feste Reihenfolge: **DOI vor arXiv-ID vor URL**. Damit ist der in Befund 3 gezeigte
„Konflikt" aufgelöst, ohne Information zu verlieren.

### 4. Die Metadaten wandern in den Index – im bestehenden atomaren Fenster

Neue Tabelle `paper_metadata` in `data/index/index.sqlite`, gebaut von
`indexing/metadata_index.build_metadata_index` **innerhalb** von
`pipeline._build_index_atomically` (Muster von `build_graph` und `build_citation_graph`, siehe
[ADR 0010](0010-drop-in-workflow-and-qa-phase6.md)). Der Index bleibt damit die einzige
Lesequelle des Retrievals; kein Werkzeug liest zur Abfragezeit Markdown oder JSON.

Index-Schema **0.4.0 → 0.5.0**, additiv. Voller Re-Index genügt, **keine** Migration. Der
Canonical-Cache bleibt **unberührt** (Schema 0.4.0) – es ist kein Re-Extract nötig, weil die
extrahierten Identifikatoren bereits vorliegen.

### 5. Durchreichung: schlank an jedem Beleg, vollständig an den Zitier-Stellen

| Ebene | Ergänzung |
| --- | --- |
| `Hit`, `Citation`, `PaperRef`, `EvidenceItem`, `CitationLink` | `identifiers` (DOI/arXiv/URL) und `citation_key` |
| `AnswerResult` / `SynthesisResult` (`answer_question`) | zusätzlich `references`: je vorkommendem Paper der **vollständige** Datensatz inkl. fertiger Harvard- und APA-Angabe |
| `PaperDetail` (`get_paper`) | zusätzlich `reference` mit demselben vollständigen Datensatz |
| neues Werkzeug `get_reference` | Literaturangabe und In-Text-Zitat zu einer `paper_id` |

Bewusst **nicht** in jedes einzelne Chunk-Zitat kopiert wird die Vollform: Fünf Belege desselben
Papers würden die Angabe fünfmal tragen. Der Identifikator ist selbsttragend, die Vollform holt
sich der Agent an genau einer Stelle.

Alle Erweiterungen sind **additiv**; bestehende Schlüssel bleiben erhalten. Die betroffenen
Tool-Spezifikationen werden auf die nächste Minor-Version gehoben.

### 6. Zwei Zitationsstile, extraktiv erzeugt

`bibliography/styles.py` erzeugt **Harvard** und **APA (7.)** deterministisch aus den Feldern –
ohne LLM, konform zu [ADR 0005](0005-graphrag-index-backend-open.md). Fehlen Autoren, Titel oder
Jahr, wird die Angabe **als unvollständig markiert** statt geraten (`is_citable() == False`).

> **Zum Paketnamen:** Das neue Unterpaket heißt `bibliography/`, nicht `citation/` – im Repo
> bezeichnet „Citation" bereits zwei andere Dinge: den Provenienz-Typ
> `retrieval.provenance.Citation` und den Zitationsgraphen aus
> [ADR 0011](0011-intra-corpus-citation-graph-phase7.md).

## Alternativen

- **Extraktions-Regex härten statt zweiter Quelle.** Verworfen: Der Fehler liegt nicht in der
  Regex, sondern in der Aufgabe – die Titelseite eines Preprints kennt den Publisher-DOI nicht,
  und Autoren/Venue sind aus dem PDF-Text nicht zuverlässig zu gewinnen (das wäre GROBID, siehe
  [ADR 0005](0005-graphrag-index-backend-open.md)).
- **Metadaten ins Canonical JSON schreiben.** Verworfen: Das vermischt „aus dem PDF gelesen" mit
  „von außen geholt", erzwingt einen Schema-Bump samt Re-Extraktion des gesamten Korpus und macht
  kuratierte Handarbeit zu einem regenerierbaren Artefakt – sie läge dann im gitignorierten
  `data/`.
- **Vollständige Zitation in jedes `Citation`-Objekt.** Verworfen wegen Redundanz (siehe
  Punkt 5); der Nutzen ist identisch, der Antwortumfang deutlich größer.
- **Die Übersicht zur Laufzeit lesen.** Verworfen: Das Retrieval liest ausschließlich den Index;
  ein zweiter Lesepfad wäre ein Konsistenzrisiko und würde jede Antwort von einer editierbaren
  Markdown-Datei abhängig machen.
- **Nur DOI/arXiv statt vollständiger Zitationsdaten.** Verworfen auf ausdrücklichen Wunsch:
  Mit dem Identifikator allein muss die Literaturangabe weiterhin von Hand gebaut werden – genau
  der Schritt, der entfallen soll.

## Konsequenzen

- **Positiv:** Jeder Beleg trägt einen extern auflösbaren Identifikator; die Literaturangabe
  entsteht ohne Handarbeit; die Herkunft jedes Feldes ist nachvollziehbar; kuratierte Arbeit ist
  erstmals versioniert und maschinell wirksam.
- **Negativ / Aufwand:** Ein neuntes Werkzeug und ein neuntes Unterpaket (`bibliography/`); fünf
  Ausgabe-Contracts werden additiv breiter; ein voller Re-Index ist nötig (kein Re-Extract).
- **Bekannte Grenze:** Ohne Online-Auflösung tragen nur wenige Paper Autoren und Venue – die
  Angabe bleibt dann unvollständig und wird als solche markiert. Diese Lücke schließt
  [ADR 0026](0026-online-metadata-resolution.md).
- **Folgeentscheidung:** [ADR 0026](0026-online-metadata-resolution.md) (Online-Auflösung).
