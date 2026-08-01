"""Tests für den Generierungs-Port (LLM-Bridge, Phase 7 / A1, ADR 0012)."""

from __future__ import annotations

from research_graphrag.generation.provider import (
    DEFAULT_SYSTEM_PROMPT,
    GenerationProvider,
    GenerationRequest,
    GenerationResult,
    NoopGenerationProvider,
    SamplingGenerationProvider,
)


def _request(query: str = "Welche Datensätze werden genutzt?") -> GenerationRequest:
    return GenerationRequest(query=query, context="[1] Paper aaaa · Seite 3\n    Beleg")


def test_noop_provider_degrades_visibly() -> None:
    """Ohne Modell wird nichts generiert – erkennbar an ``generated = False``."""
    result = NoopGenerationProvider().generate(_request())

    assert result.generated is False
    assert result.text == ""
    assert result.model == ""


def test_noop_provider_satisfies_port() -> None:
    """Beide Implementierungen erfüllen das Protokoll (strukturell geprüft)."""
    noop: GenerationProvider = NoopGenerationProvider()
    sampling: GenerationProvider = SamplingGenerationProvider(
        lambda request: GenerationResult(text="x", generated=True)
    )

    assert noop.generate(_request()).generated is False
    assert sampling.generate(_request()).generated is True


def test_sampling_provider_passes_request_and_normalizes() -> None:
    """Der Sampler erhält Frage, Kontext und Contract; die Antwort wird getrimmt."""
    seen: list[GenerationRequest] = []

    def sampler(request: GenerationRequest) -> GenerationResult:
        seen.append(request)
        return GenerationResult(text="  Antwort [1].  ", generated=True, model="test-model")

    result = SamplingGenerationProvider(sampler).generate(_request("Frage?"))

    assert [request.query for request in seen] == ["Frage?"]
    assert seen[0].system_prompt == DEFAULT_SYSTEM_PROMPT
    assert "[1]" in seen[0].context
    assert result == GenerationResult(text="Antwort [1].", generated=True, model="test-model")


def test_sampling_provider_treats_empty_completion_as_not_generated() -> None:
    """Eine leere Completion gilt als **nicht** generiert (keine Scheinantwort)."""
    provider = SamplingGenerationProvider(
        lambda request: GenerationResult(text="   \n ", generated=True, model="test-model")
    )

    result = provider.generate(_request())

    assert result.generated is False
    assert result.text == ""
    assert result.model == "test-model"


def test_default_system_prompt_states_the_contract() -> None:
    """Der Contract verlangt Evidenzbindung, Zitatmarken und 'nicht belegt'."""
    assert "ausschließlich" in DEFAULT_SYSTEM_PROMPT
    assert "[1]" in DEFAULT_SYSTEM_PROMPT
    assert "nicht belegt" in DEFAULT_SYSTEM_PROMPT
