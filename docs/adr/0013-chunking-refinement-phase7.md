# 0013 – Chunking-Verfeinerung (Phase 7 / A3): Section-Absorption & Seiten-Range statt harter Seitengrenze

- **Status:** Akzeptiert
- **Datum:** 2026-08-01

## Kontext

Die [Roadmap.md](../../Roadmap.md) beschreibt für **Phase 7 / A3** die „Chunking-Verfeinerung gegen
die `short_chunk`-Flut": 2894 von 3074 Qualitäts-Flags sind `short_chunk`. Als Ursache nennt die
Roadmap die **harte Seiten-Chunk-Grenze** aus [ADR 0006](0006-canonical-model-phase2-scope.md) und
schlägt seitenübergreifendes Zusammenführen kurzer Rest-Chunks bzw. aggregierte Flags vor.

Eine Messung am realen Korpus (145 Paper, 14 397 Chunks) **widerlegt diese Ursachenannahme**:

| Befund | Wert |
| --- | --- |
| `short_chunk` gesamt | 2894 (20,1 % aller Chunks) |
| Nachfolge-Chunk liegt in einer **anderen Section** | **2472 (85,4 %)** |
| Nachfolge-Chunk = gleiche Section, **andere Seite** | 352 (12,2 %) |
| Größenschnitt / letzter Chunk des Papers | 39 / 31 (2,4 %) |

Die eigentliche Wurzel ist die **übersegmentierende Überschriften-Heuristik**: 9367 Sections auf
145 Papern (Median 50, Maximum 652), davon **4328 (46,2 %) mit weniger als 200 Zeichen Inhalt** und
**1919**, die aus genau einem zu kurzen Chunk bestehen. Als „Überschrift" erkannt werden u. a.
Pseudocode-Zeilen (`4 𝑥 ←𝑞.𝑝𝑜𝑝();`, `while 𝑞is not empty do`), Tabellenzellen (`Gpt-4 32.00%`)
und Silbentrennungsreste (`LITERATURECOLLECTION ANDTECHNOLOGI-`). Verantwortlich sind zwei Zweige
in `detect_heading`: der Numerierungs-Zweig (frisst Zeilennummern in Algorithmen) und der
Versal-Zweig (frisst Tabellenzellen und Running Header).

Ein zweiter Befund betrifft die Seitengrenze selbst: **2779** Seitenumbrüche liegen innerhalb einer
Section, davon **2213 (79,6 %) mitten im Satz**. Die harte Seitengrenze erzeugt also nicht nur
kurze Reste, sie zerschneidet systematisch Sätze – der Beleg-Snippet bricht mitten im Satz ab, und
die Term-Kookkurrenz, auf der TF-IDF beruht, wird über zwei „Dokumente" verteilt.

Simulation der Varianten auf den realen Canonical-Daten:

| Variante | Chunks | `short_chunk` | Median Zeichen | mehrseitige Chunks |
| --- | --- | --- | --- | --- |
| Ist-Zustand | 14 397 | 2894 (20,1 %) | 840 | 0 |
| A – nur Section-Absorption | 12 583 (−12,6 %) | 956 (7,6 %) | 1042 | 0 |
| B – nur Seiten-Merge | 13 412 (−6,8 %) | 2333 (17,4 %) | 992 | 963 (7,2 %) |
| **C – Absorption + Seiten-Merge** | **11 586 (−19,5 %)** | **441 (3,8 %)** | 1192 | 1000 (8,6 %) |

## Entscheidung

A3 wird auf die **tatsächliche Ursache** umgestellt und als **Variante C** umgesetzt. Vier
Bausteine, alle deterministisch und offline:

1. **Reject-Regeln in der Überschriften-Erkennung.** `detect_heading` weist Zeilen ab, die
   eindeutig keine Überschriften sind: Mathematik-/Pseudocode-Symbole (Pfeile, Mengenoperatoren,
   mathematische Alphanumerics `U+1D400–U+1D7FF`), tabellarische Zeilen (≥ 3 Felder über Tab oder
   Mehrfach-Leerzeichen), Silbentrennungsreste (Zeilenende `-`), Pseudocode-Enden (`;` / `,`) und
   ziffernlastige Zellen (Ziffern-/Prozentanteil über 30 %).
2. **Section-Absorption.** Ein erkannter Abschnitt, dessen **eigener Inhalt** unter
   `MIN_SECTION_CHARS` (200 Zeichen, gespiegelt zur Chunk-Untergrenze) liegt, wird deterministisch
   in seinen Vorgänger zurückgeführt; die überlebenden Abschnitte werden dicht neu numeriert.
   Geschützt sind `front`, `abstract` und `references` (sie tragen Qualitäts-Flags und den
   Zitationsgraphen aus [ADR 0011](0011-intra-corpus-citation-graph-phase7.md)); ebenso wird
   **nicht in einen `references`-Abschnitt hinein** absorbiert, damit Anhänge nicht als
   Bibliografie gelten. Die Entscheidung stützt sich auf die **gemessene Textmasse** statt darauf
   zu raten, welche Heuristik-Regel danebengriff.
