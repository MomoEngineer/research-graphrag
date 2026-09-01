"""Tests für den Volltext-Download des Online-Modus (Phase 9 / S2, ADR 0035).

Der Netzzugang wird durch einen Fake-Client ersetzt – wie überall im Paket laufen die Tests ohne
Netz. Echte PDF-Fixtures entstehen über die gemeinsame ``make_pdf``-Fixture (reportlab).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.online.candidates import SOURCE_OPENALEX, Candidate
from research_graphrag.online.download import (
    DOWNLOAD_DELAY_SECONDS,
    LICENSE_WHITELIST,
    MAX_DOWNLOAD_BYTES,
    OUTCOME_DOWNLOADED,
    OUTCOME_HTTP_ERROR,
    OUTCOME_LICENSE_NOT_WHITELISTED,
    OUTCOME_NO_LICENSE,
    OUTCOME_NO_URL,
    OUTCOME_NOT_A_PDF,
    OUTCOME_TITLE_MISMATCH,
    OUTCOME_TOO_SHORT,
    describe_outcome,
    download_all,
    download_candidate,
    is_whitelisted_license,
    pdf_filename,
)
from research_graphrag.online.transport import HttpResponse


def _candidate(**overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "title": "Graph Retrieval Augmented Generation For Question Answering",
        "year": 2025,
        "sources": (SOURCE_OPENALEX,),
        "doi": "10.1145/example.doi",
        "license": "cc-by",
        "url": "https://example.org/paper.pdf",
    }
    defaults.update(overrides)
    return Candidate(**defaults)  # type: ignore[arg-type]


class _FakeClient:
    """Liefert eine feste Antwort und merkt sich die tatsächlich genutzte Grenze."""

    def __init__(self, response: HttpResponse) -> None:
        self._response = response
        self.calls: list[tuple[str, int]] = []

    def get(self, url: str, *, accept: str = "*/*", max_bytes: int = 0) -> HttpResponse:
        self.calls.append((url, max_bytes))
        return self._response


class _FailingClient:
    def get(self, url: str, *, accept: str = "*/*", max_bytes: int = 0) -> HttpResponse:
        raise DomainError(ErrorCode.DEPENDENCY_ERROR, "Anfrage fehlgeschlagen: kein Netz")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("cc-by", True),
        ("CC-BY", True),
        ("cc-by-sa", True),
        ("public-domain", True),
        ("cc-by-nc", False),
        ("publisher-specific-oa", False),
        ("", False),
    ],
)
def test_is_whitelisted_license(value: str, expected: bool) -> None:
    """Nur die drei benannten freien Lizenzen bestehen die Whitelist (ADR 0035)."""
    assert is_whitelisted_license(value) is expected


def test_license_whitelist_holds_exactly_three_values() -> None:
    """Die Whitelist ist bewusst eng – kein `cc-by-nc`, kein `mit`, kein `publisher-specific-oa`."""
    assert LICENSE_WHITELIST == frozenset({"public-domain", "cc-by", "cc-by-sa"})


def test_describe_outcome_translates_every_public_constant() -> None:
    """Jede öffentliche ``OUTCOME_*``-Konstante hat eine menschenlesbare Bezeichnung."""
    assert describe_outcome(OUTCOME_DOWNLOADED) == "geladen"
    assert describe_outcome(OUTCOME_NO_LICENSE).startswith("nicht geladen")


def test_describe_outcome_falls_back_to_the_raw_value_for_unknown_outcomes() -> None:
    """Ein unbekannter Wert bricht die Anzeige nicht, sondern zeigt sich selbst."""
    assert describe_outcome("etwas_neues") == "etwas_neues"


def test_pdf_filename_uses_arxiv_identifier_as_anchor() -> None:
    """Der arXiv-Identifikator bleibt der stabile Anker, der Titel liefert nur das sprechende Wort."""
    name = pdf_filename(_candidate(doi="", arxiv_id="2404.16130", title="GraphRAG: From Local"))

    assert name.startswith("online-graphrag-arxiv-2404.16130")
    assert name.endswith(".pdf")


def test_pdf_filename_falls_back_to_doi() -> None:
    """Ohne arXiv-ID trägt die DOI den Anker; ``/`` wird ersetzt, da es kein Pfadtrenner sein darf."""
    name = pdf_filename(_candidate(doi="10.1145/3696410.3714748", arxiv_id=""))

    assert "doi-10.1145_3696410.3714748" in name


def test_pdf_filename_has_no_path_traversal_characters() -> None:
    """Ein feindlicher Titel/Identifikator kann den Namen nicht verlassen (Whitelist-Zeichen).

    Nur ``a``-``z``, ``0``-``9``, ``.``, ``_`` und ``-`` überleben; insbesondere fehlt jeder
    Pfadtrenner (``/`` und ``\\``) – ohne ihn ist kein Verzeichniswechsel möglich, auch wenn
    einzelne Punkte aus dem Originaltext erhalten bleiben (dasselbe Muster wie
    ``references.stub_filename``).
    """
    hostile = _candidate(
        title="../../evil", doi="../../etc/passwd", arxiv_id="", url="https://example.org/a.pdf"
    )

    name = pdf_filename(hostile)

    assert "/" not in name
    assert "\\" not in name
    assert name.endswith(".pdf")


def test_download_candidate_skips_network_without_license() -> None:
    """Ohne Lizenzangabe wird gar nicht erst verbunden – kein Kontingentverbrauch für Aussichtsloses."""
    client = _FakeClient(HttpResponse(status=200, headers={}, body=b"%PDF-"))

    outcome = download_candidate(client, Path("unused"), _candidate(license=""))

    assert outcome.outcome == OUTCOME_NO_LICENSE
    assert client.calls == []


def test_download_candidate_rejects_non_whitelisted_license() -> None:
    """Eine bekannte, aber nicht gelistete Lizenz bleibt ein Link, kein Download."""
    client = _FakeClient(HttpResponse(status=200, headers={}, body=b"%PDF-"))

    outcome = download_candidate(client, Path("unused"), _candidate(license="cc-by-nc"))

    assert outcome.outcome == OUTCOME_LICENSE_NOT_WHITELISTED
    assert "cc-by-nc" in outcome.note
    assert client.calls == []


def test_download_candidate_requires_a_url() -> None:
    """Ohne Volltext-Link ist nichts zu holen."""
    client = _FakeClient(HttpResponse(status=200, headers={}, body=b"%PDF-"))

    outcome = download_candidate(client, Path("unused"), _candidate(url=""))

    assert outcome.outcome == OUTCOME_NO_URL
    assert client.calls == []


def test_download_candidate_reports_http_status(tmp_path: Path) -> None:
    """Ein Statuscode ≠ 200 ist ein benannter Fehlschlag, kein Download."""
    client = _FakeClient(HttpResponse(status=404, headers={}, body=b""))

    outcome = download_candidate(client, tmp_path, _candidate())

    assert outcome.outcome == OUTCOME_HTTP_ERROR
    assert "404" in outcome.note


def test_download_candidate_translates_transport_failures() -> None:
    """Ein Netzfehler des Transport-Ports bricht den Lauf nicht, sondern wird ausgewiesen."""
    outcome = download_candidate(_FailingClient(), Path("unused"), _candidate())

    assert outcome.outcome == OUTCOME_HTTP_ERROR
    assert "kein Netz" in outcome.note


def test_download_candidate_rejects_a_response_without_pdf_signature(tmp_path: Path) -> None:
    """Ein `Content-Type`-Header allein genügt nicht – die Signatur entscheidet."""
    client = _FakeClient(
        HttpResponse(status=200, headers={"content-type": "application/pdf"}, body=b"<html/>")
    )

    outcome = download_candidate(client, tmp_path, _candidate())

    assert outcome.outcome == OUTCOME_NOT_A_PDF


def test_download_candidate_calls_get_with_the_download_size_limit() -> None:
    """Der Download-Pfad nutzt die größere Grenze, nicht den 5-MB-Metadaten-Default."""
    client = _FakeClient(HttpResponse(status=404, headers={}, body=b""))

    download_candidate(client, Path("unused"), _candidate())

    assert client.calls == [("https://example.org/paper.pdf", MAX_DOWNLOAD_BYTES)]


def test_download_candidate_rejects_a_single_page_abstract(tmp_path: Path, make_pdf: Any) -> None:
    """Ein einzelnes Abstract-Blatt ist kein Volltext, auch mit passendem Titel."""
    title = "Graph Retrieval Augmented Generation For Question Answering"
    pdf_path = make_pdf([title])
    client = _FakeClient(HttpResponse(status=200, headers={}, body=pdf_path.read_bytes()))
    inbox = tmp_path / "inbox"

    outcome = download_candidate(client, inbox, _candidate(title=title))

    assert outcome.outcome == OUTCOME_TOO_SHORT
    assert not inbox.exists() or list(inbox.glob("*.pdf")) == []


def test_download_candidate_rejects_mismatched_content(tmp_path: Path, make_pdf: Any) -> None:
    """Ein PDF mit unpassendem Titel wird verworfen – Schutz gegen Landing-Pages/Fehlverweise."""
    pdf_path = make_pdf(["Ein völlig anderes Werk über Katzenfotografie", "Zweite Seite"])
    client = _FakeClient(HttpResponse(status=200, headers={}, body=pdf_path.read_bytes()))
    inbox = tmp_path / "inbox"

    outcome = download_candidate(client, inbox, _candidate())

    assert outcome.outcome == OUTCOME_TITLE_MISMATCH
    assert not inbox.exists() or list(inbox.glob("*.pdf")) == []


def test_download_candidate_accepts_matching_content_and_writes_atomically(
    tmp_path: Path, make_pdf: Any
) -> None:
    """Titel-Rückvergleich bestanden ⇒ Datei landet im Eingang, keine Temporärdatei bleibt zurück."""
    title = "Graph Retrieval Augmented Generation For Question Answering"
    pdf_path = make_pdf([title, "Zweite Seite mit weiterem Inhalt."])
    client = _FakeClient(HttpResponse(status=200, headers={}, body=pdf_path.read_bytes()))

    outcome = download_candidate(client, tmp_path, _candidate(title=title))

    assert outcome.outcome == OUTCOME_DOWNLOADED
    assert outcome.path is not None
    assert outcome.path.parent == tmp_path
    assert outcome.path.read_bytes() == pdf_path.read_bytes()
    assert list(tmp_path.glob("*.tmp")) == []
    assert outcome.path.name.startswith("online-")


def test_download_all_preserves_order_and_never_stops_on_failure(tmp_path: Path) -> None:
    """Ein Fehlschlag bei einem Kandidaten hält den Lauf nicht auf."""
    client = _FakeClient(HttpResponse(status=500, headers={}, body=b""))
    candidates = (
        _candidate(license="", doi="10.1/a", url="https://example.org/a.pdf"),
        _candidate(license="cc-by", doi="10.1/b", url="https://example.org/b.pdf"),
    )

    outcomes = download_all(client, tmp_path, candidates)

    assert [item.candidate.doi for item in outcomes] == ["10.1/a", "10.1/b"]
    assert outcomes[0].outcome == OUTCOME_NO_LICENSE
    assert outcomes[1].outcome == OUTCOME_HTTP_ERROR


def test_download_all_only_pauses_between_actual_network_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ein Kandidat ohne Lizenz verzögert die folgenden nicht – nur echte Abrufe pausieren."""
    sleeps: list[float] = []
    monkeypatch.setattr("research_graphrag.online.download.time.sleep", sleeps.append)
    client = _FakeClient(HttpResponse(status=500, headers={}, body=b""))
    candidates = (
        _candidate(license="", doi="10.1/a"),
        _candidate(license="cc-by", doi="10.1/b", url="https://example.org/b.pdf"),
        _candidate(license="cc-by", doi="10.1/c", url="https://example.org/c.pdf"),
    )

    download_all(client, tmp_path, candidates)

    assert sleeps == [DOWNLOAD_DELAY_SECONDS]
