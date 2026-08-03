"""Tests für Anfragebildung und Laufsteuerung des Online-Modus (Phase 9 / S1)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index
from research_graphrag.online.search import (
    DEFAULT_RECENT_YEARS,
    default_min_year,
    discover,
    query_from_community,
    query_from_seed,
    title_terms,
)
from research_graphrag.online.sources import SearchQuery
from research_graphrag.online.transport import HttpResponse

ARXIV_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v1</id>
    <published>2025-01-02T10:00:00Z</published>
    <title>Neuer Kandidat zur Graphsuche</title>
    <summary>Abstract eins.</summary>
    <link title="pdf" href="http://arxiv.org/pdf/2501.00001v1" rel="related"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1901.00002v1</id>
    <published>2019-01-02T10:00:00Z</published>
    <title>Alter Kandidat aus dem Archiv</title>
    <summary>Abstract zwei.</summary>
  </entry>
</feed>
"""

OPENALEX_PAYLOAD = json.dumps(
    {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.48550/arxiv.2501.00001",
                "title": "Neuer Kandidat zur Graphsuche",
                "publication_year": 2025,
                "open_access": {"oa_url": "https://example.org/w1.pdf"},
                "primary_location": {"license": "cc-by"},
                "abstract_inverted_index": {"Langer": [0], "Abstract": [1]},
            }
        ]
    }
).encode()


class _FakeClient:
    """Antwortet je nach Host mit dem passenden Fixture und protokolliert die Aufrufe."""

    def __init__(self, *, arxiv: bytes = ARXIV_FEED, openalex: bytes = OPENALEX_PAYLOAD) -> None:
        self._arxiv = arxiv
        self._openalex = openalex
        self.urls: list[str] = []

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        self.urls.append(url)
        body = self._arxiv if "arxiv.org" in url else self._openalex
        return HttpResponse(status=200, headers={}, body=body)


def _paper(paper_id: str, texts: Sequence[str], name: str) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index + 1:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
        )
        for index, text in enumerate(texts)
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///papers/{name}.pdf",
        source_sha256="0" * 64,
        n_pages=len(texts),
        chunks=chunks,
        quality_flags=(),
    )


def _papers() -> list[CanonicalPaper]:
    return [
        _paper(
            "aaaa0001",
            ["graphrag retrieval augmented generation graph", "graph retrieval community"],
            "Graph Retrieval Augmented Generation for Corpora",
        ),
        _paper(
            "bbbb0002",
            ["graphrag retrieval augmented graph entities", "graph retrieval augmented"],
            "Another Graph Retrieval Augmented Study",
        ),
    ]


def _build(tmp_path: Path, *, with_canonical: bool = False) -> tuple[Path, Path]:
    data_path = tmp_path / "data"
    db = data_path / "index" / "index.sqlite"
    papers = _papers()
    build_index(papers, db)
    build_graph(papers, db)
    if with_canonical:
        canonical = data_path / "canonical"
        canonical.mkdir(parents=True, exist_ok=True)
        for paper in papers:
            paper.save_json(canonical / f"{paper.paper_id}.json")
    return db, data_path


def test_title_terms_drops_stopwords_and_noise() -> None:
    """Stopwords, Kürzel und kuratierte Rausch-Terme tragen keine Suchbedeutung."""
    terms = title_terms("The Study of Retrieval with et al Graphs")

    assert "the" not in terms
    assert "et" not in terms
    assert terms[:2] == ["study", "retrieval"]


def test_title_terms_keeps_order_and_deduplicates() -> None:
    """Die Titelreihenfolge bleibt erhalten, Wiederholungen entfallen."""
    assert title_terms("Graph Graph Retrieval") == ["graph", "retrieval"]


def test_default_min_year_uses_the_configured_window() -> None:
    """Die Jahresgrenze folgt dem gemessenen Zeitfenster."""
    reference = datetime(2026, 8, 3, tzinfo=UTC)

    assert default_min_year(today=reference) == 2026 - DEFAULT_RECENT_YEARS


def test_query_from_community_uses_index_keywords(tmp_path: Path) -> None:
    """Die Anfrage entsteht aus dem eigenen Ähnlichkeitsgraphen, nicht aus freier Eingabe."""
    db, _ = _build(tmp_path)

    query = query_from_community(db, 0, terms=2)

    assert query.query_id == "C0"
    assert len(query.terms) == 2
    assert "Community 0" in query.reason


