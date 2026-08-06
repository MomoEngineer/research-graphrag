"""Contract-Tests des MCP-Servers über einen In-Memory-Client (Phase 5, ADR 0009).

Verbindet Server und Client über In-Memory-Streams (kein Prozess/Netzwerk) und prüft die
Tool-Registrierung, den Erfolgs-Contract (structuredContent) und die strukturierte
Fehlerausgabe (``isError = true``). Asynchrone Tests laufen über das anyio-Plugin
(siehe docs/adr/0003-offline-test-and-coverage-tooling.md).

Für ``answer_question`` wird zusätzlich der **Sampling-Pfad** end-to-end geprüft: Der
In-Memory-Client stellt einen Sampling-Callback bereit (Client-Modell-Attrappe), sodass die
Async-Brücke aus :mod:`research_graphrag.mcp_server.sampling` real durchlaufen wird
(docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.context import RequestContext
from mcp.shared.memory import create_connected_server_and_client_session as client_session
from mcp.types import (
    CallToolResult,
    CreateMessageRequestParams,
    CreateMessageResult,
    ErrorData,
    TextContent,
)

from research_graphrag.extraction.model import (
    SECTION_KIND_BODY,
    SECTION_KIND_REFERENCES,
    Section,
)
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.citation_graph import build_citation_graph
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.metadata_index import build_metadata_index
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.mcp_server.server import mcp

_TOOLS = {
    "search_basic",
    "search_local",
    "search_global",
    "search_drift",
    "get_paper",
    "get_citations",
    "list_topics",
    "get_reference",
    "answer_question",
}

_SAMPLED_ANSWER = "Aufmerksamkeit ist der Kern der Architektur [1]."


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
    references: str = "",
) -> CanonicalPaper:
    chunks = [
        Chunk(
            chunk_id=f"{paper_id}-c{index:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_id="s-body",
            section_title="Introduction" if index == 0 else "Methods",
        )
        for index, text in enumerate(texts)
    ]
    sections = [
        Section(
            section_id="s-body",
            title="Introduction",
            kind=SECTION_KIND_BODY,
            level=1,
            page_number=1,
            order=0,
        )
    ]
    if references:
        sections.append(
            Section(
                section_id="s-refs",
                title="References",
                kind=SECTION_KIND_REFERENCES,
                level=1,
                page_number=len(texts) + 1,
                order=1,
            )
        )
        chunks.append(
            Chunk(
                chunk_id=f"{paper_id}-c{len(texts):04d}",
                paper_id=paper_id,
                page_number=len(texts) + 1,
                text=references,
                char_count=len(references),
                section_id="s-refs",
                section_title="References",
            )
        )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=len(chunks),
        chunks=tuple(chunks),
        quality_flags=(),
        sections=tuple(sections),
        identifiers=identifiers or {},
    )


@pytest.fixture
def index_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Baut einen kleinen Index + Graphen und richtet den Server per Env darauf aus."""
    papers = [
        _paper(
            "aaaa0001",
            [
                "transformer attention mechanism self attention encoder doi:10.1145/1234",
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
            references="[1] Vorarbeit zur Aufmerksamkeit. doi:10.1145/1234",
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
    build_citation_graph(papers, db)
    build_metadata_index(papers, db)
    monkeypatch.setenv("RESEARCH_GRAPHRAG_INDEX", str(db))
    return db


@pytest.mark.anyio
async def test_list_tools_exposes_all_tools(index_db: Path) -> None:
    """Der Server listet genau die neun zugesagten Tools."""
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
async def test_get_citations_returns_edges_with_provenance(index_db: Path) -> None:
    """get_citations liefert die eingehende Kante samt Quelle und Match-Kriterium."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_citations", {"paper_id": "aaaa0001"})
    assert result.isError is False
    payload = _structured(result)
    assert payload["paper"]["paper_id"] == "aaaa0001"
    assert payload["cites"] == []
    assert [entry["paper_id"] for entry in payload["cited_by"]] == ["aaaa0002"]
    assert payload["cited_by"][0]["method"] == "doi"
    assert payload["cited_by"][0]["source_uri"].startswith("file:")


@pytest.mark.anyio
async def test_get_citations_unknown_paper_yields_not_found_envelope(index_db: Path) -> None:
    """Unbekannte paper_id -> strukturierter not_found-Fehler (isError=true)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_citations", {"paper_id": "zzzznope0"})
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "not_found"


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
async def test_get_reference_returns_both_citation_styles(index_db: Path) -> None:
    """get_reference liefert beide Stile und weist fehlende Pflichtfelder aus."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_reference", {"paper_id": "aaaa0001"})
    assert result.isError is False
    payload = _structured(result)
    assert payload["styles"] == ["harvard", "apa"]
    assert payload["reference"]["identifiers"]["doi"] == "10.1145/1234"
    assert payload["reference"]["harvard"]
    assert payload["reference"]["apa"]
    # Ohne Online-Auflösung fehlen Autoren: Das wird ausgewiesen, nicht geraten.
    assert "authors" in payload["missing"]
    assert payload["note"]


@pytest.mark.anyio
async def test_get_reference_unknown_paper_yields_not_found_envelope(index_db: Path) -> None:
    """Unbekannte paper_id -> strukturierter not_found-Fehler (isError=true)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_reference", {"paper_id": "zzzznope0"})
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "not_found"


@pytest.mark.anyio
async def test_search_results_carry_external_identifiers(index_db: Path) -> None:
    """Jeder Chunk-Beleg trägt die extern auflösbaren Identifikatoren seines Papers."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_basic", {"query": "attention"})
    citations = _structured(result)["citations"]
    by_paper = {citation["paper_id"]: citation for citation in citations}

    assert by_paper["aaaa0001"]["identifiers"] == {
        "doi": "10.1145/1234",
        "arxiv": "2405.20455",
    }
    assert by_paper["aaaa0001"]["citation_key"]


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
async def test_search_local_returns_the_seed_list(index_db: Path) -> None:
    """Das Werkzeug liefert das Feld ``seeds`` als Liste (Spec 0.2.0, ADR 0021)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_local", {"query": "attention", "fan_out": 0})

    payload = _structured(result)
    assert result.isError is False
    assert set(payload) == {"query", "seeds", "neighborhood", "fan_out"}
    assert isinstance(payload["seeds"], list)
    assert all("chunk_id" in seed for seed in payload["seeds"])


@pytest.mark.anyio
async def test_search_drift_returns_community_list_and_fallback_flag(index_db: Path) -> None:
    """Das Werkzeug liefert ``communities`` als Liste und weist den Fallback aus (Spec 0.2.0)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_drift", {"query": "attention"})

    payload = _structured(result)
    assert result.isError is False
    assert set(payload) == {"query", "communities", "fallback", "citations"}
    assert isinstance(payload["communities"], list)
    assert isinstance(payload["fallback"], bool)


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


async def _sampling_callback(
    context: RequestContext[Any, Any],
    params: CreateMessageRequestParams,
) -> CreateMessageResult | ErrorData:
    """Attrappe eines Client-Modells: bestätigt Contract und Belege in der Anfrage."""
    prompt = params.systemPrompt or ""
    message = params.messages[0].content
    assert isinstance(message, TextContent)
    assert "nicht belegt" in prompt, "Der Zitier-Contract muss den Client erreichen."
    assert "[1]" in message.text, "Die nummerierten Belege müssen mitgeschickt werden."
    return CreateMessageResult(
        role="assistant",
        content=TextContent(type="text", text=_SAMPLED_ANSWER),
        model="fake-client-model",
    )


@pytest.mark.anyio
async def test_answer_question_returns_numbered_evidence_without_sampling(index_db: Path) -> None:
    """Default (`synthesize=false`): deterministische, nummerierte Evidenz ohne Generierung."""
    async with client_session(mcp) as client:
        result = await client.call_tool("answer_question", {"query": "transformer attention"})
    assert result.isError is False
    payload = _structured(result)
    assert payload["generated"] is False
    assert payload["answer"] == ""
    assert payload["mode"] in {"basic", "local", "global", "drift"}
    assert "nicht belegt" in payload["citation_contract"]
    items = payload["evidence"]["items"]
    assert [item["index"] for item in items] == list(range(1, len(items) + 1))
    assert items[0]["source_uri"].startswith("file:")


@pytest.mark.anyio
async def test_answer_question_exposes_the_routing_decision(index_db: Path) -> None:
    """Bei `auto` weist das Tool aus, warum der Modus gewählt wurde (A7)."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "answer_question", {"query": "Wo widersprechen sich die Ergebnisse?"}
        )
    assert result.isError is False
    routing = _structured(result)["routing"]
    assert set(routing) == {"mode", "confidence", "signals", "rationale"}
    assert routing["mode"] == "drift"
    assert routing["confidence"] == "strong"


@pytest.mark.anyio
async def test_answer_question_omits_routing_for_an_explicit_mode(index_db: Path) -> None:
    """Ein explizit gewählter Modus trägt kein Router-Urteil."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "answer_question", {"query": "transformer attention", "mode": "basic"}
        )
    assert result.isError is False
    assert _structured(result)["routing"] is None


@pytest.mark.anyio
async def test_answer_question_synthesizes_via_client_sampling(index_db: Path) -> None:
    """Mit `synthesize=true` liefert das Client-Modell die Antwort (Evidenz bleibt erhalten)."""
    async with client_session(mcp, sampling_callback=_sampling_callback) as client:
        result = await client.call_tool(
            "answer_question",
            {"query": "transformer attention", "mode": "basic", "synthesize": True},
        )
    assert result.isError is False
    payload = _structured(result)
    assert payload["generated"] is True
    assert payload["answer"] == _SAMPLED_ANSWER
    assert payload["model"] == "fake-client-model"
    assert payload["evidence"]["items"]


@pytest.mark.anyio
async def test_answer_question_degrades_without_sampling_capability(index_db: Path) -> None:
    """Ohne Sampling-fähigen Client bleibt `generated=false` – die Evidenz bleibt vollständig."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "answer_question",
            {"query": "transformer attention", "mode": "basic", "synthesize": True},
        )
    assert result.isError is False
    payload = _structured(result)
    assert payload["generated"] is False
    assert payload["answer"] == ""
    assert payload["evidence"]["items"]


@pytest.mark.anyio
async def test_answer_question_unknown_mode_yields_invalid_input_envelope(index_db: Path) -> None:
    """Unbekannter Modus -> strukturierter invalid_input-Fehler (isError=true)."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "answer_question", {"query": "transformer", "mode": "telepathie"}
        )
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "invalid_input"
