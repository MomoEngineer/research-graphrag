"""Tests für die Referenz-Auflösung (Phase 13 / R1, ADR 0029).

Der Netzzugang läuft über den injizierten Port; alle Prüfungen sind damit **offline**. Geprüft
werden vier Dinge getrennt voneinander: das Deuten der Kennungsliste, die Idempotenz gegen die
drei Zustände, die Auflösung samt arXiv-Rückfall und die Bereinigung fremder Eingaben.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.intake import QUARANTINE_DIR, CorpusView
from research_graphrag.online.references import (
    ACTION_INVALID,
    ACTION_SKIPPED,
    ACTION_UNRESOLVED,
    ACTION_WRITTEN,
    DOCUMENT_KIND_REFERENCE,
    KIND_ARXIV,
    KIND_DOI,
    MAX_ABSTRACT_CHARS,
    REASON_DUPLICATE_LINE,
    REASON_IN_CORPUS,
    REASON_QUARANTINED,
    REASON_STUB_EXISTS,
    REFERENCE_FIELDS,
    STUB_SCHEMA_VERSION,
    STUB_SUFFIX,
    ReferenceRequest,
    build_stub,
    normalize_identifier,
    plan,
    process,
    read_reference_list,
    resolve_reference,
    stub_filename,
    stub_identifiers,
    title_slug,
    write_stub,
)
from research_graphrag.online.transport import HttpResponse

_DOI = "10.1145/3696410.3714748"
_ARXIV = "2404.16130"
_TITLE = "GraphRAG: From Local to Global Summarization of Large Corpora"
_ABSTRACT = "Ein Abstract mit Aussage."


def _work(
    *,
    title: str = _TITLE,
    doi: str = _DOI,
    year: int = 2024,
    authors: tuple[str, ...] = ("Anna Beispiel", "Bert Muster"),
    venue: str = "Proceedings of ACL",
    abstract: str | None = _ABSTRACT,
) -> bytes:
    """Baut eine OpenAlex-Einzelantwort in der Form des Dienstes."""
    payload: dict[str, object] = {
        "id": "https://openalex.org/W1",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "publication_year": year,
        "authorships": [{"author": {"display_name": name}} for name in authors],
        "primary_location": {"source": {"display_name": venue}},
        "open_access": {"oa_url": "https://example.org/w1.pdf"},
    }
    if abstract is not None:
        payload["abstract_inverted_index"] = {
            word: [index] for index, word in enumerate(abstract.split())
        }
    return json.dumps(payload).encode()


def _feed(
    *, title: str = _TITLE, arxiv_id: str = _ARXIV, summary: str = "Abstract aus arXiv."
) -> bytes:
    """Baut einen arXiv-Atom-Feed mit genau einem Eintrag."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/{arxiv_id}v2</id>
    <published>2024-04-24T10:00:00Z</published>
    <title>{title}</title>
    <summary>{summary}</summary>
    <author><name>Clara Feed</name></author>
    <author><name>Dorian Atom</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/{arxiv_id}v2" rel="related"/>
  </entry>
