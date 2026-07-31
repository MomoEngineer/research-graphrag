"""Query-Router: Fragetyp → Suchmodus (Offline-Hybrid, Option B, Phase 4).

Ein bewusst **schlanker, DB-freier** Heuristik-Klassifikator, der eine Anfrage anhand
deutscher/englischer Schlüsselwörter einem Suchmodus zuordnet (Präzedenz
``drift > global > local > basic``; Default ``basic`` als präzisester Modus). Er dient dem
CLI-Komfort (``--mode auto``); die explizite Modus-Wahl bleibt gleichwertig. Ab Phase 5
übernimmt Copilot selbst die Modus-/Werkzeugwahl. Grundsatz:
docs/adr/0008-retrieval-and-query-router-phase4.md.
"""

from __future__ import annotations

from dataclasses import dataclass

MODES = ("basic", "local", "global", "drift")
"""Gültige Suchmodi (auch die argparse-Auswahl der CLI, plus ``auto``)."""


@dataclass(frozen=True)
class RouteDecision:
    """Ergebnis der Heuristik: gewählter Modus plus kurze, transparente Begründung."""

    mode: str
    rationale: str


# Schlüsselwort-Regeln in Präzedenz-Reihenfolge. Substring-Matches (klein geschrieben)
# fangen deutsche Komposita/Beugungen mit ab (z. B. "widerspr" → "Widerspruch"/"widersprechen").
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "drift",
        (
            "widerspr",
            "gegensätz",
            "gegensatz",
            "vergleich",
            "unterschied",
            "versus",
            " vs ",
            "contradict",
            "compare",
            "comparison",
            "differ",
            "disagree",
        ),
    ),
    (
        "global",
        (
            "forschungsrichtung",
            "themen",
            "überblick",
            "landschaft",
            "insgesamt",
            "korpus",
            "corpus",
            "trend",
            "übergreifend",
            "research direction",
            "overall",
            "across papers",
            "themes",
            "landscape",
            "big picture",
        ),
    ),
    (
        "local",
        (
            "bauen auf",
            "baut auf",
            "aufbauen",
            "builds on",
            "build on",
            "zitier",
            "zitat",
            "cite",
            "citation",
            "verwandte arbeiten",
            "related work",
            "methodennetz",
            "welche paper",
            "which papers",
        ),
    ),
    (
        "basic",
        (
            "doi",
            "f1",
            "score",
            "metrik",
            "metric",
            "accuracy",
            "exakt",
            "exact",
            "abkürzung",
            "abbreviation",
        ),
    ),
)


def route(query: str) -> RouteDecision:
    """Ordnet eine Anfrage heuristisch einem Suchmodus zu.

    Args:
        query: Natürlichsprachige Anfrage.

    Returns:
        Eine :class:`RouteDecision` mit Modus und Begründung. Ohne erkanntes Signal wird
        ``basic`` gewählt (präziseste, belegstärkste Antwort).
    """
    text = f" {query.lower().strip()} "
    for mode, hints in _RULES:
        for hint in hints:
            if hint in text:
                rationale = f"Schlüsselwort '{hint.strip()}' → {mode}"
                return RouteDecision(mode=mode, rationale=rationale)
    return RouteDecision(mode="basic", rationale="Standard: keine Modus-Signale erkannt → basic")
