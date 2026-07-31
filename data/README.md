# data/

Abgeleitete Artefakte der Pipeline. **Nicht versioniert** (per `.gitignore`
ausgeschlossen), da vollständig regenerierbar.

- `canonical/` – extrahiertes Canonical Paper JSON (Cache, Phase 2).
- `manifest.json` – Datei-Hash → Paper-ID (Dedup, Phase 2).
- `index/` – Offline-Hybrid-Index: **SQLite** (Chunks/Graph) + TF-IDF-Artefakte (Phase 3, Option B).

Diese Struktur entsteht schrittweise ab Phase 2; in Phase 0 ist der Ordner
(bis auf diese README) leer.
