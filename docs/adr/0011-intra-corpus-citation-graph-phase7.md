# 0011 – Intra-Korpus-Zitationsgraph (Phase 7 / A2): deterministisches ID-/Titel-Matching

- **Status:** Akzeptiert
- **Datum:** 2026-08-01

## Kontext

Der in Phase 3 gebaute Graph modelliert ausschließlich **Paper-Ähnlichkeit** (TF-IDF, *mutual top-k*, [ADR 0007](0007-graphrag-index-phase3-option-b.md)). Der in der [README](../../README.md) skizzierte Domain-/Zitationsgraph (`CITES`, `USES_METHOD`, …) fehlt; Fragen vom Typ „welche Paper bauen auf X auf?" sind damit offline faktisch unbeantwortbar – Ähnlichkeit ist **keine** Zitation. Die [Roadmap](../../Roadmap.md) führt das als Phase-7-Punkt **A2** (Gruppe A, offline umsetzbar).

Rahmenbedingungen:

- **Offline** ([ADR 0002](0002-venv-and-offline-dependency-strategy.md)): **GROBID** (Docker/Java) und **Kuzu** sind nicht beschaffbar und bleiben Zielbild (Gruppe B, [ADR 0005](0005-graphrag-index-backend-open.md)).
- Vorhandene Bausteine: die **Referenz-Sektion** wird seit Phase 2 heuristisch erkannt (`kind = references`), **DOI/arXiv** liegen je Paper als Identifikatoren im Canonical JSON ([ADR 0006](0006-canonical-model-phase2-scope.md)) und seit Schema `0.3.0` auch im Index ([ADR 0009](0009-mcp-server-stdio-phase5.md)).
- **Kein tiefes Referenz-Parsing:** ADR 0006 stellt das bewusst zurück; ein vollständiger Referenz-Parser ist offline nicht seriös umsetzbar.

## Entscheidung

1. **Nur Intra-Korpus-Kanten.** Es werden ausschließlich Zitationen **auf Paper des eigenen Korpus** erzeugt. Externe Referenzen werden weder aufgelöst noch gespeichert (dafür bliebe GROBID nötig).
2. **Deterministisches Matching mit Präzedenz `DOI > arXiv > Titel`.** Der Text der Referenz-Sektion(en) eines Papers wird gegen korpuseigene DOIs, arXiv-IDs und normalisierte Titel geprüft; je Zielpaper wird die **präziseste** Methode gespeichert. Selbstzitate werden ausgeschlossen.
3. **Präzision vor Recall.** Titel-Matching gilt erst ab einer Mindestlänge (≥ 30 Zeichen, ≥ 5 Wörter) und nur exakt auf normalisiertem Text (Kleinschreibung, nur alphanumerische Token). Es gibt **kein** Fuzzy-Matching: eine falsche `CITES`-Kante ist schädlicher als eine fehlende, weil sie eine Belegkette vortäuscht.
4. **Identifikatoren müssen selbst belegt sein.** Eine DOI/arXiv-ID wird nur dann als Zielschlüssel zugelassen, wenn sie im **Frontmatter** des Zielpapers (erste zwei Seiten, **ohne** Referenzabschnitt) vorkommt. Grund: Die Extraktion liest Identifikatoren bevorzugt von der Titelseite, fällt aber auf den Volltext zurück ([ADR 0006](0006-canonical-model-phase2-scope.md)) – dabei kann eine **zitierte fremde** ID als eigene erfasst werden. Empirisch waren das **15 von 155** Identifikatoren des Korpus; ohne diesen Filter hätten sie **37 von 192** Kanten (19 %) getragen und einen falschen Zitations-Hub erzeugt. Der Filter wirkt lokal im Zitationsgraphen; die Identifikatoren selbst (z. B. für `get_paper`) bleiben unverändert.
5. **Titelquelle = Dateiname-Stamm der `source_uri`.** Das Canonical-Modell hat kein eigenes Titelfeld; ein neues Feld erzwänge eine Re-Extraktion des gesamten Korpus. Die migrierten Dateinamen sind sprechende Paper-Titel (Phase 1), damit ist der Dateiname-Stamm die pragmatisch beste verfügbare Titelquelle.
6. **Additive Persistenz, voller Re-Build.** Die Kanten liegen in der bestehenden Index-Datei (`data/index/index.sqlite`) in der Tabelle `citation_edges`, versioniert über `meta.citation_schema_version` (`0.1.0`). Die Tabelle wird bei jedem Lauf verworfen und neu gebaut; `papers`/`chunks`/`graph_*` bleiben unangetastet.
7. **Bau innerhalb des atomaren Index-Swaps.** `build_citation_graph` läuft in `pipeline._build_index_atomically` **vor** `os.replace`, damit On-Read-Leser nie einen Index mit Kanten ohne Paper (oder umgekehrt) sehen ([ADR 0010](0010-drop-in-workflow-and-qa-phase6.md)).
8. **Zugriff über eine Kernfunktion, drei Oberflächen.** `retrieval.citations.get_citations` reichert die rohen Kanten (`indexing.citation_graph.load_citations`) um **Paper-Provenienz** (`source_uri`, Leit-Snippet) an; darauf setzen die CLI `python -m scripts.citations` und das MCP-Tool `get_citations` als **dünne Wrapper** auf (Schichtung wie `graph_index` ↔ `retrieval`, [ADR 0009](0009-mcp-server-stdio-phase5.md)).

