"""Geteilte Obergrenze für Trefferzahl-Parameter der Retrieval- und MCP-Werkzeuge (ADR 0037).

Cross-cutting genutzt von ``indexing`` und ``retrieval`` (analog zu :mod:`research_graphrag.errors`
und :mod:`research_graphrag.keywords`). Ohne Obergrenze wächst eine Tool-Antwort mit einem
Trefferzahl-Parameter (``k``/``n``/``fan_out``/``communities``/``seeds``/``limit``) unbegrenzt –
gemessen am realen Korpus reicht das bis zur 1-MB-Transportgrenze des MCP-Servers
(docs/adr/0037-mcp-tool-response-size-ceiling.md). :data:`MAX_RESULT_COUNT` ist die **einzige**
Quelle dieser Grenze; :func:`check_max_count` lehnt eine Überschreitung mit ``invalid_input`` ab –
derselben Kategorie, mit der die bestehenden Untergrenzen (``k <= 0`` usw.) bereits abgelehnt
werden.
"""

from __future__ import annotations

from research_graphrag.errors import DomainError, ErrorCode

MAX_RESULT_COUNT = 50
"""Maximal erlaubter Wert für jeden Trefferzahl-Parameter (``k``, ``n``, ``fan_out``,
``communities``, ``seeds``, ``limit``) der Retrieval- und MCP-Werkzeuge.

Jede gemessene Kombination bleibt bei diesem Wert weit unter 150 KB serialisierter Antwortgröße
(siehe ADR 0037) – reichlich Marge unter der 1-MB-Transportgrenze, auch bei mehreren gleichzeitig
ausgeschöpften Parametern (z. B. ``search_local`` mit ``k=50`` **und** ``fan_out=50``)."""


def check_max_count(name: str, value: int, maximum: int = MAX_RESULT_COUNT) -> None:
    """Lehnt einen zu großen Trefferzahl-Parameter ab (``invalid_input``, ADR 0037).

    Args:
        name: Parametername für die Fehlermeldung (z. B. ``"k"``, ``"fan_out"``).
        value: Der angefragte Wert.
        maximum: Die erlaubte Obergrenze; Default :data:`MAX_RESULT_COUNT`.

    Raises:
        DomainError: ``invalid_input``, wenn ``value > maximum``.
    """
    if value > maximum:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            f"{name} darf höchstens {maximum} sein (angefragt: {value}).",
        )
