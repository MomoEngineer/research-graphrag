"""Gemeinsame FTS5-Bausteine: Verfügbarkeit, Entschärfung, Fehlerübersetzung (Phase 17 / A3).

FTS5 ist im ``sqlite3`` der Offline-Umgebung enthalten (Roadmap Phase 16: SQLite 3.38.4 mit
``ENABLE_FTS5``, Tokenizer ``trigram`` verfügbar). Zwei Stellen nutzen es: die kleine
Namenstabelle des Autorenindex (Phase 17 / A3) und künftig die Phrasensuche über ``chunks``
(Phase 16 / F2). Dieses Modul ist die **eine** Stelle für die Regeln, die beide teilen
(docs/adr/0043-author-index-and-person-tools.md):

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
