"""Kennzahlen der Retrieval-Evaluation – bewusst **retrieval-frei** (Phase 7 / A6).

Dieses Modul kennt weder Index noch Suchmodi, sondern nur Ränge: Für jede Frage wird der
**erste relevante Rang** festgehalten; Treffer, Kehrwert und alle Aggregate leiten sich daraus
ab. Damit gibt es genau eine Quelle der Wahrheit – dieselbe, die auch in der Baseline
eingefroren wird (docs/adr/0016-quantitative-retrieval-evaluation-phase7.md).

Neben Hit@k und MRR@k trägt der Bericht zwei Diagnosen, die in der Vorabmessung den
eigentlichen Erkenntnisgewinn ausmachten:

* ``diagnosis`` je Frage – **welcher Baustein** eines Modus den Treffer beisteuerte bzw. woran
  er scheiterte (trennt Auswahl- von Rankingfehlern),
* :class:`CoverageStats` – Coverage **immer zusammen mit** der Selektivität. Erst ihr Quotient
  (der *Lift*) macht die Community-Auswahl mit trivialen Strategien vergleichbar.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field


def first_hit(
    entries: Sequence[tuple[str, str]], expected: Collection[str]
) -> tuple[int | None, str | None]:
    """Sucht den ersten relevanten Eintrag in einem Evidenz-Bündel.

    Args:
        entries: Paare ``(paper_id, Baustein)`` in der Reihenfolge, in der der Modus seine
            Belege präsentiert (z. B. Seed → Nachbarschaft → Fan-out).
        expected: Die als relevant gelabelten Paper-IDs.

    Returns:
        ``(Rang, Baustein)`` des ersten relevanten Eintrags (Rang ab 1); ``(None, None)``,
        wenn das Bündel kein relevantes Paper enthält.
    """
    for rank, (paper_id, component) in enumerate(entries, start=1):
        if paper_id in expected:
            return rank, component
    return None, None


@dataclass(frozen=True)
class QuestionScore:
    """Bewertung einer Gold-Frage: erster relevanter Rang plus optionale Diagnose."""

    qid: str
    kind: str
    first_rank: int | None
    diagnosis: str | None = None

    @property
    def hit(self) -> bool:
        """``True``, wenn das Bündel mindestens ein relevantes Paper enthielt."""
        return self.first_rank is not None

    @property
    def reciprocal_rank(self) -> float:
        """Kehrwert des ersten relevanten Rangs (``0.0`` ohne Treffer)."""
        return 0.0 if self.first_rank is None else 1.0 / self.first_rank


@dataclass(frozen=True)
class CoverageStats:
    """Coverage einer Auswahlstrategie – nur zusammen mit Selektivität aussagekräftig."""

    label: str
    coverage: float
    selectivity: float

    @property
    def lift(self) -> float:
        """Coverage je Korpusanteil (``0.0``, wenn nichts ausgewählt wurde).

        Der Lift ist das eigentliche Vergleichsinstrument: Eine Strategie, die einfach die
        größten Communities zurückgibt, erreicht hohe Coverage bei ebenso hoher Selektivität
        und landet damit bei ~1,0.
        """
        return 0.0 if self.selectivity <= 0.0 else self.coverage / self.selectivity


@dataclass(frozen=True)
class EvaluationReport:
    """Aggregierte Kennzahlen eines Laufs (eine Primitive bzw. ein Modus)."""

    label: str
    k: int
    scoring: str
    scores: tuple[QuestionScore, ...]
    coverage: tuple[CoverageStats, ...] = field(default=())

    @property
    def hit_rate(self) -> float:
        """Anteil der Fragen mit mindestens einem relevanten Paper im Bündel."""
        if not self.scores:
            return 0.0
        return sum(1.0 for score in self.scores if score.hit) / len(self.scores)

    @property
    def mrr(self) -> float:
        """Mittlerer Kehrwert des ersten relevanten Rangs (0.0 ohne Treffer)."""
        if not self.scores:
            return 0.0
        return sum(score.reciprocal_rank for score in self.scores) / len(self.scores)

    def by_kind(self) -> dict[str, tuple[float, float, int]]:
        """Kennzahlen je Fragetyp: ``kind -> (Hit@k, MRR@k, Anzahl)``."""
        kinds: dict[str, list[QuestionScore]] = {}
        for score in self.scores:
            kinds.setdefault(score.kind, []).append(score)
        return {
            kind: (
                sum(1.0 for score in group if score.hit) / len(group),
                sum(score.reciprocal_rank for score in group) / len(group),
                len(group),
            )
            for kind, group in sorted(kinds.items())
        }

    def by_diagnosis(self) -> dict[str, int]:
        """Häufigkeit der gesetzten Diagnosen (Fragen ohne Diagnose bleiben unberücksichtigt)."""
        counts: dict[str, int] = {}
        for score in self.scores:
            if score.diagnosis is not None:
                counts[score.diagnosis] = counts.get(score.diagnosis, 0) + 1
        return dict(sorted(counts.items()))
