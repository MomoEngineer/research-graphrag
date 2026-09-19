"""Beispiel-Regression: prüft die in Abschnitt 10 jeder Tool-Spezifikation dokumentierten
Anfrage-/Antwort-Beispiele gegen den echten Server (`templates/tool-spec.md`, Abschnitt 10).

Anders als `docx-mcp`s `tests/test_spec_examples.py` (das seine Beispiele byte-für-byte
prüft, weil dessen Fixtures literalen, fixen Text tragen) prüft dieser Test **Struktur und
dokumentierte Kerntatsachen** (Paper-IDs, Feld-Vorhandensein, Vorzeichen/Kategorien), nicht
die vollen Fließkommawerte der Hybrid-Wertung (TF-IDF/BM25/Rank-Fusion) – deren exakte
Nachkommastellen sind Implementierungsdetail, kein dokumentierter Vertrag. Bricht dieser
Test, ist entweder die Spezifikation oder die Implementierung zu korrigieren (siehe
[docs/adr/0018](../../docs/adr/0018-code-documentation-architecture.md), Rangordnung der
Wahrheit: Tool-Spezifikation vor Code vor beschreibender Dokumentation).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as client_session
from mcp.types import CallToolResult

from research_graphrag.mcp_server.server import mcp


def _structured(result: CallToolResult) -> dict[str, Any]:
    """Liefert die strukturierte Nutzlast (structuredContent oder JSON-Text-Fallback)."""
    if result.structuredContent is not None:
        return result.structuredContent
    assert result.content and result.content[0].type == "text"
    payload: dict[str, Any] = json.loads(result.content[0].text)
    return payload


@pytest.mark.anyio
async def test_search_basic_example(index_db: Path) -> None:
    """specs/search_basic.md Abschnitt 10: query='attention', k=2 → Top-1 ist aaaa0001."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_basic", {"query": "attention", "k": 2})
    payload = _structured(result)
    assert len(payload["citations"]) == 2
    top = payload["citations"][0]
    assert top["paper_id"] == "aaaa0001"
    assert top["section_title"] == "Introduction"
    assert top["page_number"] == 1
    assert top["identifiers"] == {"doi": "10.1145/1234", "arxiv": "2405.20455"}


@pytest.mark.anyio
async def test_search_local_example(index_db: Path) -> None:
    """specs/search_local.md Abschnitt 10: aaaa0002 zitiert aaaa0001, sichtbar in fan_out."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "search_local", {"query": "attention", "k": 4, "fan_out": 5}
        )
    payload = _structured(result)
    assert payload["seeds"][0]["paper_id"] == "aaaa0001"
    assert (
        payload["neighborhood"][0]["snippet"]
        == "[1] Vorarbeit zur Aufmerksamkeit. doi:10.1145/1234"
    )
    assert payload["fan_out"][0]["paper_id"] == "aaaa0002"
    assert payload["fan_out"][0]["citation"]["paper_id"] == "aaaa0002"


@pytest.mark.anyio
async def test_search_global_example(index_db: Path) -> None:
    """specs/search_global.md Abschnitt 10: die Graph-Community gewinnt bei dieser Anfrage."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_global", {"query": "graph communities", "n": 1})
    payload = _structured(result)
    assert len(payload["communities"]) == 1
    community = payload["communities"][0]
    assert community["community_id"] == 1
    representatives = {rep["paper_id"] for rep in community["representatives"]}
    assert representatives == {"bbbb0001", "bbbb0002"}


@pytest.mark.anyio
async def test_search_drift_example(index_db: Path) -> None:
    """specs/search_drift.md Abschnitt 10: passende Community gefunden -> fallback=false."""
    async with client_session(mcp) as client:
        result = await client.call_tool("search_drift", {"query": "graph communities", "k": 2})
    payload = _structured(result)
    assert payload["fallback"] is False
    assert payload["communities"][0]["community_id"] == 1
    assert payload["citations"][0]["paper_id"] == "bbbb0002"


@pytest.mark.anyio
async def test_get_paper_example(index_db: Path) -> None:
    """specs/get_paper.md Abschnitt 10: n_pages/sections/identifiers von aaaa0001."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_paper", {"paper_id": "aaaa0001"})
    payload = _structured(result)
    assert payload["n_pages"] == 2
    assert payload["sections"] == ["Introduction", "Methods"]
    assert payload["identifiers"] == {"arxiv": "2405.20455", "doi": "10.1145/1234"}
    assert payload["reference"]["citable"] is False


@pytest.mark.anyio
async def test_get_citations_example(index_db: Path) -> None:
    """specs/get_citations.md Abschnitt 10: aaaa0002 zitiert aaaa0001 per DOI."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_citations", {"paper_id": "aaaa0001"})
    payload = _structured(result)
    assert payload["cites"] == []
    assert [entry["paper_id"] for entry in payload["cited_by"]] == ["aaaa0002"]
    assert payload["cited_by"][0]["method"] == "doi"


