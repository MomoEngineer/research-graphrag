"""Tests für die Quellen-Adapter arXiv und OpenAlex (Phase 9 / S1).

Die Fixtures bilden die **Struktur** der realen Antworten nach (Namensräume, Feldnamen,
invertierter Abstract-Index), tragen aber erfundene Inhalte – fremde Abstracts gehören nicht in
ein Repository.
"""

from __future__ import annotations

import json

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.online.candidates import SOURCE_ARXIV, SOURCE_OPENALEX
from research_graphrag.online.sources import (
    SearchQuery,
    arxiv_url,
    fetch_arxiv,
    fetch_openalex,
    openalex_url,
    parse_arxiv,
    parse_openalex,
)
from research_graphrag.online.transport import HttpResponse

QUERY = SearchQuery(query_id="C1", terms=("graphrag", "retrieval"), reason="Community 1")

ARXIV_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v2</id>
    <published>2025-01-02T10:00:00Z</published>
    <title>Ein Testtitel
      mit Umbruch</title>
    <summary>Erste Zeile
      zweite Zeile.</summary>
    <link href="http://arxiv.org/abs/2501.00001v2" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2501.00001v2" rel="related"/>
    <arxiv:doi>10.1000/testdoi</arxiv:doi>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2502.00002v1</id>
    <published>2025-02-03T10:00:00Z</published>
    <title>Zweiter Titel</title>
    <summary>Zusammenfassung zwei.</summary>
  </entry>
