"""Tests für die Online-Auflösung der Zitationsdaten (Phase 12 / K2, ADR 0026).

Der Netzzugang läuft über den injizierten Port; alle Prüfungen sind damit **offline**.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote

import pytest

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_EXTRACTED,
    ORIGIN_RESOLVED,
    MetadataRecord,
)
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SECTION_KIND_BODY, Section
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.metadata_index import build_metadata_index
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.online.metadata import (
    MATCH_ARXIV,
    MATCH_DOI,
    MATCH_TITLE,
    MAX_AUTHORS,
    ResolutionTarget,
    authors_of,
    filter_pending,
    openalex_id_url,
    openalex_title_url,
    parse_openalex_work,
    resolve_target,
    targets_from_index,
    venue_of,
)
from research_graphrag.online.transport import HttpResponse

_TITLE = "Graph Retrieval for Scientific Corpora at Scale"
_DOI = "10.1145/3696410.3714748"
_ARXIV = "2401.00001"


def _work(
    *,
    title: str = _TITLE,
    doi: str = _DOI,
    year: int = 2024,
    authors: Sequence[str] = ("Anna Beispiel", "Bert Muster"),
    venue: str = "Proceedings of ACL",
) -> dict[str, object]:
    """Baut ein OpenAlex-Werk in der Antwortform des Dienstes."""
    return {
        "id": "https://openalex.org/W1",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "publication_year": year,
        "authorships": [{"author": {"display_name": name}} for name in authors],
        "primary_location": {"source": {"display_name": venue}},
        "open_access": {"oa_url": "https://example.org/w1.pdf"},
    }


def _payload(*works: dict[str, object]) -> bytes:
    """Verpackt Werke als OpenAlex-Trefferliste."""
    return json.dumps({"results": list(works)}).encode()


_ARXIV_FEED = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/{_ARXIV}v1</id>
    <published>2024-01-02T10:00:00Z</published>
    <title>{_TITLE}</title>
    <summary>Abstract.</summary>
  </entry>
</feed>
""".encode()


class _FakeClient:
    """Antwortet je nach URL-Muster und protokolliert alle Aufrufe."""

    def __init__(
        self,
        *,
        by_id: bytes | None = None,
        by_title: bytes | None = None,
        arxiv: bytes | None = None,
        status: int = 200,
    ) -> None:
        self._by_id = by_id
        self._by_title = by_title
        self._arxiv = arxiv
        self._status = status
        self.urls: list[str] = []

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        self.urls.append(url)
        if "arxiv.org" in url:
            body = self._arxiv
        elif "works/doi:" in url:
            body = self._by_id
        else:
            body = self._by_title
        if body is None:
            return HttpResponse(status=404, headers={}, body=b"{}")
        return HttpResponse(status=self._status, headers={}, body=body)


def _paper(paper_id: str, title: str, identifiers: dict[str, str] | None = None) -> CanonicalPaper:
    """Baut ein minimales Canonical-Paper mit Titelseiten-Beleg."""
    body = f"{title} " + " ".join(f"{key}:{value}" for key, value in (identifiers or {}).items())
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{quote(title)}.pdf",
        source_sha256="0" * 64,
        n_pages=1,
        chunks=(
            Chunk(
                chunk_id=f"{paper_id}-c0001",
                paper_id=paper_id,
                page_number=1,
                text=body,
                char_count=len(body),
                section_id="s-body",
                section_title="Introduction",
            ),
        ),
        quality_flags=(),
        sections=(
            Section(
                section_id="s-body",
                title="Introduction",
                kind=SECTION_KIND_BODY,
                level=1,
                page_number=1,
                order=0,
            ),
        ),
        identifiers=identifiers or {},
    )


def _target(**fields: object) -> ResolutionTarget:
    """Baut ein Auflösungsziel mit sinnvollen Vorgaben."""
    base: dict[str, object] = {"paper_id": "aaaa0001", "title": _TITLE, "doi": _DOI}
    base.update(fields)
    return ResolutionTarget(**base)  # type: ignore[arg-type]


def test_identifier_url_escapes_the_doi() -> None:
    """Der DOI wird vollständig kodiert, damit Schrägstriche den Pfad nicht aufbrechen."""
    url = openalex_id_url(_DOI)

    assert "works/doi:10.1145%2F3696410.3714748" in url
    assert "authorships" in url


def test_title_url_requires_a_title() -> None:
    """Eine Titelsuche ohne Titel ist ein Eingabefehler."""
    with pytest.raises(DomainError) as excinfo:
        openalex_title_url("   ")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_parse_single_work_accepts_the_doi_response() -> None:
    """Die DOI-Abfrage liefert ein einzelnes Werk statt einer Trefferliste."""
    candidate = parse_openalex_work(json.dumps(_work()).encode())

    assert candidate is not None
    assert candidate.doi == _DOI
    assert candidate.year == 2024


