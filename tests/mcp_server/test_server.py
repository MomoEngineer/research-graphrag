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

import dataclasses
import json
from collections.abc import Callable
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

from research_graphrag.extraction.pdf import CanonicalPaper
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.mcp_server import server as server_module
from research_graphrag.mcp_server.server import mcp

_TOOLS = {
    "search_basic",
    "search_local",
    "search_global",
    "search_drift",
    "get_paper",
    "get_paper_file",
    "get_citations",
    "list_topics",
    "get_reference",
    "answer_question",
    "correct_paper_metadata",
}

_SAMPLED_ANSWER = "Aufmerksamkeit ist der Kern der Architektur [1]."


def _structured(result: CallToolResult) -> dict[str, Any]:
    """Liefert die strukturierte Nutzlast (structuredContent oder JSON-Text-Fallback)."""
    if result.structuredContent is not None:
        return result.structuredContent
    assert result.content and result.content[0].type == "text"
    payload: dict[str, Any] = json.loads(result.content[0].text)
    return payload


@pytest.mark.anyio
async def test_list_tools_exposes_all_tools(index_db: Path) -> None:
    """Der Server listet genau die elf zugesagten Tools."""
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
    """list_topics liefert die gefilterte, membergelöste Community-Übersicht (Spec 0.2.0)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("list_topics", {})
    assert result.isError is False
    payload = _structured(result)
    assert set(payload) == {"topics", "total_matching", "truncated"}
    assert isinstance(payload["topics"], list)
    assert payload["topics"]
    assert "members" not in payload["topics"][0]


@pytest.mark.anyio
async def test_list_topics_community_id_returns_full_detail(index_db: Path) -> None:
    """Mit community_id liefert das Werkzeug genau eine Community inklusive members."""
    async with client_session(mcp) as client:
        overview = await client.call_tool("list_topics", {})
        target = _structured(overview)["topics"][0]
        result = await client.call_tool("list_topics", {"community_id": target["community_id"]})

    assert result.isError is False
    payload = _structured(result)
    assert payload["community_id"] == target["community_id"]
    assert isinstance(payload["members"], list)
    assert payload["members"]


@pytest.mark.anyio
async def test_list_topics_unknown_community_id_yields_not_found_envelope(index_db: Path) -> None:
    """Eine unbekannte community_id -> strukturierter not_found-Fehler (isError=true)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("list_topics", {"community_id": 999_999})
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "not_found"


@pytest.mark.anyio
async def test_list_topics_min_size_one_includes_singletons(index_db: Path) -> None:
    """min_size=1 lässt auch Ein-Paper-Communities in die Übersicht."""
    async with client_session(mcp) as client:
        default = await client.call_tool("list_topics", {})
        broadened = await client.call_tool("list_topics", {"min_size": 1})

    assert _structured(broadened)["total_matching"] >= _structured(default)["total_matching"]


@pytest.mark.anyio
async def test_list_topics_limit_above_max_yields_invalid_input_envelope(index_db: Path) -> None:
    """limit > MAX_RESULT_COUNT -> strukturierter invalid_input-Fehler (ADR 0037)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("list_topics", {"limit": 51})
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "invalid_input"


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
async def test_get_paper_file_reports_missing_local_pdf(index_db: Path) -> None:
    """Die Fixture-Paper zeigen auf nicht real vorhandene Dateien -> available=false, kein Fehler."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_paper_file", {"paper_id": "aaaa0001"})
    assert result.isError is False
    payload = _structured(result)
    assert payload["document_kind"] == "full"
    assert payload["available"] is False
    assert payload["reason"] == "file_missing"
    assert payload["path"] == ""


@pytest.mark.anyio
async def test_get_paper_file_resolves_a_real_local_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_paper_fn: Callable[..., CanonicalPaper]
) -> None:
    """Ein tatsächlich vorhandenes PDF liefert available=true und den nativen Pfad."""
    pdf = tmp_path / "Original.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    paper = dataclasses.replace(
        make_paper_fn("cccc0001", ["irrelevant content for retrieval"]),
        source_uri=pdf.resolve().as_uri(),
    )
    db = tmp_path / "index" / "index.sqlite"
    build_index([paper], db)
    monkeypatch.setenv("RESEARCH_GRAPHRAG_INDEX", str(db))

    async with client_session(mcp) as client:
        result = await client.call_tool("get_paper_file", {"paper_id": "cccc0001"})
    assert result.isError is False
    payload = _structured(result)
    assert payload["available"] is True
    assert payload["path"] == str(pdf.resolve())
    assert payload["size_bytes"] == pdf.stat().st_size


@pytest.mark.anyio
async def test_get_paper_file_unknown_paper_yields_not_found_envelope(index_db: Path) -> None:
    """Unbekannte paper_id -> strukturierter not_found-Fehler (isError=true)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_paper_file", {"paper_id": "zzzznope0"})
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "not_found"


@pytest.mark.anyio
async def test_correct_paper_metadata_writes_manual_record(index_db: Path) -> None:
    """Eine erfolgreiche Korrektur meldet die geänderten Felder und effective_after."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "correct_paper_metadata",
            {"paper_id": "aaaa0001", "doi": "10.1145/9999999", "evidence": "laut Publisher-Seite"},
        )
    assert result.isError is False
    payload = _structured(result)
    assert payload["applied_fields"] == ["doi"]
    assert payload["record"]["doi"] == "10.1145/9999999"
    assert payload["record"]["origin"] == "manual"
    assert payload["effective_after"] == "python -m scripts.ingest"


