"""Contract-Tests des MCP-Servers über einen In-Memory-Client (Phase 5, ADR 0009).

Verbindet Server und Client über In-Memory-Streams (kein Prozess/Netzwerk) und prüft die
Tool-Registrierung, den Erfolgs-Contract (structuredContent) und die strukturierte
Fehlerausgabe (``isError = true``). Asynchrone Tests laufen über das anyio-Plugin
(siehe docs/adr/0003-offline-test-and-coverage-tooling.md).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as client_session
from mcp.types import CallToolResult

from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.mcp_server.server import mcp

_TOOLS = {
    "search_basic",
    "search_local",
    "search_global",
    "search_drift",
    "get_paper",
    "list_topics",
}


def _structured(result: CallToolResult) -> dict[str, Any]:
    """Liefert die strukturierte Nutzlast (structuredContent oder JSON-Text-Fallback)."""
    if result.structuredContent is not None:
        return result.structuredContent
    assert result.content and result.content[0].type == "text"
    payload: dict[str, Any] = json.loads(result.content[0].text)
    return payload


def _paper(
    paper_id: str,
    texts: Sequence[str],
    *,
    identifiers: dict[str, str] | None = None,
) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_title="Introduction" if index == 0 else "Methods",
        )
        for index, text in enumerate(texts)
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=len(texts),
        chunks=chunks,
        quality_flags=(),
        identifiers=identifiers or {},
    )


@pytest.fixture
def index_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Baut einen kleinen Index + Graphen und richtet den Server per Env darauf aus."""
    papers = [
        _paper(
            "aaaa0001",
            [
                "transformer attention mechanism self attention encoder",
                "multi head attention transformer sequence model",
            ],
            identifiers={"arxiv": "2405.20455", "doi": "10.1145/1234"},
        ),
        _paper(
            "aaaa0002",
            [
                "self attention transformer architecture heads",
                "transformer encoder attention pretraining language",
            ],
        ),
        _paper(
            "bbbb0001",
            [
                "graph neural network message passing nodes",
                "graph community detection louvain modularity",
            ],
        ),
        _paper(
            "bbbb0002",
            [
                "citation graph clustering communities dataset",
                "dataset benchmark evaluation metric accuracy graph",
            ],
        ),
    ]
    db = tmp_path / "index" / "index.sqlite"
    build_index(papers, db)
    build_graph(papers, db)
    monkeypatch.setenv("RESEARCH_GRAPHRAG_INDEX", str(db))
    return db


@pytest.mark.anyio
async def test_list_tools_exposes_all_six(index_db: Path) -> None:
    """Der Server listet genau die sechs zugesagten Tools."""
    async with client_session(mcp) as client:
        listed = await client.list_tools()
    assert {tool.name for tool in listed.tools} == _TOOLS


@pytest.mark.anyio
async def test_search_basic_returns_structured_citations(index_db: Path) -> None:
    """search_basic liefert belegte Zitate als structuredContent (isError=false)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_basic", {"query": "attention"})
    assert result.isError is False
    payload = _structured(result)
    assert payload["query"] == "attention"
    assert payload["citations"]


@pytest.mark.anyio
async def test_get_paper_returns_metadata(index_db: Path) -> None:
    """get_paper liefert Metadaten inkl. Identifikatoren zur paper_id."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_paper", {"paper_id": "aaaa0001"})
    assert result.isError is False
    payload = _structured(result)
    assert payload["paper_id"] == "aaaa0001"
    assert payload["identifiers"] == {"arxiv": "2405.20455", "doi": "10.1145/1234"}
    assert payload["n_pages"] == 2
    assert payload["sections"]


@pytest.mark.anyio
async def test_list_topics_returns_topics(index_db: Path) -> None:
    """list_topics liefert die Community-Übersicht des Korpus."""
    async with client_session(mcp) as client:
        result = await client.call_tool("list_topics", {})
    assert result.isError is False
    payload = _structured(result)
    assert isinstance(payload["topics"], list)
    assert payload["topics"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("search_local", {"query": "attention"}),
        ("search_global", {"query": "graph"}),
        ("search_drift", {"query": "dataset"}),
    ],
)
async def test_search_modes_smoke(index_db: Path, tool: str, arguments: dict[str, str]) -> None:
    """Alle Retrieval-Modi antworten ohne Fehler und spiegeln die Anfrage."""
    async with client_session(mcp) as client:
        result = await client.call_tool(tool, arguments)
    assert result.isError is False
    assert _structured(result)["query"] == arguments["query"]


@pytest.mark.anyio
async def test_unknown_paper_yields_not_found_envelope(index_db: Path) -> None:
    """Unbekannte paper_id -> strukturierter not_found-Fehler (isError=true)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_paper", {"paper_id": "zzzznope0"})
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "not_found"


@pytest.mark.anyio
async def test_empty_query_yields_invalid_input_envelope(index_db: Path) -> None:
    """Leere Anfrage -> strukturierter invalid_input-Fehler (isError=true)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_basic", {"query": "   "})
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "invalid_input"