def test_parse_single_work_rejects_broken_json() -> None:
    """Defektes JSON ist ein fachlicher Parse-Fehler."""
    with pytest.raises(DomainError) as excinfo:
        parse_openalex_work(b"{kein json")

    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_parse_single_work_returns_none_without_a_work() -> None:
    """Eine Antwort ohne Werk liefert nichts, statt zu scheitern."""
    assert parse_openalex_work(b"{}") is None
    assert parse_openalex_work(b"[]") is None


def test_authors_and_venue_are_read_from_both_response_forms() -> None:
    """Autoren und Venue werden aus Einzelwerk **und** Trefferliste gelesen."""
    single = json.dumps(_work()).encode()

    assert authors_of(single) == ("Anna Beispiel", "Bert Muster")
    assert authors_of(_payload(_work())) == ("Anna Beispiel", "Bert Muster")
    assert venue_of(single) == "Proceedings of ACL"
    assert venue_of(_payload(_work())) == "Proceedings of ACL"


def test_author_list_is_capped_and_cleaned() -> None:
    """Kollaborationslisten werden gedeckelt, Steuerzeichen entfernt."""
    names = [f"Vorname{index} Nachname{index}" for index in range(60)]
    names[0] = "Anna\u0000\nBeispiel"

    authors = authors_of(json.dumps(_work(authors=names)).encode())

    assert len(authors) == MAX_AUTHORS
    assert authors[0] == "Anna Beispiel"


def test_broken_payload_yields_no_authors_or_venue() -> None:
    """Unlesbare Antworten liefern leere Werte statt einer Ausnahme."""
    assert authors_of(b"{kein json") == ()
    assert venue_of(b"{kein json") == ""
    assert authors_of(b"[]") == ()
    assert venue_of(b"[]") == ""


def test_doi_match_is_taken_over_as_a_strong_record() -> None:
    """Ein Treffer über die belegte DOI gilt als starker Beleg."""
    client = _FakeClient(by_id=json.dumps(_work()).encode())

    result = resolve_target(client, _target())

    assert result.match == MATCH_DOI
    assert result.record is not None
    assert result.record.origin == ORIGIN_RESOLVED
    assert result.record.confidence == CONFIDENCE_STRONG
    assert result.record.authors == ("Anna Beispiel", "Bert Muster")
    assert result.record.venue == "Proceedings of ACL"
    assert result.record.year == 2024


def test_unbacked_identifier_is_taken_over_but_marked_weak() -> None:
    """Ein lokal nicht belegter Identifikator wird übernommen, aber als schwach ausgewiesen."""
    client = _FakeClient(by_id=json.dumps(_work()).encode())

    result = resolve_target(client, _target(identifier_backed=False))

    assert result.record is not None
    assert result.record.confidence == CONFIDENCE_WEAK
    assert "nicht belegt" in result.record.evidence


def test_arxiv_identifier_is_queried_through_its_datacite_doi() -> None:
    """Ohne DOI wird die arXiv-ID über ihren DataCite-DOI abgefragt."""
    client = _FakeClient(by_id=json.dumps(_work(doi=f"10.48550/arxiv.{_ARXIV}")).encode())

    result = resolve_target(client, _target(doi="", arxiv_id=_ARXIV))

    assert result.match == MATCH_ARXIV
    assert "10.48550%2FarXiv." in client.urls[0]


def test_title_match_above_the_threshold_is_weak() -> None:
    """Ein Titeltreffer ist eine Ähnlichkeitsaussage und damit nie ein starker Beleg."""
    client = _FakeClient(by_title=_payload(_work()))

    result = resolve_target(client, _target(doi=""))

    assert result.match == MATCH_TITLE
    assert result.record is not None
    assert result.record.confidence == CONFIDENCE_WEAK
    assert "Titel-Ähnlichkeit" in result.record.evidence


def test_title_match_below_the_threshold_is_discarded() -> None:
    """Unterhalb der kalibrierten Schwelle wird nichts übernommen."""
    client = _FakeClient(by_title=_payload(_work(title="Etwas ganz anderes über Kühlsysteme")))

    result = resolve_target(client, _target(doi=""))

    assert result.record is None
    assert "ohne belastbaren Treffer" in result.note


def test_arxiv_feed_is_the_last_resort() -> None:
    """Liefert OpenAlex nichts, springt der arXiv-Feed ein (Titel und Preprint-Jahr)."""
    client = _FakeClient(by_title=_payload(), arxiv=_ARXIV_FEED)

    result = resolve_target(client, _target(doi="", arxiv_id=_ARXIV))

    assert result.match == MATCH_ARXIV
    assert result.record is not None
    assert result.record.title == _TITLE
    assert result.record.year == 2024
    assert any("arxiv.org" in url for url in client.urls)


