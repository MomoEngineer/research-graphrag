# 0018 – Code-Dokumentations-Architektur: Feature-Landkarte, Konzeptdokument und Modul-Dokus

- **Status:** Akzeptiert
- **Datum:** 2026-08-02

## Kontext

Das Repository hat nach Phase 7 eine dichte Dokumentationslandschaft, in der jede Datei eine
klar getrennte Frage beantwortet:

| Dokument | Beantwortet |
| --- | --- |
| [README.md](../../README.md) | Zielbild, Kontext, Projektstatus |
| [Roadmap.md](../../Roadmap.md) | Was in welcher Phase entstanden ist (Chronologie) |
| [docs/repository-structure.md](../repository-structure.md) | Wo eine Datei liegt und wozu sie gehört (Struktur) |
| [docs/glossary.md](../glossary.md) | Was ein Fachbegriff bedeutet |
| ADR 0001–0017 | **Warum** eine Lösung so und nicht anders gebaut ist |
| `mcp_server/specs/<tool>.md` | Der **Vertrag** eines MCP-Tools (Ein-/Ausgabe, Fehler, Grenzen) |
| `scripts/README.md`, `data/README.md`, `mcp_server/README.md` | Bedienung eines Teilbereichs |

Zwei Lücken sind daraus **nicht** abgedeckt:

1. **Es gibt keine funktionale Sicht.** Wer wissen will, welche Fähigkeiten das System besitzt
   und über welchen Einstiegspunkt sie erreichbar sind, muss die Prosa der README, die
   Phasenblöcke der Roadmap und den Ordnerbaum der Repository-Struktur gedanklich verschneiden.
   Die Information existiert, aber verstreut und in drei verschiedenen Ordnungsprinzipien
   (Zielbild, Chronologie, Ordnerpfad).
2. **Es gibt keine Erklärung der inneren Funktionsweise.** ADRs begründen Entscheidungen,
   Tool-Specs definieren Verträge, Docstrings erklären einzelne Symbole – aber nichts erklärt
   den *Ablauf* eines Moduls im Zusammenhang: welche Funktion wann greift, in welcher
   Reihenfolge Regeln ausgewertet werden, wo Determinismus herkommt.

Für Punkt 2 existiert bereits eine Regel, die aber **nie erfüllt wurde**:
[docs/documentation-standards.md](../documentation-standards.md) verlangt in Abschnitt 2 für jedes
nicht-triviale MCP-Tool einen Code-Walkthrough als `mcp_server/specs/<tool>.code.md`, samt
Vorlage [templates/tool-code-walkthrough.md](../../templates/tool-code-walkthrough.md). Im
Repository existiert keine einzige `.code.md`-Datei. Die Regel hat zudem einen konzeptionellen
Zuschnittsfehler: Sie ordnet die Erklärung dem **Tool** zu, während die Logik in diesem Repo
bewusst in Modulen unter `retrieval/`, `indexing/` und `generation/` liegt und der Server nur
dünne Wrapper registriert ([ADR 0009](0009-mcp-server-stdio-phase5.md)). Große Teile des
Systems – Extraktion, Chunking, Index-Bau, Evaluation, Pipeline – sind gar keine Tools und
fielen deshalb durch das Raster.

## Entscheidung

Die Code-Dokumentation wird auf **drei Ebenen** festgelegt, die sich nicht überlappen.

### 1. Feature-Landkarte – [docs/features.md](../features.md)

Die funktionale Sicht: eine Fähigkeit pro Zeile mit Einstiegspunkt (CLI-Kommando bzw.
MCP-Tool), den tragenden Modulen und dem ADR, der sie begründet. Sie ist **navigierend**, nicht
erzählend.

Abgegrenzt wird sie durch drei Verbote:

- **keine Begründungen** – das *Warum* steht im verlinkten ADR,
- **keine Kennzahlen** – Korpus- und Messzahlen stehen in ADRs/README und sind über
  `python -m scripts.status` bzw. `python -m scripts.eval_retrieval` jederzeit reproduzierbar,
- **keine Ordnerbäume** – die Struktur steht in [docs/repository-structure.md](../repository-structure.md).

### 2. Konzeptdokument – [docs/funktionsweise.md](../funktionsweise.md)

Das große Bild mit Mermaid-Diagrammen auf **Paket- und Ablaufebene**: Ingestion-Kette,
Index-Aufbau, die vier Retrieval-Modi, die Router-Entscheidung, Evidenz und Sampling-Grenze,
Evaluation. Es erklärt Zusammenspiel und Datenfluss zwischen Paketen, **nicht** einzelne
Funktionen.