</feed>
""".encode()


class _FakeClient:
    """Antwortet je nach URL-Muster und protokolliert alle Aufrufe."""

    def __init__(self, *, openalex: bytes | None = None, arxiv: bytes | None = None) -> None:
        self._openalex = openalex
        self._arxiv = arxiv
        self.urls: list[str] = []

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        self.urls.append(url)
        body = self._arxiv if "arxiv.org" in url else self._openalex
        if body is None:
            return HttpResponse(status=404, headers={}, body=b"{}")
        return HttpResponse(status=200, headers={}, body=body)


def _empty_corpus() -> CorpusView:
    """Eine leere Prüfgrundlage (kein Korpus-Treffer möglich)."""
    return CorpusView(sha256_to_name={}, identifier_to_paper={}, titles={})


def _request(kind: str = KIND_ARXIV, value: str = _ARXIV) -> ReferenceRequest:
    """Ein einzelner Listeneintrag."""
    return ReferenceRequest(line_number=1, raw=f"{kind}:{value}", kind=kind, value=value)


# --------------------------------------------------------------------------------------
# Kennungen deuten
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10.1145/3696410.3714748", (KIND_DOI, _DOI)),
        ("doi:10.1145/3696410.3714748", (KIND_DOI, _DOI)),
        ("DOI: 10.1145/3696410.3714748", (KIND_DOI, _DOI)),
        ("https://doi.org/10.1145/3696410.3714748", (KIND_DOI, _DOI)),
        ("https://dx.doi.org/10.1145/3696410.3714748", (KIND_DOI, _DOI)),
        ("10.1145/3696410.3714748.", (KIND_DOI, _DOI)),
        ("2404.16130", (KIND_ARXIV, _ARXIV)),
        ("arXiv:2404.16130", (KIND_ARXIV, _ARXIV)),
        ("arXiv:2404.16130v3", (KIND_ARXIV, _ARXIV)),
        ("https://arxiv.org/abs/2404.16130", (KIND_ARXIV, _ARXIV)),
        ("https://arxiv.org/pdf/2404.16130v2", (KIND_ARXIV, _ARXIV)),
        ("cs/0501001", (KIND_ARXIV, "cs/0501001")),
        ("arXiv:cs/0501001v1", (KIND_ARXIV, "cs/0501001")),
        ("10.48550/arXiv.2404.16130", (KIND_ARXIV, _ARXIV)),
        ("", ("", "")),
        ("kein identifier", ("", "")),
        ("10.1/zu-kurz", ("", "")),
    ],
)
def test_identifiers_are_understood_in_every_common_spelling(
    text: str, expected: tuple[str, str]
) -> None:
    """DOI und arXiv-ID werden in allen gebräuchlichen Schreibweisen gedeutet."""
    assert normalize_identifier(text) == expected


def test_the_datacite_doi_is_normalised_to_the_arxiv_identifier() -> None:
    """``10.48550/arXiv.X`` und ``X`` bezeichnen dasselbe Werk – sonst scheitert die Dedup."""
    assert normalize_identifier("10.48550/arXiv.2404.16130") == normalize_identifier("2404.16130")


def test_the_list_is_read_with_comments_and_blank_lines(tmp_path: Path) -> None:
    """Kommentare (auch hinter der Kennung) und Leerzeilen stören nicht."""
    path = tmp_path / "referenzen.txt"
    path.write_text(
        "# Kopfkommentar\n"
        "\n"
        "10.1145/3696410.3714748   # weil mehrfach zitiert\n"
        "arXiv:2404.16130\n"
        "   \n"
        "das ist keine kennung\n",
        encoding="utf-8",
    )

    entries = read_reference_list(path)

    assert [entry.kind for entry in entries] == [KIND_DOI, KIND_ARXIV, ""]
    assert entries[0].comment == "weil mehrfach zitiert"
    assert entries[0].line_number == 3
    assert entries[2].value == ""


def test_a_missing_list_is_a_domain_error(tmp_path: Path) -> None:
    """Die fehlende Liste endet handlungsleitend, nicht in einem Stacktrace."""
    with pytest.raises(DomainError) as excinfo:
        read_reference_list(tmp_path / "fehlt.txt")

    assert excinfo.value.code is ErrorCode.NOT_FOUND
    assert "referenzen" in excinfo.value.message.lower() or "Kennungsliste" in excinfo.value.message


def test_reading_the_list_never_changes_it(tmp_path: Path) -> None:
    """Die Liste ist ein kuratiertes Dokument – sie wird ausschließlich gelesen."""
    path = tmp_path / "referenzen.txt"
    path.write_bytes(b"# Kopf\r\n10.1145/3696410.3714748\r\n")
    before = path.read_bytes()

    read_reference_list(path)

    assert path.read_bytes() == before


# --------------------------------------------------------------------------------------
# Dateiname
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("GraphRAG: From Local to Global", "graphrag"),
        ("Llama 2: Open Foundation Models", "llama-2"),
        ("From Local to Global: A Graph RAG Approach", "local-global"),
        ("A Survey of Retrieval Augmented Generation Methods", "survey-retrieval-augmented"),
        ("Über Ähnlichkeit und Größe", "ueber-aehnlichkeit-und"),
        ("!!! ???", ""),
    ],
)
def test_the_title_slug_prefers_the_system_name(title: str, expected: str) -> None:
    """Ein kurzer Vorspann vor dem Doppelpunkt ist fast immer der System-/Modellname."""
    assert title_slug(title) == expected


def test_the_filename_carries_a_speaking_word_and_the_identifier_anchor() -> None:
    """Der Name ist für Menschen lesbar und trägt zugleich die eindeutige Kennung."""
    name = stub_filename(KIND_ARXIV, _ARXIV, _TITLE)

    assert name == f"ref-graphrag-arxiv-{_ARXIV}{STUB_SUFFIX}"


def test_the_filename_works_without_a_title() -> None:
    """Ohne Titel bleibt der Name gültig – nur eben nicht sprechend."""
    assert stub_filename(KIND_DOI, _DOI) == f"ref-doi-10.1145_3696410.3714748{STUB_SUFFIX}"


def test_a_long_identifier_is_shortened_deterministically() -> None:
    """Ein überlanger DOI wird gekürzt und mit einem stabilen Kurz-Hash eindeutig gehalten."""
    long_doi = "10.1234/" + "x" * 200

    first = stub_filename(KIND_DOI, long_doi, _TITLE)
    second = stub_filename(KIND_DOI, long_doi, _TITLE)

    assert first == second
    assert len(first) < 120


@pytest.mark.parametrize(
    "title",
    ["../../etc/passwd", "C:\\Windows\\system32", "a/b/c", "..", "  ..\\..  "],
)
def test_the_filename_can_never_leave_the_inbox(title: str) -> None:
    """Der Slug entsteht über eine Whitelist – ein fremder Titel kann nicht ausbrechen."""
    name = stub_filename(KIND_ARXIV, _ARXIV, title)

    assert "/" not in name
    assert "\\" not in name
    assert ".." not in name.replace(STUB_SUFFIX, "")
    assert Path(name).name == name


# --------------------------------------------------------------------------------------
# Idempotenz gegen die drei Zustände
# --------------------------------------------------------------------------------------


def _write_stub_file(folder: Path, name: str, payload: dict[str, object]) -> Path:
    """Legt eine Stub-Datei direkt ab (ohne Auflösung)."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_existing_stubs_are_recognised_by_content_not_by_name(tmp_path: Path) -> None:
    """Auch eine von Hand umbenannte Stub-Datei wird wiedererkannt."""
    _write_stub_file(tmp_path, "voellig-anderer-name.refjson", {"arxiv_id": _ARXIV, "doi": _DOI})

    found = stub_identifiers(tmp_path)

    assert (KIND_ARXIV, _ARXIV) in found
    assert (KIND_DOI, _DOI.lower()) in found


