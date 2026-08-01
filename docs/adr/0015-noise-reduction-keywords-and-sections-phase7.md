# 0015 – Rausch-Reduktion (Phase 7 / A5): Textnormalisierung, Bibliografie-Rejects & Keyword-Politik

- **Status:** Akzeptiert
- **Datum:** 2026-08-01

## Kontext

Die [Roadmap.md](../../Roadmap.md) beschreibt für **Phase 7 / A5** die „Rausch-Reduktion bei
Keywords & Section-Provenienz". Der Punkt gilt als *teilweise* erledigt: die Übersegmentierung der
Überschriften-Heuristik wurde in A3 ([ADR 0013](0013-chunking-refinement-phase7.md)) adressiert
(Maximum 652 → 85 Sections je Paper). Offen sind laut Roadmap die **Keyword-Bereinigung**
(„Rauschen wie et/al/arxiv/Jahreszahlen/OCR-Ligaturen wie `uni00000013`") und die **verbleibenden
verrauschten Abschnittstitel**. Als Akzeptanz nennt die Roadmap „kuratierte Domänen-Stopwords +
Token-Filter (rein numerische Token/Ligatur-Artefakte)".

Wie bei A3 wurde vor der ersten Code-Zeile am realen Korpus gemessen (145 Paper, 11 339 Chunks,
43 Communities). Die Messung bestätigt das Rauschen, **präzisiert aber die Ursachenannahme der
Roadmap an zwei Stellen**.

### Befund 1 – Keyword-Rauschen ist ein Artefakt der Summen-Rangfolge, nicht des Vektorraums

Von 430 Keyword-Slots sind 26 (6,0 %) eindeutig Rauschen; sie treffen die **größte** Community
besonders hart (4 von 10 Slots: `al`, `et`, `arxiv`, `2024`). Die Ursache ist messbar:

| Term | Dokumentfrequenz | aggregierte TF-IDF-Masse |
| --- | --- | --- |
| `al` | 143 / 145 | 7,87 |
| `et` | 142 / 145 | 7,70 |
| `arxiv` | 139 / 145 | 6,73 |
| `2024` | 123 / 145 | 5,92 |

Bei einer Dokumentfrequenz nahe *N* ist die IDF ≈ 0 – für die **paarweise Ähnlichkeit** sind diese
Terme praktisch bedeutungslos. Die Keyword-Auswahl summiert jedoch über alle Paper einer Community,
und dort schlägt die hohe Termfrequenz durch. Das Problem sitzt damit in der **Auswahlpolitik**,
nicht im Ähnlichkeitsmodell.

### Befund 2 – „Ligatur-Artefakte" sind zwei verschiedene Phänomene

Die Roadmap nennt `uni00000013` als Beispiel für „Ligatur-Artefakte" und schlägt vor, solche Token
zu **filtern**. Die Messung trennt zwei Fälle mit gegensätzlicher Behandlung:

| Artefakt | Vorkommen | Bewertung |
| --- | --- | --- |
| `/uniXXXXXXXX` (Glyph-Indizes einer subsettierten Font) | 1615 in 10 Chunks / 4 Papern | nicht dekodierbar → **entfernen** |
| Typografische Ligaturen `ﬁ ﬂ ﬀ ﬃ` | **3628** Zeichen in 533 Wörtern, 764 Chunks (6,7 %), 22 Paper | tragen Inhalt → **reparieren** |

Die Ligaturen sind kein Anzeigeproblem, sondern ein **Retrieval-Defekt**: `conﬁguration` (209×),
`ﬁle`/`ﬁles` (404×), `veriﬁcation` (133×) und `ﬂow` (100×) sind für die Anfragen `configuration`,
`file`, `verification`, `flow` unauffindbar – auch für das in
[ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md) eingeführte BM25. Ein Keyword-Filter würde
diese Wörter zusätzlich noch *löschen*; heute sind `ﬂow` und `bertoverﬂow` reguläre
Community-Keywords.

### Befund 3 – Verrauschte Abschnittstitel entstehen überwiegend in der Bibliografie

425 von 2838 distinct Abschnittstiteln tragen ein Verdachtsmerkmal – Bibliografie- oder
Code-Fragmente wie `(Issre). Ieee, 104–115.`, `[Online]. Available: https://arxiv.org/abs/2306.10998`
oder `"metadata": {title, authors, journal, …}`. Davon fallen **267** auf die vier Merkmale, die
unten zu Reject-Regeln werden (Satzpunkt-Ende, URL/DOI, `et al`, Code-Zeichen); der Rest ist
weicher Verdacht (etwa sehr kurze oder ziffernlastige Titel). Bei **114 von 145** Papern folgt
mindestens ein
Abschnitt *nach* dem Beginn des Referenzabschnitts. Der dominierende Mechanismus ist der
**Numerierungs-Zweig** von `detect_heading`, der die laufende Nummer eines Literatureintrags als
Abschnittsnummer liest: aus `27. REALM: Retrieval-Augmented Language Model Pre-training.
InProceedings` wird eine Überschrift. Damit wird der Referenzabschnitt zerschnitten – dieselbe
Wurzel, die in A3 den unerwarteten Sprung von 158 auf 256 `CITES`-Kanten verursacht hat.

## Entscheidung

A5 wird in **drei Bausteinen** umgesetzt, alle deterministisch und offline.

### 1. Textnormalisierung bei der Extraktion (neu: `extraction/normalization.py`)

`extract_pdf` normalisiert jeden Seitentext, **bevor** Struktur-Analyse, Chunking und
Qualitäts-Gates darauf arbeiten:

- **Ligatur-Reparatur** über eine feste Zeichen-Map (`U+FB00`–`U+FB06` → `ff`, `fi`, `fl`, `ffi`,
  `ffl`, `st`).
- **Entfernen der Glyph-Artefakte** `/uniXXXXXXXX`. In Zeilen, aus denen Artefakte entfernt wurden,
  werden die zurückbleibenden Leerraum-Ketten zu einem Leerzeichen zusammengefasst – sonst würden
  sie die Tabellen-Heuristik (`looks_tabular`, ≥ 3 Felder über Mehrfach-Leerzeichen) auslösen.

Bewusst **kein** pauschales `unicodedata.normalize("NFKC")`: NFKC bildet auch die mathematischen
Alphanumerics `U+1D400–U+1D7FF` auf ASCII ab (`𝑥` → `x`) und würde damit exakt die
Pseudocode-Reject-Regel aus [ADR 0013](0013-chunking-refinement-phase7.md) aushebeln – die
Übersegmentierung käme zurück. Die Map ist klein, verlustfrei und explizit.

### 2. Bibliografie-Rejects in der Überschriften-Erkennung (`extraction/structure.py`)

Eine Regel greift **vor** dem `_KNOWN_SECTIONS`-Zweig, vier danach in `_is_rejected`:

| Regel | Position | Verwirft | Belege (Stichprobe außerhalb der Referenzen) |
| --- | --- | --- | --- |
| Kleingeschriebener Zeilenrest mit Satzzeichen | **vor** dem Schlüsselwort-Zweig | `methods.`, `evaluation.`, `model.` | Teil der 35 Satzzeichen-Treffer |
| Satzpunkt am Zeilenende (`.` in `_REJECT_TAIL`) | in `_is_rejected` | `Llm.`, `31715. Pmlr.` | 35 Treffer (mit der Regel oben) |
| Bibliografie-/URL-Marker (`http://`, `https://`, `www.`, `doi:`, `doi.org/`, `arxiv:`) | in `_is_rejected` | `https://github.com/xlab-si/xopera-opera` | 13 Treffer |
| Zitat-Muster `et al` | in `_is_rejected` | `(Singhal et al., 2023). While many are fine-tuned` | 7 Treffer |
| Code-/JSON-Zeichen (`" { } [ ] = < > \|`) | in `_is_rejected` | `"Insert Question"`, `Kg= Φ(D),(1)` | 72 Treffer |

Die **erste** Regel ist nötig, weil `_is_rejected` den Schlüsselwort-Zweig gar nicht erreicht: Eine
Fließtextzeile, die zufällig nur `methods.` oder `evaluation.` enthält, wird sonst als bekannter
Abschnitt gelesen – in der Messung hingen daran bis zu 6166 Zeichen falsch zugeordneter Text. Sie
ist eng gefasst (**unnumeriert**, beginnt mit einem **Kleinbuchstaben**, endet auf einem
Satzzeichen), damit `METHODS.`, `Abstract.` und `3. Methods` unberührt bleiben – echte
Überschriften beginnen nicht klein.

Die übrigen vier greifen wie in A3 **nach** dem `_KNOWN_SECTIONS`-Zweig, damit `Abstract` und
`References` in ihrer üblichen Schreibweise niemals verworfen werden.

Dazu **eine Kontextregel**: **innerhalb eines `references`-Abschnitts ist der Numerierungs-Zweig
deaktiviert.** Eine nummerierte Zeile ist dort ein Literatureintrag, keine Überschrift. Der
`_KNOWN_SECTIONS`-Zweig und der Versal-Zweig bleiben aktiv, damit ein nachfolgender `Appendix` den
Referenzabschnitt weiterhin beendet.

### 3. Keyword-Politik als Nachfilter (neu: `keywords.py`)

Ein Querschnittsmodul (neben `errors.py`) bündelt die kuratierten Domänen-Stopwords und den
Token-Filter (rein numerische Token inkl. Jahreszahlen, `uniXXXXXXXX` defensiv). Es wird von
`indexing/graph_index.py` (Community-Keywords) und `overview/drafts.py` (Entwurfszeilen) genutzt –
**eine** Politik, zwei Aufrufer, keine neue Schichtkante zwischen `overview/` und `indexing/`.

Der Filter greift **vor** dem Top-*k*-Schnitt: die verdrängten Rausch-Slots werden durch echte
Terme aufgefüllt statt gestrichen.

Der Filter gilt **ausschließlich für den Keyword-/Anzeigepfad**, nie für das Retrieval. Der
`CountVectorizer` in `indexing/tfidf_index.py` bleibt bewusst ohne Stopwords, damit Fakt-Anfragen
nach Jahreszahlen, DOIs oder Abkürzungen weiterhin treffen ([ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md)).

### Schema-Folgen

- **Canonical-Schema 0.3.0 → 0.4.0.** Die Struktur bleibt unverändert; der **Inhalts-Contract**
  ändert sich (normalisierter Text, geschärfte Überschriften). Die Versionsanhebung ist zugleich
  der etablierte Trigger für die Re-Extraktion (`pipeline._can_skip`).
- **Index-Schema bleibt 0.4.0**, **Graph-Teilschema bleibt 0.1.0**: keine Tabellen-/Spaltenänderung.
  Der Inhalt der Spalte `communities.keywords` ändert sich, ihre Struktur nicht.

## Alternativen

- **Domänen-Stopwords direkt im `TfidfVectorizer` von `build_graph`** (der „konzeptuell sauberere"
  Weg: eine Politik, ein Tokenuniversum). **Verworfen aufgrund einer Messung:** Bereits eine
  17 Terme umfassende Vorab-Liste (Bibliografie- und Web-Vokabular) verändert den Graphen deutlich
  – Kanten 216 → 213 (Jaccard 0,89), Communities 43 → 45,
  **adjusted Rand 0,759**. Ursache ist die Schwellenoperation *mutual top-k*, die auf minimale
  Gewichtsdrift (Ø 0,0066) mit gekippten Nachbarschaften reagiert. Ein **Nutzen** dieser
  Umpartitionierung ist nicht belegbar (es gibt keine Ground Truth für Themencluster), während der
  **Preis** konkret ist: der Nachfilter lässt Kanten und Communities byte-identisch und macht A5.1
  damit isoliert beweisbar – bei einer Vektorraum-Änderung wäre die Community-Drift nach dem
  Re-Ingest nicht mehr von der Textnormalisierung zu trennen. Konsistent zu A4, wo aus demselben
  Grund auf ein nicht belastbares Tuning verzichtet wurde.
- **Ligaturen nur im Keyword-Pfad normalisieren** (kleiner Eingriff, keine Re-Extraktion).
  Verworfen: löst das Anzeigeproblem, lässt aber 3628 Vorkommen im Chunk-Text unauffindbar – der
  eigentliche Schaden bliebe bestehen.
- **Pauschales NFKC** – verworfen, siehe Baustein 1 (bricht die Pseudocode-Reject-Regel aus A3).
- **Reject-Regel für Seitenbereiche** (`104–115`), ursprünglich als fünfte Zeilenregel geplant.
  **Verworfen nach Simulation:** 4 von 6 Treffern außerhalb der Referenzen wären **echte**
  Überschriften gewesen (`A. Clarity Of Objectives (0–3 Points)`), und das Zielbeispiel
  `(Issre). Ieee, 104–115.` wird bereits von der Satzpunkt-Regel erfasst. Fehlalarm-Risiko ohne
  zusätzlichen Nutzen.
- **Kontextregel „im Referenzabschnitt gar keine Überschriften"** – verworfen nach Simulation:
  692 Abschnitte wären entfallen und der Referenztext hätte sich von 1,57 auf 2,36 Mio. Zeichen
  vergrößert, weil ganze **Anhänge** einbezogen worden wären. Das hätte dem Zitationsgraphen
  geschadet (Titel-Matching im Anhangstext) und die Provenienz verschlechtert. Die enge Variante
  (nur Numerierungs-Zweig) trifft den gemessenen Mechanismus, ohne Anhänge zu schlucken.

## Konsequenzen

- **Positiv:** Community-Keywords und Abschnittstitel werden sauberer; die Ligatur-Reparatur macht
  3628 bisher unauffindbare Zeichenvorkommen durchsuchbar (Wirkung über das Gold-Set messbar); der
  Referenzabschnitt wird seltener zerschnitten, was den Zitationsgraphen vervollständigt.
- **Negativ / Aufwand:** Voller Re-Ingest nötig (Canonical-Schema-Anhebung); Chunk-IDs,
  Community-Zuschnitt und `CITES`-Kanten verschieben sich, alle Kennzahlen in der Dokumentation
  müssen nachgezogen werden. Der Canonical-Text ist nicht mehr die exakte Zeichenfolge, die `pypdf`
  liefert – die Provenienz auf Paper/Abschnitt/Seite bleibt davon unberührt.
- **Grenze:** Die Stopword-Liste ist kuratiert und damit korpus-spezifisch; sie wird bewusst
  minimal gehalten und nur erweitert, wenn eine Vorher/Nachher-Stichprobe den Bedarf belegt.
- **Folgeentscheidungen:** Das Gold-Set ([eval/retrieval-gold.json](../../eval/retrieval-gold.json))
  wird nach dem Re-Ingest über `python -m scripts.eval_retrieval --verify-labels` neu verifiziert
  und auf **1.2.0** gehoben; die Labels bleiben mechanisch aus dem Chunk-Text abgeleitet.

## Ergebnis nach der Umsetzung

Voller Re-Ingest über alle 145 Paper (`python -m scripts.ingest`):

| Kennzahl | vorher | nachher |
| --- | --- | --- |
| Chunks | 11 339 | 11 181 (−1,4 %) |
| Sections | 4406 (Median 27, Max 85) | **3948** (Median **25**, Max 85) |
| distinct Abschnittstitel | 2838 | 2455 |
| davon mit Rauschmerkmal | 267 | **0** |
| Keyword-Slots / davon Rauschen | 430 / 26 (6,0 %) | 440 / **0** |
| Ligaturen im Chunk-Text | 3628 | **0** |
| Glyph-Artefakte `/uniXXXXXXXX` | 1615 | **0** |
| Communities · Ähnlichkeitskanten | 43 · 216 | 44 · 215 |
| `CITES`-Kanten | 256 | **382** (+49 %) |
| Qualitäts-Flags | 320 auf 136 Papern | 316 auf 137 Papern |
| Hit@5 · MRR@5 (Gold-Set, `hybrid`) | 0,882 · 0,641 | 0,882 · **0,650** |

**Retrieval-Wirkung.** Die Ligatur-Reparatur macht bisher unauffindbare Wortvorkommen zugänglich:
`configuration` +133 Chunks, `specific` +153, `flow` +119, `file` +118, `verification` +97. Die
Gold-Set-Messung zeigt keinen Rückgang (Abbruchkriterium nicht ausgelöst): Hit@5 bleibt bei 0,882,
MRR steigt auf 0,650, bei Fakt-Fragen von 0,680 auf **0,695**. Die Rangfolge der Wertungen aus
[ADR 0014](0014-hybrid-retrieval-bm25-tfidf-phase7.md) bleibt unverändert (`tfidf` 0,735/0,574 ·
`hybrid` 0,882/0,650 · `bm25` 0,912/0,722), die dortige Default-Entscheidung gilt weiter.

**Unerwarteter Nebeneffekt: verrauschte Überschriften kosteten Retrieval-Treffer.** Eine Zeile,
die als Überschrift gelesen wird, landet **nicht** im Chunk-Text und ist damit nicht durchsuchbar.
Zwei Gold-Labels (G12/G16, `terraform`) ändern sich genau deshalb: In *Static Analysis of
Infrastructure as Code – a Survey* stand `https://www .terraform.io/` in einer Zeile, die als
Abschnittstitel galt; der Fließtext schreibt dort nur `T erraform`. Mit der URL-Reject-Regel ist
die Zeile wieder Text – und das Paper auffindbar. Das Gold-Set wurde entsprechend auf **1.2.0**
gehoben (Labels mechanisch neu abgeleitet, `--verify-labels` 34/34).

**Zitationsgraph.** Alle **382/382** Kanten sind mechanisch im Referenztext der Quelle belegt
(Titel-Match über dieselbe Normalisierung wie im Aufbau); Selbstzitate und Duplikate: 0. Die
Kontext-Stichprobe über alle drei Methoden zeigt echte Bibliografie-Einträge. Die Zahl der Paper
mit erkanntem Referenzabschnitt bleibt bei **143/145**.

**Determinismus.** Erneute Extraktion einer Stichprobe über den gesamten Bestand: **37/37**
identisch. Rebuild von Index, Ähnlichkeitsgraph und Zitationskanten aus den Canonical-Daten:
`chunks`, `graph_edges`, `communities`, `community_members`, `citation_edges` und `meta` jeweils
**identisch** zum Live-Index.

**Nebenbefund:** Der in [ADR 0013](0013-chunking-refinement-phase7.md) offen dokumentierte
Zielwert „Sections-Median ≤ 25" wird mit **25** nun erreicht (dort waren es 27).

### Bekannte Grenzen

- **Anhang im Referenzabschnitt.** Der Referenztext wächst von 1,61 auf 2,89 Mio. Zeichen. Der
  Zuwachs ist überwiegend echter Bibliografietext, der zuvor von Pseudo-Überschriften zerschnitten
  war; ein Rest ist Anhangstext, dessen Überschrift die Heuristik nicht erkennt. Gemessen geht
  dabei genau **eine** zuvor erkannte Anhang-Überschrift verloren (`A PPENDIX` in *LightRAG*, ein
  Kapitälchen-Artefakt der Extraktion), 18 bleiben erhalten. Der Provenienz-Saldo ist positiv:
  Anhangstext trug vorher den Titel eines **Literatureintrags** (z. B. `REALM: Retrieval-Augmented
  Language Model Pre-training. InProceedings`), heute trägt er `References` – ungenau, aber
  einheitlich und ehrlich. Für eine Kapitälchen-tolerante Erkennung (`A PPENDIX`, `I NTRODUCTION`)
  wurde bewusst keine Regel ergänzt: ein Einzelfall rechtfertigt keine neue Heuristik.
- **Restrauschen in Abschnittstiteln.** Titel wie `CODEBERT-RAG: Retrieves nodes using` oder
  `Training-free Search Agent. Observation 2 Agentic search` bleiben – es sind numerierte
  Fließtextreste ohne eines der geprüften Rauschmerkmale. Sie zu fangen erforderte eine
  semantische Prüfung; das bleibt außerhalb des offline-deterministischen Rahmens.
- **Die Stopword-Liste ist korpus-spezifisch.** `based` wurde als einziger generischer Füller
  aufgenommen, nachdem die Vorher/Nachher-Stichprobe ihn in den aufgefüllten Slots zeigte.
