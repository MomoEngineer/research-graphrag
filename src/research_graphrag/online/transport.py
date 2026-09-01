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

Der Endpunkt wird in zwei Stufen bestimmt: zuerst die ausdrückliche Angabe (``--proxy`` bzw.
:data:`PROXY_ENV`), danach die **Windows-Systemkonfiguration** über
:func:`~.systemproxy.detect_system_proxy` – sie wertet auch eine PAC-Datei aus. Erst wenn beides
nichts liefert, wird direkt verbunden (docs/adr/0032-system-proxy-autodetection.md).
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
from .systemproxy import detect_system_proxy

PROXY_ENV = "RESEARCH_GRAPHRAG_PROXY"
"""Umgebungsvariable mit dem Proxy-Endpunkt (``host:port``).

Ein Unternehmens-Hostname ist ein Firmeninternum und gehört nicht in ein Repository. Die Variable
ist der **Vorrang**-Weg; ohne sie wird die Windows-Systemkonfiguration befragt.
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

    def get(
        self, url: str, *, accept: str = "*/*", max_bytes: int = MAX_RESPONSE_BYTES
    ) -> HttpResponse:
        """Führt genau eine GET-Anfrage aus.

        Args:
            url: Vollständige ``https``-URL.
            accept: Wert der ``Accept``-Kopfzeile.
            max_bytes: Obergrenze der gelesenen Antwort; der Default passt für Metadaten-Anfragen
                (JSON/Atom), der Volltext-Download (ADR 0035) ruft mit einer größeren Grenze auf.
        """
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

    def __init__(
        self,
        proxy: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        auto_proxy: bool = False,
    ) -> None:
        """Erzeugt den Client.

        Args:
            proxy: Endpunkt als ``host:port``; ``None`` überlässt die Wahl ``auto_proxy``.
            timeout: Zeitgrenze je Verbindung und Lesevorgang in Sekunden.
            auto_proxy: Ermittelt den Endpunkt ohne ``proxy`` je Zielhost aus der
                Windows-Systemkonfiguration. Ohne Fund wird direkt verbunden.

        Raises:
            DomainError: ``invalid_input`` wenn ``proxy`` nicht der Form ``host:port`` entspricht.
        """
        if proxy is not None and not _PROXY_PATTERN.match(proxy):
            raise DomainError(
                ErrorCode.INVALID_INPUT,
                f"Proxy-Angabe muss die Form 'host:port' haben, erhalten: {proxy!r}",
            )
        self._proxy = proxy
        self._auto_proxy = auto_proxy
        self._detected: dict[str, str | None] = {}
        self._timeout = timeout
        self._context = ssl.create_default_context(cafile=certifi.where())

    def get(
        self, url: str, *, accept: str = "*/*", max_bytes: int = MAX_RESPONSE_BYTES
    ) -> HttpResponse:
        """Führt genau eine GET-Anfrage aus.

        Weiterleitungen wird **nicht** gefolgt; ein 3xx-Status wird unverändert zurückgegeben,
        damit kein fremdbestimmtes Ziel angesteuert wird.

        Args:
            url: Vollständige ``https``-URL.
            accept: Wert der ``Accept``-Kopfzeile.
            max_bytes: Obergrenze der gelesenen Antwort (siehe :class:`HttpClient`).

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
                raw = _read_limited(tls, max_bytes=max_bytes)
        except OSError as exc:
            sock.close()
            raise DomainError(
                ErrorCode.DEPENDENCY_ERROR,
                f"Anfrage an {host} fehlgeschlagen: {exc}",
            ) from exc
        return _parse_response(raw)

    def _connect(self, host: str, port: int) -> socket.socket:
        """Öffnet die Verbindung – direkt oder als authentifizierter Tunnel."""
        proxy = self._proxy_for(host)
        if proxy is None:
            return self._connect_direct(host, port)
        return self._connect_tunnel(proxy, host, port)

    def _proxy_for(self, host: str) -> str | None:
        """Bestimmt den Endpunkt für einen Zielhost; das Ergebnis wird je Host gemerkt.

        Die ausdrückliche Angabe gilt unverändert für jedes Ziel. Nur ohne sie und nur bei
        ``auto_proxy`` wird Windows befragt – eine PAC-Datei entscheidet hostabhängig, deshalb
        wird je Host einmal ermittelt und das Ergebnis für weitere Anfragen behalten.
        """
        if self._proxy is not None or not self._auto_proxy:
            return self._proxy
        if host not in self._detected:
            self._detected[host] = _validated(detect_system_proxy(f"https://{host}/"))
        return self._detected[host]

    def _connect_direct(self, host: str, port: int) -> socket.socket:
        try:
            sock = socket.create_connection((host, port), timeout=self._timeout)
        except OSError as exc:
            searched = (
                "; die Windows-Proxy-Konfiguration nennt für dieses Ziel keinen Endpunkt"
                if self._auto_proxy
                else ""
            )
            raise DomainError(
                ErrorCode.DEPENDENCY_ERROR,
                f"Keine direkte Verbindung zu {host}:{port} ({exc}){searched}. "
                f"Falls ein Proxy nötig ist, {PROXY_ENV}=host:port setzen.",
            ) from exc
        sock.settimeout(self._timeout)
        return sock

    def _connect_tunnel(self, proxy: str, host: str, port: int) -> socket.socket:
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
    """Erzeugt den Standard-Client mit der zweistufigen Endpunkt-Wahl.

    Stufe 1 ist die ausdrückliche Angabe – ``proxy`` oder :data:`PROXY_ENV`. Fehlt sie, ermittelt
    der Client den Endpunkt bei Bedarf aus der Windows-Systemkonfiguration (Stufe 2, schließt die
    Auswertung einer PAC-Datei ein). Bleibt auch das ergebnislos, wird direkt verbunden.

    Args:
        proxy: Ausdrücklicher Endpunkt ``host:port``; ``None`` liest :data:`PROXY_ENV`.
        timeout: Zeitgrenze je Verbindung und Lesevorgang in Sekunden.

    Returns:
        Ein einsatzbereiter :class:`HttpClient`.
    """
    resolved = proxy if proxy is not None else (os.environ.get(PROXY_ENV) or None)
    return ProxyHttpClient(resolved, timeout=timeout, auto_proxy=resolved is None)


def _validated(proxy: str | None) -> str | None:
    """Lässt nur einen Endpunkt der Form ``host:port`` durch; alles andere heißt „kein Proxy".

    Der Wert stammt aus der Windows-Schnittstelle und damit nicht aus der eigenen Konfiguration;
    ein unerwarteter Wert darf deshalb nicht zum Abbruch führen, sondern nur zur Direktverbindung.
    """
    if proxy is None or not _PROXY_PATTERN.match(proxy):
        return None
    return proxy


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


def _read_limited(sock: ssl.SSLSocket, *, max_bytes: int = MAX_RESPONSE_BYTES) -> bytes:
    """Liest bis zum Verbindungsende, aber höchstens ``max_bytes``."""
    chunks: list[bytes] = []
    total = 0
    while True:
        data = sock.recv(32768)
        if not data:
            break
        total += len(data)
        if total > max_bytes:
            raise DomainError(
                ErrorCode.CONSTRAINT_VIOLATION,
                f"Antwort überschreitet {max_bytes} Bytes und wird verworfen.",
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
