"""Async-Brücke zum Client-Modell (MCP-Sampling) – **nur** an der Servergrenze.

Die Kernlogik der Antwort-Synthese ist synchron und modellfrei
(:mod:`research_graphrag.generation`); ein Modell kommt ausschließlich über den aufrufenden
MCP-Client ins Spiel (``session.create_message``). Dieses Modul übersetzt zwischen beiden Welten:
Es baut aus einer aktiven :class:`~mcp.server.fastmcp.Context` einen **synchronen**
:class:`~research_graphrag.generation.provider.GenerationProvider`, dessen Sampler den Aufruf per
``anyio`` aus dem Worker-Thread zurück in den Event-Loop reicht.

Grundsätze: kein gebundenes Modell und keine Secrets im Server
(docs/adr/0004-llm-bridge-via-mcp-sampling.md); Sampling ist **opt-in** und degradiert sichtbar,
statt zu scheitern (docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md).
"""

from __future__ import annotations

import logging

import anyio.from_thread
import mcp.types as types
from mcp.server.fastmcp import Context

from research_graphrag.generation.provider import (
    MAX_ANSWER_TOKENS,
    SAMPLING_TEMPERATURE,
    GenerationProvider,
    GenerationRequest,
    GenerationResult,
    NoopGenerationProvider,
    SamplingGenerationProvider,
)

logger = logging.getLogger("research_graphrag.mcp_server.sampling")


def _supports_sampling(context: Context) -> bool:  # type: ignore[type-arg]
    """Prüft, ob der verbundene Client Sampling anbietet."""
    capability = types.ClientCapabilities(sampling=types.SamplingCapability())
    return bool(context.session.check_client_capability(capability))


def _user_message(request: GenerationRequest) -> str:
    """Baut die Nutzernachricht aus Frage und nummeriertem Beleg-Kontext."""
    return f"Frage: {request.query}\n\nBelege:\n{request.context}"


async def _request_completion(context: Context, request: GenerationRequest) -> GenerationResult:  # type: ignore[type-arg]
    """Fordert die Completion beim Client an und bildet sie auf den Port-Typ ab."""
    result = await context.session.create_message(
        messages=[
            types.SamplingMessage(
                role="user",
                content=types.TextContent(type="text", text=_user_message(request)),
            )
        ],
        max_tokens=MAX_ANSWER_TOKENS,
        system_prompt=request.system_prompt,
        temperature=SAMPLING_TEMPERATURE,
    )
    text = result.content.text if isinstance(result.content, types.TextContent) else ""
    return GenerationResult(text=text, generated=bool(text.strip()), model=result.model)


def provider_for(context: Context) -> GenerationProvider:  # type: ignore[type-arg]
    """Liefert den passenden Generierungs-Port für die laufende Anfrage.

    Kann der Client kein Sampling, wird der :class:`NoopGenerationProvider` zurückgegeben – die
    Antwort degradiert dann sichtbar (``generated = false``) und die Evidenz bleibt vollständig.

    Args:
        context: Der von FastMCP injizierte Anfrage-Kontext (enthält die Client-Session).

    Returns:
        Einen synchronen Generierungs-Port; Sampling-Fehler werden protokolliert und in eine
        nicht-generierte Antwort übersetzt, statt den Tool-Aufruf abzubrechen.
    """
    if not _supports_sampling(context):
        logger.info("Client bietet kein Sampling an – Antwort-Synthese wird übersprungen.")
        return NoopGenerationProvider()

    def sampler(request: GenerationRequest) -> GenerationResult:
        try:
            return anyio.from_thread.run(_request_completion, context, request)
        except Exception:  # noqa: BLE001 - Sampling ist optional; Evidenz bleibt maßgeblich
            logger.warning("Sampling beim Client fehlgeschlagen – liefere nur Evidenz.")
            return GenerationResult(text="", generated=False)

    return SamplingGenerationProvider(sampler)
