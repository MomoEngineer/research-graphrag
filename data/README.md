# data/

Abgeleitete Artefakte der Pipeline. **Nicht versioniert** (per `.gitignore`
ausgeschlossen), da vollständig regenerierbar.

- `canonical/` – extrahiertes Canonical Paper JSON (Cache, Phase 2).
- `manifest.json` – Datei-Hash → Paper-ID (Dedup, Phase 2).
- `graphrag/` – GraphRAG-Workspace mit `input/`, `output/`, `cache/` (Phase 3).

Diese Struktur entsteht schrittweise ab Phase 2; in Phase 0 ist der Ordner
(bis auf diese README) leer.
