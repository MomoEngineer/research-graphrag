# 0004 – LLM-Bridge über MCP-Sampling (Abfragezeit)

- **Status:** Akzeptiert
- **Datum:** 2026-07-31

## Kontext

Zur **Abfragezeit** kann eine Antwort-Synthese ein LLM benötigen (z. B. das Zusammenfassen von Retrieval-Evidenz zu einer belegten Antwort). Rahmenbedingungen: Offline-Umfeld ([ADR 0002](0002-venv-and-offline-dependency-strategy.md)), **keine Secrets** im Server ([documentation-standards.md](../documentation-standards.md), Abschnitt 8), Nutzung durch **GitHub Copilot** als MCP-Client. Vorbild: `mcs-copilot-tools`, ADR 0010/0021.

## Entscheidung

1. **Keine gebundenen Modelle/Keys im Server.** Wo zur Abfragezeit ein LLM nötig ist, wird die Completion per **MCP-Sampling** (`session.create_message`) vom **Client (Copilot)** angefordert. Modellwahl und -zugang liegen ausschließlich beim Client.
2. **Injizierbarer Generierungs-Port** (Protocol) mit zwei Implementierungen: `SamplingGenerationProvider` (Standard) und `NoopGenerationProvider` (Fallback → `generated = false`), damit die Pipeline auch ohne Sampling **sichtbar degradiert**, statt zu scheitern.
3. **Async-Brücke nur an der Servergrenze** (`anyio`); die Kernlogik bleibt synchron und offline testbar.
4. **Bevorzugter Antwort-Weg:** Wo möglich, liefert der Server **strukturierte Evidenz + Provenienz** und überlässt die eigentliche Formulierung dem Copilot-Modell – kein zweiter Generator im Server.

## Geltungsbereich / Abgrenzung

Diese Entscheidung betrifft die **Abfrage-/Generierungszeit**. Der **Index-Bau** (Entity-/Relationship-Extraktion, Community-Reports, Embeddings) ist ein **Batch-Lauf ohne MCP-Client** und wird von der LLM-Bridge **nicht** abgedeckt (MCP-Sampling liefert insbesondere **keine Embeddings**). Dafür ist der offene [ADR 0005](0005-graphrag-index-backend-open.md) zuständig.

## Alternativen

- **LLM-SDK/HTTP-Client im Server:** offline nicht installierbar, erfordert Secrets, bündelt Modellzugang im Server → verworfen.
- **Gebundenes lokales Modell (z. B. Ollama) auf Abfrageebene:** Beschaffbarkeit offen; würde die Secret-Freiheit/Modell-Agnostik aufweichen → auf Abfragezeit-Ebene verworfen.

## Konsequenzen

- **Positiv:** Der Server ist offline-sicher, modell-agnostisch und secret-frei; nutzt exakt den Modellzugang des aufrufenden Clients (Copilot); die Pipeline ist immer lauffähig.
- **Negativ / Aufwand:** Sampling-Ergebnisse sind **nicht deterministisch**; Reproduzierbarkeit wird best-effort über Lauf-Metadaten hergestellt. Eine schmale Async-Brücke an der Servergrenze ist nötig.
- **Folgeentscheidungen:** [ADR 0005](0005-graphrag-index-backend-open.md).
