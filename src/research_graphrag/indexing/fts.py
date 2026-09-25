"""Gemeinsame FTS5-Bausteine: Verfügbarkeit, Entschärfung, Fehlerübersetzung (Phase 17 / A3).

FTS5 ist im ``sqlite3`` der Offline-Umgebung enthalten (Roadmap Phase 16: SQLite 3.38.4 mit
``ENABLE_FTS5``, Tokenizer ``trigram`` verfügbar). Zwei Stellen nutzen es: die kleine
Namenstabelle des Autorenindex (Phase 17 / A3) und die Phrasen-, Präfix- und Nähe-Suche über
``chunks`` (Phase 16 / F2, :mod:`research_graphrag.indexing.chunk_fts`). Dieses Modul ist die
**eine** Stelle für die Regeln, die beide teilen (docs/adr/0043-author-index-and-person-tools.md,
docs/adr/0044-response-latency-bit-identical-scoring-and-fts5-phase16.md):

* **FTS5-Anfragen sind Nutzereingaben.** Jedes Token wird als String-Literal gesetzt, innere
  Anführungszeichen werden verdoppelt. Operatoren (``AND``/``OR``/``NOT``/``NEAR``), Präfix-``*``,
  Spaltenfilter ``:`` und Klammern verlieren so ihre Bedeutung.
* **Eine missglückte Anfrage endet als ``invalid_input``**, nie als ``sqlite3.OperationalError``
  an der MCP-Grenze.
* **Verfügbarkeit wird geprüft, nicht vorausgesetzt.** Fehlt FTS5 oder der Tokenizer, nutzt der
  Aufrufer seinen dokumentierten Rückfallweg.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode

TRIGRAM_MIN_CHARS = 3
"""Kürzere Suchwörter findet der Tokenizer ``trigram`` nicht (er liefert dann still nichts)."""

_TOKENIZER = re.compile(r"^[a-z0-9_ ]{1,64}$")


def tokenizer_available(connection: sqlite3.Connection, tokenizer: str = "unicode61") -> bool:
    """Prüft, ob FTS5 mit dem gegebenen Tokenizer angelegt werden kann.

    Die Probe legt eine **temporäre** Tabelle an und entfernt sie sofort; die Index-Datei bleibt
    unberührt.

    Raises:
        DomainError: ``invalid_input`` bei einem Tokenizer-Namen außerhalb der Whitelist (der Name
            wird in SQL eingesetzt, weil SQLite ihn nicht als Parameter annimmt).
    """
    if not _TOKENIZER.match(tokenizer):
        raise DomainError(ErrorCode.INVALID_INPUT, f"Unzulässiger Tokenizer {tokenizer!r}.")
    try:
        connection.execute(
            f"CREATE VIRTUAL TABLE temp.fts5_probe USING fts5(x, tokenize='{tokenizer}')"
        )
        connection.execute("DROP TABLE temp.fts5_probe")
    except sqlite3.Error:
        return False
    return True


def quote_tokens(tokens: Sequence[str]) -> str:
    """Setzt Tokens als FTS5-String-Literale, verbunden durch Leerzeichen (implizites UND).

    Raises:
        DomainError: ``invalid_input``, wenn kein Token übrig bleibt.
    """
    cleaned = [token for token in tokens if token.strip()]
    if not cleaned:
        raise DomainError(ErrorCode.INVALID_INPUT, "Leere Suchanfrage.")
    return " ".join('"' + token.replace('"', '""') + '"' for token in cleaned)


def quote_phrase(text: str) -> str:
    """Setzt einen Text als **eine** FTS5-Phrase: ein String-Literal, innere ``"`` verdoppelt.

    FTS5 zerlegt das Literal mit dem Tokenizer der Tabelle in eine Wortfolge; Operatoren,
    Präfix-``*``, Spaltenfilter und Klammern im Text sind darin wirkungslos (Phase 16 / F2).

    Raises:
        DomainError: ``invalid_input`` bei leerem Text.
    """
    if not text.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "Leere Suchanfrage.")
    return '"' + text.replace('"', '""') + '"'


def quote_prefix(text: str) -> str:
    """Phrase, deren **letztes** Wort als Präfix gilt (FTS5-Syntax ``"…" *``).

    Raises:
        DomainError: ``invalid_input`` bei leerem Text.
    """
    return quote_phrase(text) + " *"


def quote_near(terms: Sequence[str], distance: int) -> str:
    """``NEAR``-Gruppe: alle Begriffe höchstens ``distance`` Wörter auseinander.

    Jeder Begriff wird als eigene Phrase gesetzt; ``distance`` ist eine geprüfte Ganzzahl und
    stammt nie als Text aus der Eingabe.

    Raises:
        DomainError: ``invalid_input`` bei weniger als zwei Begriffen oder negativem Abstand.
    """
    cleaned = [term for term in terms if term.strip()]
    if len(cleaned) < 2:
        raise DomainError(ErrorCode.INVALID_INPUT, "NEAR braucht mindestens zwei Begriffe.")
    if distance < 0:
        raise DomainError(ErrorCode.INVALID_INPUT, "Der Abstand muss >= 0 sein.")
    return "NEAR(" + " ".join(quote_phrase(term) for term in cleaned) + f", {int(distance)})"


def safe_match(connection: sqlite3.Connection, sql: str, params: Sequence[Any]) -> list[Any]:
    """Führt eine ``MATCH``-Abfrage aus und übersetzt FTS5-Syntaxfehler in ``invalid_input``.

    Args:
        connection: Offene Verbindung.
        sql: Die Abfrage (mit ``?``-Platzhaltern).
        params: Die Parameter; der ``MATCH``-Ausdruck stammt aus :func:`quote_tokens`.

    Returns:
        Alle Zeilen.

    Raises:
        DomainError: ``invalid_input`` bei einem Fehler im ``MATCH``-Ausdruck.
    """
    try:
        return connection.execute(sql, tuple(params)).fetchall()
    except sqlite3.OperationalError as exc:
        raise DomainError(ErrorCode.INVALID_INPUT, f"Ungültige Suchanfrage: {exc}") from exc
