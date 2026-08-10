"""Tests für die Proxy-Ermittlung aus der Windows-Systemkonfiguration (ADR 0032).

Geprüft wird alles außer dem ``ctypes``-Aufruf selbst: die Auswahl aus einer Windows-Proxy-Liste,
die Reihenfolge der Auflösungsversuche, der Kurzschluss auf Nicht-Windows-Systemen und das
Verhalten, wenn die Schnittstelle nichts liefert. Der Aufruf von ``winhttp.dll`` ist plattform-
und netzgebunden und bleibt – wie der Socket-Pfad in
docs/adr/0020-online-candidate-search-phase9.md – bewusst ungetestet.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any

import pytest

from research_graphrag.online import systemproxy
from research_graphrag.online.systemproxy import (
    WINHTTP_AUTOPROXY_AUTO_DETECT,
    WINHTTP_AUTOPROXY_CONFIG_URL,
    _attempts,
    _first_endpoint,
    _IeProxyConfig,
    _load_winhttp,
    _read_string,
    detect_system_proxy,
)


class _FakeWinHttp:
    """Ersatz für ``winhttp.dll``, der ohne Zeiger auskommt: Er findet nie einen Endpunkt."""

    def __init__(self, *, session: int) -> None:
        self.session = session
        self.asked = 0
        self.closed = 0

    def WinHttpGetIEProxyConfigForCurrentUser(self, _ref: Any) -> int:  # noqa: N802
        return 0

    def WinHttpOpen(self, *_args: Any) -> int:  # noqa: N802
        return self.session

    def WinHttpGetProxyForUrl(self, *_args: Any) -> int:  # noqa: N802
        self.asked += 1
        return 0

    def WinHttpCloseHandle(self, _session: Any) -> int:  # noqa: N802
        self.closed += 1
        return 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("proxy.example:8080", "proxy.example:8080"),
        ("a.example:8080;b.example:8080", "a.example:8080"),
        ("http://proxy.example:8080", "proxy.example:8080"),
        ("https=proxy.example:3128", "proxy.example:3128"),
        ("DIRECT", None),
        ("PROXY proxy.example:8080", "proxy.example:8080"),
        ("", None),
        (None, None),
        ("   ", None),
    ],
)
def test_first_endpoint_reads_the_windows_list(value: str | None, expected: str | None) -> None:
    """Windows liefert Listen mit Präfixen – gewählt wird der erste brauchbare Endpunkt."""
    assert _first_endpoint(value) == expected


def test_first_endpoint_ignores_entries_without_port() -> None:
    """Ohne Portangabe ist ein Eintrag für den CONNECT-Tunnel unbrauchbar."""
    assert _first_endpoint("proxy.example;proxy.example:8080") == "proxy.example:8080"


def test_attempts_prefers_the_configured_pac_file() -> None:
    """Ist eine PAC-Adresse hinterlegt, wird sie zuerst ausgewertet, WPAD nur als Rückfall."""
    attempts = _attempts("http://pac.example/proxy.pac", auto_detect=True)

    assert [item.dwFlags for item in attempts] == [
        WINHTTP_AUTOPROXY_CONFIG_URL,
        WINHTTP_AUTOPROXY_AUTO_DETECT,
    ]
    assert attempts[0].lpszAutoConfigUrl == "http://pac.example/proxy.pac"


def test_attempts_uses_wpad_without_a_pac_file() -> None:
    """Ohne PAC-Adresse bleibt nur die Suche über DHCP/DNS."""
    attempts = _attempts(None, auto_detect=False)

    assert [item.dwFlags for item in attempts] == [WINHTTP_AUTOPROXY_AUTO_DETECT]
    assert attempts[0].dwAutoDetectFlags != 0


def test_attempts_skips_wpad_when_only_the_pac_file_is_configured() -> None:
    """Ist WPAD abgeschaltet, wird es auch nicht versucht – das spart eine Zeitgrenze."""
    attempts = _attempts("http://pac.example/proxy.pac", auto_detect=False)

    assert [item.dwFlags for item in attempts] == [WINHTTP_AUTOPROXY_CONFIG_URL]


def test_detect_returns_none_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ohne Windows gibt es keine Systemkonfiguration – der Aufrufer verbindet direkt."""
    monkeypatch.setattr(systemproxy.sys, "platform", "linux")

    assert detect_system_proxy("https://api.example/") is None


def test_detect_returns_none_when_the_library_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Eine fehlende oder defekte ``winhttp.dll`` ist kein Fehler, sondern „kein Proxy bekannt"."""

    def _raise() -> Any:
        raise OSError("winhttp.dll nicht ladbar")

    monkeypatch.setattr(systemproxy, "_load_winhttp", _raise)

    assert detect_system_proxy("https://api.example/") is None


def test_detect_returns_none_without_a_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kommt keine Sitzung zustande, wird nicht weiter gefragt."""
    fake = _FakeWinHttp(session=0)
    monkeypatch.setattr(systemproxy, "_load_winhttp", lambda: fake)

    assert detect_system_proxy("https://api.example/") is None
    assert (fake.asked, fake.closed) == (0, 0)


def test_detect_closes_the_session_after_a_fruitless_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auch ohne Fund wird die Sitzung geschlossen – sonst bleibt sie bis Prozessende offen."""
    fake = _FakeWinHttp(session=42)
    monkeypatch.setattr(systemproxy, "_load_winhttp", lambda: fake)

    assert detect_system_proxy("https://api.example/") is None
    assert (fake.asked, fake.closed) == (1, 1)


@pytest.mark.parametrize("pointer", [None, 0])
def test_read_string_without_a_pointer(pointer: int | None) -> None:
    """Ein Nullzeiger bedeutet „nicht gesetzt" und wird nicht dereferenziert."""
    assert _read_string(pointer) is None


@pytest.mark.skipif(sys.platform != "win32", reason="winhttp.dll gibt es nur unter Windows.")
def test_load_winhttp_declares_the_required_signatures() -> None:
    """Die DLL wird geladen und alle vier Aufrufe sind typisiert – ohne jede Netzverbindung."""
    winhttp = _load_winhttp()

    assert winhttp.WinHttpOpen.restype is ctypes.c_void_p
    assert winhttp.WinHttpGetProxyForUrl.argtypes[1] is wintypes.LPCWSTR
    assert winhttp.WinHttpGetIEProxyConfigForCurrentUser.argtypes[0]._type_ is _IeProxyConfig
    assert winhttp.WinHttpCloseHandle.argtypes == (ctypes.c_void_p,)
