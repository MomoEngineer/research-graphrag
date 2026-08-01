"""Tests für die heuristische Struktur-/Identifier-Erkennung (AP1, Phase 2)."""

from __future__ import annotations

from research_graphrag.extraction.model import (
    SECTION_KIND_ABSTRACT,
    SECTION_KIND_BODY,
    SECTION_KIND_FRONT,
    SECTION_KIND_REFERENCES,
)
from research_graphrag.extraction.structure import (
    analyze,
    detect_heading,
    extract_identifiers,
)


def test_detect_known_keyword_heading() -> None:
    """Ein bekanntes Schlüsselwort wird als Abstract-Überschrift erkannt."""
    heading = detect_heading("Abstract")
    assert heading is not None
    assert heading.kind == SECTION_KIND_ABSTRACT


def test_detect_numbered_heading_level_one() -> None:
    """Eine numerierte Überschrift ohne Punkt ist Ebene 1 (body)."""
    heading = detect_heading("3 Proposed Approach")
    assert heading is not None
    assert heading.kind == SECTION_KIND_BODY
    assert heading.level == 1
    assert heading.title == "Proposed Approach"


def test_detect_subsection_level_two() -> None:
    """Eine Unterüberschrift ``4.2`` ergibt Ebene 2."""
    heading = detect_heading("4.2 Datasets")
    assert heading is not None
    assert heading.level == 2


def test_detect_allcaps_references() -> None:
    """Eine reine Versalzeile ``REFERENCES`` wird als references klassifiziert."""
    heading = detect_heading("REFERENCES")
    assert heading is not None
    assert heading.kind == SECTION_KIND_REFERENCES


def test_detect_roman_numeral_heading() -> None:
    """Eine römisch numerierte Zeile ``IV. Experiments`` wird erkannt."""
    heading = detect_heading("IV. Experiments")
    assert heading is not None
    assert heading.kind == SECTION_KIND_BODY


def test_detect_numbered_unknown_heading() -> None:
    """Eine kurze numerierte, unbekannte Zeile gilt als body-Überschrift."""
    heading = detect_heading("5 Widget Fabrication Steps")
    assert heading is not None
    assert heading.kind == SECTION_KIND_BODY


def test_detect_allcaps_unknown_heading() -> None:
    """Eine kurze unbekannte Versalzeile gilt als body-Überschrift."""
    heading = detect_heading("PROPOSED FRAMEWORK")
    assert heading is not None
    assert heading.kind == SECTION_KIND_BODY


def test_detect_abstract_inline_prefix() -> None:
    """Eine kurze mit ``Abstract`` beginnende Zeile wird als Abstract erkannt."""
    heading = detect_heading("Abstract of")
    assert heading is not None
    assert heading.kind == SECTION_KIND_ABSTRACT


def test_sentence_is_not_a_heading() -> None:
    """Ein vollständiger Satz ist keine Überschrift."""
    assert detect_heading("We propose a new method that clearly improves the results.") is None


def test_overlong_line_is_not_a_heading() -> None:
    """Eine sehr lange Zeile ist keine Überschrift."""
    assert detect_heading("Introduction " * 10) is None


def test_pseudocode_line_is_rejected() -> None:
    """Eine numerierte Pseudocode-Zeile mit Mathe-Symbolen ist keine Überschrift."""
    assert detect_heading("4 𝑥 ←𝑞.𝑝𝑜𝑝();") is None


def test_table_cell_line_is_rejected() -> None:
    """Eine ziffernlastige Versalzeile (Tabellenzelle) ist keine Überschrift."""
    assert detect_heading("GPT-4 32.00%") is None


def test_tabular_line_is_rejected() -> None:
    """Eine Zeile mit drei Spalten (Mehrfach-Leerzeichen) ist keine Überschrift."""
    assert detect_heading("MODEL    PREC    REC") is None


