"""Tests für den append-only Bericht der Online-Suche (Phase 9 / S1).

Schwerpunkt ist die Entschärfung fremder Inhalte: Titel und Abstracts stammen aus fremden
Diensten und dürfen die Struktur des Berichts nicht verändern.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_graphrag.bibliography.model import ORIGIN_RESOLVED, MetadataRecord
from research_graphrag.online.candidates import SOURCE_ARXIV, Candidate, KnownCandidate
from research_graphrag.online.download import (
    OUTCOME_DOWNLOADED,
    OUTCOME_NO_LICENSE,
    DownloadOutcome,
)
from research_graphrag.online.metadata import MATCH_DOI, Resolution, ResolutionTarget
from research_graphrag.online.report import (
    MAX_ABSTRACT_CHARS,
    METADATA_REPORT_NAME,
    REPORT_NAME,
    DiscoveryReport,
    append_report,
    append_resolutions,
    escape_markdown,
    render_report,
    render_resolutions,
    safe_url,
    store_raw,
)
from research_graphrag.online.sources import SearchQuery, SourceResult

QUERY = SearchQuery(query_id="C1", terms=("graphrag",), reason="Community 1 (11 Paper)")


def _candidate(**overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "title": "Ein Kandidat",
        "year": 2025,
        "sources": (SOURCE_ARXIV,),
        "arxiv_id": "2501.00001",
        "abstract": "Ein kurzer Abstract.",
        "url": "https://example.org/a.pdf",
        "query_id": "C1",
        "reason": "Community 1 (11 Paper)",
    }
    defaults.update(overrides)
    return Candidate(**defaults)  # type: ignore[arg-type]


def _report(**overrides: object) -> DiscoveryReport:
    defaults: dict[str, object] = {
        "timestamp": "20260803T120000Z",
        "queries": (QUERY,),
        "sources": (SourceResult(source="arXiv", url="https://x", status=200, raw=b"<feed/>"),),
        "fresh": (_candidate(),),
        "known": (),
        "found": 1,
        "dropped_old": 0,
        "min_year": 2021,
    }
    defaults.update(overrides)
    return DiscoveryReport(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize("char", ["|", "`", "*", "_", "[", "]", "<", ">", "\\"])
def test_escape_markdown_masks_structural_characters(char: str) -> None:
    """Fremde Steuerzeichen werden maskiert, damit die Berichtstruktur hält."""
    assert escape_markdown(f"a{char}b", limit=100) == f"a\\{char}b"


def test_escape_markdown_neutralises_injected_link() -> None:
    """Ein als Titel geschmuggelter Markdown-Link wird nicht klickbar."""
    escaped = escape_markdown("[klick](javascript:alert(1))", limit=100)

    assert "[klick]" not in escaped
    assert escaped.startswith("\\[")


def test_escape_markdown_collapses_line_breaks() -> None:
    """Zeilenumbrüche entfallen – sonst könnte fremder Text eigene Blockelemente erzeugen."""
    escaped = escape_markdown("erste\n## Überschrift\r\nzweite", limit=100)

    assert "\n" not in escaped
    assert escaped == "erste ## Überschrift zweite"


def test_escape_markdown_removes_control_characters() -> None:
    """Nicht druckbare Zeichen werden entfernt."""
    assert escape_markdown("a\x00\x07b", limit=100) == "ab"


def test_escape_markdown_truncates_before_masking() -> None:
    """Gekürzt wird vor dem Maskieren, damit die Grenze auf den Inhalt wirkt."""
    result = escape_markdown("x" * 50, limit=10)

    assert result == "x" * 10 + " …"


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "file:///etc/passwd", "data:text/html,x", "", "ftp://example.org/a"],
)
def test_safe_url_rejects_foreign_schemes(url: str) -> None:
    """Nur http(s) überlebt – alles andere wird verworfen statt ausgegeben."""
    assert safe_url(url) == ""


def test_safe_url_rejects_overlong_values() -> None:
    """Übermäßig lange Verweise werden verworfen."""
    assert safe_url("https://example.org/" + "x" * 1000) == ""


def test_safe_url_keeps_plain_https() -> None:
    """Ein regulärer Verweis bleibt erhalten und wird als Klartext ausgegeben."""
    assert safe_url(" https://example.org/a.pdf ") == "https://example.org/a.pdf"


def test_render_lists_query_source_and_balance() -> None:
    """Der Kopf eines Laufs weist Anfrage, Quellenstatus und Bilanz aus."""
    text = "\n".join(render_report(_report()))

    assert "## Lauf 20260803T120000Z" in text
    assert "Anfrage `C1`" in text
    assert "Quelle arXiv: HTTP 200" in text
    assert "1 Treffer · 0 bereits im Korpus · 0 vor 2021 · 1 neu" in text


def test_render_states_why_a_candidate_was_proposed() -> None:
    """Ohne Begründung ist ein Vorschlag nicht prüfbar (Roadmap-Vorgabe)."""
    text = "\n".join(render_report(_report()))

    assert "Vorgeschlagen wegen `C1`: Community 1 (11 Paper)" in text
    assert "`arXiv:2501.00001`" in text
    assert "`https://example.org/a.pdf`" in text


def test_render_marks_missing_license_and_fulltext() -> None:
    """Fehlende Angaben werden benannt statt weggelassen."""
    text = "\n".join(render_report(_report(fresh=(_candidate(license="", url=""),))))

    assert "Lizenz: (nicht ausgewiesen)" in text
    assert "Volltext: (keiner ausgewiesen)" in text


def test_render_documents_known_candidates_with_evidence() -> None:
    """Die Dedup-Entscheidung wird mit Beleg ausgewiesen."""
    known = KnownCandidate(_candidate(), "identifier", "arxiv:2501.00001")

    text = "\n".join(render_report(_report(fresh=(), known=(known,), found=1)))

    assert "Bereits im Korpus" in text
    assert "Beleg über identifier: `arxiv:2501.00001`" in text


def test_render_shows_the_download_status_of_each_candidate() -> None:
    """Mit ``--download`` trägt jeder frische Kandidat einen Status – Beleg für ADR 0035."""
    candidate = _candidate()
    outcome = DownloadOutcome(candidate, OUTCOME_DOWNLOADED, "123456 Bytes")

    text = "\n".join(render_report(_report(fresh=(candidate,), downloads=(outcome,))))

    assert "Download: geladen — 123456 Bytes" in text


def test_render_explains_why_a_candidate_was_not_downloaded() -> None:
    """Der Grund steht im Klartext – nicht nur „nicht geladen"."""
    candidate = _candidate(license="")
    outcome = DownloadOutcome(candidate, OUTCOME_NO_LICENSE, "keine Lizenz ausgewiesen")

    text = "\n".join(render_report(_report(fresh=(candidate,), downloads=(outcome,))))

    assert "Download: nicht geladen (keine Lizenz ausgewiesen) — keine Lizenz ausgewiesen" in text


