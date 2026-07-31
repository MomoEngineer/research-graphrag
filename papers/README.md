# papers/

PDF-Korpus (wissenschaftliche Paper). **Nicht versioniert** – die Inhalte dieses
Ordners werden per `.gitignore` ausgeschlossen (siehe README.md,
„Geplante Projektstruktur").

- **Layout:** eine Ebene, flach. Themencluster leben in `Übersicht.md`, nicht im
  Dateisystem (siehe Roadmap.md, offene Entscheidungen).
- **Migration** des Altbestands aus `Recherche/` erfolgt in **Phase 1**.
- **Neue PDFs** werden per Drop-in ergänzt und über `scripts/ingest.py`
  (Phase 2/6) verarbeitet; nur neue/geänderte Dateien werden neu extrahiert.

In Phase 0 ist der Ordner (bis auf diese README) leer.