@pytest.mark.anyio
async def test_get_reference_example(index_db: Path) -> None:
    """specs/get_reference.md Abschnitt 10: Autoren fehlen ohne Online-Auflösung."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_reference", {"paper_id": "aaaa0001"})
    payload = _structured(result)
    assert payload["styles"] == ["harvard", "apa"]
    assert payload["missing"] == ["authors"]
    assert payload["reference"]["doi"] == "10.1145/1234"
    assert payload["reference"]["harvard"].startswith("aaaa0001 (2024)")


@pytest.mark.anyio
async def test_get_paper_file_example(index_db: Path) -> None:
    """specs/get_paper_file.md Abschnitt 10: kein Fehler, sondern available=false."""
    async with client_session(mcp) as client:
        result = await client.call_tool("get_paper_file", {"paper_id": "aaaa0001"})
    assert result.isError is False
    payload = _structured(result)
    assert payload["available"] is False
    assert payload["reason"] == "file_missing"
    assert payload["path"] == ""


@pytest.mark.anyio
async def test_list_topics_example(index_db: Path) -> None:
    """specs/list_topics.md Abschnitt 10: zwei thematisch getrennte Communities."""
    async with client_session(mcp) as client:
        result = await client.call_tool("list_topics", {})
    payload = _structured(result)
    assert payload["total_matching"] == 2
    assert payload["truncated"] is False
    representatives_by_community = {
        topic["community_id"]: set(topic["representatives"]) for topic in payload["topics"]
    }
    assert representatives_by_community == {
        0: {"aaaa0001", "aaaa0002"},
        1: {"bbbb0001", "bbbb0002"},
    }


@pytest.mark.anyio
async def test_answer_question_example(index_db: Path) -> None:
    """specs/answer_question.md Abschnitt 10: ohne Router-Signal -> Fallback auf basic."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "answer_question", {"query": "How does attention work?", "k": 2}
        )
    payload = _structured(result)
    assert payload["mode"] == "basic"
    assert payload["routing"]["confidence"] == "none"
    assert payload["generated"] is False
    assert payload["evidence"]["items"][0]["paper_id"] == "aaaa0001"
    assert (
        payload["evidence"]["items"][0]["label"]
        == "Paper aaaa0001 · Abschnitt Introduction · Seite 1"
    )


@pytest.mark.anyio
async def test_correct_paper_metadata_example(index_db: Path) -> None:
    """specs/correct_paper_metadata.md Abschnitt 10: record trägt kein eigenes paper_id-Feld."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "correct_paper_metadata",
            {
                "paper_id": "aaaa0001",
                "venue": "ACM SIGCOMM",
                "evidence": "laut Publisher-Landingpage doi.org/10.1145/1234",
            },
        )
    payload = _structured(result)
    assert payload["applied_fields"] == ["venue"]
    assert "paper_id" not in payload["record"]
    assert payload["record"]["origin"] == "manual"
    assert payload["record"]["venue"] == "ACM SIGCOMM"
    assert payload["record"]["cleared_fields"] == []
    assert payload["effective_after"] == "python -m scripts.ingest"


@pytest.mark.anyio
async def test_correct_paper_metadata_clear_example(index_db: Path) -> None:
    """specs/correct_paper_metadata.md Abschnitt 10.2: arxiv_id explizit leeren (ADR 0040)."""
    async with client_session(mcp) as client:
        result = await client.call_tool(
            "correct_paper_metadata",
            {
                "paper_id": "aaaa0001",
                "clear_fields": ["arxiv_id"],
                "evidence": (
                    "arXiv-ID gehoert zu einem im Volltext zitierten Fremdpaper, "
                    "nicht zu diesem Buch"
                ),
            },
        )
    payload = _structured(result)
    assert payload["applied_fields"] == ["arxiv_id"]
    assert payload["previous"] == {"arxiv_id": ""}
    assert payload["record"]["arxiv_id"] == ""
    assert payload["record"]["cleared_fields"] == ["arxiv_id"]
