"""Retrieval: Query-Router über Local / Global / DRIFT / Basic Search.

Platzhalter für **Phase 4** (siehe Roadmap.md). Kapselt künftig die Suchmodi und wählt je
Fragetyp den passenden; im Offline-Hybrid nachgebildet (Basic ≈ TF-IDF-Top-k, Local ≈
Graph-Nachbarschaft, Global ≈ Community-Zusammenfassung, DRIFT ≈ Hybrid; ADR 0005). Stellt
einen Provenienz-Assembler bereit (Paper-ID, Abschnitt, Seite/Chunk).
"""

from __future__ import annotations