</feed>
"""

OPENALEX_PAYLOAD = json.dumps(
    {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.48550/arxiv.2501.00001",
                "title": "Ein Testtitel mit Umbruch",
                "publication_year": 2025,
                "open_access": {"oa_url": "https://example.org/w1.pdf", "oa_status": "green"},
                "primary_location": {"license": "cc-by"},
                "abstract_inverted_index": {"Zweites": [1], "Wort": [2], "Erstes": [0]},
            },
            {
                "id": "https://openalex.org/W2",
                "doi": None,
                "title": "Ohne Identifikator",
                "publication_year": None,
                "open_access": {},
                "primary_location": None,
                "abstract_inverted_index": None,
            },
        ]
    }
).encode()


class _FakeClient:
    """Liefert vorbereitete Antworten und merkt sich die abgefragten URLs."""

    def __init__(self, *responses: HttpResponse) -> None:
        self._responses = list(responses)
        self.urls: list[str] = []

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        self.urls.append(url)
        return self._responses.pop(0)


def _ok(body: bytes, **headers: str) -> HttpResponse:
    return HttpResponse(status=200, headers=dict(headers), body=body)


def test_arxiv_url_joins_terms_with_and() -> None:
    """Die Terme werden UND-verknüpft und URL-kodiert."""
    url = arxiv_url(QUERY, limit=5)

    assert url.startswith("https://export.arxiv.org/api/query?search_query=")
    assert "max_results=5" in url
    assert "AND" in url


def test_arxiv_url_limits_the_number_of_terms() -> None:
    """Zu viele UND-Terme lassen die Suche leer laufen, deshalb wird abgeschnitten."""
    query = SearchQuery(query_id="C1", terms=("a", "b", "c", "d", "e"), reason="x")

    assert arxiv_url(query).count("AND") == 2


def test_openalex_url_uses_free_text_and_narrow_field_list() -> None:
    """OpenAlex bekommt Freitext und eine schmale Feldauswahl (Antwortgröße, Kontingent)."""
    url = openalex_url(QUERY, limit=3)

    assert url.startswith("https://api.openalex.org/works?search=")
    assert "per-page=3" in url
    assert "abstract_inverted_index" in url


@pytest.mark.parametrize("terms", [(), ("",), ("  ",)])
def test_url_builders_reject_empty_queries(terms: tuple[str, ...]) -> None:
    """Eine Anfrage ohne Begriffe wird gemeldet statt blind abgeschickt."""
    query = SearchQuery(query_id="C1", terms=terms, reason="x")

    for builder in (arxiv_url, openalex_url):
        with pytest.raises(DomainError) as excinfo:
            builder(query)
        assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_parse_arxiv_extracts_fields_and_strips_version() -> None:
    """Titel und Abstract werden verdichtet, die Versionskennung entfällt."""
    candidates = parse_arxiv(ARXIV_FEED, QUERY)

    assert len(candidates) == 2
    first = candidates[0]
    assert first.title == "Ein Testtitel mit Umbruch"
    assert first.abstract == "Erste Zeile zweite Zeile."
    assert first.arxiv_id == "2501.00001"
    assert first.doi == "10.1000/testdoi"
    assert first.year == 2025
    assert first.url == "http://arxiv.org/pdf/2501.00001v2"
    assert first.sources == (SOURCE_ARXIV,)
    assert (first.query_id, first.reason) == ("C1", "Community 1")


def test_parse_arxiv_falls_back_to_the_entry_link() -> None:
    """Ohne PDF-Link bleibt der Eintrags-Verweis erhalten."""
    assert parse_arxiv(ARXIV_FEED, QUERY)[1].url == "http://arxiv.org/abs/2502.00002v1"


def test_parse_arxiv_rejects_doctype_declaration() -> None:
    """Schutz vor Entity-Expansion: Dokumenttyp-Deklarationen werden abgelehnt."""
    payload = b'<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY x "y">]><feed/>'

    with pytest.raises(DomainError) as excinfo:
        parse_arxiv(payload, QUERY)

    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_parse_arxiv_reports_broken_xml() -> None:
    """Unlesbares XML wird als Parse-Fehler gemeldet, nicht verschluckt."""
    with pytest.raises(DomainError) as excinfo:
        parse_arxiv(b"<feed", QUERY)

    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_parse_openalex_restores_inverted_abstract() -> None:
    """Der invertierte Index wird in die richtige Wortreihenfolge zurückgebaut."""
    candidates = parse_openalex(OPENALEX_PAYLOAD, QUERY)

    assert candidates[0].abstract == "Erstes Zweites Wort"


def test_parse_openalex_derives_arxiv_id_from_doi() -> None:
    """Ein DOI der Form ``10.48550/arxiv.X`` trägt die arXiv-ID – wichtig für den Abgleich."""
    first = parse_openalex(OPENALEX_PAYLOAD, QUERY)[0]

    assert first.arxiv_id == "2501.00001"
    assert first.doi == "10.48550/arxiv.2501.00001"
    assert first.license == "cc-by"
    assert first.sources == (SOURCE_OPENALEX,)


def test_parse_openalex_tolerates_missing_fields() -> None:
    """Fehlende Felder führen zu leeren Werten, nicht zu einem Abbruch."""
    second = parse_openalex(OPENALEX_PAYLOAD, QUERY)[1]

    assert (second.doi, second.abstract, second.license, second.year) == ("", "", "", 0)
    assert second.url == "https://openalex.org/W2"


def test_parse_openalex_reports_broken_json() -> None:
    """Unlesbares JSON wird als Parse-Fehler gemeldet."""
    with pytest.raises(DomainError) as excinfo:
        parse_openalex(b"{kein json", QUERY)

    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_fetch_arxiv_returns_candidates_on_success() -> None:
    """Der Adapter reicht die Rohantwort für die Ablage durch."""
    client = _FakeClient(_ok(ARXIV_FEED))

    result = fetch_arxiv(client, QUERY, limit=2)

    assert result.status == 200
    assert result.raw == ARXIV_FEED
    assert len(result.candidates) == 2
    assert client.urls[0].startswith("https://export.arxiv.org/")


def test_fetch_reports_http_error_without_raising() -> None:
    """Ein Rate-Limit einer Quelle darf den Lauf nicht abbrechen – er wird berichtet."""
    client = _FakeClient(HttpResponse(status=429, headers={}, body=b"{}"))

    result = fetch_openalex(client, QUERY)

    assert result.status == 429
    assert result.candidates == ()
    assert "429" in result.note


def test_fetch_openalex_passes_through_rate_limit_headers() -> None:
    """Die Kontingent-Angaben werden für den Bericht durchgereicht."""
    client = _FakeClient(
        _ok(OPENALEX_PAYLOAD, **{"x-ratelimit-remaining": "980", "x-ratelimit-limit": "1000"})
    )

    result = fetch_openalex(client, QUERY)

    assert result.rate_limit == {"x-ratelimit-remaining": "980", "x-ratelimit-limit": "1000"}
