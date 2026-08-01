# data/

Abgeleitete Artefakte der Pipeline. **Nicht versioniert** (per `.gitignore`
ausgeschlossen), da vollständig regenerierbar.

- `canonical/` – extrahiertes Canonical Paper JSON (Schema **0.2.0**: Sections, Chunks, Identifikatoren, Qualitätsflags; Cache, Phase 2).
- `manifest.json` – Datei-Hash → Paper-ID (Dedup, Phase 2).
- `quality_report.json` / `quality_report.md` – aggregierter Qualitätsreport der Ingestion (Phase 2).
- `overview_drafts.md` – append-only Staging für Übersicht-Entwürfe (`scripts/update_overview.py`, Phase 2).
- `index/` – Offline-Hybrid-Index in **SQLite** (Source of Truth): Papers/Chunks (Schema **0.3.0** – inkl. `section_title`-Abschnitts-Provenienz seit Phase 4 und `identifiers` (DOI/arXiv) für `get_paper` seit Phase 5) + Graph/Communities (Phase 3) + **Zitationskanten** (`citation_edges`, Teilschema **0.1.0** über `meta.citation_schema_version`, Phase 7 / A2, [ADR 0011](../docs/adr/0011-intra-corpus-citation-graph-phase7.md)); der **TF-IDF-Raum wird beim Laden deterministisch rekonstruiert** (keine serialisierten Modelle, Option B). Der Re-Index erfolgt **atomar** (Build nach `index/index.sqlite.tmp` + `os.replace`; ein Fehler lässt den Alt-Index intakt, Phase 6, [ADR 0010](../docs/adr/0010-drop-in-workflow-and-qa-phase6.md)) und umfasst Index, Graph und Zitationskanten gemeinsam.

Ein read-only Überblick über diese Artefakte (Kennzahlen + Konsistenz-Check `papers/ ↔ manifest ↔ canonical`) liefert `python -m scripts.status`.

Diese Struktur entsteht schrittweise ab Phase 2; in Phase 0 ist der Ordner
(bis auf diese README) leer.