def test_render_without_download_flag_shows_no_status_line() -> None:
    """Ohne ``--download`` ändert sich am Bericht gegenüber S1 nichts."""
    text = "\n".join(render_report(_report()))

    assert "Download:" not in text


def test_render_reports_empty_run() -> None:
    """Ein Lauf ohne Treffer wird ausdrücklich als solcher ausgewiesen."""
    text = "\n".join(render_report(_report(fresh=(), known=(), found=0)))

    assert "*Keine Treffer.*" in text


def test_render_shortens_the_raw_directory() -> None:
    """Der Ablageort erscheint relativ – ein absoluter Pfad trüge den Benutzernamen hinein."""
    raw = Path("C:/Users/jemand/repo/data/online_raw/20260803T120000Z")

    text = "\n".join(render_report(_report(raw_dir=raw)))

    assert "`online_raw/20260803T120000Z`" in text
    assert "jemand" not in text


def test_render_truncates_long_abstracts() -> None:
    """Ein überlanger Abstract wird gekürzt statt den Bericht zu fluten."""
    text = "\n".join(render_report(_report(fresh=(_candidate(abstract="w" * 5000),))))

    assert "w" * (MAX_ABSTRACT_CHARS + 1) not in text


def test_append_creates_file_with_header(tmp_path: Path) -> None:
    """Beim ersten Lauf entsteht die Datei mit erklärendem Kopf."""
    target = append_report(tmp_path, _report())

    content = target.read_text(encoding="utf-8")
    assert target.name == REPORT_NAME
    assert content.startswith("# Online-Kandidaten")
    assert "kein Bestand" in content