def test_quarantined_stubs_count_as_known(tmp_path: Path) -> None:
    """Ein in die Quarantäne verschobener Stub darf nicht erneut erzeugt werden."""
    _write_stub_file(tmp_path / QUARANTINE_DIR, f"ref-arxiv-{_ARXIV}.refjson", {"arxiv_id": _ARXIV})

    found = stub_identifiers(tmp_path)

    assert found[(KIND_ARXIV, _ARXIV)].parent.name == QUARANTINE_DIR


def test_a_broken_stub_file_is_skipped_instead_of_stopping_the_run(tmp_path: Path) -> None:
    """Eine defekte Datei darf einen ganzen Lauf nicht blockieren."""
    (tmp_path / "kaputt.refjson").write_text("{kein json", encoding="utf-8")
    (tmp_path / "liste.refjson").write_text("[1, 2]", encoding="utf-8")
    _write_stub_file(tmp_path, "gut.refjson", {"arxiv_id": _ARXIV})

    found = stub_identifiers(tmp_path)

    assert list(found) == [(KIND_ARXIV, _ARXIV)]


def test_the_requested_identifier_of_a_stub_also_counts(tmp_path: Path) -> None:
    """Auch die auslösende Kennung wird geführt – sie kann von den Feldern abweichen."""
    _write_stub_file(tmp_path, "ref.refjson", {"requested": f"arxiv:{_ARXIV}"})

    assert (KIND_ARXIV, _ARXIV) in stub_identifiers(tmp_path)


