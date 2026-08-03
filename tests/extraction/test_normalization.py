"""Tests für die Textnormalisierung der Extraktion (Phase 7 / A5, ADR 0015)."""

from __future__ import annotations

from research_graphrag.extraction.normalization import LIGATURES, normalize_text


def test_repairs_common_ligatures() -> None:
    """Typografische Ligaturen werden in ihre Buchstabenfolge zurückgeführt."""
    assert normalize_text("con\ufb01guration") == "configuration"
    assert normalize_text("work\ufb02ow") == "workflow"
    assert normalize_text("di\ufb00erent") == "different"
    assert normalize_text("e\ufb03cient") == "efficient"


def test_ligature_map_is_complete_for_the_unicode_block() -> None:
    """Die Map deckt den gesamten Ligatur-Block U+FB00–U+FB06 ab."""
    assert {ord(char) for char in LIGATURES} == set(range(0xFB00, 0xFB07))


def test_removes_glyph_artifacts() -> None:
    """Nicht dekodierbare ``/uniXXXXXXXX``-Glyphen werden entfernt."""
    assert normalize_text("/uni00000044/uni00000055 text") == "text"
    assert normalize_text("uni00000013") == ""


def test_removes_lone_surrogates() -> None:
    """Einzelne Surrogate einer defekten CMap werden entfernt (real: ``U+D835``)."""
    assert normalize_text("Endpoints: \ud8359, \ud8354") == "Endpoints: 9, 4"
    assert normalize_text("\ud835") == ""


def test_result_is_utf8_encodable() -> None:
    """Der normalisierte Text lässt sich nach UTF-8 kodieren (Canonical JSON schreibbar)."""
    normalize_text("a\ud835b\udfffc").encode("utf-8")


def test_collapses_whitespace_only_in_touched_lines() -> None:
    """Nur Zeilen mit entfernten Glyphen werden im Leerraum verdichtet."""
    text = "a/uni00000013b    c\ncolumn1    column2    column3"
    normalized = normalize_text(text)
    assert normalized.splitlines()[0] == "ab c"
    assert normalized.splitlines()[1] == "column1    column2    column3"


def test_keeps_mathematical_alphanumerics() -> None:
    """Mathematische Alphanumerics bleiben erhalten (Reject-Regel aus ADR 0013)."""
    line = "4 \U0001d465 \u2190\U0001d45e.\U0001d45d\U0001d45c\U0001d45d();"
    assert normalize_text(line) == line


def test_is_idempotent_and_keeps_plain_text() -> None:
    """Unauffälliger Text bleibt unverändert; die Normalisierung ist idempotent."""
    text = "Section 4.2 Datasets and Evaluation Metrics"
    assert normalize_text(text) == text
    once = normalize_text("con\ufb01g /uni00000013 x")
    assert normalize_text(once) == once


def test_handles_empty_input() -> None:
    """Leerer Text bleibt leer (kein Fehler, keine Zeilenerzeugung)."""
    assert normalize_text("") == ""


def test_preserves_line_structure() -> None:
    """Zeilenumbrüche und Leerzeilen bleiben erhalten (Absatzlogik der Analyse)."""
    text = "Heading\n\nBody con\ufb01g\n"
    assert normalize_text(text) == "Heading\n\nBody config\n"
