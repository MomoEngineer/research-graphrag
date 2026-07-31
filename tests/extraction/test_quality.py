"""Tests für die heuristischen Qualitäts-Gates (AP1, Phase 2)."""

from __future__ import annotations

from research_graphrag.extraction.model import (
    SECTION_KIND_ABSTRACT,
    SECTION_KIND_FRONT,
    SECTION_KIND_REFERENCES,
    Chunk,
    Section,
)
from research_graphrag.extraction.quality import assess


def _section(section_id: str, kind: str) -> Section:
    return Section(section_id=section_id, title=kind, kind=kind, level=1, page_number=1, order=1)


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        paper_id="pid",
        page_number=1,
        text=text,
        char_count=len(text),
        section_id="pid-s001",
        section_title="Body",
    )


def test_empty_document_is_flagged() -> None:
    """Nur leere Seiten ergeben ``empty_document`` und ``empty_page``."""
    flags = assess([(1, ""), (2, "  ")], (), ())
    assert "empty_document" in flags
    assert "empty_page:1" in flags


def test_missing_abstract_and_references() -> None:
    """Nur ein front-Abschnitt löst missing/no-sections-Flags aus."""
    sections = (_section("pid-s000", SECTION_KIND_FRONT),)
    flags = assess([(1, "some real body text here")], sections, ())
    assert "missing_abstract" in flags
    assert "missing_references" in flags
    assert "no_sections_detected" in flags


def test_clean_paper_has_no_flags() -> None:
    """Vollständige Struktur, sauberer Text und passende Chunkgröße → keine Flags."""
    pages = [(1, "Normal readable sentence text with enough words to avoid noise. " * 5)]
    sections = (
        _section("pid-s000", SECTION_KIND_FRONT),
        _section("pid-s001", SECTION_KIND_ABSTRACT),
        _section("pid-s002", SECTION_KIND_REFERENCES),
    )
    chunks = (_chunk("pid-c0000", "word " * 100),)

    assert assess(pages, sections, chunks) == ()


def test_ocr_noise_is_flagged() -> None:
    """Viele Ein-Zeichen-Token deuten auf OCR-Rauschen."""
    noisy = "a b c d e f g h i j k l m n o p q r s t u v w x y z " * 10
    flags = assess([(1, noisy)], (), ())
    assert "ocr_noise" in flags


def test_headless_table_is_flagged() -> None:
    """Ein tabellarischer Block ohne Caption wird markiert."""
    page = "col a    col b    col c\n1        2        3\n4        5        6"
    flags = assess([(1, page)], (), ())
    assert "possible_headless_table:1" in flags


def test_table_with_caption_is_not_flagged() -> None:
    """Ein tabellarischer Block mit „Table"-Caption wird nicht markiert."""
    page = "Table 1: Results\ncol a    col b    col c\n1        2        3\n4        5        6"
    flags = assess([(1, page)], (), ())
    assert "possible_headless_table:1" not in flags


def test_short_and_long_chunk_flags() -> None:
    """Chunks außerhalb des Zielfensters werden als short/long markiert."""
    chunks = (_chunk("pid-c0000", "x" * 10), _chunk("pid-c0001", "y" * 2000))
    flags = assess([(1, "body text")], (_section("pid-s001", "body"),), chunks)
    assert "short_chunk:pid-c0000" in flags
    assert "long_chunk:pid-c0001" in flags
