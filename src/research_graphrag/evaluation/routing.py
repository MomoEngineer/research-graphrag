"""Messung des Query-Routers gegen den dokumentierten Fragetyp→Modus-Contract (Phase 7 / A7).

**Labels ohne Urteil:** Die zulässigen Modi einer Frage werden nicht kuratiert, sondern aus
ihrem Fragetyp über die Tabelle „Fragetypen → Suchmodus" der README abgeleitet
(:data:`CONTRACT_MODES`). Damit ist jedes Label mechanisch nachrechenbar – das Pendant zur
Label-Regel des Retrieval-Gold-Sets
(docs/adr/0016-quantitative-retrieval-evaluation-phase7.md).

Bewusst getrennt bleibt diese Messung vom Retrieval-Gold-Set: Sie misst, ob der Router den
**Contract** trifft, nicht ob eine Antwort besser wird. Eine Optimierung auf Hit@k/MRR hätte ein
triviales Optimum („immer basic") und ist deshalb ausgeschlossen
(docs/adr/0017-router-hardening-phase7.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from research_graphrag.retrieval.router import SIGNALS, matched_signals, route

CONTRACT_MODES: dict[str, tuple[str, ...]] = {
    "detail": ("local", "basic"),
    "synthesis": ("global",),
    "network": ("local",),
    "fact": ("basic",),
    "contrast": ("drift",),
}
"""Fragetyp → zulässige Modi, abgeleitet aus der README-Tabelle „Fragetypen → Suchmodus".

``detail`` trägt zwei zulässige Modi, weil die README für Detailfragen ausdrücklich
„Local + Basic" nennt; alle übrigen Typen sind eindeutig.
"""


@dataclass(frozen=True)
class RouterQuestion:
    """Eine Router-Gold-Frage samt Fragetyp und eingefrorener Modus-Menge."""

    qid: str
    query: str
    kind: str
    language: str
    expected_modes: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class RouterGoldSet:
    """Versioniertes Router-Gold-Set (die Datei ist die Single Source of Truth)."""

    version: str
    questions: tuple[RouterQuestion, ...]


@dataclass(frozen=True)
class RouterScore:
    """Bewertung einer Router-Gold-Frage."""

    qid: str
    kind: str
    expected_modes: tuple[str, ...]
    actual_mode: str
    confidence: str
    signals: tuple[str, ...]

    @property
    def hit(self) -> bool:
        """``True``, wenn der geroutete Modus im Contract der Frage liegt."""
        return self.actual_mode in self.expected_modes


@dataclass(frozen=True)
class RouterReport:
    """Aggregierte Kennzahlen eines Router-Laufs."""

    version: str
    scores: tuple[RouterScore, ...]

    @property
    def accuracy(self) -> float:
        """Anteil der Fragen, deren Modus im Contract liegt."""
        if not self.scores:
            return 0.0
        return sum(1.0 for score in self.scores if score.hit) / len(self.scores)

    @property
    def misses(self) -> tuple[RouterScore, ...]:
        """Alle Fragen, deren Modus außerhalb des Contracts liegt."""
        return tuple(score for score in self.scores if not score.hit)

    def by_kind(self) -> dict[str, tuple[float, int]]:
        """Kennzahlen je Fragetyp: ``kind -> (Trefferquote, Anzahl)``."""
        kinds: dict[str, list[RouterScore]] = {}
        for score in self.scores:
            kinds.setdefault(score.kind, []).append(score)
        return {
            kind: (sum(1.0 for score in group if score.hit) / len(group), len(group))
            for kind, group in sorted(kinds.items())
        }

    def by_confidence(self) -> dict[str, tuple[float, int]]:
        """Kennzahlen je Konfidenzstufe: ``confidence -> (Trefferquote, Anzahl)``."""
        levels: dict[str, list[RouterScore]] = {}
        for score in self.scores:
            levels.setdefault(score.confidence, []).append(score)
        return {
            level: (sum(1.0 for score in group if score.hit) / len(group), len(group))
            for level, group in sorted(levels.items())
        }

    def confusion(self) -> dict[tuple[str, str], int]:
        """Verwechslungen: ``(Fragetyp, gerouteter Modus) -> Anzahl`` (nur Fehlgriffe)."""
        counts: dict[tuple[str, str], int] = {}
        for score in self.misses:
            key = (score.kind, score.actual_mode)
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))


def load_router_gold(path: str | Path) -> RouterGoldSet:
    """Lädt das Router-Gold-Set aus JSON.

    Args:
        path: Pfad zur Gold-Set-Datei.

    Returns:
        Das geladene :class:`RouterGoldSet` in Dateireihenfolge.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    questions = tuple(
        RouterQuestion(
            qid=str(entry["qid"]),
            query=str(entry["query"]),
            kind=str(entry["kind"]),
            language=str(entry["language"]),
            expected_modes=tuple(str(mode) for mode in entry["expected_modes"]),
            note=str(entry.get("note", "")),
        )
        for entry in payload["questions"]
    )
    return RouterGoldSet(version=str(payload["router_gold_version"]), questions=questions)


def verify_router_labels(gold: RouterGoldSet) -> tuple[str, ...]:
    """Prüft die eingefrorenen Modus-Mengen gegen den dokumentierten Contract.

    Args:
        gold: Das geladene Router-Gold-Set.

    Returns:
        Meldungen zu abweichenden Fragen; leer, wenn jede Modus-Menge exakt der Abbildung
        ihres Fragetyps entspricht.
    """
    findings: list[str] = []
    for question in gold.questions:
        expected = CONTRACT_MODES.get(question.kind)
        if expected is None:
            findings.append(f"{question.qid}: unbekannter Fragetyp {question.kind!r}")
        elif question.expected_modes != expected:
            findings.append(
                f"{question.qid}: eingefroren {question.expected_modes}, "
                f"Contract für {question.kind!r} = {expected}"
            )
    return tuple(findings)


def evaluate_router(gold: RouterGoldSet) -> RouterReport:
    """Routet jede Gold-Frage und bewertet sie gegen ihre zulässigen Modi.

    Args:
        gold: Das geladene Router-Gold-Set.

    Returns:
        Der aggregierte :class:`RouterReport` in Dateireihenfolge.
    """
    scores = tuple(
        RouterScore(
            qid=question.qid,
            kind=question.kind,
            expected_modes=question.expected_modes,
            actual_mode=(decision := route(question.query)).mode,
            confidence=decision.confidence,
            signals=decision.signals,
        )
        for question in gold.questions
    )
    return RouterReport(version=gold.version, scores=scores)


def signal_coverage(gold: RouterGoldSet) -> tuple[str, ...]:
    """Ermittelt Signale, die von keiner Gold-Frage berührt werden.

    Ein ungeprüftes Signal ist eine unbelegte Regel – die Vorabmessung fand 9 von 51 Signalen
    überhaupt getroffen (docs/adr/0017-router-hardening-phase7.md).

    Args:
        gold: Das geladene Router-Gold-Set.

    Returns:
        Die Texte der nicht abgedeckten Signale in Lexikon-Reihenfolge.
    """
    touched: set[str] = set()
    for question in gold.questions:
        for texts in matched_signals(question.query).values():
            touched.update(texts)
    return tuple(signal.text for signal in SIGNALS if signal.text not in touched)
