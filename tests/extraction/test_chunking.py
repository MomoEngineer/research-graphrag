"""Tests für das abschnitts-/größenbasierte Chunking (AP1, Phase 2)."""

from __future__ import annotations

from research_graphrag.extraction.chunking import build_chunks
from research_graphrag.extraction.structure import ContentBlock

_TITLES = {"pid-s001": "Methods", "pid-s002": "Results"}


def _blocks(*specs: tuple[int, str, str]) -> list[ContentBlock]:
    return [ContentBlock(page, section, text) for page, section, text in specs]


def test_small_paragraphs_merge_within_page_and_section() -> None:
    """Kleine Absätze derselben Seite/Section werden zu einem Chunk zusammengefasst."""
    blocks = _blocks((1, "pid-s001", "a" * 120), (1, "pid-s001", "b" * 120))

    chunks = build_chunks("pid", blocks, _TITLES)

    assert len(chunks) == 1
    assert chunks[0].section_title == "Methods"
    assert chunks[0].page_number == 1


def test_page_boundary_forces_split() -> None:
    """Ein Seitenwechsel trennt Chunks (exakte Seiten-Provenienz)."""
    chunks = build_chunks(
        "pid", _blocks((1, "pid-s001", "x" * 300), (2, "pid-s001", "y" * 300)), _TITLES
    )

    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[1].page_number == 2


def test_section_boundary_forces_split() -> None:
    """Ein Abschnittswechsel trennt Chunks."""
    chunks = build_chunks(
        "pid", _blocks((1, "pid-s001", "x" * 300), (1, "pid-s002", "y" * 300)), _TITLES
    )

    assert len(chunks) == 2
    assert chunks[0].section_id == "pid-s001"
    assert chunks[1].section_id == "pid-s002"


def test_max_chars_splits_content() -> None:
    """Zwei große Absätze überschreiten das Zielfenster und werden getrennt."""
    chunks = build_chunks(
        "pid",
        _blocks((1, "pid-s001", "z" * 1000), (1, "pid-s001", "z" * 1000)),
        _TITLES,
        max_chars=1500,
    )

    assert len(chunks) == 2


def test_long_paragraph_splits_at_sentences() -> None:
    """Ein übergroßer Absatz wird an Satzgrenzen in Chunks ≤ max unterteilt."""
    paragraph = "This is a sentence. " * 200

    chunks = build_chunks("pid", _blocks((1, "pid-s001", paragraph)), _TITLES, max_chars=1500)

    assert len(chunks) >= 2
    assert all(chunk.char_count <= 1500 for chunk in chunks)


def test_oversized_single_sentence_stays_whole() -> None:
    """Ein einzelner übergroßer Satz (ohne Satzgrenze) bleibt ein Chunk > max."""
    chunks = build_chunks("pid", _blocks((1, "pid-s001", "q" * 2000)), _TITLES, max_chars=1500)

    assert len(chunks) == 1
    assert chunks[0].char_count > 1500


def test_chunk_ids_are_sequential() -> None:
    """Chunk-IDs sind fortlaufend über das gesamte Paper."""
    chunks = build_chunks(
        "pid", _blocks((1, "pid-s001", "a" * 300), (2, "pid-s001", "b" * 300)), _TITLES
    )

    assert [chunk.chunk_id for chunk in chunks] == ["pid-c0000", "pid-c0001"]


def test_blank_blocks_yield_no_chunks() -> None:
    """Nur-Whitespace-Blöcke erzeugen keine Chunks."""
    assert build_chunks("pid", _blocks((1, "pid-s001", "   "), (1, "pid-s001", "")), _TITLES) == ()
