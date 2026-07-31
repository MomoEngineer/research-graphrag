# papers/

PDF-Korpus (wissenschaftliche Paper). **Nicht versioniert** – die Inhalte dieses
Ordners werden per `.gitignore` ausgeschlossen (siehe README.md,
„Geplante Projektstruktur").

- **Layout:** eine Ebene, flach. Themencluster leben in `Übersicht.md`, nicht im
  Dateisystem (siehe Roadmap.md, offene Entscheidungen).
- **Migration (Phase 1) abgeschlossen:** 145 kuratierte Paper aus dem bisherigen
  `Recherche/` übernommen (flaches Layout); die Zuordnung Quelle → Zeile steht in
  [`Übersicht.md`](../Übersicht.md).
- **Neue PDFs** werden per Drop-in ergänzt und über `scripts/ingest.py`
  (Phase 2/6) verarbeitet; nur neue/geänderte Dateien werden neu extrahiert.

Aktueller Stand: **145 PDFs** (Phase-1-Migration). Ein unkuratiertes Korpus-PDF
wurde bewusst nicht übernommen (kein `Übersicht.md`-Eintrag). Die PDFs sind nicht
versioniert; nur diese README wird getrackt.
