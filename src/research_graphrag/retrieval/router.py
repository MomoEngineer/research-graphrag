"""Query-Router: Fragetyp → Suchmodus (Offline-Hybrid, Option B; gehärtet in Phase 7 / A7).

Ein bewusst **schlanker, DB-freier** Heuristik-Klassifikator. Er ordnet eine Anfrage anhand
deklarierter deutscher/englischer Signale einem Suchmodus zu und macht dabei **sichtbar**, worauf
die Entscheidung beruht: gewählter Modus, Konfidenzstufe, auslösende Signale und eine
Begründung im Klartext.

Drei Festlegungen prägen das Modul (Grundsatz und Messbelege:
docs/adr/0017-router-hardening-phase7.md):

1. **Die Match-Art ist je Signal deklariert.** Englische Signale greifen an Wortgrenzen
   (``word``) oder wortanfangs-verankert samt Beugung (``prefix``); die Teilwort-Semantik
   (``stem``) bleibt deutschen Wortstämmen vorbehalten, für die sie gemessen ohne Fehlalarm ist
   und für Komposita/Beugung gebraucht wird.
2. **Nur strukturelle Modi sind Kandidaten.** ``basic`` ist der Default und braucht kein Signal;
   seine Signale sind ausschließlich **bestätigend** und verschieben keine Entscheidung.
3. **Unsicherheit fällt zurück, statt still zu entscheiden.** Bei Gleichstand gewinnt kein
   Kandidat, sondern der Fallback ``basic`` – die Konkurrenten stehen in der Begründung. Damit
   ist die feste Präzedenz aus docs/adr/0008-retrieval-and-query-router-phase4.md abgelöst.

Der Router dient dem CLI-Komfort (``--mode auto``) und dem Tool ``answer_question``; die
explizite Modus-Wahl bleibt gleichwertig.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

MODES = ("basic", "local", "global", "drift")
"""Gültige Suchmodi (auch die argparse-Auswahl der CLI, plus ``auto``)."""

DEFAULT_MODE = "basic"
"""Rückfallebene ohne bzw. bei mehrdeutigem Signal (belegstärkster Modus)."""

STRUCTURAL_MODES = ("drift", "global", "local")
"""Modi, die eine **Frageform** beschreiben und daher als Kandidaten antreten."""

CONFIDENCE_STRONG = "strong"
"""Genau ein Kandidat bzw. ein eindeutiger Sieger nach Signalzahl."""

CONFIDENCE_WEAK = "weak"
"""Gleichstand mehrerer Kandidaten – die Entscheidung fällt auf den Fallback."""

CONFIDENCE_NONE = "none"
"""Kein strukturelles Signal – der Default greift."""

CONFIDENCES = (CONFIDENCE_STRONG, CONFIDENCE_WEAK, CONFIDENCE_NONE)
"""Alle Konfidenzstufen (bewusst benannte Stufen statt Pseudo-Wahrscheinlichkeiten)."""

MatchKind = Literal["word", "prefix", "stem"]
"""Deklarierte Match-Arten: ganzes Wort · Wortanfang mit Beugung · Teilwort."""


@dataclass(frozen=True)
class Signal:
    """Ein Router-Signal: Text, Zielmodus und die Art, wie es getroffen wird."""

    text: str
    mode: str
    match: MatchKind = "word"


SIGNALS: tuple[Signal, ...] = (
    # --- Widersprüche / Vergleiche → DRIFT -------------------------------------------------
    Signal("widerspr", "drift", "stem"),
    Signal("gegensatz", "drift", "stem"),
    Signal("gegensätz", "drift", "stem"),
    Signal("vergleich", "drift", "stem"),
    Signal("contradict", "drift", "prefix"),
    Signal("disagree", "drift", "prefix"),
    Signal("versus", "drift"),
    Signal("vs", "drift"),
    # "differ"/"unterschied" tragen das Signal nur in diesen Formen; "different",
    # "differentiation" und "unterschiedlich" sind gemessene Fehlalarm-Quellen und bleiben
    # bewusst draußen. Aus demselben Grund steht "compare" als Wortliste statt als Wortanfang
    # ("comparable"/"comparative" beschreiben keine Vergleichsfrage).
    Signal("differ", "drift"),
    Signal("differs", "drift"),
    Signal("difference", "drift"),
    Signal("differences", "drift"),
    Signal("compare", "drift"),
    Signal("compares", "drift"),
    Signal("compared", "drift"),
    Signal("comparison", "drift"),
    Signal("comparisons", "drift"),
    Signal("unterschied", "drift"),
    Signal("unterschiede", "drift"),
    Signal("unterschieden", "drift"),
    # --- Cross-Paper-Synthese / Themen → GLOBAL --------------------------------------------
    Signal("forschungsrichtung", "global", "stem"),
    Signal("themen", "global", "stem"),
    Signal("überblick", "global", "stem"),
    Signal("landschaft", "global", "stem"),
    Signal("insgesamt", "global", "stem"),
    Signal("übergreifend", "global", "stem"),
    Signal("korpusweit", "global", "stem"),
    Signal("research direction", "global", "prefix"),
    Signal("thematic cluster", "global", "prefix"),
    # "corpus"/"korpus" allein bezeichnen einen Gegenstand; nur die Reichweiten-Formulierung
    # markiert eine corpusweite Frage.
    Signal("across the corpus", "global"),
    Signal("across papers", "global"),
    Signal("corpus-wide", "global"),
    Signal("im korpus", "global"),
    Signal("über den korpus", "global"),
    Signal("themes", "global"),
    Signal("landscape", "global"),
    Signal("big picture", "global"),
    Signal("overall", "global"),
    # Der Singular "trend" bezeichnet einen Gegenstand, der Plural die Übersichtsfrage.
    Signal("trends", "global"),
    # --- Zitations-/Methodennetze → LOCAL ---------------------------------------------------
    Signal("zitier", "local", "stem"),
    Signal("zitat", "local", "stem"),
    Signal("methodennetz", "local", "stem"),
    Signal("folgearbeit", "local", "stem"),
    Signal("cite", "local", "prefix"),
    Signal("citation", "local", "prefix"),
    Signal("build on", "local"),
    Signal("builds on", "local"),
    Signal("built on", "local"),
    Signal("build upon", "local"),
    Signal("related work", "local"),
    Signal("relate to", "local"),
    Signal("relates to", "local"),
    Signal("related to", "local"),
    Signal("bauen auf", "local"),
    Signal("baut auf", "local"),
    Signal("aufbauen", "local"),
    Signal("verwandte arbeiten", "local"),
    Signal("verwandt mit", "local"),
    # --- Exakte Fakten → BASIC (bestätigend, nicht entscheidend) ----------------------------
    Signal("abkürzung", "basic", "stem"),
    Signal("exakt", "basic", "stem"),
    # "metrik" steckt im Zeitschriftennamen "Biometrika" und ist daher – anders als die übrigen
    # deutschen Stämme – als Wortform geführt (QA-Befund A7).
    Signal("metrik", "basic"),
    Signal("metriken", "basic"),
    Signal("score", "basic", "prefix"),
    Signal("metric", "basic", "prefix"),
    Signal("doi", "basic"),
    Signal("f1", "basic"),
    Signal("exact", "basic"),
    Signal("accuracy", "basic"),
    Signal("abbreviation", "basic"),
)
"""Signal-Lexikon in Auswertungsreihenfolge (Single Source of Truth des Routers)."""


def _compile(signal: Signal) -> re.Pattern[str]:
    """Übersetzt die deklarierte Match-Art in ein reguläres Suchmuster."""
    escaped = re.escape(signal.text)
    if signal.match == "word":
        return re.compile(rf"\b{escaped}\b")
    if signal.match == "prefix":
        return re.compile(rf"\b{escaped}\w*")
    return re.compile(escaped)


_PATTERNS: tuple[tuple[Signal, re.Pattern[str]], ...] = tuple(
    (signal, _compile(signal)) for signal in SIGNALS
)


@dataclass(frozen=True)
class RouteDecision:
    """Ergebnis der Heuristik: Modus, Konfidenzstufe, Signale und Begründung."""

    mode: str
    rationale: str
    confidence: str = CONFIDENCE_NONE
    signals: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Entscheidung (Feldnamen = Ausgabeschema von ``answer_question``)."""
        return {
            "mode": self.mode,
            "confidence": self.confidence,
            "signals": list(self.signals),
            "rationale": self.rationale,
        }


