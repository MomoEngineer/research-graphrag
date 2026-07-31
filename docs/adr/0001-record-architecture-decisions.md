# 0001 – Architekturentscheidungen als ADR festhalten

- **Status:** Akzeptiert
- **Datum:** 2026-07-31

## Kontext

research-graphrag entsteht als persönliches, aber bewusst nachvollziehbares Werkzeug (siehe [README.md](../../README.md)). Entscheidungen zu Struktur, Abhängigkeiten und Backends sollen begründet und auffindbar sein – analog zum Vorbild-Repo `mcs-copilot-tools`.

## Entscheidung

Bedeutsame Architektur- und Grundsatzentscheidungen werden als fortlaufend nummerierte **ADRs** unter `docs/adr/` festgehalten (Vorlage: [templates/adr-template.md](../../templates/adr-template.md); Prozess: [docs/adr/README.md](README.md)).

## Alternativen

- **Entscheidungen nur in Commits/Issues:** schlechter auffindbar, kein stabiler Kontext → verworfen.
- **Keine formale Dokumentation:** widerspricht dem Leitprinzip „Nachvollziehbarkeit vor Tempo" → verworfen.

## Konsequenzen

- **Positiv:** Nachvollziehbarkeit; konsistente, auffindbare Begründungen; niedrige Einstiegshürde beim Wiederaufnehmen der Arbeit.
- **Negativ / Aufwand:** geringer Schreibaufwand je Entscheidung.
