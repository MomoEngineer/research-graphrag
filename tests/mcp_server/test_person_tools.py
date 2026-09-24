"""Contract- und Beispieltests der Personen-Werkzeuge (Phase 17 / A4, ADR 0043).

Verbindet Server und Client über In-Memory-Streams, wie ``test_server.py``, aber gegen den
Personen-Index aus ``tests/conftest.py`` (``make_person_index``). Geprüft werden je Werkzeug der
Erfolgs-Contract, die Fehlerausgabe (``isError = true``) und das Beispiel aus Abschnitt 10 der
Spezifikation (Struktur und dokumentierte Kerntatsachen, wie ``test_spec_examples.py``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as client_session
from mcp.types import CallToolResult

from research_graphrag.mcp_server.server import mcp

ASAI = "A5023888391"


@pytest.fixture
def person_db(make_person_index: Callable[..., Path], monkeypatch: pytest.MonkeyPatch) -> Path:
    """Personen-Index, auf den der Server per Env zeigt."""
    db = make_person_index()
    monkeypatch.setenv("RESEARCH_GRAPHRAG_INDEX", str(db))
    return db


def _structured(result: CallToolResult) -> dict[str, Any]:
    """Liefert die strukturierte Nutzlast (structuredContent oder JSON-Text-Fallback)."""
    if result.structuredContent is not None:
        return result.structuredContent
    assert result.content and result.content[0].type == "text"
    payload: dict[str, Any] = json.loads(result.content[0].text)
    return payload


async def _call(tool: str, arguments: dict[str, Any]) -> CallToolResult:
    """Ruft ein Werkzeug über den In-Memory-Client auf."""
    async with client_session(mcp) as client:
        return await client.call_tool(tool, arguments)


def _coverage_ok(payload: dict[str, Any]) -> None:
    """Jede Antwort trägt die Abdeckung der Personenebene."""
    assert payload["coverage"]["full_texts_with_authors"] == 4
    assert payload["coverage"]["full_texts"] == 6
    assert payload["coverage"]["note"]


@pytest.mark.anyio
async def test_search_authors_example(person_db: Path) -> None:
    """specs/search_authors.md Abschnitt 10: zwei Kandidaten, mehrdeutig."""
    result = await _call("search_authors", {"name": "Asai"})

    assert result.isError is False
    payload = _structured(result)
    assert [c["person_key"] for c in payload["candidates"]] == [ASAI, "name:akari asai"]
    assert [c["identity"] for c in payload["candidates"]] == ["openalex", "name"]
    assert payload["candidates"][0]["names"] == ["Akari Asai", "Asai, Akari"]
    assert payload["candidates"][0]["year_span"] == [2024, 2025]
    assert payload["total_matching"] == 2
    assert payload["ambiguous"] is True
    _coverage_ok(payload)


@pytest.mark.anyio
async def test_get_author_example(person_db: Path) -> None:
    """specs/get_author.md Abschnitt 10: Paper, Community, Mitautoren."""
    result = await _call("get_author", {"person_key": ASAI})

    assert result.isError is False
    payload = _structured(result)
    assert [paper["paper_id"] for paper in payload["papers"]] == ["aaaa0002", "aaaa0001"]
    assert payload["papers"][0]["citation_key"] == "Asai2025"
    assert payload["papers"][0]["position"] == 1
    assert payload["year_span"] == [2024, 2025]
    assert [c["person_key"] for c in payload["coauthors"]] == [
        "name:zeqiu wu",
        "A5000000003",
        "name:bert muster",
    ]
    assert payload["coauthors"][0]["n_shared"] == 2
    assert sum(community["n_papers"] for community in payload["communities"]) == 2
    _coverage_ok(payload)


@pytest.mark.anyio
async def test_search_author_papers_example(person_db: Path) -> None:
    """specs/search_author_papers.md Abschnitt 10: Zitate nur aus Papern der Person."""
    result = await _call("search_author_papers", {"person_key": ASAI, "query": "attention", "k": 2})

    assert result.isError is False
    payload = _structured(result)
    assert [c["paper_id"] for c in payload["citations"]] == ["aaaa0002", "aaaa0001"]
    assert payload["citations"][0]["section_title"] == "Introduction"
    assert payload["citations"][0]["identifiers"] == {"doi": "10.1000/reflect"}
    assert payload["papers_searched"] == 2
    _coverage_ok(payload)


@pytest.mark.anyio
async def test_get_author_citations_example(person_db: Path) -> None:
    """specs/get_author_citations.md Abschnitt 10: beide Richtungen, Selbstzitate markiert."""
    result = await _call("get_author_citations", {"person_key": ASAI})

    assert result.isError is False
    payload = _structured(result)
    assert payload["scope"] == "corpus"
    assert [(c["paper"]["paper_id"], c["self"]) for c in payload["cites"]] == [
        ("aaaa0001", True),
        ("cccc0001", False),
    ]
    assert [c["paper"]["paper_id"] for c in payload["cited_by"]] == [
        "cccc0001",
        "aaaa0002",
        "bbbb0001",
    ]
    assert payload["cited_by"][0]["via"] == ["aaaa0001", "aaaa0002"]
    assert payload["cited_by"][0]["methods"] == ["doi"]
    assert (payload["cites_total"], payload["cited_by_total"]) == (2, 3)
    _coverage_ok(payload)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "arguments", "code"),
    [
        ("search_authors", {"name": "Nobody"}, "not_found"),
        ("search_authors", {"name": "Asai", "limit": 51}, "invalid_input"),
        ("get_author", {"person_key": "A999"}, "not_found"),
        ("get_author", {"person_key": ""}, "invalid_input"),
        ("search_author_papers", {"person_key": ASAI, "query": ""}, "invalid_input"),
        ("search_author_papers", {"person_key": "A999", "query": "x"}, "not_found"),
        ("get_author_citations", {"person_key": ASAI, "limit": 0}, "invalid_input"),
        ("get_author_citations", {"person_key": "A999"}, "not_found"),
    ],
)
async def test_person_tools_report_errors_as_envelope(
    person_db: Path, tool: str, arguments: dict[str, Any], code: str
) -> None:
    """Fachliche Fehler kommen als strukturierter Envelope mit ``isError = true``."""
    result = await _call(tool, arguments)

    assert result.isError is True
    assert _structured(result)["error"]["code"] == code


@pytest.mark.anyio
async def test_not_found_names_the_coverage(person_db: Path) -> None:
    """Ein unbekannter Name nennt die Abdeckung, damit „nicht gefunden“ nicht als „nicht da“
    missverstanden wird."""
    result = await _call("search_authors", {"name": "Nobody"})

    assert "4 von 6" in _structured(result)["error"]["message"]
