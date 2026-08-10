# 0032 – Proxy-Endpunkt aus der Windows-Systemkonfiguration ermitteln (PAC-Auswertung)

- **Status:** Akzeptiert
- **Datum:** 2026-08-10

## Kontext

[ADR 0020](0020-online-candidate-search-phase9.md) hat festgelegt: Der Proxy-Endpunkt kommt
**ausschließlich** aus der Umgebungsvariablen `RESEARCH_GRAPHRAG_PROXY`, ohne sie wird direkt
verbunden. Die Begründung – ein Unternehmens-Hostname gehört nicht ins Repository – gilt
unverändert. Die daraus abgeleitete Annahme, der Endpunkt sei „einmal nachschlagen und
eintragen", gilt nicht.

Ein Lauf von `python -m scripts.resolve_references` scheiterte am 2026-08-10 für **alle zwölf**
Kennungen der Liste mit derselben Meldung:

```
[referenzen] Fehler [dependency_error]: Keine direkte Verbindung zu api.openalex.org:443
([Errno 11001] getaddrinfo failed).
```

Die Messung der Umgebung erklärt es:

| Einstellung | Wert |
| --- | --- |
| `ProxyEnable` | `0` |
| `ProxyServer` | *(leer)* |
| `AutoConfigURL` | `http://pac.…/proxy.pac` |
| `HTTPS_PROXY` / `HTTP_PROXY` | *(leer)* |

Es gibt **kein statisches Proxy-Feld**, das man nachschlagen könnte. Der Endpunkt steht in einer
**PAC-Datei**, wird also erst zur Laufzeit aus einer JavaScript-Funktion `FindProxyForURL`
berechnet – hostabhängig und ohne Zusage, morgen derselbe zu sein. Die Modul-Doku zu
`transport.py` hielt genau das als Grenze fest: „keine PAC-Auswertung (ohne JavaScript-Engine
nicht möglich)".

Damit trifft die Fehlermeldung zwar zu, ihr Lösungsvorschlag aber ins Leere: Wer keinen
Endpunkt kennt, kann keinen eintragen. Der Online-Modus ist in der Zielumgebung **ohne
Handarbeit an einer nicht dokumentierten Stelle unbenutzbar** – und die von Hand eingetragene
Adresse veraltet still, sobald die PAC-Datei sich ändert.

## Entscheidung

### 1. Der Endpunkt wird zweistufig bestimmt

1. **Ausdrückliche Angabe** – `--proxy` bzw. `RESEARCH_GRAPHRAG_PROXY`. Unverändert Vorrang,
   unverändert die einzige Stelle, an der ein Hostname von Hand gesetzt wird.
2. **Windows-Systemkonfiguration** – nur wenn Stufe 1 leer ist.

Bleiben beide ergebnislos, wird wie bisher direkt verbunden. Der bisherige Vertrag wird also
**erweitert, nicht ersetzt**: Wer die Variable setzt, merkt keinen Unterschied.

### 2. Die PAC-Datei wertet Windows aus, nicht wir

Neues Modul `online/systemproxy.py`. Es ruft über `ctypes` drei Funktionen aus `winhttp.dll` auf:

| Aufruf | Zweck |
| --- | --- |
| `WinHttpGetIEProxyConfigForCurrentUser` | statischer Proxy, `AutoConfigURL`, WPAD-Kennzeichen |
| `WinHttpOpen` | Sitzung, die **nur** der Auflösung dient |
| `WinHttpGetProxyForUrl` | lädt die PAC-Datei, führt `FindProxyForURL` aus, liefert den Endpunkt |

Das löst die in ADR 0020 notierte Grenze auf, **ohne** eine JavaScript-Engine ins Projekt zu
holen: Windows hat die Engine bereits, samt Zwischenspeicher für die PAC-Datei. Gemessen liefert
der Aufruf in der Zielumgebung `…:8080;…:8080`; genutzt wird der erste Eintrag der Form
`host:port`.

Es entsteht **keine neue Abhängigkeit** – `ctypes` ist Standardbibliothek.

### 3. Eine gescheiterte Ermittlung ist kein Fehler