def test_query_from_community_reports_unknown_id(tmp_path: Path) -> None:
    """Eine unbekannte Community wird als ``not_found`` gemeldet."""
    db, _ = _build(tmp_path)

    with pytest.raises(DomainError) as excinfo:
        query_from_community(db, 99)

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_query_from_seed_uses_the_paper_title(tmp_path: Path) -> None:
    """„Mehr wie dieses" leitet die Begriffe aus dem Titel des Seed-Papers ab."""
    db, _ = _build(tmp_path)

    query = query_from_seed(db, "aaaa0001", terms=3)

    assert query.query_id == "Saaaa0001"
    assert query.terms == ("graph", "retrieval", "augmented")
    assert "Seed-Paper" in query.reason


def test_query_from_seed_reports_unknown_paper(tmp_path: Path) -> None:
    """Eine unbekannte Paper-Kennung wird als ``not_found`` gemeldet."""
    db, _ = _build(tmp_path)

    with pytest.raises(DomainError) as excinfo:
        query_from_seed(db, "gibtesnicht")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_discover_merges_sources_and_applies_recency(tmp_path: Path) -> None:
    """Ein Lauf führt Quellen zusammen, filtert nach Jahr und weist die Bilanz aus."""
    db, data_path = _build(tmp_path)
    client = _FakeClient()
    query = SearchQuery(query_id="C0", terms=("graph",), reason="Community 0")

    report = discover(db, data_path, [query], client, min_year=2021)

    assert report.found == 2
    assert report.dropped_old == 1
    assert len(report.fresh) == 1
    fresh = report.fresh[0]
    assert fresh.sources == ("arXiv", "OpenAlex")
    assert fresh.license == "cc-by"
    assert fresh.abstract == "Langer Abstract"


def test_discover_queries_both_sources_once_per_query(tmp_path: Path) -> None:
    """Je Anfrage genau eine Abfrage pro Quelle – kein Bulk-Abruf."""
    db, data_path = _build(tmp_path)
    client = _FakeClient()
    query = SearchQuery(query_id="C0", terms=("graph",), reason="Community 0")

    discover(db, data_path, [query], client, keep_raw=False)

    assert len(client.urls) == 2
    assert sum("arxiv.org" in url for url in client.urls) == 1


def test_discover_recognises_papers_already_in_the_corpus(tmp_path: Path) -> None:
    """Akzeptanzbedingung: ein vorhandenes Paper wird nicht als neu ausgewiesen."""
    db, data_path = _build(tmp_path, with_canonical=True)
    feed = ARXIV_FEED.replace(
        b"Neuer Kandidat zur Graphsuche",
        b"Graph Retrieval Augmented Generation for Corpora",
    )
    client = _FakeClient(arxiv=feed, openalex=b'{"results": []}')
    query = SearchQuery(query_id="C0", terms=("graph",), reason="Community 0")

    report = discover(db, data_path, [query], client, min_year=2021)

    assert [item.match for item in report.known] == ["title"]
    assert report.fresh == ()


def test_discover_stores_raw_answers(tmp_path: Path) -> None:
    """Die Rohantworten werden datiert abgelegt (Reproduzierbarkeit)."""
    db, data_path = _build(tmp_path)
    query = SearchQuery(query_id="C0", terms=("graph",), reason="Community 0")

    report = discover(db, data_path, [query], _FakeClient())

    assert report.raw_dir is not None
    assert len(list(report.raw_dir.iterdir())) == 2


def test_discover_can_skip_raw_storage(tmp_path: Path) -> None:
    """Die Ablage lässt sich abschalten, ohne den Lauf zu verändern."""
    db, data_path = _build(tmp_path)
    query = SearchQuery(query_id="C0", terms=("graph",), reason="Community 0")

    report = discover(db, data_path, [query], _FakeClient(), keep_raw=False)

    assert report.raw_dir is None
    assert not (data_path / "online_raw").exists()


def test_discover_rejects_empty_query_list(tmp_path: Path) -> None:
    """Ein Lauf ohne Anfrage ist ein Eingabefehler, kein leerer Bericht."""
    db, data_path = _build(tmp_path)

    with pytest.raises(DomainError) as excinfo:
        discover(db, data_path, [], _FakeClient())

    assert excinfo.value.code is ErrorCode.INVALID_INPUT
