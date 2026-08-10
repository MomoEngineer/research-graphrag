"""Tests für die Übersicht-Entwürfe (AP-Overview, Phase 2)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import (
    DOCUMENT_KIND_REFERENCE,
    SECTION_KIND_ABSTRACT,
    CanonicalPaper,
    Chunk,
    Section,
)
from research_graphrag.overview.drafts import (
    REFERENCE_DRAFT_PREFIX,
    append_overview_rows,
    build_draft_row,
    display_name,
    extractive_summary,
    keyword_table,
    link_column,
    next_draft_number,
    parse_internal_links,
    retarget_overview_row,
)

_HEADER = (
    "| ID | Name | Themenfokus | Keyword | Kompakte Zusammenfassung | Interner Link "
    "| Relevanz fuer Expose | SRQ-Zuordnung | Externer Link/Indetifikator |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)

_UEBERSICHT = (
    "# Übersicht\n\n"
    + _HEADER
    + "| A1 | Foo | x | k | s | [Quelle](papers/Foo%20Bar.pdf) | hoch | SRQ1 | y |\n"
    + "| A2 | Baz | x | k | s | [Quelle](papers/Baz%20%28RAG%29.pdf) | hoch | SRQ1 | y |\n"
)


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
    assert link_column(_UEBERSICHT) == 5
    assert link_column("kein Tabellenkopf") is None
    assert parse_internal_links("kein Tabellenkopf") == set()


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
    """Die Entwurfszeile trägt die vergebene ID, Name, internen Link, Keywords und DOI."""
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

    row = build_draft_row("Z1", "Paper A.pdf", paper, ["alpha", "beta"])

    assert row.startswith("| Z1 |")
    assert "papers/Paper%20A.pdf" in row
    assert "Paper A" in row
    assert "10.1/abc" in row
    assert "alpha, beta" in row
    assert row.count("(manuell)") == 3


def test_next_draft_number_continues_existing_series() -> None:
    """Die ID-Reihe setzt hinter der höchsten vorhandenen Z-Nummer fort."""
    assert next_draft_number(_UEBERSICHT) == 1
    assert next_draft_number(_UEBERSICHT + "| Z2 | x | y | z | w |\n") == 3


def test_build_draft_row_marks_a_reference_entry() -> None:
    """Ein Referenz-Eintrag ist in der Übersicht als solcher erkennbar."""
    paper = CanonicalPaper(
        "pid",
        "file:///x.refjson",
        "0" * 64,
        0,
        (Chunk("pid-c0001", "pid", 0, "Titel\n\nAbstract", 15, "pid-s0001", "Abstract"),),
        (),
        (),
        {"doi": "10.1/abc"},
        DOCUMENT_KIND_REFERENCE,
    )

    row = build_draft_row("Z1", "Ein Titel.refjson", paper, [])

    assert REFERENCE_DRAFT_PREFIX in row
    assert "| Ein Titel |" in row
    assert "papers/Ein%20Titel.refjson" in row


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Paper A.pdf", "Paper A"),
        ("Ein Titel.refjson", "Ein Titel"),
        ("Ohne Endung", "Ohne Endung"),
        ("Version 1.2.pdf", "Version 1.2"),
    ],
)
def test_display_name_strips_known_suffixes(filename: str, expected: str) -> None:
    """Beide Dokumenttypen führen zum selben Anzeigenamen."""
    assert display_name(filename) == expected


def test_retarget_overview_row_replaces_name_and_link(tmp_path: Path) -> None:
    """Der Upgrade biegt genau eine Zeile um – Name und interner Link."""
    target = tmp_path / "Übersicht.md"
    target.write_bytes(
        (
            _UEBERSICHT + "| Z1 | Alt | (manuell) | k | ENTWURF: s "
            "| [Quelle](papers/Alt%20Titel.refjson) | (manuell) | (manuell) | y |\n"
        ).encode("utf-8")
    )

    changed = retarget_overview_row(
        target,
        old_filename="Alt Titel.refjson",
        new_filename="Neuer Titel.pdf",
        new_name="Neuer Titel",
    )

    text = target.read_text(encoding="utf-8")
    assert changed is True
    assert "papers/Neuer%20Titel.pdf" in text
    assert ".refjson" not in text
    assert "| Z1 | Neuer Titel |" in text


def test_retarget_overview_row_keeps_curated_cells_and_other_bytes(tmp_path: Path) -> None:
    """Nur die eine Zeile wird angefasst; alle anderen Bytes bleiben identisch."""
    target = tmp_path / "Übersicht.md"
    original = (
        _UEBERSICHT.replace("\n", "\r\n") + "| Z1 | Alt | Cluster A | k | ENTWURF: s "
        "| [Quelle](papers/Alt%20Titel.refjson) | sehr hoch | SRQ2 | y |\r\n"
    ).encode("utf-8")
    target.write_bytes(original)

    retarget_overview_row(
        target,
        old_filename="Alt Titel.refjson",
        new_filename="Neu.pdf",
        new_name="Neu",
    )

    after = target.read_bytes()
    assert after.startswith(original[: original.index(b"| Z1 |")])
    assert b"sehr hoch" in after and b"SRQ2" in after and b"Cluster A" in after
    assert after.endswith(b"\r\n")


def test_retarget_overview_row_reports_a_missing_row(tmp_path: Path) -> None:
    """Ohne passende Zeile wird nichts geschrieben und ``False`` gemeldet."""
    target = tmp_path / "Übersicht.md"
    target.write_bytes(_UEBERSICHT.encode("utf-8"))
    before = target.read_bytes()

    assert (
        retarget_overview_row(
            target, old_filename="fehlt.refjson", new_filename="x.pdf", new_name="x"
        )
        is False
    )
    assert target.read_bytes() == before


def test_append_overview_rows_skips_listed_and_is_idempotent(tmp_path: Path) -> None:
    """Gelistete Paper werden übersprungen; ein zweiter Lauf schreibt nichts erneut."""
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
    uebersicht.write_bytes(_UEBERSICHT.encode("utf-8"))
    before = uebersicht.read_bytes()

    first = append_overview_rows(data_dir=data, target_path=uebersicht)

    assert first.written == 1
    assert first.skipped_known == 1
    assert first.row_ids == ("Z1",)
    after = uebersicht.read_bytes()
    assert after.startswith(before), "kuratierte Zeilen müssen byte-identisch bleiben"
    body = after.decode("utf-8")
    assert "| Z1 |" in body
    assert "New Paper" in body
    assert "papers/New%20Paper.pdf" in body
    assert "arXiv:2405.20455" in body

    second = append_overview_rows(data_dir=data, target_path=uebersicht)

    assert second.written == 0
    assert second.skipped_known == 2
    assert uebersicht.read_bytes() == after
    assert not (uebersicht.parent / f"{uebersicht.name}.tmp").exists()


def test_append_overview_rows_honours_legacy_staging_file(tmp_path: Path) -> None:
    """Ein Altbestand in data/overview_drafts.md verhindert eine zweite Zeile (ADR 0019)."""
    data = tmp_path / "data"
    canonical = data / "canonical"
    canonical.mkdir(parents=True)
    _save_paper(
        canonical,
        "bbbb2222bbbb2222",
        "file:///papers/New%20Paper.pdf",
        ["reinforcement learning agents reward"],
        identifiers={},
    )
    (data / "overview_drafts.md").write_text(
        "| ID | Name | Interner Link |\n| --- | --- | --- |\n"
        "| ENTWURF | New Paper | [Quelle](papers/New%20Paper.pdf) |\n",
        encoding="utf-8",
    )
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_text(_UEBERSICHT, encoding="utf-8")

    report = append_overview_rows(data_dir=data, target_path=uebersicht)

    assert report.written == 0
    assert report.skipped_known == 1


def test_append_overview_rows_preserves_crlf_line_endings(tmp_path: Path) -> None:
    """Eine Übersicht mit CRLF behält CRLF – ein Text-Schreibvorgang würde alle Zeilen ändern."""
    data = tmp_path / "data"
    canonical = data / "canonical"
    canonical.mkdir(parents=True)
    _save_paper(
        canonical,
        "ffff6666ffff6666",
        "file:///papers/CRLF%20Paper.pdf",
        ["content about retrieval and graphs"],
        identifiers={},
    )
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_bytes(_UEBERSICHT.replace("\n", "\r\n").encode("utf-8"))
    before = uebersicht.read_bytes()

    append_overview_rows(data_dir=data, target_path=uebersicht)

    after = uebersicht.read_bytes()
    assert after.startswith(before)
    assert after[len(before) :].replace(b"\r\n", b"").count(b"\n") == 0


def test_append_overview_rows_adds_missing_trailing_newline(tmp_path: Path) -> None:
    """Fehlt der abschließende Zeilenumbruch, wird er ergänzt statt Zeilen zu verschmelzen."""
    data = tmp_path / "data"
    canonical = data / "canonical"
    canonical.mkdir(parents=True)
    _save_paper(
        canonical,
        "aaaa7777aaaa7777",
        "file:///papers/Ohne%20Umbruch.pdf",
        ["content about retrieval and graphs"],
        identifiers={},
    )
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_bytes(_UEBERSICHT.rstrip("\n").encode("utf-8"))

    append_overview_rows(data_dir=data, target_path=uebersicht)

    lines = uebersicht.read_text(encoding="utf-8").splitlines()
    assert lines[-2] == _UEBERSICHT.rstrip("\n").splitlines()[-1]
    assert lines[-1].startswith("| Z1 |")


@pytest.mark.parametrize(
    ("label", "transform"),
    [
        ("lf", lambda text: text.encode("utf-8")),
        ("crlf", lambda text: text.replace("\n", "\r\n").encode("utf-8")),
        ("ohne-schluss-umbruch", lambda text: text.rstrip("\n").encode("utf-8")),
        ("mit-bom", lambda text: "\ufeff".encode() + text.encode("utf-8")),
        ("leerzeile-am-ende", lambda text: (text + "\n\n").encode("utf-8")),
    ],
)
def test_append_overview_rows_never_touches_existing_bytes(
    tmp_path: Path, label: str, transform: Callable[[str], bytes]
) -> None:
    """Der bestehende Inhalt bleibt in jeder Dateiform ein **exaktes Byte-Präfix**."""
    data = tmp_path / "data"
    canonical = data / "canonical"
    canonical.mkdir(parents=True)
    _save_paper(
        canonical,
        "bbbb8888bbbb8888",
        f"file:///papers/Form%20{label}.pdf",
        ["content about graph retrieval evaluation"],
        identifiers={},
    )
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_bytes(transform(_UEBERSICHT))
    before = uebersicht.read_bytes()

    report = append_overview_rows(data_dir=data, target_path=uebersicht)

    after = uebersicht.read_bytes()
    assert report.written == 1
    assert after.startswith(before), f"bestehende Bytes verändert ({label})"
    assert after[len(before) :].strip().startswith(b"| Z1 |")
    assert after.endswith(b"\n")


def test_append_overview_rows_missing_canonical_raises_not_found(tmp_path: Path) -> None:
    """Fehlt der canonical-Ordner, wird not_found gemeldet."""
    with pytest.raises(DomainError) as excinfo:
        append_overview_rows(data_dir=tmp_path / "nope", target_path=tmp_path / "Übersicht.md")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_append_overview_rows_missing_target_raises_not_found(tmp_path: Path) -> None:
    """Fehlt die kuratierte Übersicht, wird not_found gemeldet (statt sie zu erfinden)."""
    data = tmp_path / "data"
    (data / "canonical").mkdir(parents=True)

    with pytest.raises(DomainError) as excinfo:
        append_overview_rows(data_dir=data, target_path=tmp_path / "fehlt.md")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_append_overview_rows_rejects_unexpected_layout(tmp_path: Path) -> None:
    """Eine Zieltabelle mit fremdem Spaltenlayout wird nicht befüllt (constraint_violation)."""
    data = tmp_path / "data"
    (data / "canonical").mkdir(parents=True)
    target = tmp_path / "fremd.md"
    target.write_text("| ID | Interner Link |\n| --- | --- |\n", encoding="utf-8")

    with pytest.raises(DomainError) as excinfo:
        append_overview_rows(data_dir=data, target_path=target)
    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


def test_append_overview_rows_uses_uri_when_manifest_absent(tmp_path: Path) -> None:
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
    uebersicht.write_text(_HEADER, encoding="utf-8")

    report = append_overview_rows(data_dir=data, target_path=uebersicht)

    assert report.written == 1
    body = uebersicht.read_text(encoding="utf-8")
    assert "papers/Solo%20Paper.pdf" in body
    assert "Solo Paper" in body


def test_append_overview_rows_appends_to_curated_table(tmp_path: Path) -> None:
    """Die neue Zeile landet am Ende der Tabelle, ohne bestehende Zeilen zu verändern."""
    data = tmp_path / "data"
    canonical = data / "canonical"
    canonical.mkdir(parents=True)
    _save_paper(
        canonical,
        "eeee5555eeee5555",
        "file:///papers/Weiteres%20Paper.pdf",
        ["content about graph neural retrieval"],
        identifiers={},
    )
    uebersicht = tmp_path / "Übersicht.md"
    uebersicht.write_bytes(_UEBERSICHT.encode("utf-8"))

    append_overview_rows(data_dir=data, target_path=uebersicht)

    lines = uebersicht.read_text(encoding="utf-8").splitlines()
    assert lines[-1].startswith("| Z1 |")
    assert lines[:-1] == _UEBERSICHT.splitlines()