def test_plan_skips_everything_that_is_already_settled(tmp_path: Path) -> None:
    """Korpus, Eingang, Quarantäne und Dubletten werden **vor** jeder Abfrage aussortiert."""
    corpus = CorpusView(
        sha256_to_name={},
        identifier_to_paper={(KIND_DOI, "10.1111/im-korpus"): "abc123"},
        titles={},
    )
    stubs = {
        (KIND_ARXIV, "1111.11111"): tmp_path / "ref-a.refjson",
        (KIND_ARXIV, "2222.22222"): tmp_path / QUARANTINE_DIR / "ref-b.refjson",
    }
    requests = (
        ReferenceRequest(1, "10.1111/im-korpus", KIND_DOI, "10.1111/im-korpus"),
        ReferenceRequest(2, "1111.11111", KIND_ARXIV, "1111.11111"),
        ReferenceRequest(3, "2222.22222", KIND_ARXIV, "2222.22222"),
        ReferenceRequest(4, "3333.33333", KIND_ARXIV, "3333.33333"),
        ReferenceRequest(5, "3333.33333", KIND_ARXIV, "3333.33333"),
        ReferenceRequest(6, "unsinn", "", ""),
    )

    pending, settled = plan(requests, corpus, stubs)

    assert [request.value for request in pending] == ["3333.33333"]
    assert [(item.action, item.reason) for item in settled] == [
        (ACTION_SKIPPED, REASON_IN_CORPUS),
        (ACTION_SKIPPED, REASON_STUB_EXISTS),
        (ACTION_SKIPPED, REASON_QUARANTINED),
        (ACTION_SKIPPED, REASON_DUPLICATE_LINE),
        (ACTION_INVALID, ""),
    ]


# --------------------------------------------------------------------------------------
# Auflösung
# --------------------------------------------------------------------------------------


def test_a_doi_is_resolved_via_openalex_without_touching_arxiv() -> None:
    """Für einen DOI mit vollständiger Antwort genügt eine einzige Abfrage."""
    client = _FakeClient(openalex=_work())

    found = resolve_reference(client, _request(KIND_DOI, _DOI))

    assert found.title == _TITLE
    assert found.abstract == _ABSTRACT
    assert found.authors == ("Anna Beispiel", "Bert Muster")
    assert found.venue == "Proceedings of ACL"
    assert found.year == 2024
    assert len(client.urls) == 1
    assert "arxiv.org" not in client.urls[0]


def test_the_abstract_index_is_requested_explicitly() -> None:
    """Ohne ``abstract_inverted_index`` liefert OpenAlex keinen Abstract – der Kern der Phase."""
    client = _FakeClient(openalex=_work())

    resolve_reference(client, _request(KIND_DOI, _DOI))

    assert "abstract_inverted_index" in REFERENCE_FIELDS
    assert "abstract" in client.urls[0]


def test_arxiv_is_queried_through_the_datacite_doi() -> None:
    """Die arXiv-Kennung wird über den DataCite-DOI abgefragt – ein Abfrageweg, nicht zwei."""
    client = _FakeClient(openalex=_work())

    resolve_reference(client, _request(KIND_ARXIV, _ARXIV))

    assert f"10.48550%2FarXiv.{_ARXIV}" in client.urls[0].replace("%2E", ".")