## Alternativen

- **GROBID für echtes Referenz-Parsing:** präziseste Lösung, braucht aber Docker/Java → offline nicht verfügbar, bleibt Zielbild (Gruppe B).
- **Kuzu + Text2Cypher für Multi-Hop-Abfragen:** offline nicht beschaffbar; baut ohnehin auf den hier erzeugten Kanten auf (Gruppe B).
- **Fuzzy-/Token-Overlap-Matching der Titel:** höherer Recall, aber schwellenwertabhängig und fehleranfällig (ähnliche Titel im selben Themencluster) → widerspricht „Präzision vor Recall" und dem Determinismus-Grundsatz.
- **Fehl-extrahierte Identifikatoren in der Extraktion korrigieren** (statt im Zitationsgraphen zu filtern): sauberer an der Wurzel, erzwingt aber eine Änderung der Phase-2-Heuristik samt vollständiger Re-Extraktion und wirkt auf alle Identifikator-Nutzer (u. a. `get_paper`, Übersicht-Entwürfe) → zurückgestellt; der lokale Filter löst das Präzisionsproblem ohne diese Blast-Radius.
- **Titelfeld im Canonical-Modell ergänzen:** sauberer, erzwingt aber ein Schema-Update **mit** vollständiger Re-Extraktion des Korpus – unverhältnismäßig für den erwarteten Gewinn; nachrüstbar, ohne diesen ADR zu brechen.
- **Zitationskanten in den vorhandenen `graph_edges` ablegen:** würde die ungerichteten Ähnlichkeitskanten mit gerichteten `CITES`-Kanten vermischen und die Phase-3-Semantik (Louvain-Communities) verfälschen → eigene Tabelle.

## Konsequenzen

- **Positiv:** Multi-Hop-Zitationsfragen innerhalb des Korpus sind erstmals **belegbar** (CLI + MCP-Tool, jeweils mit `source_uri`); der Bau ist deterministisch und reproduzierbar; die Erweiterung ist rein additiv (kein Re-Extract, keine Migration bestehender Tabellen); die Kanten sind eine tragfähige Grundlage für Kuzu/Text2Cypher (Gruppe B).
- **Negativ / Aufwand:** Der **Recall ist begrenzt** – er hängt an der Referenz-Sektions-Heuristik (Paper ohne erkannte Referenzen liefern keine Kanten), an vorhandenen DOI/arXiv-IDs und an den Dateinamen als Titelquelle. Zitationskontexte (*warum* zitiert) und externe Referenzen fehlen. Die Präzision wird nicht formal gemessen, sondern **stichprobenhaft** geprüft (Nachweis im Roadmap-Status).
- **Folgeentscheidungen:** die LLM-Bridge/Antwort-Synthese (Roadmap-Punkt **A1**) erhält einen eigenen ADR; Gruppe B (GROBID/Kuzu) bleibt Zielbild unter [ADR 0005](0005-graphrag-index-backend-open.md).
