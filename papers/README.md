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
  `python -m scripts.intake` in den Korpus – mit Duplikatprüfung, Index-Neubau und
  Übersicht-Zeile in einem Schritt ([ADR 0019](../docs/adr/0019-corpus-intake-new-papers-phase8.md)).
  Der direkte Weg (PDF hier ablegen, dann `python -m scripts.ingest`) bleibt daneben bestehen;
  er dedupliziert allerdings nur über Dateiname und Hash.

Aktueller Stand: **204 PDFs** nach Korpuszufluss und fachlicher Bereinigung am
03.08.2026. Alle PDFs besitzen genau einen Eintrag in [`Übersicht.md`](../Übersicht.md).
Die PDFs sind nicht versioniert; nur diese README wird getrackt.
