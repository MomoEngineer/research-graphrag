"""Tests der Sampling-Brücke an der Servergrenze (Phase 7 / A1, ADR 0012).

Der vollständige Roundtrip (Client-Modell → Antwort) wird in ``test_server.py`` über einen
In-Memory-Client mit Sampling-Callback geprüft. Hier steht der **Capability-Fallback** im Fokus:
Ohne Sampling-fähigen Client darf gar nicht erst gesampelt werden.
"""

from __future__ import annotations

from typing import Any, cast

from mcp.server.fastmcp import Context

from research_graphrag.generation.provider import GenerationRequest, NoopGenerationProvider
from research_graphrag.mcp_server.sampling import _user_message, provider_for


class _Session:
    """Minimale Session-Attrappe: meldet die konfigurierte Sampling-Fähigkeit."""

    def __init__(self, supports: bool) -> None:
        self._supports = supports

    def check_client_capability(self, capability: object) -> bool:
        return self._supports


class _Context:
    """Minimaler Kontext mit Session-Attrappe (nur die genutzte Schnittstelle)."""

    def __init__(self, supports: bool) -> None:
        self.session = _Session(supports)


def test_provider_is_noop_without_sampling_capability() -> None:
    """Kann der Client kein Sampling, wird der Noop-Fallback gewählt."""
    provider = provider_for(cast(Context[Any, Any], _Context(supports=False)))

    assert isinstance(provider, NoopGenerationProvider)


def test_provider_is_sampling_capable_client() -> None:
    """Mit Sampling-Fähigkeit entsteht ein Provider, der den Client befragt."""
    provider = provider_for(cast(Context[Any, Any], _Context(supports=True)))

    assert not isinstance(provider, NoopGenerationProvider)


def test_user_message_contains_question_and_evidence() -> None:
    """Die Nutzernachricht trägt Frage **und** nummerierte Belege."""
    message = _user_message(
        GenerationRequest(query="Welche Datensätze?", context="[1] Paper aaaa · Seite 3\n    Beleg")
    )

    assert "Frage: Welche Datensätze?" in message
    assert "[1] Paper aaaa" in message