`detect_system_proxy` gibt **nie** eine Ausnahme nach außen und liefert `None`, wenn kein
Endpunkt feststellbar ist: auf Nicht-Windows-Systemen, ohne `winhttp.dll`, bei `DIRECT`, bei
jedem unerwarteten Rückgabewert. „Kein Proxy bekannt" ist eine gültige Aussage, kein Abbruch –
sonst würde ein Werkzeug, das an anderen Standorten direkt verbindet, an der Ermittlung
scheitern.

Aus demselben Grund wird der ermittelte Wert in `transport.py` gegen dieselbe `host:port`-Prüfung
geführt wie eine Angabe von Hand. Er stammt aus einer Fremdquelle und wird nicht ungeprüft in
einen `CONNECT`-Aufruf gegeben.

### 4. Ermittelt wird je Zielhost, gemerkt wird pro Client

PAC-Dateien entscheiden hostabhängig; ein einmalig für ein beliebiges Ziel ermittelter Endpunkt
wäre eine stille Falschannahme. `ProxyHttpClient` fragt deshalb **je Zielhost** und behält das
Ergebnis für die Lebensdauer des Clients – ein Lauf über 12 Kennungen kostet so zwei
Auflösungen (OpenAlex, arXiv) statt zweier Dutzend.

### 5. Die Fehlermeldung sagt, was schon versucht wurde

Scheitert die Direktverbindung, obwohl die Systemkonfiguration befragt wurde, nennt die Meldung
beides. Andernfalls stünde dort weiterhin ein Rat, der bereits befolgt wurde.

## Alternativen

- **PAC-Datei selbst auswerten.** Verlangt eine JavaScript-Engine (`dukpy`, `pypac`,
  `js2py`); offline nicht beschaffbar ([ADR 0002](0002-venv-and-offline-dependency-strategy.md))
  und eine Neuimplementierung der PAC-Hilfsfunktionen wäre eine eigene Fehlerquelle.
- **Nur `HTTPS_PROXY`/`HTTP_PROXY` zusätzlich lesen.** Löst den gemessenen Fall nicht – beide
  sind leer, weil die Umgebung ausschließlich über PAC konfiguriert ist.
- **Nur die Registry lesen** (`ProxyServer`). Ebenfalls leer; deckt genau den Fall nicht ab, der
  hier auftritt.
- **Endpunkt von Hand eintragen lassen** (Status quo). Verlagert eine automatisierbare
  Ermittlung auf den Nutzer, veraltet still bei jeder PAC-Änderung und war der Auslöser dieses
  ADR.
- **`urllib.request.getproxies()`.** Liest unter Windows nur die statischen Registry-Felder und
  ignoriert `AutoConfigURL` – dieselbe Lücke.

## Konsequenzen

- **Positiv:** `python -m scripts.resolve_references`, `resolve_metadata` und `discover` laufen in
  der Zielumgebung ohne Vorbereitung. Ein Wechsel der PAC-Datei wird automatisch nachvollzogen.
  Keine neue Abhängigkeit, kein Hostname im Repository.
- **Negativ / Aufwand:** Der `ctypes`-Aufruf ist plattform- und netzgebunden und damit offline
  nicht testbar – dieselbe, in [ADR 0020](0020-online-candidate-search-phase9.md) begründete
  Unterschreitung des Coverage-Richtwerts wie beim Socket-Pfad. Getestet sind die Auswahl aus der
  Windows-Proxy-Liste, die Reihenfolge der Auflösungsversuche, der Kurzschluss auf
  Nicht-Windows-Systemen und die Einbindung in `ProxyHttpClient`.
- **Sicherheit:** Die Ermittlung liefert nur einen Endpunkt; TLS-Verifikation über certifi,
  Schema-Beschränkung auf `https` und alle Größen- und Weiterleitungsgrenzen aus ADR 0020 bleiben
  unangetastet. Der Endpunkt wird vor der Verwendung gegen `host:port` geprüft.
- **Folgeentscheidungen:** Ergänzt ADR 0020, Punkt 2. Der dortige Satz „Ohne die Variable wird
  direkt verbunden" gilt fortan als „Ohne die Variable **und** ohne ermittelbaren Systemproxy".