def matched_signals(query: str) -> dict[str, tuple[str, ...]]:
    """Ermittelt je Modus die Signale, die in der Anfrage vorkommen.

    Args:
        query: Natürlichsprachige Anfrage.

    Returns:
        Abbildung ``Modus -> Signale`` in Lexikon-Reihenfolge; Modi ohne Treffer fehlen.
    """
    text = query.lower().strip()
    found: dict[str, list[str]] = {}
    for signal, pattern in _PATTERNS:
        if pattern.search(text):
            found.setdefault(signal.mode, []).append(signal.text)
    return {mode: tuple(texts) for mode, texts in found.items()}


def _quote(texts: tuple[str, ...]) -> str:
    """Formatiert Signale für die Begründung."""
    return ", ".join(f"'{text}'" for text in texts)


def route(query: str) -> RouteDecision:
    """Ordnet eine Anfrage heuristisch einem Suchmodus zu – nachvollziehbar begründet.

    Kandidaten sind ausschließlich die strukturellen Modi (``drift``/``global``/``local``); der
    Kandidat mit den meisten Signalen gewinnt. Bei Gleichstand oder ohne Kandidat greift der
    Fallback ``basic``. Signale des Modus ``basic`` bestätigen diese Rückfallebene, verschieben
    aber keine Entscheidung.

    Args:
        query: Natürlichsprachige Anfrage.

    Returns:
        Eine :class:`RouteDecision` mit Modus, Konfidenzstufe, auslösenden Signalen und
        Begründung.
    """
    found = matched_signals(query)
    confirming = found.get(DEFAULT_MODE, ())
    candidates = {mode: found[mode] for mode in STRUCTURAL_MODES if mode in found}

    if not candidates:
        if confirming:
            rationale = f"Kein Modus-Signal; Fakt-Signal {_quote(confirming)} bestätigt basic"
        else:
            rationale = "Kein Modus-Signal erkannt → Standard basic"
        return RouteDecision(
            mode=DEFAULT_MODE,
            rationale=rationale,
            confidence=CONFIDENCE_NONE,
            signals=confirming,
        )

    best = max(len(texts) for texts in candidates.values())
    leaders = [mode for mode in STRUCTURAL_MODES if len(candidates.get(mode, ())) == best]

    if len(leaders) > 1:
        tie = " und ".join(f"{mode} ({_quote(candidates[mode])})" for mode in leaders)
        return RouteDecision(
            mode=DEFAULT_MODE,
            rationale=f"Gleichstand zwischen {tie} → Fallback basic",
            confidence=CONFIDENCE_WEAK,
            signals=confirming,
        )

    winner = leaders[0]
    beaten = [mode for mode in STRUCTURAL_MODES if mode in candidates and mode != winner]
    rationale = f"Signal {_quote(candidates[winner])} → {winner}"
    if beaten:
        suffix = ", ".join(f"{mode} ({_quote(candidates[mode])})" for mode in beaten)
        rationale = f"{rationale}; schwächer: {suffix}"
    return RouteDecision(
        mode=winner,
        rationale=rationale,
        confidence=CONFIDENCE_STRONG,
        signals=candidates[winner],
    )
