"""Zitierfähige Paper-Metadaten (Phase 12 / K1).

Das Paket verwaltet die bibliografischen Daten eines Papers – **getrennt nach Herkunft** – und
erzeugt daraus fertige Literaturangaben in Harvard und APA. Grundsatz:
docs/adr/0025-citable-paper-metadata.md.

Der Name lautet bewusst ``bibliography`` und nicht ``citation``: Im Repository bezeichnet
„Citation" bereits den Provenienz-Typ :class:`research_graphrag.retrieval.provenance.Citation`
und den Zitationsgraphen aus docs/adr/0011-intra-corpus-citation-graph-phase7.md.
"""
