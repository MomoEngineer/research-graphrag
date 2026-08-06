"""Antwort-Synthese aus Retrieval-Evidenz (LLM-Bridge, Phase 7 / A1).

Enthält die **mode-agnostische** Zwischenrepräsentation der Belege (:class:`Evidence`) und die
Orchestrierung :func:`synthesize_answer`. Die Evidenz-Assemblierung ist **deterministisch**; die
einzige mögliche Quelle von Nichtdeterminismus ist ein reales Sampling im Provider. Ohne Modell
(Noop) bleibt die volle Evidenz erhalten und die Pipeline degradiert **sichtbar**
(``generated = False``), statt zu scheitern (Provenienz zuerst).

Dieses Modul importiert bewusst **keine** Retrieval-Typen; die Adapter von den vier Modus-
Ergebnissen auf :class:`Evidence` liegen in :mod:`research_graphrag.generation.evidence`.
Grundsatz: docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from research_graphrag.generation.provider import (
    DEFAULT_SYSTEM_PROMPT,
    GenerationProvider,
    GenerationRequest,
)


@dataclass(frozen=True)
class EvidenceSource:
    """Eingabeform eines Belegs für :meth:`Evidence.build` (vor der Nummerierung).

    Bewusst ein benannter Typ statt eines Tupels: Die Felder ``label``, ``snippet`` und
    ``source_uri`` sind allesamt Zeichenketten und wären in einem Tupel still vertauschbar.
    """

    paper_id: str
    label: str
    snippet: str
    source_uri: str
    identifiers: Mapping[str, str] = field(default_factory=dict)
    citation_key: str = ""


@dataclass(frozen=True)
class EvidenceItem:
    """Ein nummerierter Beleg: Provenienz-Label, Textausschnitt und Quelle.

    ``index`` ist die Zitatmarke (``[1]``, ``[2]`` …), auf die sich die Antwort beziehen muss.
    ``identifiers`` und ``citation_key`` machen den Beleg extern auflösbar; die vollständige
    Literaturangabe steht gesammelt in ``references``
    (docs/adr/0025-citable-paper-metadata.md).
    """

    index: int
    paper_id: str
    label: str
    snippet: str
    source_uri: str
    identifiers: Mapping[str, str] = field(default_factory=dict)
    citation_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Beleg."""
        return {
            "index": self.index,
            "paper_id": self.paper_id,
            "label": self.label,
            "snippet": self.snippet,
            "source_uri": self.source_uri,
            "identifiers": dict(self.identifiers),
            "citation_key": self.citation_key,
        }


@dataclass(frozen=True)
class Evidence:
    """Mode-agnostische Beleg-Sammlung zu einer Anfrage."""

    query: str
    mode: str
    items: tuple[EvidenceItem, ...]

    @classmethod
    def build(cls, query: str, mode: str, entries: Sequence[EvidenceSource]) -> Evidence:
        """Baut die Evidenz aus :class:`EvidenceSource`-Einträgen.

        Die Nummerierung vergibt diese Methode – so ist sie an genau einer Stelle definiert und
        über alle Modi hinweg identisch.
        """
        items = tuple(
            EvidenceItem(
                index=position,
                paper_id=source.paper_id,
                label=source.label,
                snippet=source.snippet,
                source_uri=source.source_uri,
                identifiers=source.identifiers,
                citation_key=source.citation_key,
            )
            for position, source in enumerate(entries, start=1)
        )
        return cls(query=query, mode=mode, items=items)

    def is_empty(self) -> bool:
        """``True``, wenn keine Belege vorliegen (dann wird kein Provider befragt)."""
        return not self.items

    def as_context(self) -> str:
        """Fügt die Belege deterministisch zu einem nummerierten Prompt-Kontext zusammen."""
        return "\n".join(
            f"[{item.index}] {item.label}\n    {item.snippet}\n    Quelle: {item.source_uri}"
            for item in self.items
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Beleg-Sammlung."""
        return {
            "query": self.query,
            "mode": self.mode,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class SynthesisResult:
    """Ergebnis der Synthese: Antwort (falls generiert) **plus** die vollständige Evidenz.

    ``references`` enthält je vorkommendem Paper **einmal** die vollständige Literaturangabe
    (Harvard und APA). Sie steht bewusst neben der Evidenz statt in jedem Beleg: Fünf Belege
    desselben Papers würden die Angabe sonst fünfmal tragen
    (docs/adr/0025-citable-paper-metadata.md, Punkt 5). Wie ``routing`` wird sie als einfache
    Abbildung durchgereicht, damit dieses Modul frei von Retrieval-Typen bleibt.
    """

    query: str
    mode: str
    answer: str
    generated: bool
    evidence: Evidence
    model: str = ""
    routing: dict[str, Any] | None = None
    references: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Ergebnis inkl. Evidenz, Zitier-Contract und Literaturangaben."""
        return {
            "query": self.query,
            "mode": self.mode,
            "routing": self.routing,
            "answer": self.answer,
            "generated": self.generated,
            "model": self.model,
            "citation_contract": DEFAULT_SYSTEM_PROMPT,
            "evidence": self.evidence.to_dict(),
            "references": [dict(reference) for reference in self.references],
        }


def synthesize_answer(
    evidence: Evidence,
    provider: GenerationProvider,
    *,
    routing: dict[str, Any] | None = None,
    references: Sequence[dict[str, Any]] = (),
) -> SynthesisResult:
    """Synthetisiert eine belegte Antwort aus der Evidenz über den Generierungs-Port.

    Der Provider wird **nur** bei nicht-leerer Evidenz befragt: Ohne Belege gäbe es nichts zu
    zitieren, und eine Antwort ohne Provenienz widerspräche dem Leitprinzip. Liefert der Provider
    nichts (kein Modell, leere Completion), bleibt ``generated = False`` und die Evidenz erhalten.

    Args:
        evidence: Die deterministisch nummerierten Belege inkl. Anfrage und Modus.
        provider: Der Generierungs-Port (z. B. ``NoopGenerationProvider``).
        routing: Serialisiertes Router-Urteil, falls der Modus heuristisch gewählt wurde. Es
            wird bewusst als einfache Abbildung durchgereicht, damit dieses Modul retrieval-frei
            bleibt (docs/adr/0017-router-hardening-phase7.md).
        references: Vollständige Literaturangaben der belegten Paper (dieselbe Begründung).

    Returns:
        Ein :class:`SynthesisResult`; ``answer`` ist leer, wenn nicht generiert wurde.
    """
    if evidence.is_empty():
        return SynthesisResult(
            query=evidence.query,
            mode=evidence.mode,
            answer="",
            generated=False,
            evidence=evidence,
            routing=routing,
            references=tuple(references),
        )
    result = provider.generate(
        GenerationRequest(query=evidence.query, context=evidence.as_context())
    )
    return SynthesisResult(
        query=evidence.query,
        mode=evidence.mode,
        answer=result.text,
        generated=result.generated,
        evidence=evidence,
        model=result.model,
        routing=routing,
        references=tuple(references),
    )