3. **Seite ist kein Segmentierungskriterium mehr, sondern Provenienz-Range.** Der Chunk-Puffer
   bricht nur noch bei **Abschnittswechsel** oder **Größenlimit**. Der Chunk trägt zusätzlich
   `page_end`; `page_number` behält seine Bedeutung als **Startseite**, damit der
   Retrieval-Contract rückwärtskompatibel bleibt. Angezeigt wird „Seite 7" bzw. „Seiten 7–8".
4. **Aggregierte `short_chunks`-Flags.** `short_chunk:<chunk_id>` wird durch ein aggregiertes
   `short_chunks:<n>` je Paper ersetzt; `long_chunk:<chunk_id>` bleibt pro Chunk, weil selten und
   einzeln handlungsleitend (ein unteilbarer Übersatz).

Schema-Folgen (additiv, voller Re-Index – keine Migration):

- **Canonical JSON `0.2.0` → `0.3.0`** (`chunks[].page_end`; Abschnitts-/Chunk-Grenzen ändern sich).
  Bestehende Artefakte werden über die `schema_version`-Prüfung neu extrahiert.
- **Index `0.3.0` → `0.4.0`** (`chunks.page_end`).
- `Hit` und `Citation` erhalten `page_end` **additiv**; `Citation.to_dict()` hat damit 8 Schlüssel.

Der Frontmatter-Guard des Zitationsgraphen (`_front_matter_text`) prüft ab sofort
`page_end <= TITLE_PAGE_PAGES` statt `page_number <= TITLE_PAGE_PAGES` – also **strenger**: ein
Chunk, der von der Titelseite auf eine Folgeseite überläuft, gilt nicht mehr als Frontmatter. Ohne
diese Anpassung könnte eine zitierte fremde Kennung wieder als eigene gelten und die in
[ADR 0011](0011-intra-corpus-citation-graph-phase7.md) erkaufte Präzision untergraben.

`MIN_CHARS`/`MAX_CHARS` bleiben **unverändert** (200/1500), damit die Wirkung dieser Änderung
eindeutig zuzuordnen bleibt.

## Alternativen

- **A3 wörtlich umsetzen** (nur seitenübergreifendes Merging). Verworfen: adressiert 12,2 % der
  Fälle; die Akzeptanz „`short_chunk`-Anteil sinkt messbar" wäre nur kosmetisch erfüllt, während
  die Kosten (Seiten-Range im Schema, Contract-Fläche) voll anfallen.
- **Nur Flag-Aggregation.** Verworfen: kaschiert das Symptom, ohne Retrieval oder Provenienz zu
  verbessern – 2894 zerstückelte Chunks blieben bestehen.
- **Nur Section-Absorption (Variante A).** Erfüllt das Zielkriterium bereits (7,6 %), lässt aber
  2213 Chunk-Grenzen mitten im Satz stehen und verschenkt −19,5 % Chunkzahl. Da
  `TfidfIndex.load` den TF-IDF-Raum **pro Anfrage** neu aufbaut ([ADR 0005](0005-graphrag-index-backend-open.md),
  On-Read aus [ADR 0010](0010-drop-in-workflow-and-qa-phase6.md)), ist die Chunkzahl ein
  **Laufzeitfaktor je Anfrage**, nicht nur Build-Kosten.
