"""Proxy-Endpunkt aus der Windows-Systemkonfiguration ermitteln (Phase 9 / S1, Nachtrag).

Die Zielumgebung konfiguriert den Weg nach außen **nicht** über ein statisches Proxy-Feld,
sondern über eine **PAC-Datei** (``AutoConfigURL``). Deren ``FindProxyForURL`` ist JavaScript und
damit aus Python heraus nicht auswertbar – Windows kann es aber: ``WinHttpGetProxyForUrl`` lädt
die PAC-Datei, führt sie aus und gibt den zuständigen Endpunkt zurück
(docs/adr/0032-system-proxy-autodetection.md).

Dieses Modul kapselt genau diesen Aufruf über :mod:`ctypes`. Es ist **plattformabhängig, aber
nicht plattformzwingend**: Ohne ``winhttp.dll`` liefert :func:`detect_system_proxy` schlicht
``None`` und der Aufrufer verbindet direkt. Nach außen wird **nie** eine Ausnahme gegeben – eine
gescheiterte Ermittlung ist kein Fehler, sondern die Aussage „kein Proxy bekannt".

Vorrang hat immer die ausdrückliche Konfiguration: ``RESEARCH_GRAPHRAG_PROXY`` bzw. ``--proxy``
liest :mod:`~.transport` zuerst; dieses Modul greift nur, wenn dort nichts steht.
"""

from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes
from typing import Any

WINHTTP_ACCESS_TYPE_NO_PROXY = 1
"""Die Sitzung dient nur der Auflösung, nicht dem Transport – sie braucht selbst keinen Proxy."""

WINHTTP_AUTOPROXY_AUTO_DETECT = 0x00000001
"""WPAD: Endpunkt über DHCP/DNS suchen (greift, wenn keine PAC-Adresse hinterlegt ist)."""

WINHTTP_AUTOPROXY_CONFIG_URL = 0x00000002
"""PAC-Datei unter der hinterlegten ``AutoConfigURL`` auswerten."""

WINHTTP_AUTO_DETECT_TYPE_DHCP = 0x00000001
"""WPAD-Suche über die DHCP-Option 252."""

WINHTTP_AUTO_DETECT_TYPE_DNS_A = 0x00000002
"""WPAD-Suche über den DNS-Namen ``wpad``."""

_AGENT = "research-graphrag"
_ENDPOINT_PATTERN = re.compile(r"^(?:[A-Za-z]+(?:=|://))?(?P<endpoint>[A-Za-z0-9._-]+:\d{1,5})$")
_SEPARATOR_PATTERN = re.compile(r"[;,\s]+")


class _AutoProxyOptions(ctypes.Structure):
    """``WINHTTP_AUTOPROXY_OPTIONS`` – wie aufgelöst werden soll."""

    _fields_ = (
        ("dwFlags", wintypes.DWORD),
        ("dwAutoDetectFlags", wintypes.DWORD),
        ("lpszAutoConfigUrl", wintypes.LPCWSTR),
        ("lpvReserved", ctypes.c_void_p),
        ("dwReserved", wintypes.DWORD),
        ("fAutoLogonIfChallenged", wintypes.BOOL),
    )


class _ProxyInfo(ctypes.Structure):
    """``WINHTTP_PROXY_INFO`` – das Ergebnis der Auflösung.

    Die Zeichenketten sind bewusst als ``c_void_p`` deklariert: Nur so bleibt der von Windows
    belegte Zeiger erhalten und lässt sich mit ``GlobalFree`` wieder freigeben.
    """

    _fields_ = (
        ("dwAccessType", wintypes.DWORD),
        ("lpszProxy", ctypes.c_void_p),
        ("lpszProxyBypass", ctypes.c_void_p),
    )


class _IeProxyConfig(ctypes.Structure):
    """``WINHTTP_CURRENT_USER_IE_PROXY_CONFIG`` – die hinterlegte Benutzerkonfiguration."""

    _fields_ = (
        ("fAutoDetect", wintypes.BOOL),
        ("lpszAutoConfigUrl", ctypes.c_void_p),
        ("lpszProxy", ctypes.c_void_p),
        ("lpszProxyBypass", ctypes.c_void_p),
    )


def detect_system_proxy(url: str) -> str | None:
    """Ermittelt den für ``url`` zuständigen Proxy aus der Windows-Konfiguration.

    Geprüft wird in der Reihenfolge, die Windows selbst verwendet: zuerst ein statisch
    hinterlegter Proxy, dann die PAC-Datei aus ``AutoConfigURL``, zuletzt WPAD über DHCP/DNS.

    Args:
        url: Ziel-URL, für die der Endpunkt gelten soll. PAC-Dateien entscheiden hostabhängig,
            deshalb ist die Angabe nicht optional.

    Returns:
        Der Endpunkt als ``host:port`` – oder ``None``, wenn keiner ermittelt werden kann; das
        gilt auch auf Nicht-Windows-Systemen und bei jedem Fehler der Windows-Schnittstelle.
    """
    if sys.platform != "win32":
        return None
    try:
        return _detect(url)
    except OSError:  # pragma: no cover - nur bei fehlender oder defekter winhttp.dll
        return None


