"""Retrieval: Query-Router über Basic / Local / Global / DRIFT Search (Phase 4, Option B).

Die vier Suchmodi sind offline-deterministisch nachgebildet (siehe
docs/adr/0008-retrieval-and-query-router-phase4.md):

* :mod:`~research_graphrag.retrieval.basic` – TF-IDF-Top-k über Chunks (exakte Fakten).
* :mod:`~research_graphrag.retrieval.local` – Chunk-Nachbarschaft + Paper-Fan-out (Detail/Netz).
* :mod:`~research_graphrag.retrieval.global_search` – Query→Community-Ranking (Themen/Synthese).
* :mod:`~research_graphrag.retrieval.drift` – pragmatischer Global→Local-Hybrid (Widersprüche).

:mod:`~research_graphrag.retrieval.router` ordnet eine Frage heuristisch einem Modus zu;
:mod:`~research_graphrag.retrieval.provenance` stellt die gemeinsamen Provenienz-Typen
(``Citation``/``PaperRef``, Paper · Abschnitt · Seite · Chunk) und den Provenienz-Assembler bereit.
"""

from __future__ import annotations
