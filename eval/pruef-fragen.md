# Prüf-Fragen-Set

Pragmatisches, festes Frageset zur Qualitätssicherung über alle **fünf Fragetypen** (siehe [README.md](../README.md)). Es dient als wiederholbare Stichprobe: Liefert der Assistent eine plausible Antwort **mit korrekter Provenienz** (Paper, Abschnitt, Seite/Chunk)?

> **Status Phase 0:** Die Fragen sind als Gerüst formuliert. Konkrete, auf den eigenen Korpus bezogene Fragen und erwartete Belege werden ab **Phase 1/2** ergänzt (Platzhalter `<…>`).

Für jede Frage werden festgehalten:

- **Erwarteter Suchmodus** (gemäß Fragetyp-Mapping der README),
- **Erwartete Provenienz** (welche Quelle/Seite sollte belegt sein),
- **Befund** (bei der Durchführung: korrekt / teilweise / falsch + Notiz).

---

## 1. Präzise Detailfrage → Local + Basic

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| D1 | Welche Methode verwendet `<Paper X>` in Abschnitt `<n>`? | Local + Basic | `<Paper X>`, Abschnitt `<n>` | |
| D2 | Welche Datensätze nutzt `<Paper Y>` zur Evaluation? | Local | `<Paper Y>`, Abschnitt „Experiments/Datasets" | |

## 2. Cross-Paper-Synthese / Themen → Global

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| S1 | Welche Forschungsrichtungen zeichnen sich im Korpus ab? | Global | mehrere Community-Reports | |
| S2 | Welche Methodenfamilien werden am häufigsten kombiniert? | Global | Community-Reports | |

## 3. Zitations-/Autoren-/Methodennetze → Local (Fan-out)

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| N1 | Welche Paper bauen auf Methode `<Y>` auf? | Local (Fan-out) | über Beziehungen verknüpfte Paper | |
| N2 | Welche Arbeiten zitieren `<Paper Z>` im Kontext von `<Thema>`? | Local (Fan-out) | Zitationskanten + Belegstellen | |

## 4. Exakte Fakten → Basic

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| F1 | Wie lautet die DOI von `<Paper Z>`? | Basic | `<Paper Z>`, Metadaten/Kopf | |
| F2 | Welcher F1-Score wird in `<Paper Z>` berichtet? | Basic | `<Paper Z>`, Ergebnis-Tabelle/Abschnitt | |

## 5. Widersprüche & Vergleiche → DRIFT

| Nr. | Frage | Suchmodus | Erwartete Provenienz | Befund |
| --- | --- | --- | --- | --- |
| W1 | Wo widersprechen sich die Ergebnisse zu `<Thema T>`? | DRIFT | ≥ 2 Paper mit gegensätzlichen Aussagen | |
| W2 | Wie unterscheiden sich `<Paper A>` und `<Paper B>` in `<Aspekt>`? | DRIFT | `<Paper A>` und `<Paper B>`, relevante Abschnitte | |

---

## Durchführung

1. Voraussetzung: Index vorhanden (Phase 3) und MCP-Server aktiv (Phase 5).
2. Jede Frage über den passenden Suchmodus stellen.
3. Antwort **und** gelieferte Provenienz gegen die Erwartung prüfen, Befund eintragen.
4. Auffälligkeiten (fehlende/falsche Quelle) als Stichprobenfund notieren (siehe README, „Qualitätssicherung").