@pytest.mark.anyio
async def test_correct_paper_metadata_without_fields_yields_invalid_input_envelope(
    index_db: Path,
) -> None:
    """Ohne mindestens ein Korrekturfeld -> strukturierter invalid_input-Fehler."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "correct_paper_metadata", {"paper_id": "aaaa0001", "evidence": "Beleg"}
        )
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "invalid_input"


@pytest.mark.anyio
async def test_correct_paper_metadata_wrong_type_is_rejected_at_the_protocol_boundary(
    index_db: Path,
) -> None:
    """Ein falscher Parametertyp (year als String) wird per Schema abgelehnt, nicht als Crash.

    Das ist die vom SDK behandelte Protokoll-/Discovery-Fehlerebene (docs/error-model.md,
    Abschnitt 1) – anders als eine fachliche DomainError trägt sie keinen strukturierten
    Envelope, sondern eine SDK-eigene Validierungsmeldung. Wichtig ist nur: kein unbehandelter
    Absturz, `isError = true`.
    """
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "correct_paper_metadata",
            {"paper_id": "aaaa0001", "evidence": "x", "year": "not-a-number"},
        )
    assert result.isError is True
    assert result.content and result.content[0].type == "text"
    assert "year" in result.content[0].text


@pytest.mark.anyio
async def test_correct_paper_metadata_unknown_paper_yields_not_found_envelope(
    index_db: Path,
) -> None:
    """Unbekannte paper_id -> strukturierter not_found-Fehler (isError=true)."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "correct_paper_metadata",
            {"paper_id": "zzzznope0", "doi": "10.1/x", "evidence": "Beleg"},
        )
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "not_found"


@pytest.mark.anyio
async def test_correct_paper_metadata_clear_fields_marks_field_explicitly_empty(
    index_db: Path,
) -> None:
    """clear_fields (ADR 0040) meldet das Feld als geändert und markiert es in cleared_fields."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "correct_paper_metadata",
            {
                "paper_id": "aaaa0001",
                "evidence": "arXiv-ID gehört zu einem Fremdpaper",
                "clear_fields": ["arxiv_id"],
            },
        )
    assert result.isError is False
    payload = _structured(result)
    assert payload["applied_fields"] == ["arxiv_id"]
    assert payload["record"]["arxiv_id"] == ""
    assert payload["record"]["cleared_fields"] == ["arxiv_id"]


@pytest.mark.anyio
async def test_correct_paper_metadata_field_set_and_cleared_at_once_is_invalid(
    index_db: Path,
) -> None:
    """Ein Feld gleichzeitig setzen und leeren -> strukturierter invalid_input-Fehler."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "correct_paper_metadata",
            {
                "paper_id": "aaaa0001",
                "doi": "10.1/x",
                "clear_fields": ["doi"],
                "evidence": "Beleg",
            },
        )
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "invalid_input"


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
    """Das Werkzeug liefert das Feld ``seeds`` als Liste (Spec 0.3.0, ADR 0021/0031)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_local", {"query": "attention", "fan_out": 0})

    payload = _structured(result)
    assert result.isError is False
    assert set(payload) == {"query", "seeds", "neighborhood", "fan_out"}
    assert isinstance(payload["seeds"], list)
    assert all("chunk_id" in seed for seed in payload["seeds"])


@pytest.mark.anyio
async def test_search_drift_returns_community_list_and_fallback_flag(index_db: Path) -> None:
    """Das Werkzeug liefert ``communities`` als Liste und weist den Fallback aus (Spec 0.3.0)."""
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


@pytest.mark.anyio
async def test_search_basic_k_above_max_result_count_yields_invalid_input_envelope(
    index_db: Path,
) -> None:
    """k > MAX_RESULT_COUNT -> strukturierter invalid_input-Fehler (ADR 0037)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_basic", {"query": "attention", "k": 51})
    assert result.isError is True
    assert _structured(result)["error"]["code"] == "invalid_input"


@pytest.mark.anyio
async def test_get_citations_limit_caps_and_exposes_totals(index_db: Path) -> None:
    """get_citations deckelt cites/cited_by über limit und weist die Totals aus (ADR 0037)."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_citations", {"paper_id": "aaaa0001", "limit": 1})
    assert result.isError is False
    payload = _structured(result)
    assert set(payload) == {"paper", "cites", "cites_total", "cited_by", "cited_by_total"}


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


def test_guard_rejects_a_response_over_the_safety_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_guard verwirft eine zu große Antwort als constraint_violation, nie gekürzt (ADR 0037)."""
    monkeypatch.setattr(server_module, "_MAX_RESPONSE_BYTES", 10)

    result = server_module._guard("dummy_tool", lambda: {"citations": ["x" * 100]})

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    assert result.structuredContent is not None
    assert result.structuredContent["error"]["code"] == "constraint_violation"


def test_guard_passes_through_a_response_within_the_safety_threshold() -> None:
    """Unterhalb der Schwelle liefert _guard die Antwort unverändert durch."""
    payload = {"citations": ["ok"]}

    result = server_module._guard("dummy_tool", lambda: payload)

    assert result == payload
