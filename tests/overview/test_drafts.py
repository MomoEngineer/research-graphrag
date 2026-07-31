"""Tests für die Übersicht-Entwürfe (AP-Overview, Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import (
    SECTION_KIND_ABSTRACT,
    CanonicalPaper,
    Chunk,
    Section,
)
from research_graphrag.overview.drafts import (
    build_draft_row,
    extractive_summary,
    generate_drafts,
    keyword_table,
    parse_internal_links,
)

_UEBERSICHT = """# Übersicht

| ID | Name | Themenfokus | Interner Link | Extern |
| --- | --- | --- | --- | --- |
| A1 | Foo | x | [Quelle](papers/Foo%20Bar.pdf) | y |
| A2 | Baz | x | [Quelle](papers/Baz%20%28RAG%29.pdf) | y |
"""


def _save_paper(
    canonical_dir: Path, paper_id: str, uri: str, texts: list[str], *, identifiers: dict[str, str]
) -> None:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index:04d}",
            paper_id=paper_id,
            page_number=1,
            text=text,
            char_count=len(text),
            section_id=f"{paper_id}-s001",
            section_title="Body",
        )
        for index, text in enumerate(texts)
    )
    paper = CanonicalPaper(
        paper_id=paper_id,
        source_uri=uri,
        source_sha256="0" * 64,
        n_pages=1,
        chunks=chunks,
        quality_flags=(),
        sections=(),
        identifiers=identifiers,
    )
    paper.save_json(canonical_dir / f"{paper_id}.json")


def test_parse_internal_links_handles_parens_and_encoding() -> None:
    """Interne Links werden dekodiert, auch bei Klammern im Dateinamen."""
    links = parse_internal_links(_UEBERSICHT)
    assert "Foo Bar.pdf" in links
    assert "Baz (RAG).pdf" in links


def test_keyword_table_extracts_discriminative_terms() -> None:
    """TF-IDF liefert je Dokument unterscheidende Top-Terme (deterministisch)."""
    corpus = [
        "graph retrieval augmented generation graph graph nodes",
        "reinforcement learning agents reward policy gradient",
    ]
    table = keyword_table(corpus, top_k=3)
    assert "graph" in table[0]
    assert any(term in table[1] for term in ("reinforcement", "learning", "policy"))


def test_keyword_table_empty_corpus() -> None:
    """Ein leerer Korpus liefert leere Term-Listen (kein Fehler)."""
    assert keyword_table(["", "   "]) == [[], []]


def test_extractive_summary_prefers_abstract() -> None:
    """Die Zusammenfassung bevorzugt den Abstract-Chunk."""
    chunks = (
        Chunk("pid-c0000", "pid", 1, "Body first chunk text", 21, "pid-s000", ""),
        Chunk("pid-c0001", "pid", 1, "Abstract content here", 21, "pid-s001", "Abstract"),
    )
    sections = (Section("pid-s001", "Abstract", SECTION_KIND_ABSTRACT, 1, 1, 1),)
    paper = CanonicalPaper("pid", "file:///x.pdf", "0" * 64, 1, chunks, (), sections, {})

    assert extractive_summary(paper) == "Abstract content here"


def test_build_draft_row_shape() -> None:
    """Die Entwurfszeile trägt ID=ENTWURF, Name, internen Link, Keywords und DOI."""
    paper = CanonicalPaper(
        "pid",
        "file:///x.pdf",
        "0" * 64,
        1,
        (Chunk("pid-c0000", "pid", 1, "content", 7, "pid-s000", ""),),
        (),
        (),
        {"doi": "10.1/abc"},
    )

    row = build_draft_row("Paper A.pdf", paper, ["alpha", "beta"])

    assert row.startswith("| ENTWURF |")
    assert "papers/Paper%20A.pdf" in row
    assert "Paper A" in row
    assert "10.1/abc" in row
    assert "alpha, beta" in row


def test_generate_drafts_skips_curated_and_is_idempotent(tmp_path: Path) -> None:
    """Kuratierte Paper werden übersprungen; ein zweiter Lauf schreibt nichts erneut."""
    data = tmp_path / "data"
    canonical = data / "canonical"
    canonical.mkdir(parents=True)
    _save_paper(
        canonical,
        "aaaa1111aaaa1111",
        "file:///papers/Foo%20Bar.pdf",
        ["graph retrieval augmented generation"],
        identifiers={},
    )
    _save_paper(
        canonical,
        "bbbb2222bbbb2222",
        "file:///papers/New%20Paper.pdf",
        ["reinforcement learning agents reward"],
        identifiers={"arxiv": "2405.20455"},
    )
    (data / "manifest.json").write_text(
        json.dumps(
            {
                "Foo Bar.pdf": {"sha256": "0" * 64, "paper_id": "aaaa1111aaaa1111"},
                "New Paper.pdf": {"sha256": "1" * 64, "paper_id": "bbbb2222bbbb2222"},
            }
        ),
        encoding="utf-8",
    )
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_text(_UEBERSICHT, encoding="utf-8")
    drafts = data / "overview_drafts.md"

    first = generate_drafts(data_dir=data, uebersicht_path=uebersicht, drafts_path=drafts)

    assert first.written == 1
    assert first.skipped_curated == 1
    assert first.skipped_existing == 0
    body = drafts.read_text(encoding="utf-8")
    assert "New Paper" in body
    assert "papers/New%20Paper.pdf" in body
    assert "arXiv:2405.20455" in body

    second = generate_drafts(data_dir=data, uebersicht_path=uebersicht, drafts_path=drafts)

    assert second.written == 0
    assert second.skipped_existing == 1
    assert second.skipped_curated == 1


def test_generate_drafts_missing_canonical_raises_not_found(tmp_path: Path) -> None:
    """Fehlt der canonical-Ordner, wird not_found gemeldet."""
    with pytest.raises(DomainError) as excinfo:
        generate_drafts(
            data_dir=tmp_path / "nope",
            uebersicht_path=tmp_path / "Übersicht.md",
            drafts_path=tmp_path / "drafts.md",
        )
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_generate_drafts_uses_uri_when_manifest_absent(tmp_path: Path) -> None:
    """Ohne manifest.json wird der Dateiname aus der Quell-URI abgeleitet."""
    data = tmp_path / "data"
    canonical = data / "canonical"
    canonical.mkdir(parents=True)
    _save_paper(
        canonical,
        "cccc3333cccc3333",
        "file:///papers/Solo%20Paper.pdf",
        ["some content about graphs and retrieval"],
        identifiers={},
    )
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_text("| ID | Name | Interner Link |\n| --- | --- | --- |\n", encoding="utf-8")
    drafts = data / "overview_drafts.md"

    report = generate_drafts(data_dir=data, uebersicht_path=uebersicht, drafts_path=drafts)

    assert report.written == 1
    body = drafts.read_text(encoding="utf-8")
    assert "papers/Solo%20Paper.pdf" in body
    assert "Solo Paper" in body


def test_generate_drafts_warns_when_uebersicht_absent(tmp_path: Path) -> None:
    """Fehlt die Übersicht, gelten alle Paper als unkuratiert."""
    data = tmp_path / "data"
    canonical = data / "canonical"
    canonical.mkdir(parents=True)
    _save_paper(
        canonical,
        "dddd4444dddd4444",
        "file:///papers/Only%20Paper.pdf",
        ["content about retrieval systems"],
        identifiers={},
    )
    drafts = data / "overview_drafts.md"

    report = generate_drafts(
        data_dir=data, uebersicht_path=tmp_path / "absent.md", drafts_path=drafts
    )

    assert report.written == 1
    assert report.skipped_curated == 0