def test_tab_separated_line_is_rejected() -> None:
    """Auch eine tabgetrennte Zeile gilt als tabellarisch und ist keine Überschrift."""
    assert detect_heading("MODEL\tPREC") is None


def test_numbering_without_content_is_rejected() -> None:
    """Eine Zeile aus reiner Numerierung hat keinen Titelkern und wird verworfen."""
    assert detect_heading("3. ") is None


def test_hyphenated_line_end_is_rejected() -> None:
    """Ein Silbentrennungsrest am Zeilenende ist keine Überschrift."""
    assert detect_heading("LITERATURECOLLECTION ANDTECHNOLOGI-") is None


def test_known_section_survives_reject_rules() -> None:
    """Bekannte Schlüsselwörter werden nie verworfen (Referenzabschnitt bleibt erhalten)."""
    heading = detect_heading("REFERENCES")
    assert heading is not None
    assert heading.kind == SECTION_KIND_REFERENCES


def test_sentence_tail_in_capital_line_is_rejected() -> None:
    """Eine Versalzeile mit Satzpunkt ist ein Zeilenrest, keine Überschrift (ADR 0015)."""
    assert detect_heading("EVALUATION METRICS.") is None


def test_lowercase_sentence_remainder_is_rejected() -> None:
    """Ein kleingeschriebener Zeilenrest gilt auch dann nicht, wenn er einem Keyword gleicht."""
    assert detect_heading("methods.") is None
    assert detect_heading("evaluation.") is None


def test_capitalised_known_section_still_wins() -> None:
    """Groß geschriebene bzw. numerierte Schlüsselwörter bleiben trotz Punkt erhalten."""
    assert detect_heading("METHODS.") is not None
    assert detect_heading("3. Methods") is not None


def test_bibliography_url_line_is_rejected() -> None:
    """Zeilen mit URL-/DOI-Markern stammen aus der Bibliografie (ADR 0015)."""
    assert detect_heading("HTTPS://GITHUB.COM/EXAMPLE/REPO") is None
    assert detect_heading("6 Leaderboard at https://example.org/spaces/Research") is None
    assert detect_heading("6 Leaderboard at Example Spaces Research") is not None


def test_citation_line_is_rejected() -> None:
    """Eine Zeile mit ``et al`` ist ein Zitat, keine Überschrift (ADR 0015)."""
    assert detect_heading("7 CONVFINQA (Chen et al., 2022) and") is None


def test_code_fragment_line_is_rejected() -> None:
    """Zeilen mit JSON-/Code-Zeichen sind keine Überschriften (ADR 0015)."""
    assert detect_heading('"INSERT QUESTION"') is None
    assert detect_heading("3 Kg= PHI(D)") is None


def test_numbered_line_inside_references_is_rejected() -> None:
    """Im Referenzabschnitt ist eine numerierte Zeile ein Literatureintrag (ADR 0015)."""
    line = "27 REALM: Retrieval-Augmented Language Model Pre-training"
    assert detect_heading(line) is not None
    assert detect_heading(line, in_references=True) is None


def test_known_and_capital_headings_still_end_the_references() -> None:
    """Auch im Referenzkontext beenden Schlüsselwörter und Versalzeilen die Bibliografie."""
    assert detect_heading("Appendix", in_references=True) is not None
    assert detect_heading("SUPPLEMENTARY MATERIAL", in_references=True) is not None


def test_analyze_keeps_bibliography_entries_inside_references() -> None:
    """Numerierte Literatureinträge zerschneiden den Referenzabschnitt nicht mehr."""
    body = "The evaluation covers several benchmark datasets in detail. " * 5
    entries = "\n".join(
        f"{index} Author Name and Other Author: A Study of Retrieval Methods"
        for index in range(1, 12)
    )
    pages = [(1, f"2 Evaluation\n{body}\n\nReferences\n{entries}")]

    sectioning = analyze("pid", pages)
    references = [s for s in sectioning.sections if s.kind == SECTION_KIND_REFERENCES]

    assert len(references) == 1
    reference_id = references[0].section_id
    assert sectioning.sections[-1].section_id == reference_id
    assert any(block.section_id == reference_id for block in sectioning.blocks)