def test_the_arxiv_feed_fills_a_missing_abstract() -> None:
    """OpenAlex ohne Abstract plus arXiv-Feed – genau die in R0 gemessene Kombination."""
    client = _FakeClient(openalex=_work(abstract=None), arxiv=_feed())

    found = resolve_reference(client, _request(KIND_ARXIV, _ARXIV))

    assert found.abstract == "Abstract aus arXiv."
    assert found.venue == "Proceedings of ACL"  # übrige Felder bleiben von OpenAlex
    assert len(client.urls) == 2


def test_the_arxiv_feed_carries_the_entry_when_openalex_knows_nothing() -> None:
    """Kennt OpenAlex das Werk nicht, trägt der Feed den Eintrag allein."""
    client = _FakeClient(openalex=None, arxiv=_feed())

    found = resolve_reference(client, _request(KIND_ARXIV, _ARXIV))

    assert found.title == _TITLE
    assert found.arxiv_id == _ARXIV
    assert found.source == "arXiv"


def test_the_feed_also_supplies_the_authors() -> None:
    """Ohne Autoren wäre der Eintrag nicht zitierfähig – gerade dann, wenn nur arXiv trägt."""
    client = _FakeClient(openalex=None, arxiv=_feed())

    found = resolve_reference(client, _request(KIND_ARXIV, _ARXIV))

    assert found.authors == ("Clara Feed", "Dorian Atom")


def test_the_feed_is_queried_by_identifier_not_by_full_text() -> None:
    """Eine Volltextsuche nach der Kennung liefert nachweislich ein **fremdes** Paper."""
    client = _FakeClient(openalex=None, arxiv=_feed())

    resolve_reference(client, _request(KIND_ARXIV, _ARXIV))

    feed_url = next(url for url in client.urls if "arxiv.org" in url)
    assert f"id_list={_ARXIV}" in feed_url
    assert "search_query" not in feed_url


def test_an_old_style_identifier_survives_the_feed_comparison() -> None:
    """``cs/0501001`` verliert im Feed sein Archiv-Präfix – das darf kein Ausschluss sein."""
    client = _FakeClient(openalex=None, arxiv=_feed(arxiv_id="cs/0501001"))

    found = resolve_reference(client, _request(KIND_ARXIV, "cs/0501001"))

    assert found.title == _TITLE
    assert found.arxiv_id == "cs/0501001"


def test_a_feed_answering_with_another_identifier_is_rejected() -> None:
    """Eine Antwort zu einer anderen ID wäre eine falsche Zuordnung."""
    client = _FakeClient(openalex=None, arxiv=_feed(arxiv_id="9999.99999"))

    found = resolve_reference(client, _request(KIND_ARXIV, _ARXIV))

    assert found.title == ""
    assert "andere ID" in found.note


def test_an_empty_openalex_answer_is_reported_not_misread() -> None:
    """HTTP 200 ohne Werk ist kein Treffer – der Grund steht in der Begründung."""
    client = _FakeClient(openalex=b"{}")

    found = resolve_reference(client, _request(KIND_DOI, _DOI))

    assert found.title == ""
    assert "kennt" in found.note


def test_an_unresolvable_identifier_creates_no_file(tmp_path: Path) -> None:
    """Ohne Titel entsteht **keine** Datei – ein solcher Eintrag wäre wertlos."""
    client = _FakeClient(openalex=None, arxiv=None)

    outcome = process(client, _request(KIND_ARXIV, _ARXIV), tmp_path)

    assert outcome.action == ACTION_UNRESOLVED
    assert outcome.path is None
    assert list(tmp_path.glob(f"*{STUB_SUFFIX}")) == []


def test_a_missing_abstract_still_creates_a_file_with_a_hint(tmp_path: Path) -> None:
    """Der manuelle Weg führt über die erzeugte Datei, nicht über ein zweites Eingabeformat."""
    client = _FakeClient(openalex=_work(abstract=None))

    outcome = process(client, _request(KIND_DOI, _DOI), tmp_path)

    assert outcome.action == ACTION_WRITTEN
    assert outcome.has_abstract is False
    assert outcome.path is not None
    payload = json.loads(outcome.path.read_text(encoding="utf-8"))
    assert payload["abstract"] == ""
    assert "nachtragen" in payload["note"]


