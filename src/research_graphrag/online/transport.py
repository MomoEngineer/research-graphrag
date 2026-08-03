"""Netzzugang des Online-Modus: injizierbarer Port und Proxy-Transport.

Definiert den Port :class:`HttpClient` (genau eine Methode) samt der einzigen Implementierung
:class:`ProxyHttpClient`. Alle übrigen Module des Pakets arbeiten ausschließlich gegen diesen
Port und sind dadurch **netzfrei testbar** – dasselbe Muster, mit dem
docs/adr/0004-llm-bridge-via-mcp-sampling.md den Modellzugriff gekapselt hat.

Zwei gemessene Eigenheiten der Zielumgebung bestimmen den Aufbau
(docs/adr/0020-online-candidate-search-phase9.md):

* Der Weg nach außen führt über einen Proxy, der ``CONNECT`` mit **HTTP 407** und
  ``Proxy-Authenticate: Negotiate`` beantwortet. Der Tunnel wird deshalb selbst aufgebaut und
  über SSPI aus dem bestehenden Windows-Anmeldekontext authentifiziert – **ohne** Zugangsdaten
  im Code.
* Die Verifikation nutzt das **certifi**-Bundle, weil im Windows-Zertifikatsspeicher die
  Wurzel der ausstellenden CA von arXiv fehlt. Abgeschaltet wird die Verifikation nie.

Der Proxy-Endpunkt stammt ausschließlich aus :data:`PROXY_ENV`; ohne diese Variable wird direkt
verbunden.
"""

from __future__ import annotations

import os
import re
import socket
import ssl
from base64 import b64decode, b64encode
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import certifi

from ..errors import DomainError, ErrorCode

PROXY_ENV = "RESEARCH_GRAPHRAG_PROXY"
"""Umgebungsvariable mit dem Proxy-Endpunkt (``host:port``).

Ein Unternehmens-Hostname ist ein Firmeninternum und gehört nicht in ein Repository.
"""

USER_AGENT = "research-graphrag/0.1 (persoenlicher Forschungsassistent; Einzelabfragen)"
"""Identifizierender User-Agent – gute Praxis gegenüber den abgefragten Diensten."""

DEFAULT_TIMEOUT = 30.0
"""Zeitgrenze je Verbindung und Lesevorgang in Sekunden."""

MAX_RESPONSE_BYTES = 5_000_000
"""Obergrenze der gelesenen Antwort; schützt vor unbegrenzten Fremdantworten."""

MAX_AUTH_ROUNDS = 5
"""Obergrenze der Negotiate-Runden (der Handshake gelingt real in einer)."""

_PROXY_PATTERN = re.compile(r"^[A-Za-z0-9._-]+:\d{1,5}$")
_ALLOWED_SCHEME = "https"


@dataclass(frozen=True)
class HttpResponse:
    """Antwort einer Einzelabfrage.

    Attributes:
        status: HTTP-Statuscode.
        headers: Kopfzeilen mit kleingeschriebenen Schlüsseln.
        body: Unveränderter Rumpf (bereits entchunkt).
    """

    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        """Rumpf als Text; nicht dekodierbare Bytes werden ersetzt statt zu scheitern."""
        return self.body.decode("utf-8", errors="replace")


class HttpClient(Protocol):
    """Injizierbarer Port für lesende Einzelabfragen (ADR 0020, Punkt 1)."""

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        """Führt genau eine GET-Anfrage aus."""
        ...


class _NegotiateAuth:
    """Kapselt den SSPI-Handshake gegen den Proxy (Windows-Anmeldekontext, kein Passwort)."""

    def __init__(self, proxy_host: str) -> None:
        try:
            import sspi  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - plattformabhängig
            raise DomainError(
                ErrorCode.DEPENDENCY_ERROR,
                "Die Proxy-Authentifizierung benötigt pywin32 (nur unter Windows verfügbar). "
                f"Ohne Proxy: {PROXY_ENV} nicht setzen.",
            ) from exc
        self._auth: Any = sspi.ClientAuth("Negotiate", targetspn=f"HTTP/{proxy_host}")

    def step(self, challenge: bytes | None) -> bytes:
        """Erzeugt das nächste Negotiate-Token zur (optionalen) Challenge des Proxys."""
        _, buffers = self._auth.authorize(challenge)
        token: bytes = bytes(buffers[0].Buffer)
        return token


