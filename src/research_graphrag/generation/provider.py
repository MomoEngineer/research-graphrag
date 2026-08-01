"""Generierungs-Port für die optionale Antwort-Synthese (LLM-Bridge).

Definiert den **injizierbaren** Port (:class:`GenerationProvider`) samt zweier Implementierungen:
:class:`SamplingGenerationProvider` (bezieht die Completion zur Abfragezeit vom Client-Modell über
MCP-Sampling) und :class:`NoopGenerationProvider` (Fallback ohne Modell → ``generated = False``).

Die Kernlogik bleibt **synchron und offline testbar**: Der Sampling-Provider adaptiert lediglich
einen injizierten, synchronen :data:`GenerationSampler`; die Async-Brücke zu
``session.create_message`` lebt ausschließlich an der Servergrenze
(docs/adr/0004-llm-bridge-via-mcp-sampling.md,
docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

DEFAULT_SYSTEM_PROMPT = (
    "Du beantwortest Fragen zu einem wissenschaftlichen Paper-Korpus. "
    "Nutze ausschließlich die nummerierten Belege im Kontext – kein Vorwissen, keine Vermutungen. "
    "Belege jede Aussage mit der passenden Marke in eckigen Klammern, z. B. [1] oder [2, 3]. "
    "Wenn die Belege eine Teilfrage nicht abdecken, schreibe dazu ausdrücklich "
    "'nicht belegt' statt zu spekulieren. Antworte knapp und auf Deutsch."
)
"""Verbindlicher Antwort-Contract der Synthese (strikt evidenzgebunden, ADR 0012)."""

MAX_ANSWER_TOKENS = 800
"""Obergrenze der angeforderten Completion (Sampling)."""

SAMPLING_TEMPERATURE = 0.0
"""Temperatur der Completion – 0 für best-effort-Reproduzierbarkeit (ADR 0004)."""


@dataclass(frozen=True)
class GenerationRequest:
    """Anfrage an den Generierungs-Port: Frage plus nummerierter Beleg-Kontext."""

    query: str
    context: str
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


@dataclass(frozen=True)
class GenerationResult:
    """Ergebnis einer Generierung; ``generated`` trennt Antwort von sichtbarer Degradation."""

    text: str
    generated: bool
    model: str = ""


GenerationSampler = Callable[[GenerationRequest], GenerationResult]
"""Synchroner Adapter auf ein Client-Modell (an der Servergrenze über ``anyio`` gebrückt)."""


class GenerationProvider(Protocol):
    """Injizierbarer Port für die Antwort-Synthese (ADR 0004, Punkt 2)."""

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Erzeugt – oder verweigert – eine Completion zur gegebenen Anfrage."""
        ...


class NoopGenerationProvider:
    """Fallback ohne Modell: liefert **keine** Antwort, damit die Evidenz maßgeblich bleibt."""

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Gibt ein leeres, nicht generiertes Ergebnis zurück (sichtbare Degradation)."""
        return GenerationResult(text="", generated=False)


class SamplingGenerationProvider:
    """Bezieht die Completion über einen injizierten, synchronen Sampler (MCP-Sampling).

    Der Provider erzwingt den Degradations-Contract: Eine leere Completion gilt als **nicht**
    generiert, damit nie eine inhaltsleere Antwort als Ergebnis ausgegeben wird.
    """

    def __init__(self, sampler: GenerationSampler) -> None:
        self._sampler = sampler

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Fordert die Completion über den injizierten Sampler an und normalisiert sie."""
        result = self._sampler(request)
        text = result.text.strip()
        if not text:
            return GenerationResult(text="", generated=False, model=result.model)
        return GenerationResult(text=text, generated=True, model=result.model)