### 3. Modul-Dokus – `src/research_graphrag/<paket>/doc/<modul>.md`

Zu jeder Python-Datei in `src/research_graphrag/` gehört eine Markdown-Datei gleichen Namens im
`doc/`-Ordner des jeweiligen Pakets. Die Top-Level-Module (`errors.py`, `keywords.py`,
`pipeline.py`) liegen in `src/research_graphrag/doc/`. Aufbau nach
[templates/module-doc.md](../../templates/module-doc.md).

Bewusst ausgenommen sind `__init__.py` und `__main__.py`: Sie enthalten Paket-Metadaten bzw.
einen Bootstrap-Aufruf; der Server-Einstiegspunkt wird in `mcp_server/doc/server.md` miterklärt.

### Ablösung der Code-Walkthrough-Regel

Die Modul-Doku **ersetzt** den Code-Walkthrough aus
[docs/documentation-standards.md](../documentation-standards.md) Abschnitt 2. Ein Tool wird künftig
über die Modul-Doku des Moduls erklärt, das seine Logik trägt;
`mcp_server/specs/<tool>.code.md` entfällt als Artefakt, die Vorlage
[templates/tool-code-walkthrough.md](../../templates/tool-code-walkthrough.md) geht in
[templates/module-doc.md](../../templates/module-doc.md) auf. Tool-**Spezifikationen** unter
`mcp_server/specs/<tool>.md` bleiben unverändert bestehen.

### Rangordnung der Wahrheit

Alle drei neuen Ebenen sind **beschreibend, nicht normativ**. Bei einem Widerspruch gilt
unverändert:

1. die Tool-Spezifikation als verbindlicher Contract,
2. der Code,
3. die beschreibende Dokumentation.

Wird ein Widerspruch entdeckt, wird die beschreibende Dokumentation korrigiert – nie umgekehrt.

### Right-sizing

Ein Mermaid-Diagramm ist Pflicht in [docs/funktionsweise.md](../funktionsweise.md) und in
Modul-Dokus mit mehrstufigem Ablauf. Module ohne verzweigten Kontrollfluss (etwa reine
Datentyp- oder Konstanten-Module) dokumentieren ihre öffentliche Schnittstelle tabellarisch
ohne Diagramm. Das entspricht dem Right-sizing-Grundsatz aus
[CONTRIBUTING.md](../../CONTRIBUTING.md).

## Alternativen

**Eine einzelne Erklärdatei für alles.** Verworfen: Ein Dokument, das 35 Module abdeckt, wird
unübersichtlich und lädt beim Nachschlagen einer Einzelfrage die gesamte Erklärung mit. Für die
Nutzung als Kontextquelle eines Agenten ist die Zerlegung pro Modul deutlich zielführender.

**Nur die fehlenden `<tool>.code.md` nachziehen.** Verworfen: Das deckt ausschließlich die
acht Tools ab und lässt Extraktion, Indexierung, Pipeline und Evaluation – also den größeren
Teil der Logik – weiterhin ohne Ablauferklärung.

**Eine README je Unterpaket statt einer Datei je Modul.** Verworfen als zu grob: Pakete wie
`retrieval/` (acht Module) oder `extraction/` (sechs Module) hätten wieder ein Sammeldokument,
in dem die Einzelmodule untergehen.

**Status quo belassen und auf Docstrings vertrauen.** Verworfen: Docstrings erklären Symbole,
nicht Abläufe über Modulgrenzen hinweg, und lassen sich nicht diagrammieren.

## Konsequenzen

- **Positiv:** Die funktionale Sicht und die Ablauferklärung existieren erstmals; die seit
  Phase 5 unerfüllte Walkthrough-Anforderung wird durch eine Regel ersetzt, die zum tatsächlichen
  Zuschnitt des Codes passt und vollständig erfüllt wird. Redundanz wird durch explizite
  Abgrenzungsverbote statt durch gute Absicht verhindert.
- **Negativ / Aufwand:** Es entstehen 35 Modul-Dokus plus zwei übergeordnete Dokumente. Jede
  Änderung an einem Modul erfordert ab jetzt die Pflege der zugehörigen Doku, sonst driftet sie.
  Das Verbot, Kennzahlen zu duplizieren, begrenzt diesen Aufwand, beseitigt ihn aber nicht.
- **Folgeentscheidungen:** [CONTRIBUTING.md](../../CONTRIBUTING.md) Abschnitt 5 und
  [docs/repository-structure.md](../repository-structure.md) Abschnitt 3 erhalten einen
  Pflegepunkt in der Definition of Done;
  [docs/documentation-standards.md](../documentation-standards.md) Abschnitt 2 wird auf die
  Modul-Doku umgestellt.
