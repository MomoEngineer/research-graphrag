"""Antwort-Synthese / LLM-Bridge (Phase 7 / A1).

Bündelt den injizierbaren Generierungs-Port, die mode-agnostische Evidenz-Repräsentation und die
Adapter von den vier Retrieval-Modi. Die eigentliche natürlichsprachige Antwort entsteht nur mit
einem sampling-fähigen Client; ohne ihn degradiert die Pipeline sichtbar (``generated = False``),
während die volle Provenienz erhalten bleibt (docs/adr/0004-llm-bridge-via-mcp-sampling.md,
docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md).
"""

from __future__ import annotations

from research_graphrag.generation.answer import (
    AUTO_MODE,
    EVIDENCE_BUILDERS,
    answer_question,
    resolve_mode,
    resolve_routing,
)
from research_graphrag.generation.evidence import (
    evidence_from_basic,
    evidence_from_drift,
    evidence_from_global,
    evidence_from_local,
)
from research_graphrag.generation.provider import (
    DEFAULT_SYSTEM_PROMPT,
    GenerationProvider,
    GenerationRequest,
    GenerationResult,
    GenerationSampler,
    NoopGenerationProvider,
    SamplingGenerationProvider,
)
from research_graphrag.generation.synthesis import (
    Evidence,
    EvidenceItem,
    SynthesisResult,
    synthesize_answer,
)

__all__ = [
    "AUTO_MODE",
    "DEFAULT_SYSTEM_PROMPT",
    "EVIDENCE_BUILDERS",
    "Evidence",
    "EvidenceItem",
    "GenerationProvider",
    "GenerationRequest",
    "GenerationResult",
    "GenerationSampler",
    "NoopGenerationProvider",
    "SamplingGenerationProvider",
    "SynthesisResult",
    "answer_question",
    "evidence_from_basic",
    "evidence_from_drift",
    "evidence_from_global",
    "evidence_from_local",
    "resolve_mode",
    "resolve_routing",
    "synthesize_answer",
]
