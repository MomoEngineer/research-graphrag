# 0006 – Canonical-Modell Phase 2: Heuristik-Umfang & zurückgestellte Bounding-Boxes

- **Status:** Akzeptiert
- **Datum:** 2026-07-31

## Kontext

Die [Roadmap.md](../../Roadmap.md) beschreibt für **Phase 2** ein reiches Canonical Paper JSON mit
**Section-Hierarchie, Referenzen, Chunk-IDs, Seiten-/Bounding-Box-Provenienz** und
**Qualitäts-Gates**. Dieser Text stammt aus der Zeit *vor* [ADR 0005](0005-graphrag-index-backend-open.md)
und spiegelt teils den Docling-/Microsoft-GraphRAG-Anspruch, der im Offline-Umfeld
([ADR 0002](0002-venv-and-offline-dependency-strategy.md)) nicht bedienbar ist.

Rahmenbedingungen der tatsächlichen Umsetzung (Option B, [ADR 0005](0005-graphrag-index-backend-open.md)):

- **`pypdf`** liefert über `extract_text()` reinen Text je Seite – **keine** verlässlichen
  Koordinaten. Bounding-Boxes wären nur über den `visitor_text`-Callback (Transformationsmatrizen)
  zu rekonstruieren: aufwändig, layout-/scanabhängig und **nicht deterministisch testbar**
  (Widerspruch zu [docs/testing.md](../testing.md)).
- **Kein LLM zur Ingest-Zeit** (Kern von [ADR 0005](0005-graphrag-index-backend-open.md)):
  Section-Erkennung, Keywords und Zusammenfassungen können nur **deterministisch/extraktiv**
  entstehen, nicht in LLM-Qualität.
- **Verlässliches Referenz-/Zitations-Parsing** ist GROBID-Territorium und in der
  [Roadmap.md](../../Roadmap.md) explizit **Phase 7** zugeordnet.

Der Grundsatz des Repos ist **right-sized** ([CONTRIBUTING.md](../../CONTRIBUTING.md)): Formalien
nur dort, wo sie realen Nutzen stiften.

## Entscheidung

Phase 2 setzt ein **deterministisches, heuristisches** Canonical-Modell um und stellt die
fragilen bzw. Phase-7-nahen Teile bewusst zurück:

| Aspekt | Phase-2-Umsetzung |
| --- | --- |
| Section-Hierarchie | **Heuristisch** über Überschriften-Erkennung (numerierte Überschriften, bekannte Sektions-Schlüsselwörter, Kurz-/Versal-Zeilen); Klassifikation `front`/`abstract`/`body`/`references`. Bei geringer Konfidenz Qualitäts-Flag. |
| Chunking | **Abschnitts-/größenbasiert** mit Zielfenster (`MIN_CHARS`/`MAX_CHARS`); **Seite ist harte Chunk-Grenze** (exakte Seiten-Provenienz bleibt erhalten). |
| Identifikatoren | **DOI/arXiv** per Regex aus dem extrahierten Text (deterministisch). |
| Qualitäts-Gates | **Heuristische Flags** (fehlender Abstract, fehlender/auffälliger Referenz-Abschnitt, OCR-Rauschen, leere Seite, mögliche kopflose Tabelle, zu kurze/lange Chunks). |
| Provenienz | **Paper-ID · Seite · Section** (Section im Canonical JSON persistiert). |
| **Bounding-Box-Provenienz** | **Zurückgestellt** (Phase 7, mit Docling/GROBID). |
| **Tiefes Referenz-/Tabellen-Parsing** | **Zurückgestellt** (Phase 7, GROBID). |

Das Canonical-JSON-Schema wird von `0.1.0` auf **`0.2.0`** angehoben; bestehende `0.1.0`-Artefakte
werden bei der Ingestion **neu extrahiert** (Erkennung über `schema_version`; `data/` ist ohnehin
regenerierbar). Index- und Retrieval-**Contracts bleiben in Phase 2 unverändert** (Section fließt
erst in Phase 4 in Index/Retrieval ein) – die Phasen-Grenzen bleiben scharf.

## Alternativen

- **Volle Roadmap-Tiefe inkl. Bounding-Boxes jetzt.** Verworfen: `pypdf` liefert keine
  verlässlichen Koordinaten; der Aufwand für brüchigen, nicht deterministisch testbaren Code steht
  in keinem Verhältnis zum Nutzen bei ≤ 500 Papern. Seiten- + Section-Provenienz erfüllt das
  „Provenienz zuerst"-Prinzip bereits.
- **LLM-gestützte Sections/Keywords/Zusammenfassungen im Ingest.** Verworfen: widerspricht
  [ADR 0005](0005-graphrag-index-backend-open.md) (kein Batch-LLM offline); LLM bleibt der
  Abfragezeit vorbehalten ([ADR 0004](0004-llm-bridge-via-mcp-sampling.md)).
- **Section in Index/Retrieval schon in Phase 2 durchreichen.** Zurückgestellt: würde den
  `search_basic`-Contract mitten in Phase 2 ändern; sauberer als eigene, testgetriebene Änderung in
  Phase 4.

## Konsequenzen

- **Positiv:** Voll offline-tauglich, deterministisch und reproduzierbar; exakte Seiten-Provenienz
  bleibt erhalten und wird um Section-Provenienz ergänzt; keine fragilen Koordinaten; klare
  Phasen-Grenze zu Index/Retrieval.
- **Negativ / Aufwand:** Section-Hierarchie und Tabellen-/Referenz-Erkennung sind **heuristisch**
  (mit Qualitäts-Flags signalisiert); keine Bounding-Boxes; Schema-Bump erzwingt eine einmalige
  Re-Extraktion.
- **Folgeentscheidungen:** Bounding-Boxes und tiefes Referenz-/Tabellen-Parsing werden mit
  Docling/GROBID in **Phase 7** erneut bewertet (ggf. Folge-ADR im Rahmen von **Option C**,
  [ADR 0005](0005-graphrag-index-backend-open.md)).

---

## Nachtrag (2026-08-01, Phase 7 / A3)

Zwei hier getroffene Festlegungen sind durch [ADR 0013](0013-chunking-refinement-phase7.md)
**abgelöst**; der übrige Umfang dieses ADR (keine Bounding-Boxes, kein tiefes Referenz-/
Tabellen-Parsing, heuristische Sections) gilt unverändert weiter:

- **„Seite ist harte Chunk-Grenze"** – aufgehoben. Die Seite ist ein Layout-Artefakt und dient
  nicht mehr der Segmentierung; sie wird als **Provenienz-Range** geführt (`page_number` =
  Startseite, neu `page_end`). Auslöser: 79,6 % der Seitenumbrüche innerhalb einer Section lagen
  mitten im Satz.
- **Qualitäts-Flag `short_chunk:<chunk_id>`** – ersetzt durch das aggregierte `short_chunks:<n>`
  je Paper; `long_chunk:<chunk_id>` bleibt unverändert pro Chunk.

Ergänzt wurde außerdem eine **Section-Absorption** gegen die Übersegmentierung der hier
festgelegten Überschriften-Heuristik (Messwerte und Begründung in
[ADR 0013](0013-chunking-refinement-phase7.md)).
