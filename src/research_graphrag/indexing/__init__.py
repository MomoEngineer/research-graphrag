"""Indexierung: Canonical Paper JSON → Offline-Hybrid-Index (Option B).

Platzhalter für **Phase 3** (siehe Roadmap.md). Enthält künftig die Orchestrierung des
Index-Baus im Offline-Hybrid: Chunking, **TF-IDF** (``scikit-learn``), Graph + **Louvain**
(``networkx``) und Ablage in **SQLite** (siehe docs/adr/0005-graphrag-index-backend-open.md).
Ein LLM kommt nur zur Abfragezeit über die LLM-Bridge (ADR 0004).
"""

from __future__ import annotations