class ProxyHttpClient:
    """Einzige Implementierung des Ports: direkt oder über einen authentifizierenden Proxy."""

    def __init__(self, proxy: str | None = None, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Erzeugt den Client.

        Args:
            proxy: Endpunkt als ``host:port`` oder ``None`` für eine direkte Verbindung.
            timeout: Zeitgrenze je Verbindung und Lesevorgang in Sekunden.

        Raises:
            DomainError: ``invalid_input`` wenn ``proxy`` nicht der Form ``host:port`` entspricht.
        """
        if proxy is not None and not _PROXY_PATTERN.match(proxy):
            raise DomainError(
                ErrorCode.INVALID_INPUT,
                f"Proxy-Angabe muss die Form 'host:port' haben, erhalten: {proxy!r}",
            )
        self._proxy = proxy
        self._timeout = timeout
        self._context = ssl.create_default_context(cafile=certifi.where())

    def get(self, url: str, *, accept: str = "*/*") -> HttpResponse:
        """Führt genau eine GET-Anfrage aus.

        Weiterleitungen wird **nicht** gefolgt; ein 3xx-Status wird unverändert zurückgegeben,
        damit kein fremdbestimmtes Ziel angesteuert wird.

        Args:
            url: Vollständige ``https``-URL.
            accept: Wert der ``Accept``-Kopfzeile.

        Returns:
            Die gelesene Antwort.

        Raises:
            DomainError: ``invalid_input`` bei fremdem Schema, ``dependency_error`` wenn keine
                Verbindung zustande kommt, ``constraint_violation`` bei zu großer Antwort,
                ``parse_error`` bei unlesbarer Antwort.
        """
        host, port, path = _split_url(url)
        sock = self._connect(host, port)
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {USER_AGENT}\r\n"
            f"Accept: {accept}\r\n"
            "Accept-Encoding: identity\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode()
        try:
            with self._context.wrap_socket(sock, server_hostname=host) as tls:
                tls.settimeout(self._timeout)
                tls.sendall(request)
                raw = _read_limited(tls)
        except OSError as exc:
            sock.close()
            raise DomainError(
                ErrorCode.DEPENDENCY_ERROR,
                f"Anfrage an {host} fehlgeschlagen: {exc}",
            ) from exc
        return _parse_response(raw)

    def _connect(self, host: str, port: int) -> socket.socket:
        """Öffnet die Verbindung – direkt oder als authentifizierter Tunnel."""
        if self._proxy is None:
            return self._connect_direct(host, port)
        return self._connect_tunnel(host, port)

    def _connect_direct(self, host: str, port: int) -> socket.socket:
        try:
            sock = socket.create_connection((host, port), timeout=self._timeout)
        except OSError as exc:
            raise DomainError(
                ErrorCode.DEPENDENCY_ERROR,
                f"Keine direkte Verbindung zu {host}:{port} ({exc}). "
                f"Falls ein Proxy nötig ist, {PROXY_ENV}=host:port setzen.",
            ) from exc
        sock.settimeout(self._timeout)
        return sock

    def _connect_tunnel(self, host: str, port: int) -> socket.socket:
        proxy = self._proxy or ""
        proxy_host, _, proxy_port = proxy.partition(":")
        auth = _NegotiateAuth(proxy_host)
        try:
            sock = socket.create_connection((proxy_host, int(proxy_port)), timeout=self._timeout)
        except OSError as exc:
            raise DomainError(
                ErrorCode.DEPENDENCY_ERROR,
                f"Proxy {proxy} nicht erreichbar ({exc}).",
            ) from exc
        sock.settimeout(self._timeout)
        challenge: bytes | None = None
        for _ in range(MAX_AUTH_ROUNDS):
            token = b64encode(auth.step(challenge)).decode("ascii")
            try:
                sock.sendall(
                    (
                        f"CONNECT {host}:{port} HTTP/1.1\r\n"
                        f"Host: {host}:{port}\r\n"
                        f"User-Agent: {USER_AGENT}\r\n"
                        "Proxy-Connection: Keep-Alive\r\n"
                        f"Proxy-Authorization: Negotiate {token}\r\n"
                        "\r\n"
                    ).encode()
                )
                head = _read_head(sock)
            except OSError as exc:
                sock.close()
                raise DomainError(
                    ErrorCode.DEPENDENCY_ERROR,
                    f"Proxy-Handshake abgebrochen: {exc}",
                ) from exc
            status_line = head.splitlines()[0] if head else ""
            if status_line.split()[1:2] == ["200"]:
                return sock
            challenge = _challenge_of(head)
            if challenge is None:
                sock.close()
                raise DomainError(
                    ErrorCode.DEPENDENCY_ERROR,
                    f"Proxy lehnt die Verbindung ab: {status_line or '<keine Antwort>'}",
                )
        sock.close()
        raise DomainError(
            ErrorCode.DEPENDENCY_ERROR,
            f"Proxy-Authentifizierung nach {MAX_AUTH_ROUNDS} Runden nicht abgeschlossen.",
        )


def create_client(*, proxy: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> HttpClient:
    """Erzeugt den Standard-Client; der Proxy stammt aus :data:`PROXY_ENV`, wenn nicht gesetzt.

    Args:
        proxy: Ausdrücklicher Endpunkt ``host:port``; ``None`` liest :data:`PROXY_ENV`.
        timeout: Zeitgrenze je Verbindung und Lesevorgang in Sekunden.

    Returns:
        Ein einsatzbereiter :class:`HttpClient`.
    """
    resolved = proxy if proxy is not None else (os.environ.get(PROXY_ENV) or None)
    return ProxyHttpClient(resolved, timeout=timeout)


def _split_url(url: str) -> tuple[str, int, str]:
    """Zerlegt die URL und lässt ausschließlich ``https`` zu."""
    parts = urlsplit(url)
    if parts.scheme != _ALLOWED_SCHEME or not parts.hostname:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            f"Nur {_ALLOWED_SCHEME}-URLs sind zulässig, erhalten: {url!r}",
        )
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return parts.hostname, parts.port or 443, path


def _read_head(sock: socket.socket) -> str:
    """Liest Statuszeile, Kopfzeilen und einen etwaigen Fehlerrumpf des Proxys."""
    buffer = b""
    while b"\r\n\r\n" not in buffer and len(buffer) < MAX_RESPONSE_BYTES:
        data = sock.recv(4096)
        if not data:
            break
        buffer += data
    head, _, rest = buffer.partition(b"\r\n\r\n")
    text = head.decode("latin-1")
    length = 0
    for line in text.splitlines()[1:]:
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip() or 0)
    body = rest
    while len(body) < length:
        data = sock.recv(4096)
        if not data:
            break
        body += data
    return text


def _challenge_of(head: str) -> bytes | None:
    """Zieht das Negotiate-Token aus ``Proxy-Authenticate``; ``None`` wenn keines angeboten wird."""
    for line in head.splitlines():
        if not line.lower().startswith("proxy-authenticate:"):
            continue
        value = line.split(":", 1)[1].strip()
        if value.lower().startswith("negotiate") and len(value) > len("negotiate"):
            return b64decode(value[len("negotiate") :].strip())
    return None


def _read_limited(sock: ssl.SSLSocket) -> bytes:
    """Liest bis zum Verbindungsende, aber höchstens :data:`MAX_RESPONSE_BYTES`."""
    chunks: list[bytes] = []
    total = 0
    while True:
        data = sock.recv(32768)
        if not data:
            break
        total += len(data)
        if total > MAX_RESPONSE_BYTES:
            raise DomainError(
                ErrorCode.CONSTRAINT_VIOLATION,
                f"Antwort überschreitet {MAX_RESPONSE_BYTES} Bytes und wird verworfen.",
            )
        chunks.append(data)
    return b"".join(chunks)


def _parse_response(raw: bytes) -> HttpResponse:
    """Zerlegt die Rohantwort in Status, Kopfzeilen und Rumpf."""
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").splitlines()
    fields = lines[0].split() if lines else []
    if len(fields) < 2 or not fields[1].isdigit():
        raise DomainError(ErrorCode.PARSE_ERROR, "Antwort ohne gültige HTTP-Statuszeile.")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip().lower()] = value.strip()
    if headers.get("transfer-encoding", "").lower() == "chunked":
        body = _dechunk(body)
    return HttpResponse(status=int(fields[1]), headers=headers, body=body)


def _dechunk(body: bytes) -> bytes:
    """Setzt einen ``chunked`` übertragenen Rumpf zusammen."""
    out = b""
    rest = body
    while True:
        line, sep, rest = rest.partition(b"\r\n")
        if not sep:
            return out
        try:
            size = int(line.split(b";")[0], 16)
        except ValueError as exc:
            raise DomainError(ErrorCode.PARSE_ERROR, "Chunked-Antwort nicht lesbar.") from exc
        if size == 0:
            return out
        out += rest[:size]
        rest = rest[size + 2 :]