def test_the_written_stub_carries_every_field_r2_needs(tmp_path: Path) -> None:
    """Die Feldnamen sind deckungsgleich mit ``MetadataRecord`` – R2 bleibt eine Zuweisung."""
    client = _FakeClient(openalex=_work())

    outcome = process(client, _request(KIND_ARXIV, _ARXIV), tmp_path)

    assert outcome.path is not None
    payload = json.loads(outcome.path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == STUB_SCHEMA_VERSION
    assert payload["document_kind"] == DOCUMENT_KIND_REFERENCE
    assert payload["requested"] == f"{KIND_ARXIV}:{_ARXIV}"
    assert payload["title"] == _TITLE
    assert payload["authors"] == ["Anna Beispiel", "Bert Muster"]
    assert payload["year"] == 2024
    assert payload["venue"] == "Proceedings of ACL"
    assert payload["doi"] == _DOI
    assert payload["url"].startswith("https://")
    assert payload["source"] == "OpenAlex"
    assert payload["retrieved_at"].endswith("Z")
    assert list(payload)[-1] == "abstract"


# --------------------------------------------------------------------------------------
# Bereinigung fremder Eingaben
# --------------------------------------------------------------------------------------


def test_foreign_text_is_reduced_to_a_single_printable_line() -> None:
    """Titel und Abstract stammen aus fremder Quelle und werden vor dem Schreiben entschärft."""
    payload = build_stub(
        _request(),
        title="Zeile eins\nZeile\u0000 zwei\tdrei",
        abstract="a" * (MAX_ABSTRACT_CHARS + 500),
        venue="Ort\r\nmit Umbruch",
    )

    assert payload["title"] == "Zeile eins Zeile zwei drei"
    assert payload["venue"] == "Ort mit Umbruch"
    assert len(str(payload["abstract"])) == MAX_ABSTRACT_CHARS


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "file:///c:/secret", "ftp://example.org/x", "x" * 900],
)
def test_only_http_urls_survive(url: str) -> None:
    """Ein Verweis mit fremdem Schema oder Überlänge wird verworfen, nicht übernommen."""
    assert build_stub(_request(), title=_TITLE, url=url)["url"] == ""


def test_the_author_list_is_capped() -> None:
    """Kollaborationslisten sprengen sonst jede Angabe."""
    payload = build_stub(_request(), title=_TITLE, authors=[f"Autor {i}" for i in range(200)])

    assert len(list(payload["authors"])) == 25


def test_writing_is_atomic_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    """Ein Abbruch darf nichts Halbfertiges hinterlassen (Muster aus ADR 0010)."""
    payload = build_stub(_request(), title=_TITLE, abstract=_ABSTRACT)

    path = write_stub(tmp_path, payload, stub_filename(KIND_ARXIV, _ARXIV, _TITLE))

    assert path.is_file()
    assert list(tmp_path.glob("*.tmp")) == []
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert json.loads(path.read_text(encoding="utf-8"))["title"] == _TITLE


def test_a_second_run_neither_queries_nor_writes(tmp_path: Path) -> None:
    """Die Akzeptanz der Phase: ein Wiederholungslauf ist vollständig folgenlos."""
    client = _FakeClient(openalex=_work())
    first = process(client, _request(KIND_ARXIV, _ARXIV), tmp_path)
    queries_after_first = len(client.urls)

    pending, settled = plan(
        (_request(KIND_ARXIV, _ARXIV),), _empty_corpus(), stub_identifiers(tmp_path)
    )

    assert first.action == ACTION_WRITTEN
    assert pending == []
    assert settled[0].reason == REASON_STUB_EXISTS
    assert len(client.urls) == queries_after_first
