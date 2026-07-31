# data/

Abgeleitete Artefakte der Pipeline. **Nicht versioniert** (per `.gitignore`
ausgeschlossen), da vollständig regenerierbar.

- `canonical/` – extrahiertes Canonical Paper JSON (Schema **0.2.0**: Sections, Chunks, Identifikatoren, Qualitätsflags; Cache, Phase 2).
- `manifest.json` – Datei-Hash → Paper-ID (Dedup, Phase 2).
- `quality_report.json` / `quality_report.md` – aggregierter Qualitätsreport der Ingestion (Phase 2).
- `overview_drafts.md` – append-only Staging für Übersicht-Entwürfe (`scripts/update_overview.py`, Phase 2).
- `index/` – Offline-Hybrid-Index in **SQLite** (Source of Truth): Papers/Chunks (Schema **0.3.0** – inkl. `section_title`-Abschnitts-Provenienz seit Phase 4 und `identifiers` (DOI/arXiv) für `get_paper` seit Phase 5) + Graph/Communities (Phase 3); der **TF-IDF-Raum wird beim Laden deterministisch rekonstruiert** (keine serialisierten Modelle, Option B).

Diese Struktur entsteht schrittweise ab Phase 2; in Phase 0 ist der Ordner
(bis auf diese README) leer.
