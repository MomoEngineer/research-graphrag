# Pilot-Korpus (Phase 1)

> **Zweck:** Kleine, bewusst **struktur-diverse** Auswahl aus dem migrierten Korpus (`papers/`)
> zum Entwickeln und Härten der PDF-Ingestion-Pipeline (Phasen 2 ff.). Der Pilot-Korpus ist ein
> **QS-/Entwicklungs-Artefakt**, keine inhaltliche Bewertung – die kuratierte Einordnung der
> Quellen bleibt allein in [`Übersicht.md`](../Übersicht.md) (Spalten `Relevanz`, `SRQ-Zuordnung`).

## Auswahlmethode und Grenzen

- **Grundlage:** die 145 migrierten Quellen aus [`Übersicht.md`](../Übersicht.md). Die `ID` verweist
  direkt auf die dortige Zeile; sie ist die maßgebliche Referenz.
- **Diversitätskriterien (Proxy für Layout-/Extraktionsvielfalt):** Streuung über **alle 19
  Themencluster (A–S)** sowie über **Publikations-/Format-Typen** (arXiv-Preprint, IEEE- und
  ACM-Doppelspalten, ACL/NAACL, USENIX, OpenReview, AAAI) und **Jahrgänge** (ältere Scans vs.
  aktuelle Preprints). Ergänzt um bekannte **Sonderfälle** (Ligaturen, Klammern/lange Dateinamen,
  nicht-englischer Inhalt, Wurzel-Ablage, nachzupflegender externer Identifikator).
- **Grenze (bitte bestätigen):** Scan-, Tabellen- und Formel-Qualität lassen sich ohne Öffnen der
  PDFs nicht sicher beurteilen. Die Auswahl optimiert daher **strukturelle Diversität als Proxy**.
  Eine Verfeinerung mit `pypdf`-Signalen (Textausbeute/Seite als Scan-Indikator, Ziffern-/
  Tabellendichte) ist in Phase 2 möglich. **Diese Liste ist ein Vorschlag und von dir final zu
  bestätigen bzw. anzupassen.**

## Vorschlag (25 Paper)

| ID | Name | Cluster | Format-Proxy | Warum repräsentativ (Extraktions-Stress) |
| --- | --- | --- | --- | --- |
| A1 | Automated Cloud Infrastructure-as-Code Reconciliation with AI Agents | A · Agentische Systeme, IaC | arXiv (aktuell) | Fließtext-Baseline, aktuelles Preprint-Layout |
| A7 | Tortoise - Interactive System Configuration Repair | A · Agentische Systeme, IaC | arXiv (2017) | Älterer Jahrgang, abweichender Satzspiegel |
| B1 | Design Patterns for AI-based Systems | B · AI-Systemarchitektur | IEEE/CAIN + arXiv | Doppelspalten-Layout; Sonderfall Wurzel-Ablage |
| C1 | A Toolkit for Generating Code Knowledge Graphs | C · Code-Dokumentations-Fusion | arXiv/ACM (2020) | Code-Listings, älteres Format |
| D1 | Agent-G - An Agentic Framework for Graph Retrieval Augmented Generation | D · CPG, LLM-Tooling, Agenten | OpenReview | Benchmark-Tabellen, OpenReview-Satz |
| E1 | DependEval - Benchmarking LLMs for Repository Dependency Understanding | E · Evaluation Codegenerierung | ACL Findings | Metrik-/Tabellen-lastig |
| E17 | From Model-centered to Human-Centered - Revision Distance as a Metric for Text Evaluation in LLMs-based Applications | E · Evaluation Codegenerierung | ACL (Identifier offen) | Provenienz-Nachpflege (nicht-arXiv-ID) testen |
| F1 | ArchRAG - Attributed Community-based Hierarchical Retrieval-Augmented Generation | F · GraphRAG hierarchisch | AAAI + arXiv | Formeln, hierarchische Abbildungen |
| G3 | GRAG - Graph Retrieval-Augmented Generation | G · GraphRAG, Multi-Hop | NAACL Findings | Graph-Abbildungen |
| G6 | Retrieval-Augmented Generation with Graphs (GraphRAG) | G · GraphRAG, Multi-Hop | arXiv | Klammern im Dateinamen (Link-/Pfad-Robustheit) |
| H1 | Evaluating Long Range Dependency Handling in Code Generation LLMs | H · LLM-Codegenerierung | arXiv | Langkontext-Evaluation, Tabellen |
| I1 | A First Look at Bugs in LLM Inference Engines | I · LLM-Inferenzrobustheit | ACM (Journal) | Fehler-Taxonomie-Tabellen; einziger Cluster-Vertreter |
| J6 | Consolidating and Developing Benchmarking Datasets for the Nepali Natural Language Understanding Tasks | J · Masking, Ablation, Benchmarks | arXiv | Nicht-englischer Inhalt – Unicode/OCR-Stress |
| K3 | Benchmarking Vector, Graph and Hybrid Retrieval Augmented Generation (RAG) Pipelines for Open Radio Access Networks (ORAN) | K · Netzwerk-Konfiguration | arXiv | Sehr langer Titel + doppelte Klammern |
| K4 | Config2Spec - Mining Network Specifications from Network Configurations | K · Netzwerk-Konfiguration | USENIX NSDI | USENIX-Layout, Spezifikations-Tabellen |
| L2 | Evaluating Agentic Configuration Repair for Computer Networks | L · Netzwerk-Validierung (agentisch) | arXiv | Diagramme; kleiner Cluster |
| M4 | CodexGraph - Bridging Large Language Models and Code Repositories via Code Graph Databases | M · Repository-Level Code | NAACL + arXiv | Code-Listings + Tabellen |
| M10 | Prometheus - Unified Knowledge Graphs for Issue Resolution in Multilingual Codebases | M · Repository-Level Code | OpenReview | Mehrsprachige Codebasen, Schema-Grafiken |
| N1 | Rehearsal - A Conﬁguration Veriﬁcation Tool for Puppet | N · Template-Parsing / statische Analyse / IR | ACM (2016) | **ﬁ-Ligaturen** – Unicode-Extraktion (Kernfall) |
| N5 | SoK - Static Configuration Analysis in Infrastructure as Code Scripts | N · Template-Parsing / statische Analyse / IR | IEEE | Doppelspalten + Tabellen |
| O1 | Code Fingerprints - Disentangled Attribution of LLM-Generated Code | O · Source Attribution & Provenienz | arXiv | Architekturdiagramme, Formeln |
| P1 | From Local to Global - A Graph RAG Approach to Query-Focused Summarization | P · KG-RAG und hybrides Retrieval | arXiv | MS-GraphRAG-Referenz, Abbildungen |
| Q7 | Variational Reasoning for Question Answering with Knowledge Graph | Q · KG-Reasoning und KG-QA | arXiv (2017) | Älterer Jahrgang, mathematische Notation |
| R2 | Talk like a Graph - Encoding Graphs for Large Language Models | R · Graph-Encoding und KG-Konstruktion | arXiv | Viele Abbildungen/Prompt-Beispiele |
| S1 | Zep - A Temporal Knowledge Graph Architecture for Agent Memory | S · Agent-Memory und temporale KG | arXiv | Architektur-Diagramme, Zeitstempel-Tabellen |

**Abdeckung:** alle 19 Themencluster (A–S) vertreten; Format-Mix aus arXiv, IEEE, ACM, ACL/NAACL,
USENIX, OpenReview und AAAI; Jahrgänge von 2016 bis aktuell.
