# 0005 – Index-Backend offline: MS-GraphRAG vs. Offline-Hybrid

- **Status:** Vorgeschlagen (offen)
- **Datum:** 2026-07-31

## Kontext

Die [README.md](../../README.md) beschreibt eine Architektur auf Basis von **Microsoft GraphRAG** (file-based, Parquet + LanceDB, Leiden-Communities, Local/Global/DRIFT/Basic Search). Der **Index-Bau** benötigt zwingend:

- ein **LLM** für Entity-/Relationship-/Claim-Extraktion und Community-Reports (viele Batch-Aufrufe) und
- ein **Embedding-Modell** für TextUnit-/Entity-Embeddings.

Dieser Schritt läuft als **Batch in `scripts/ingest.py`**, **ohne** MCP-Client. Damit greift die LLM-Bridge ([ADR 0004](0004-llm-bridge-via-mcp-sampling.md)) hier **nicht**; MCP-Sampling liefert zudem **keine** Embeddings. Rahmenbedingung: Offline-Umfeld ([ADR 0002](0002-venv-and-offline-dependency-strategy.md)), in dem Cloud-APIs und ggf. lokale Modelle/Wheels nicht ohne Weiteres verfügbar sind.

## Zur Entscheidung stehende Optionen

- **A – MS-GraphRAG beibehalten, reales Index-Backend.** Lokales Modell (z. B. Ollama, falls beschaffbar) für Extraktion + kompatible/lokale Embeddings; alternativ ein einmaliges Online-/Mirror-Fenster für den Index-Bau. Nähe zur README, aber Offline-Beschaffung offen.
- **B – Offline-Hybrid (wie Vorbild-Repo).** Deterministische Extraktion + **TF-IDF**-Retrieval + Graph in SQLite; ein LLM kommt nur zur Abfragezeit über die Bridge. Voll offline-tauglich, weicht aber von der MS-GraphRAG-Architektur der README ab.
- **C – Hybrid.** MS-GraphRAG-Datenmodell und Suchmodi, aber austauschbare, offline-fähige Backends (pluggable LLM/Embedding).

## Warum jetzt offen

Für **Phase 0 (Fundament)** ist die Wahl **nicht** erforderlich; sie hängt von der Beschaffbarkeit der Wheels/Modelle (Phase 0b/2) ab. Die Entscheidung wird **vor Phase 2/3** als Folge-ADR getroffen und schließt diesen ADR. Bewusst wird die Spannung dokumentiert, statt sie zu verstecken.

## Vorläufige Konsequenzen

- Phase 0 bleibt unblockiert; der Kern (`pip install -e .`) hängt nicht am Pipeline-Stack.
- `.env.example` markiert die Index-Backend-Variablen als „OFFEN".
- Die Extraktions-/Index-/Retrieval-Platzhalter unter `src/research_graphrag/` treffen bewusst **keine** Backend-Annahme.
