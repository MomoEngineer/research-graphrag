"""Tests für den Netzzugang des Online-Modus (Phase 9 / S1).

Geprüft wird alles außer dem tatsächlichen Verbindungsaufbau: URL-Prüfung, Antwort-Zerlegung,
Chunked-Transfer, Challenge-Auswertung, Größengrenze und Konfiguration. Der Socket-Pfad selbst
ist plattform- und netzgebunden und bleibt bewusst ungetestet
(docs/adr/0020-online-candidate-search-phase9.md).
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.online.transport import (
    MAX_RESPONSE_BYTES,
    PROXY_ENV,
    HttpResponse,
    ProxyHttpClient,
    _challenge_of,
    _dechunk,
    _parse_response,
    _read_head,
    _read_limited,
    _split_url,
    create_client,
)


class _FakeSocket:
    """Minimaler Socket-Ersatz, der eine feste Byte-Folge in Stücken ausliefert."""

    def __init__(self, payload: bytes, chunk: int = 8) -> None:
        self._payload = payload
        self._chunk = chunk
        self._position = 0

    def recv(self, size: int) -> bytes:
        end = min(self._position + min(size, self._chunk), len(self._payload))
        data = self._payload[self._position : end]
        self._position = end
        return data


def test_response_text_replaces_undecodable_bytes() -> None:
    """Nicht dekodierbare Bytes ersetzen statt zu scheitern – Fremdantworten sind unzuverlässig."""
    response = HttpResponse(status=200, headers={}, body=b"a\xffb")

    assert response.text.startswith("a")
    assert response.text.endswith("b")


def test_split_url_accepts_https_with_query() -> None:
    """Pfad und Query werden zusammengeführt, der Standard-Port ist 443."""
    host, port, path = _split_url("https://example.org/api?q=1&r=2")

    assert (host, port, path) == ("example.org", 443, "/api?q=1&r=2")


def test_split_url_defaults_to_root_path() -> None:
    """Ohne Pfadangabe wird der Wurzelpfad angefragt."""
    assert _split_url("https://example.org")[2] == "/"


@pytest.mark.parametrize("url", ["http://example.org", "file:///etc/passwd", "ftp://example.org"])
def test_split_url_rejects_other_schemes(url: str) -> None:
    """Nur https ist zulässig – das verhindert Klartext- und Dateizugriffe."""
    with pytest.raises(DomainError) as excinfo:
        _split_url(url)

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_get_rejects_foreign_scheme_before_connecting() -> None:
    """Die Schema-Prüfung greift, bevor irgendeine Verbindung versucht wird."""
    client = ProxyHttpClient()

    with pytest.raises(DomainError) as excinfo:
        client.get("http://example.org/api")

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_parse_response_reads_status_and_headers() -> None:
    """Statuszeile und Kopfzeilen werden kleingeschrieben übernommen."""
    raw = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nX-Test: 1\r\n\r\n{}"

    response = _parse_response(raw)

    assert response.status == 200
    assert response.headers["content-type"] == "application/json"
    assert response.body == b"{}"


def test_parse_response_decodes_chunked_body() -> None:
    """Ein chunked übertragener Rumpf wird zusammengesetzt."""
    raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n4\r\nabcd\r\n2\r\nef\r\n0\r\n\r\n"

    assert _parse_response(raw).body == b"abcdef"


def test_parse_response_rejects_broken_status_line() -> None:
    """Ohne gültige Statuszeile wird der Lauf nicht stillschweigend fortgesetzt."""
    with pytest.raises(DomainError) as excinfo:
        _parse_response(b"NOT-HTTP\r\n\r\n")

    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_dechunk_stops_at_terminator() -> None:
    """Nach dem Null-Chunk wird nichts mehr übernommen."""
    assert _dechunk(b"3\r\nabc\r\n0\r\n\r\nignoriert") == b"abc"


def test_dechunk_rejects_invalid_size() -> None:
    """Eine unlesbare Größenangabe ist ein Parse-Fehler, kein stiller Abbruch."""
    with pytest.raises(DomainError) as excinfo:
        _dechunk(b"zz\r\nabc\r\n")

    assert excinfo.value.code is ErrorCode.PARSE_ERROR


def test_dechunk_returns_what_it_has_on_truncation() -> None:
    """Bricht der Rumpf ab, wird das Gelesene zurückgegeben statt zu scheitern."""
    assert _dechunk(b"3\r\nabc") == b"abc"


def test_read_head_stops_after_the_header_block() -> None:
    """Die Kopfzeilen werden vollständig gelesen, auch wenn sie stückweise eintreffen."""
    sock = cast(Any, _FakeSocket(b"HTTP/1.1 200 OK\r\nX-A: 1\r\n\r\nrumpf", chunk=5))

    head = _read_head(sock)

    assert head.startswith("HTTP/1.1 200 OK")
    assert "X-A: 1" in head
    assert "rumpf" not in head


def test_read_head_consumes_an_announced_error_body() -> None:
    """Der Rumpf einer 407-Antwort wird mitgelesen, damit die Folgeanfrage sauber aufsetzt."""
    payload = b"HTTP/1.1 407 x\r\nContent-Length: 5\r\n\r\nfehler"
    sock = cast(Any, _FakeSocket(payload, chunk=4))

    assert _read_head(sock).startswith("HTTP/1.1 407")


def test_read_head_tolerates_early_close() -> None:
    """Bricht die Gegenstelle ab, wird das Gelesene zurückgegeben."""
    sock = cast(Any, _FakeSocket(b"HTTP/1.1 200 OK\r\n", chunk=4))

    assert _read_head(sock).splitlines()[0] == "HTTP/1.1 200 OK"


def test_challenge_of_reads_negotiate_token() -> None:
    """Das base64-kodierte Token wird aus der Proxy-Antwort gelesen."""
    head = "HTTP/1.1 407 x\r\nProxy-Authenticate: NTLM\r\nProxy-Authenticate: Negotiate dGVzdA=="

    assert _challenge_of(head) == b"test"


def test_challenge_of_returns_none_without_token() -> None:
    """Ein reines ``Negotiate`` ohne Token ist keine Challenge."""
    assert _challenge_of("HTTP/1.1 407 x\r\nProxy-Authenticate: Negotiate") is None


def test_read_limited_collects_until_close() -> None:
    """Gelesen wird bis zum Verbindungsende."""
    sock = cast(Any, _FakeSocket(b"0123456789", chunk=4))

    assert _read_limited(sock) == b"0123456789"


def test_read_limited_rejects_oversized_response() -> None:
    """Eine überlange Fremdantwort wird verworfen statt in den Speicher gelesen."""
    payload = b"x" * (MAX_RESPONSE_BYTES + 10)
    sock = cast(Any, _FakeSocket(payload, chunk=MAX_RESPONSE_BYTES + 10))

    with pytest.raises(DomainError) as excinfo:
        _read_limited(sock)

    assert excinfo.value.code is ErrorCode.CONSTRAINT_VIOLATION


@pytest.mark.parametrize("proxy", ["kein-port", "host:", ":8080", "host:8080/pfad", "host 8080"])
def test_client_rejects_malformed_proxy(proxy: str) -> None:
    """Eine unbrauchbare Proxy-Angabe wird sofort gemeldet, nicht erst beim Verbinden."""
    with pytest.raises(DomainError) as excinfo:
        ProxyHttpClient(proxy)

    assert excinfo.value.code is ErrorCode.INVALID_INPUT


def test_create_client_reads_proxy_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Der Proxy stammt aus der Umgebung – niemals aus dem Repository."""
    monkeypatch.setenv(PROXY_ENV, "proxy.example:8080")

    client = create_client()

    assert isinstance(client, ProxyHttpClient)
    assert client._proxy == "proxy.example:8080"


def test_create_client_without_environment_connects_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ohne Variable wird direkt verbunden; der Proxy ist die Ausnahme, nicht die Regel."""
    monkeypatch.delenv(PROXY_ENV, raising=False)

    assert cast(Any, create_client())._proxy is None


def test_direct_connection_failure_names_the_proxy_variable() -> None:
    """Die Fehlermeldung führt zur Lösung – Akzeptanzbedingung „sauberer Abbruch"."""
    client = ProxyHttpClient(timeout=0.05)

    with pytest.raises(DomainError) as excinfo:
        client.get("https://localhost:9/api")

    assert excinfo.value.code is ErrorCode.DEPENDENCY_ERROR
    assert PROXY_ENV in excinfo.value.message
