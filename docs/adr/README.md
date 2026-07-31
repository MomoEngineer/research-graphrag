# Architecture Decision Records (ADRs)

Ein **Architecture Decision Record (ADR)** dokumentiert eine bedeutsame Architektur- oder Grundsatzentscheidung: den Kontext, die getroffene Entscheidung und die Konsequenzen. ADRs machen nachvollziehbar, **warum** das System so ist, wie es ist – zentral für die Nachvollziehbarkeit dieses Repos.

---

## 1. Wann ist ein ADR erforderlich?

Ein ADR wird angelegt bei u. a.:

- Einführung/Wechsel eines schweren Backends (Extraktion, Index, Vektor-Store).
- Wechsel der Extraktions-/Index-/Retrieval-Strategie.
- Wahl einer anderen Programmiersprache als Python für eine Komponente.
- Betrieb des Servers über HTTP/SSE statt `stdio`.
- Bewusst in Kauf genommener Redundanz.
- Jeder Entscheidung, die schwer umkehrbar ist oder mehrere Komponenten betrifft.

---

## 2. Prozess

1. Kopiere [templates/adr-template.md](../../templates/adr-template.md).
2. Nummeriere fortlaufend: `NNNN-kurzer-titel.md`.
3. Setze den Status auf `Vorgeschlagen`, während die Entscheidung diskutiert wird.
4. Nach Annahme: Status auf `Akzeptiert` setzen.
5. Wird eine Entscheidung später ersetzt: alten ADR auf `Ersetzt durch NNNN` setzen, nicht löschen.

---

## 3. Status-Werte

- **Vorgeschlagen** – zur Diskussion.
- **Akzeptiert** – in Kraft.
- **Abgelehnt** – verworfen, aber zur Nachvollziehbarkeit erhalten.
- **Ersetzt** – durch einen neueren ADR abgelöst (mit Verweis).

---

## 4. Verzeichnis der ADRs

| Nr. | Titel | Status |
| --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Architekturentscheidungen als ADR festhalten | Akzeptiert |
| [0002](0002-venv-and-offline-dependency-strategy.md) | venv- und Offline-Dependency-Strategie | Akzeptiert |
| [0003](0003-offline-test-and-coverage-tooling.md) | Offline-Test- und Coverage-Tooling | Akzeptiert |
| [0004](0004-llm-bridge-via-mcp-sampling.md) | LLM-Bridge über MCP-Sampling (Abfragezeit) | Akzeptiert |
| [0005](0005-graphrag-index-backend-open.md) | Index-Backend: Offline-Hybrid (Option B) | Akzeptiert |
| [0006](0006-canonical-model-phase2-scope.md) | Canonical-Modell Phase 2: Heuristik-Umfang & zurückgestellte Bounding-Boxes | Akzeptiert |

---

## 5. Offene/geplante ADRs

- Derzeit sind **keine** ADR-pflichtigen Entscheidungen offen: [ADR 0005](0005-graphrag-index-backend-open.md) wurde nach einem empirischen Beschaffbarkeits-Test auf **Option B (Offline-Hybrid)** entschieden; [ADR 0006](0006-canonical-model-phase2-scope.md) grenzt den Heuristik-Umfang der Phase-2-Extraktion ab (Bounding-Boxes zurückgestellt).
- Geplant: **Umstieg auf `uv`** (sobald ein Mirror/Netz verfügbar ist) – löst [ADR 0002](0002-venv-and-offline-dependency-strategy.md) teilweise ab; **Option C** (pluggable Backends) als Folge-ADR, falls Teile des MS-GraphRAG-Stacks beschaffbar werden.
