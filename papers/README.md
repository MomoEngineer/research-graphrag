# papers/

PDF-Korpus (wissenschaftliche Paper). **Nicht versioniert** – die Inhalte dieses
Ordners werden per `.gitignore` ausgeschlossen (siehe README.md,
„Geplante Projektstruktur").

- **Layout:** eine Ebene, flach. Themencluster leben in `Übersicht.md`, nicht im
  Dateisystem (siehe [Roadmap-Historie](../docs/roadmap-historie.md), „Offene
  Entscheidungen").
- **Migration (Phase 1) abgeschlossen:** 145 kuratierte Paper aus dem bisherigen
  `Recherche/` übernommen (flaches Layout); die Zuordnung Quelle → Zeile steht in
  [`Übersicht.md`](../Übersicht.md).
- **Neue PDFs** gehen über den Eingangsordner [`new_papers/`](../new_papers/README.md) und
  `python -m scripts.intake` in den Korpus – mit Duplikatprüfung und Index-Neubau
  ([ADR 0019](../docs/adr/0019-corpus-intake-new-papers-phase8.md)). Seit Phase 15 / G4 bekommt
  `Übersicht.md` dabei **keine** neue Zeile mehr ([ADR 0034](../docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md)).
  Der direkte Weg (PDF hier ablegen, dann `python -m scripts.ingest`) bleibt daneben bestehen;
  er dedupliziert allerdings nur über Dateiname und Hash.
- **Zweiter Dokumenttyp:** Neben `*.pdf` liegen hier seit Phase 13 / R2 auch **Referenz-Einträge**
  `*.refjson` – Paper, von denen nur der Abstract öffentlich ist. Sie tragen ihren Titel als
  Dateinamen wie jedes PDF und werden von einem später eintreffenden Volltext **abgelöst**
  ([ADR 0030](../docs/adr/0030-reference-entries-in-corpus-phase13.md)). Seit R3 weist jede
  Ausgabe sie als unvollständig aus, und in der Chunk-Suche stehen sie hinter den
  Volltext-Treffern ([ADR 0031](../docs/adr/0031-reference-contract-and-guardrail-phase13.md)).

Aktueller Stand: **606 Paper** (Stand 2026-09-01). `Übersicht.md` ist seit Phase 15 / G4 außer
Dienst und deckt deshalb nur noch den historischen Bestand bis zu diesem Datum ab – neuere PDFs
haben dort **keinen** Eintrag mehr; das einzige menschliche Relevanzurteil der 131 kuratierten
Zeilen liegt maschinenlesbar in [`metadata/curation.json`](../metadata/curation.json)
([ADR 0034](../docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md)).
Die PDFs sind nicht versioniert; nur diese README wird getrackt.
