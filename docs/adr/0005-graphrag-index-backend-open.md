# 0005 – Index-Backend: Offline-Hybrid (Option B)

- **Status:** Akzeptiert
- **Datum:** 2026-07-31
- **Historie:** ursprünglich „Vorgeschlagen (offen)"; nach empirischem Beschaffbarkeits-Test geschlossen.

## Kontext

Die [README.md](../../README.md) beschreibt eine Architektur auf Basis von **Microsoft GraphRAG** (file-based, Parquet + LanceDB, Leiden-Communities, Local/Global/DRIFT/Basic Search). Der **Index-Bau** benötigt zwingend ein **LLM** (Entity-/Relationship-/Claim-Extraktion, Community-Reports) und ein **Embedding-Modell** – als **Batch in `scripts/ingest.py`**, **ohne** MCP-Client. Damit greift die LLM-Bridge ([ADR 0004](0004-llm-bridge-via-mcp-sampling.md)) hier **nicht**; MCP-Sampling liefert zudem **keine** Embeddings. Rahmenbedingung: Offline-Umfeld ([ADR 0002](0002-venv-and-offline-dependency-strategy.md)).

**Empirischer Beschaffbarkeits-Test (2026-07-31):**

- `docling`, `graphrag`, `lancedb` sind **nicht beschaffbar** (`pip install --dry-run` → „No matching distribution found"; kein PyPI, kein Mirror).
- Offline vorhanden: `pypdf 5.6.0`, `scikit-learn 1.8.0`, `networkx 3.6.1`, `numpy`, `scipy`, `sqlite3` (stdlib), `mcp 1.21.0`.
- `leidenalg`/`python-igraph` fehlen (kein Leiden).

## Entscheidung

**Option B – Offline-Hybrid.** Der Index wird vollständig offline und deterministisch gebaut:

| Schicht | Umsetzung |
| --- | --- |
| PDF-Extraktion | `pypdf` (Text + Seiten-Provenienz; Layout/Tabellen begrenzt) |
| Embeddings | deterministisches **TF-IDF** (`scikit-learn`) |
| Vektor-/Speicher | **SQLite** (stdlib) + TF-IDF-Matrix |
| Graph + Communities | `networkx` + **Louvain** (Leiden offline nicht verfügbar) |
| Suchmodi (nachgebildet) | Basic ≈ TF-IDF-Top-k · Local ≈ Graph-Nachbarschaft · Global ≈ Community-Zusammenfassung · DRIFT ≈ Hybrid |
| Antwort-Synthese | **LLM-Bridge** (MCP-Sampling, [ADR 0004](0004-llm-bridge-via-mcp-sampling.md)); Community-Zusammenfassungen extraktiv oder on-demand über die Bridge |

Kein externer Dienst, keine Secrets, kein Batch-LLM im Index-Bau. Die Deps (`pypdf`, `scikit-learn`, `networkx`) werden Kern-Abhängigkeiten in `pyproject.toml`; das `[pipeline]`-Extra entfällt.

## Alternativen

- **A – MS-GraphRAG + reales Backend (Ollama/Cloud).** Verworfen: `graphrag`/`docling`/`lancedb` offline **nicht beschaffbar**; Cloud/Ollama im Umfeld nicht verfügbar bzw. secretpflichtig.
- **C – Hybrid mit pluggable Backends.** Zurückgestellt: sinnvoll erst, wenn Teile des MS-Stacks beschaffbar werden → dann Folge-ADR.
- **Warten auf Wheels/Mirror.** Verworfen als Blocker; B ist sofort tragfähig.

## Konsequenzen

- **Positiv:** Voll offline-tauglich, deterministischer und reproduzierbarer Index; nutzt ausschließlich vorhandene Bausteine; secret-frei. Konzeptuelle Nähe zum Vorbild-Repo `mcs-copilot-tools` (SQLite-Graph, TF-IDF, RRF, Sampling).
- **Negativ / Aufwand:** Weicht vom README-/Roadmap-Stack ab (Reconcile nötig); `pypdf` liefert weniger Struktur/Tabellen als Docling; **Louvain statt Leiden**; „Community-Reports" nicht als vorab erzeugte LLM-Zusammenfassungen; DRIFT nur angenähert.
- **Folgeentscheidungen:** README/Roadmap-Reconcile (Tech-Stack); spätere **Option C** per Folge-ADR, falls Teile des MS-GraphRAG-Stacks beschaffbar werden.