- **Seiten-Merge nur, wenn der Satz nachweislich weiterläuft.** Verworfen: eine bedingte
  Sonderregel, deren Nutzen bei 79,6 % Satzschnitten marginal ist – die einfache Regel
  („Puffer bricht bei Abschnitt oder Größe") ist verständlicher und weniger Code.
- **`detect_heading` grundlegend neu schreiben.** Zurückgestellt: Die Absorption arbeitet
  evidenzbasiert (gemessene Textmasse) und ist damit robuster gegen unbekannte Layouts als weitere
  Regel-Akrobatik. Die verbleibende Titel-/Keyword-Säuberung bleibt **A5**.
- **Bounding-Boxes / GROBID für exakte Layoutgrenzen.** Unverändert zurückgestellt
  ([ADR 0006](0006-canonical-model-phase2-scope.md), Gruppe B in der [Roadmap.md](../../Roadmap.md)).

## Konsequenzen

- **Positiv:** `short_chunk`-Anteil sinkt von 20,1 % auf wenige Prozent; rund 2200 Chunk-Grenzen
  mitten im Satz entfallen; Chunk-Median rückt mit ~1200 Zeichen in das gewollte Zielfenster;
  über 20 % weniger Chunks senken Ladezeit und Speicher **jeder** Anfrage; die Abschnitts-Provenienz
  (`section_title`) wird spürbar weniger verrauscht; der Qualitätsreport wird wieder lesbar.
- **Negativ / Aufwand:** Ein Teil der Zitate nennt künftig eine Seiten-**Spanne** statt einer
  Einzelseite (die Nachprüfbarkeit bleibt erhalten, die Angabe ist ehrlicher als ein
  zerschnittener Absatz). Zwei Schema-Versionen steigen; alle `chunk_id`s verschieben sich, damit
  werden Index, Ähnlichkeitsgraph und Zitationskanten neu gebaut (ohnehin voller Re-Index).
  `Citation` bekommt ein achtes Feld – Tool-Specs und Shape-Tests ziehen nach (Präzedenz:
  `section_title` in [ADR 0008](0008-retrieval-and-query-router-phase4.md)).
- **Risiko & Gegenmaßnahme:** Eine strengere Heuristik könnte einen Referenzabschnitt verlieren und
  damit `CITES`-Kanten kosten. Gegenmaßnahme: `references` ist von der Absorption ausgenommen, und
  die Kennzahlen (Paper mit Referenzabschnitt, Kantenzahl) werden nach dem Re-Ingest gegen den
  Stand aus [ADR 0011](0011-intra-corpus-citation-graph-phase7.md) geprüft.
- **Folgeentscheidungen:** Die Bereinigung von Community-Keywords und den verbleibenden
  Abschnittstiteln bleibt **A5**; die quantitative Retrieval-Evaluation (Hit@k/MRR) bleibt **A6**
  und würde erlauben, den hier erreichten Effekt über den Proxy „Flag-Anteil" hinaus zu messen.

## Ergebnis nach der Umsetzung

Die obige Tabelle zeigt die **Simulation**, die der Entscheidung zugrunde lag. Der reale
Re-Ingest (145 Paper) bestätigt sie und fällt etwas günstiger aus:

| Kennzahl | vorher | nachher |
| --- | --- | --- |
| Chunks | 14 397 | **11 339** (−21,2 %) |
| `short_chunk`-Anteil | 20,1 % | **3,7 %** (423) |
| Chunk-Median | 840 | **1245** Zeichen |
| Sections (Median/Paper · Maximum) | 9367 (50 · 652) | **4406 (27 · 85)** |
| Qualitäts-Flags · geflaggte Paper | 3074 · 145 | **320 · 136** |
| Mehrseitige Chunks | 0 | **862 (7,6 %)**, maximale Spanne 4 |

Belege für die zentralen Behauptungen dieses ADR:

- **Die Seite erzeugt keine Chunk-Grenze mehr.** Von 1963 Chunk-Grenzen, die auf einen
  Seitenwechsel fallen, sind **alle 1963 durch `MAX_CHARS` erzwungen** (die Summe beider Chunks
  überschreitet das Zielfenster) – keine einzige ist seitenbedingt.
- **Kein Textverlust durch das Zusammenführen.** Auf einer Stichprobe von 20 realen PDFs stimmt
  der zeichenweise Inhalt der Chunks exakt mit dem der Fließtext-Blöcke überein; ein
  Property-Test über 250 generierte Blockfolgen bestätigt das zusätzlich.
- **Übergroße Chunks bleiben unteilbare Einzelsätze** – die Begründung dafür, `long_chunk` weiter
  pro Chunk zu führen, ist am Korpus geprüft.
- **Determinismus:** erneute Extraktion **145/145** textidentisch; Rebuild von Index,
  Ähnlichkeitsgraph und Zitationskanten byte-identisch zum Live-Index.

Das eingangs benannte **Risiko für den Zitationsgraphen** hat sich nicht materialisiert – im
Gegenteil: Der Referenzabschnitt wird nicht mehr von Pseudo-Überschriften abgeschnitten, deshalb
steigen die `CITES`-Kanten von **158 auf 256** (arXiv 149, Titel 104, DOI 3) bei unverändert
**143/145** erkannten Referenzabschnitten. Die Präzision wurde erneut geprüft: **256/256** Kanten
sind mechanisch im Referenztext der Quelle belegt, jede ID-Kante zeigt weiterhin auf eine
selbst-belegte Kennung, eine Kontext-Stichprobe (12 Kanten über alle drei Methoden) war
**12/12** korrekt, und nur ein einziges Paper (ein 102-seitiger Survey) hat einen
Referenzanteil über 50 % des Textes.

**Bekannte Grenze (unverändert):** Der angestrebte Sections-Median von ≤ 25 wird mit **27** knapp
verfehlt. Ein Dokument, dessen Seiten zwar Text enthalten, aber keinen Fließtext ergeben
(z. B. nur Überschriftenzeilen), erzeugt **0 Chunks und dennoch kein Qualitäts-Flag** – eine
vorbestehende Lücke des Flag-Katalogs aus [ADR 0006](0006-canonical-model-phase2-scope.md), die im
realen Korpus nicht auftritt (jedes Paper hat mindestens 20 Chunks).
