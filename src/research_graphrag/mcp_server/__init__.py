"""MCP-Server (stdio): stellt Retrieval als Tools für GitHub Copilot bereit.

Registriert die Phase-4-Retrieval-Modi (`search_basic`, `search_local`, `search_global`,
`search_drift`) sowie die Katalog-Tools `get_paper` und `list_topics` als MCP-Tools und
startet den `stdio`-Transport (Einstiegspunkt `python -m research_graphrag.mcp_server`;
Implementierung in :mod:`research_graphrag.mcp_server.server`). Grundsatz:
docs/adr/0009-mcp-server-stdio-phase5.md – die Tools liefern strukturierte Evidenz +
Provenienz, die Antwort formuliert der aufrufende Agent (kein serverseitiges LLM-Sampling,
vgl. docs/adr/0004-llm-bridge-via-mcp-sampling.md).
"""

from __future__ import annotations

from research_graphrag.mcp_server.server import main, mcp

__all__ = ["main", "mcp"]