def test_arxiv_feed_rejects_a_different_identifier() -> None:
    """Antwortet arXiv mit einer anderen ID, wird nichts übernommen."""
    feed = _ARXIV_FEED.replace(_ARXIV.encode(), b"2999.99999")
    client = _FakeClient(by_title=_payload(), arxiv=feed)

    result = resolve_target(client, _target(doi="", arxiv_id=_ARXIV))

    assert result.record is None
    assert "andere ID" in result.note


def test_target_without_identifier_and_title_is_reported() -> None:
    """Ohne jede Abfragemöglichkeit wird das ehrlich vermerkt – ohne Netzaufruf."""
    client = _FakeClient()

    result = resolve_target(client, _target(doi="", title=""))

    assert result.record is None
    assert client.urls == []
    assert "keine Abfragemöglichkeit" in result.note


def test_http_error_is_reported_without_raising() -> None:
    """Ein Fehlerstatus beendet den Lauf nicht, sondern steht im Befund."""
    client = _FakeClient(by_id=b"{}", status=503)

    result = resolve_target(client, _target(title=""))

    assert result.record is None
    assert result.raw and result.raw[0].status == 503


def test_raw_responses_are_collected_across_attempts() -> None:
    """Alle Rohantworten eines Laufs bleiben für die Ablage erhalten."""
    client = _FakeClient(by_title=_payload(_work()))

    result = resolve_target(client, _target())

    assert len(result.raw) >= 2  # gescheiterte DOI-Abfrage + erfolgreiche Titelsuche


def test_targets_are_selected_from_the_index(tmp_path: Path) -> None:
    """Nur Paper mit unvollständiger Angabe werden ausgewählt."""
    papers = [_paper("aaaa0001", _TITLE, {"arxiv": _ARXIV})]
    db = tmp_path / "index.sqlite"
    build_index(papers, db)
    build_metadata_index(papers, db)

    targets = targets_from_index(db)

    assert len(targets) == 1
    assert targets[0].paper_id == "aaaa0001"
    assert targets[0].arxiv_id == _ARXIV
    assert targets[0].identifier_backed is True
    assert set(targets[0].missing) == {"authors"}


def test_unbacked_identifier_is_flagged_in_the_target(tmp_path: Path) -> None:
    """Ein nur im Volltext gefundener Identifikator senkt die Belegkraft des Ziels."""
    papers = [_paper("aaaa0001", _TITLE, {"arxiv": "2108.07732"})]
    papers[0] = CanonicalPaper(
        paper_id=papers[0].paper_id,
        source_uri=papers[0].source_uri,
        source_sha256=papers[0].source_sha256,
        n_pages=1,
        chunks=papers[0].chunks,
        quality_flags=(),
        sections=papers[0].sections,
        identifiers={"arxiv": "2999.99999"},  # steht nicht im Text
    )
    db = tmp_path / "index.sqlite"
    build_index(papers, db)
    build_metadata_index(papers, db)

    targets = targets_from_index(db)

    assert targets[0].identifier_backed is False


def test_pending_filter_skips_already_stored_results() -> None:
    """Ein zweiter Lauf vor dem nächsten Ingest fragt dieselben Paper nicht erneut ab."""
    target = _target(missing=("authors", "year"))
    stored = [
        MetadataRecord(
            paper_id="aaaa0001",
            origin=ORIGIN_RESOLVED,
            authors=("Anna Beispiel",),
            year=2024,
        )
    ]

    assert filter_pending([target], stored) == ()


def test_pending_filter_keeps_partially_covered_targets() -> None:
    """Deckt der gespeicherte Datensatz nur einen Teil ab, bleibt das Ziel offen."""
    target = _target(missing=("authors", "year"))
    stored = [MetadataRecord(paper_id="aaaa0001", origin=ORIGIN_RESOLVED, year=2024)]

    assert filter_pending([target], stored) == (target,)


def test_pending_filter_ignores_records_of_other_origins() -> None:
    """Extrahierte oder kuratierte Datensätze zählen nicht als bereits aufgelöst."""
    target = _target(missing=("authors",))
    stored = [
        MetadataRecord(paper_id="aaaa0001", origin=ORIGIN_EXTRACTED, authors=("Anna Beispiel",))
    ]

    assert filter_pending([target], stored) == (target,)


def test_pending_filter_keeps_targets_without_missing_fields() -> None:
    """Mit ``--alle`` angefragte, vollständige Ziele bleiben erhalten."""
    target = _target(missing=())

    assert filter_pending([target], []) == (target,)