def test_analyze_detects_front_abstract_and_body() -> None:
    """Fließtext vor der ersten Überschrift wird front; Abstract/Body werden erkannt."""
    body = "The introduction motivates the work in depth. " * 6
    pages = [
        (
            1,
            "Title line and authors before any heading\n\n"
            "Abstract\nWe present a study of retrieval methods.\n\n"
            f"1 Introduction\n{body}",
        )
    ]

    sectioning = analyze("pid", pages)
    kinds = [section.kind for section in sectioning.sections]

    assert SECTION_KIND_FRONT in kinds
    assert SECTION_KIND_ABSTRACT in kinds
    assert SECTION_KIND_BODY in kinds
    abstract_id = next(s.section_id for s in sectioning.sections if s.kind == SECTION_KIND_ABSTRACT)
    assert any(block.section_id == abstract_id for block in sectioning.blocks)


def test_analyze_absorbs_content_poor_body_section() -> None:
    """Ein inhaltsarmer body-Abschnitt verschwindet und sein Text geht an den Vorgänger."""
    body = "The method section carries enough text to stand on its own. " * 5
    pages = [(1, f"3 Method\n{body}\n\nGRAPHCODER\nA stray caption line.")]

    sectioning = analyze("pid", pages)
    titles = [section.title for section in sectioning.sections]

    assert "Method" in titles
    assert "Graphcoder" not in titles
    method_id = next(s.section_id for s in sectioning.sections if s.title == "Method")
    assert {block.section_id for block in sectioning.blocks} == {method_id}


def test_analyze_keeps_short_reference_section() -> None:
    """Der Referenzabschnitt bleibt trotz geringer Textmasse erhalten (Zitationsgraph)."""
    body = "The evaluation covers several benchmark datasets in detail. " * 5
    pages = [(1, f"2 Evaluation\n{body}\n\nReferences\n[1] A. Author, A short entry.")]

    sectioning = analyze("pid", pages)

    assert SECTION_KIND_REFERENCES in {section.kind for section in sectioning.sections}


def test_analyze_does_not_absorb_into_references() -> None:
    """Nach dem Referenzabschnitt wird nicht hinein absorbiert (Anhang bleibt getrennt)."""
    body = "The evaluation covers several benchmark datasets in detail. " * 5
    pages = [(1, f"2 Evaluation\n{body}\n\nReferences\n[1] A. Author.\n\nAPPENDIX\nA short note.")]

    sectioning = analyze("pid", pages)
    kinds = [section.kind for section in sectioning.sections]

    assert kinds.count(SECTION_KIND_REFERENCES) == 1
    assert "APPENDIX" in [section.title for section in sectioning.sections]


def test_analyze_without_headings_is_all_front() -> None:
    """Ohne Überschriften ist der gesamte Text ein front-Abschnitt."""
    sectioning = analyze("pid", [(1, "just some text\n\nmore text on the page")])

    assert [section.kind for section in sectioning.sections] == [SECTION_KIND_FRONT]
    assert all(block.section_id == "pid-s000" for block in sectioning.blocks)


def test_extract_identifiers_finds_doi_and_arxiv() -> None:
    """DOI und arXiv-ID (inkl. Versionssuffix) werden extrahiert."""
    identifiers = extract_identifiers("see 10.1000/xyz.123 and arXiv:2601.08734v2 online")
    assert identifiers["doi"] == "10.1000/xyz.123"
    assert identifiers["arxiv"] == "2601.08734"


def test_extract_identifiers_none_present() -> None:
    """Ohne Identifikatoren ist das Ergebnis leer."""
    assert extract_identifiers("no identifiers in this plain text") == {}