def test_append_preserves_existing_bytes(tmp_path: Path) -> None:
    """Bestehender Inhalt bleibt **byte-identisch** – der Bericht wird nur ergänzt."""
    target = tmp_path / REPORT_NAME
    target.write_bytes(b"# Online-Kandidaten\r\n\r\nAlte Zeile\r\n")
    before = target.read_bytes()

    append_report(tmp_path, _report())

    assert target.read_bytes().startswith(before)


def test_append_leaves_no_temporary_file(tmp_path: Path) -> None:
    """Nach dem atomaren Schreiben bleibt keine Temporärdatei zurück."""
    append_report(tmp_path, _report())

    assert list(tmp_path.glob("*.tmp")) == []


def test_append_adds_second_run(tmp_path: Path) -> None:
    """Ein zweiter Lauf hängt einen weiteren Abschnitt an."""
    append_report(tmp_path, _report())
    target = append_report(tmp_path, _report(timestamp="20260803T130000Z"))

    content = target.read_text(encoding="utf-8")
    assert content.count("## Lauf ") == 2


def test_store_raw_writes_one_file_per_source(tmp_path: Path) -> None:
    """Die Rohantworten landen datiert und quellenbenannt auf der Platte."""
    sources = (
        SourceResult(source="arXiv", url="https://x", status=200, raw=b"<feed/>"),
        SourceResult(source="OpenAlex", url="https://y", status=200, raw=b"{}"),
    )

    folder = store_raw(tmp_path, "20260803T120000Z", sources)

    names = sorted(item.name for item in folder.iterdir())
    assert names == ["01-arxiv.xml", "02-openalex.json"]
    assert (folder / "01-arxiv.xml").read_bytes() == b"<feed/>"


def _resolution(*, confidence: str = "strong", resolved: bool = True) -> Resolution:
    """Baut ein Auflösungsergebnis für den Berichtstest."""
    target = ResolutionTarget(paper_id="aaaa0001", title="Ein Titel", doi="10.1145/abc")
    if not resolved:
        return Resolution(target=target, record=None, note="kein belastbarer Treffer")
    return Resolution(
        target=target,
        record=MetadataRecord(
            paper_id="aaaa0001",
            origin=ORIGIN_RESOLVED,
            title="Ein *fremder* Titel",
            authors=("Anna Beispiel",),
            year=2024,
            venue="Proceedings",
            confidence=confidence,
            evidence="OpenAlex über doi:10.1145/abc",
        ),
        match=MATCH_DOI,
        note="OpenAlex über doi:10.1145/abc",
    )


def test_resolution_report_separates_strong_from_weak(tmp_path: Path) -> None:
    """Der Bericht trennt starke von schwachen Belegen und nennt die offenen Fälle."""
    lines = render_resolutions(
        "20260805T120000Z",
        [_resolution(), _resolution(confidence="weak"), _resolution(resolved=False)],
    )
    text = "\n".join(lines)

    assert "übernommen: 2 (stark belegt 1, schwach belegt 1)" in text
    assert "offen: 1" in text
    assert "**(schwach belegt)**" in text
    assert "### Nicht aufgelöst" in text


def test_resolution_report_escapes_foreign_titles() -> None:
    """Fremde Titel können die Struktur des Berichts nicht verändern."""
    text = "\n".join(render_resolutions("20260805T120000Z", [_resolution()]))

    assert r"\*fremder\*" in text


def test_empty_resolution_report_states_that_nothing_was_pending() -> None:
    """Ein Lauf ohne Ziele meldet das ausdrücklich."""
    text = "\n".join(render_resolutions("20260805T120000Z", []))

    assert "Nichts aufzulösen" in text


def test_resolutions_are_appended_to_their_own_log(tmp_path: Path) -> None:
    """Das Protokoll wird angelegt und bei einem zweiten Lauf ergänzt."""
    append_resolutions(tmp_path, "20260805T120000Z", [_resolution()])
    target = append_resolutions(tmp_path, "20260805T130000Z", [_resolution()])

    content = target.read_text(encoding="utf-8")
    assert target.name == METADATA_REPORT_NAME
    assert content.count("## Lauf ") == 2
    assert content.count("# Metadaten-Auflösung") == 1
