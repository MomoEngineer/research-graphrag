"""Tests für die Antwort-Synthese (Evidenz + Port, Phase 7 / A1, ADR 0012)."""

from __future__ import annotations

from research_graphrag.generation.provider import (
    DEFAULT_SYSTEM_PROMPT,
    GenerationRequest,
    GenerationResult,
    NoopGenerationProvider,
    SamplingGenerationProvider,
)
from research_graphrag.generation.synthesis import Evidence, synthesize_answer

_ENTRIES = (
    (
        "aaaa0001",
        "Paper aaaa0001 · Abschnitt Datasets · Seite 7",
        "Wir nutzen SQuALITY.",
        "file:///a.pdf",
    ),
    ("bbbb0001", "Paper bbbb0001 · Abschnitt Results · Seite 3", "F1 von 0,82.", "file:///b.pdf"),
)


def _evidence(mode: str = "basic") -> Evidence:
    return Evidence.build("Welche Datensätze?", mode, _ENTRIES)


def test_build_numbers_items_deterministically() -> None:
    """Die Belege werden in Eingabereihenfolge ab 1 nummeriert."""
    evidence = _evidence()

    assert [item.index for item in evidence.items] == [1, 2]
    assert evidence.items[0].paper_id == "aaaa0001"
    assert evidence.build("q", "basic", _ENTRIES) == Evidence.build("q", "basic", _ENTRIES)


def test_as_context_renders_numbered_block_with_sources() -> None:
    """Der Prompt-Kontext trägt Marke, Label, Ausschnitt und Quelle je Beleg."""
    context = _evidence().as_context()

    assert context.startswith("[1] Paper aaaa0001 · Abschnitt Datasets · Seite 7")
    assert "Wir nutzen SQuALITY." in context
    assert "Quelle: file:///a.pdf" in context
    assert "[2] Paper bbbb0001" in context


def test_empty_evidence_is_reported() -> None:
    """Ohne Belege meldet die Evidenz Leerheit und rendert einen leeren Kontext."""
    empty = Evidence.build("q", "basic", ())

    assert empty.is_empty() is True
    assert empty.as_context() == ""


def test_synthesize_with_noop_keeps_full_evidence() -> None:
    """Ohne Modell bleibt die Evidenz vollständig, die Antwort leer und sichtbar ungeneriert."""
    result = synthesize_answer(_evidence(), NoopGenerationProvider())

    assert result.generated is False
    assert result.answer == ""
    assert result.model == ""
    assert len(result.evidence.items) == 2
    assert result.mode == "basic"


def test_synthesize_with_sampling_returns_answer_and_model() -> None:
    """Mit Sampling entsteht eine belegte Antwort inkl. Modellangabe."""
    captured: list[GenerationRequest] = []

    def sampler(request: GenerationRequest) -> GenerationResult:
        captured.append(request)
        return GenerationResult(text="SQuALITY wird genutzt [1].", generated=True, model="m-1")

    result = synthesize_answer(_evidence("local"), SamplingGenerationProvider(sampler))

    assert result.generated is True
    assert result.answer == "SQuALITY wird genutzt [1]."
    assert result.model == "m-1"
    assert captured[0].context == _evidence("local").as_context()
    assert result.evidence.items[1].index == 2


def test_empty_evidence_skips_the_provider() -> None:
    """Ohne Belege wird kein Provider befragt (nichts zu zitieren)."""
    calls: list[GenerationRequest] = []

    def sampler(request: GenerationRequest) -> GenerationResult:
        calls.append(request)
        return GenerationResult(text="frei erfunden", generated=True)

    result = synthesize_answer(
        Evidence.build("q", "global", ()), SamplingGenerationProvider(sampler)
    )

    assert calls == []
    assert result.generated is False
    assert result.answer == ""


def test_result_to_dict_shape() -> None:
    """Das serialisierte Ergebnis entspricht der Tool-Spezifikation."""
    payload = synthesize_answer(_evidence(), NoopGenerationProvider()).to_dict()

    assert set(payload) == {
        "query",
        "mode",
        "answer",
        "generated",
        "model",
        "citation_contract",
        "evidence",
    }
    assert payload["citation_contract"] == DEFAULT_SYSTEM_PROMPT
    assert set(payload["evidence"]) == {"query", "mode", "items"}
    assert set(payload["evidence"]["items"][0]) == {
        "index",
        "paper_id",
        "label",
        "snippet",
        "source_uri",
    }
