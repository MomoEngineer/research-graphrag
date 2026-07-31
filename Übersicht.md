# Übersicht Wissenschaftlicher Quellen

> Diese Datei ist die **kuratierte, menschlich gepflegte Literaturübersicht** des Repos und ersetzt die gleichnamige Datei aus dem bisherigen `Recherche`-Ordner. Sie ergänzt den GraphRAG-Index: Der Index beantwortet inhaltliche Fragen *über* die Paper, während diese Tabelle die Quellen strukturiert nach **Themenclustern** und **Sub-Forschungsfragen (SRQ)** einordnet und für Exposé/Masterarbeit nachvollziehbar hält.
>
> **Arbeitsteilung mit der Pipeline:** Die Ingestion (`scripts/ingest.py` / `scripts/update_overview.py`) kann für neue Paper **Entwurfszeilen** vorbefüllen – `Name`, `Interner Link`, `Externer Link/Identifikator`, `Keyword` und `Kompakte Zusammenfassung` aus Extraktion/LLM. **Menschlich kuratiert** bleiben die wertenden Spalten `Relevanz fuer Expose` und `SRQ-Zuordnung`. Der `Themenfokus` kann an den GraphRAG-Communities ausgerichtet werden.
>
> **Status:** Format bereit; die vollständige Migration der bestehenden Quellen aus `Recherche/Übersicht.md` (inkl. Umbiegen der internen Links auf `papers/`) erfolgt gemäß [Roadmap](Roadmap.md). Die Zeilen unten sind Beispiele im Zielformat.

## Spaltenerklaerung und Regeln

Die Tabelle dient der strukturierten, nachvollziehbaren und reproduzierbaren Einordnung wissenschaftlicher Quellen fuer die Masterarbeit.

1. ID: Die ID ist eine Ordnungsvariable zur schnellen Einordnung. Sie wird nach Themenfokus geclustert (z. B. A, B, C, ...) und innerhalb des Clusters nach Relevanz fuer das Expose absteigend sortiert.
2. Name: Der Name ist der Originaltitel der Quelle.
3. Themenfokus: Ordnet die Quelle einem Forschungsbereich zu (kann an den GraphRAG-Communities ausgerichtet werden).
4. Keyword: Enthalten die wichtigsten inhaltlichen Konzepte der Quelle. Die Keywords sollen nicht nur den Titel paraphrasieren, sondern zentrale Methoden, Mechanismen oder Evaluationsaspekte abbilden und als Suchgrundlage fuer weitere aehnliche Quellen dienen.
5. Kompakte Zusammenfassung: Ein bis zwei sehr praezise Saetze, die den Kernbeitrag der Quelle beschreiben.
6. Interner Link: Verlinkung auf die abgelegte Quelle unter `papers/`.
7. Relevanz fuer Expose: Einordnung, wie stark die Quelle zur Argumentation und zum Aufbau von Expose und Forschungsdesign beitraegt.
8. SRQ-Zuordnung: Zuordnung zu den Sub-Forschungsfragen aus Expose und Forschungsfragen-Datei; eine Quelle kann mehreren SRQs zugeordnet werden, wenn sie mehrere Aspekte substantiell stuetzt.
9. Externer Link/Indetifikator: Eindeutiger externer Nachweis (z. B. DOI, arXiv, OpenReview, IEEE), damit die Quelle im Internet eindeutig identifizierbar und pruefbar bleibt.

### Pflege-Regeln

- Pro Zeile genau eine Quelle.
- Reihenfolge innerhalb eines Themenclusters nach Relevanz fuer das Expose: Sehr hoch, Hoch, Mittel, Gering.
- Zusammenfassungen nur inhaltlich belastbar und ohne ungestuetzte Interpretationen formulieren.
- Bei SRQ-Zuordnung nur Fragen markieren, zu denen ein klarer inhaltlicher Bezug besteht.
- Interne und externe Links bei jeder Quelle pflegen, damit lokale Nachvollziehbarkeit und externe Verifizierbarkeit gleichzeitig gesichert sind; interne Links zeigen auf `papers/`.
- Von der Pipeline erzeugte Entwurfszeilen vor Uebernahme pruefen; die wertenden Spalten (Relevanz, SRQ-Zuordnung) immer manuell bestaetigen.

## Tabelle

| ID | Name | Themenfokus | Keyword | Kompakte Zusammenfassung | Interner Link | Relevanz fuer Expose | SRQ-Zuordnung | Externer Link/Indetifikator |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | From Local to Global - A Graph RAG Approach to Query-Focused Summarization | KG-RAG und hybrides Retrieval | GraphRAG, Community Detection, Hierarchical Retrieval, Query-Focused Summarization | Grundlegender Microsoft-GraphRAG-Ansatz, der aus einem LLM-erstellten Wissensgraphen Community-Zusammenfassungen bildet und diese fuer globale, themenuebergreifende Fragen aggregiert. | [Quelle](papers/From%20Local%20to%20Global%20-%20A%20Graph%20RAG%20Approach%20to%20Query-Focused%20Summarization.pdf) | Hoch | SRQ2, SRQ4 | [arXiv:2404.16130](https://arxiv.org/abs/2404.16130) |
| P2 | HybridRAG - Integrating Knowledge Graphs and Vector Retrieval Augmented Generation for Efficient Information Extraction | KG-RAG und hybrides Retrieval | GraphRAG, Hybrid Retrieval, Classical RAG, Information Extraction | Kombiniert Wissensgraph- und Vektor-Retrieval, um bei der Extraktion aus komplexen Dokumenten robustere und vollstaendigere Antworten als jede Einzelmethode zu erzielen. | [Quelle](papers/HybridRAG%20-%20Integrating%20Knowledge%20Graphs%20and%20Vector%20Retrieval%20Augmented%20Generation%20for%20Efficient%20Information%20Extraction.pdf) | Hoch | SRQ2, SRQ4 | [arXiv:2408.04948](https://arxiv.org/abs/2408.04948) |

*Beispielzeilen im Zielformat. Die vollständige Migration der bestehenden Quellen erfolgt gemäß [Roadmap](Roadmap.md).*