def _detect(url: str) -> str | None:
    """Führt die Auflösung durch; Rückgabe wie in :func:`detect_system_proxy`."""
    winhttp = _load_winhttp()
    static_proxy, auto_config_url, auto_detect = _read_user_config(winhttp)
    if static_proxy is not None:
        return static_proxy

    session = winhttp.WinHttpOpen(_AGENT, WINHTTP_ACCESS_TYPE_NO_PROXY, None, None, 0)
    if not session:
        return None
    try:
        for options in _attempts(auto_config_url, auto_detect):
            endpoint = _ask_winhttp(winhttp, session, url, options)
            if endpoint is not None:
                return endpoint
    finally:
        winhttp.WinHttpCloseHandle(session)
    return None


def _read_user_config(winhttp: Any) -> tuple[str | None, str | None, bool]:
    """Liest die Benutzerkonfiguration: statischer Proxy, PAC-Adresse, WPAD-Kennzeichen."""
    config = _IeProxyConfig()
    if not winhttp.WinHttpGetIEProxyConfigForCurrentUser(ctypes.byref(config)):
        return None, None, True
    try:
        return (
            _first_endpoint(_read_string(config.lpszProxy)),
            _read_string(config.lpszAutoConfigUrl),
            bool(config.fAutoDetect),
        )
    finally:
        _free(config.lpszAutoConfigUrl, config.lpszProxy, config.lpszProxyBypass)


def _ask_winhttp(winhttp: Any, session: int, url: str, options: _AutoProxyOptions) -> str | None:
    """Stellt einen Auflösungsversuch; ``None`` heißt „dieser Weg führt nicht zum Ziel"."""
    info = _ProxyInfo()
    if not winhttp.WinHttpGetProxyForUrl(session, url, ctypes.byref(options), ctypes.byref(info)):
        return None
    try:
        return _first_endpoint(_read_string(info.lpszProxy))
    finally:
        _free(info.lpszProxy, info.lpszProxyBypass)


def _load_winhttp() -> Any:
    """Bindet ``winhttp.dll`` mit den vier benötigten Signaturen ein."""
    winhttp = ctypes.WinDLL("winhttp", use_last_error=True)
    winhttp.WinHttpOpen.restype = ctypes.c_void_p
    winhttp.WinHttpOpen.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
    )
    winhttp.WinHttpCloseHandle.restype = wintypes.BOOL
    winhttp.WinHttpCloseHandle.argtypes = (ctypes.c_void_p,)
    winhttp.WinHttpGetProxyForUrl.restype = wintypes.BOOL
    winhttp.WinHttpGetProxyForUrl.argtypes = (
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(_AutoProxyOptions),
        ctypes.POINTER(_ProxyInfo),
    )
    winhttp.WinHttpGetIEProxyConfigForCurrentUser.restype = wintypes.BOOL
    winhttp.WinHttpGetIEProxyConfigForCurrentUser.argtypes = (ctypes.POINTER(_IeProxyConfig),)
    return winhttp


def _attempts(auto_config_url: str | None, auto_detect: bool) -> list[_AutoProxyOptions]:
    """Baut die Auflösungsversuche: erst die hinterlegte PAC-Datei, dann WPAD."""
    attempts: list[_AutoProxyOptions] = []
    if auto_config_url:
        by_url = _AutoProxyOptions()
        by_url.dwFlags = WINHTTP_AUTOPROXY_CONFIG_URL
        by_url.lpszAutoConfigUrl = auto_config_url
        by_url.fAutoLogonIfChallenged = True
        attempts.append(by_url)
    if auto_detect or not auto_config_url:
        by_wpad = _AutoProxyOptions()
        by_wpad.dwFlags = WINHTTP_AUTOPROXY_AUTO_DETECT
        by_wpad.dwAutoDetectFlags = WINHTTP_AUTO_DETECT_TYPE_DHCP | WINHTTP_AUTO_DETECT_TYPE_DNS_A
        by_wpad.fAutoLogonIfChallenged = True
        attempts.append(by_wpad)
    return attempts


def _first_endpoint(value: str | None) -> str | None:
    """Liest den ersten brauchbaren ``host:port``-Eintrag aus einer Windows-Proxy-Liste.

    Windows liefert mehrere Endpunkte durch ``;`` getrennt und erlaubt Präfixe wie ``http://``
    oder ``https=``. Genommen wird der erste Eintrag in der geforderten Form; einen Rückfall auf
    die weiteren Einträge gibt es bewusst nicht.

    Args:
        value: Rohwert der Windows-Schnittstelle, etwa ``"a.example:8080;b.example:8080"``.

    Returns:
        Der erste passende Endpunkt oder ``None`` – auch bei ``DIRECT`` und bei leerem Wert.
    """
    if not value:
        return None
    for entry in _SEPARATOR_PATTERN.split(value.strip()):
        match = _ENDPOINT_PATTERN.match(entry)
        if match:
            return match.group("endpoint")
    return None


def _read_string(pointer: int | None) -> str | None:
    """Liest eine von Windows belegte Zeichenkette, ohne den Zeiger zu verlieren."""
    if not pointer:
        return None
    text: str = ctypes.wstring_at(pointer)
    return text


def _free(*pointers: int | None) -> None:
    """Gibt die von Windows belegten Zeichenketten frei – die Schnittstelle verlangt es."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for pointer in pointers:
        if pointer:
            kernel32.GlobalFree(ctypes.c_void_p(pointer))
