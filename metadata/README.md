# metadata/ – zitierfähige Paper-Metadaten & kuratiertes Relevanzurteil

Dieser Ordner enthält zwei **versionierte**, aus keiner anderen Quelle rekonstruierbare
Artefakte: die bibliografischen Daten des Korpus und (seit Phase 15 / G4) das einzige
menschliche Relevanzurteil.

## Warum nicht unter `data/`?

`data/` ist als *abgeleitet und regenerierbar* definiert und daher nicht versioniert. Die Daten
hier sind das Gegenteil: Sie enthalten **kuratierte** und **extern aufgelöste** Wahrheit, die
sich aus den PDFs nicht rekonstruieren lässt. Geht dieser Ordner verloren, ist die Arbeit weg –
deshalb wird er versioniert ([ADR 0025](../docs/adr/0025-citable-paper-metadata.md),
[ADR 0034](../docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md)).

## Inhalt

| Datei                   | Inhalt                                                                                                  |
| ----------------------- | ------------------------------------------------------------------------------------------------------- |
| `paper_metadata.json` | Metadaten-Datensätze der Herkünfte`resolved` (Online-Auflösung) und `manual` (von Hand gepflegt) |
| `curation.json` | Kuratiertes Relevanzurteil je Paper (`Themenfokus`, `Relevanz fuer Expose`, `SRQ-Zuordnung`), aus [`Übersicht.md`](../Übersicht.md) überführt |

Die Herkünfte `extracted` (Regex auf dem PDF) und `curated` (Spalte
`Externer Link/Indetifikator` der [Übersicht](../Übersicht.md)) werden bei **jedem** Index-Bau
neu abgeleitet und deshalb hier **nicht** dupliziert – sonst gäbe es zwei Wahrheiten.

`curation.json` ist **kein** Teil dieser bibliografischen Auflösungskette – es ist ein
eigenständiges, themenfokus-/SRQ-bezogenes Artefakt für die Auswahlregel der geplanten
[Referenz-Ernte](../docs/roadmap-historie.md#phase-14--referenz-ernte-externe-verweise-aus-dem-eigenen-bestand)
und fließt nicht in `paper_metadata.origins` ein. Erzeugt und geprüft wird es über
`python -m scripts.migrate_curation` (siehe
[curation.md](../src/research_graphrag/overview/doc/curation.md)).

## Vorrang der Herkünfte

Beim Index-Bau wird **feldweise** aufgelöst; es gewinnt die erste Herkunft mit nicht-leerem Wert:

```
manual  >  curated  >  resolved  >  extracted
```

Welche Herkunft je Feld gewonnen hat, steht im Index (`paper_metadata.origins`) und in jeder
Ausgabe von `get_reference` bzw. `python -m scripts.cite <paper_id>`.

## Von Hand pflegen

Ein Eintrag der Herkunft `manual` überschreibt alles andere. Format:

```json
{
  "schema_version": "0.1.0",
  "papers": {
    "0d3e35fe1c945c9b": [
      {
        "origin": "manual",
        "title": "Ein korrigierter Titel",
        "authors": ["Anna Beispiel", "Bert Muster"],
        "year": 2024,
        "venue": "Proceedings of …",
        "doi": "10.1145/…",
        "arxiv_id": "",
        "url": "",
        "confidence": "strong",
        "evidence": "von Hand geprüft am 2026-08-05"
      }
    ]
  }
}
```

Nach dem Bearbeiten `python -m scripts.ingest` ausführen – erst dann wirkt die Änderung im Index.

## Erzeugen und aktualisieren

```powershell
python -m scripts.resolve_metadata --dry-run   # zeigt, was aufgelöst würde
python -m scripts.resolve_metadata             # löst auf und schreibt paper_metadata.json
```

Der Lauf benötigt Netz (Proxy wie beim Online-Modus, siehe
[docs/online-recherche.md](../docs/online-recherche.md)) und lässt `manual`-Einträge unangetastet.
