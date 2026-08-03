"""Eingefrorene Baseline und qid-genauer Regressions-Check (Phase 7 / A6).

Die Baseline speichert **ausschließlich den ersten relevanten Rang je Frage und Ebene**; alle
Aggregate werden daraus abgeleitet – es gibt keine doppelt gepflegten Kennzahlen. Verglichen
wird mit zwei Schweregraden: ``Treffer → kein Treffer`` ist eine **Regression** (Exit-Code 1),
eine reine Rangverschiebung wird nur berichtet. Aggregierte Schwellenwerte wären bei wenigen
Dutzend Fragen Scheingenauigkeit und würden zudem nicht sagen, *welche* Frage kaputtging.

Ein **Fingerprint-Guard** verhindert das stille Verrotten: Passt der Index (Gold-Set-Version,
Schema, Bestand, Parameter) nicht mehr zur Baseline, wird der Vergleich abgelehnt (Exit-Code 2)
statt gegen einen fremden Korpus geprüft
(docs/adr/0016-quantitative-retrieval-evaluation-phase7.md).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.evaluation.metrics import EvaluationReport

BASELINE_VERSION = "1.0.0"
"""Schema-Version des Baseline-Artefakts."""

REGRESSION = "regression"
"""Treffer verloren – der einzige Schweregrad, der den Lauf scheitern lässt."""

WORSE = "verschlechterung"
"""Relevantes Paper weiter hinten – wird berichtet, nicht bewertet."""

BETTER = "verbesserung"
"""Relevantes Paper weiter vorn oder neu gefunden."""


@dataclass(frozen=True)
class Fingerprint:
    """Identität des gemessenen Zustands – Baseline und Lauf müssen darin übereinstimmen."""

    gold_set_version: str
    index_schema_version: str
    n_papers: int
    n_chunks: int
    n_communities: int
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Fingerprint."""
        return {
            "gold_set_version": self.gold_set_version,
            "index_schema_version": self.index_schema_version,
            "n_papers": self.n_papers,
            "n_chunks": self.n_chunks,
            "n_communities": self.n_communities,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Fingerprint:
        """Liest einen Fingerprint aus seiner serialisierten Form."""
        return cls(
            gold_set_version=str(payload["gold_set_version"]),
            index_schema_version=str(payload["index_schema_version"]),
            n_papers=int(payload["n_papers"]),
            n_chunks=int(payload["n_chunks"]),
            n_communities=int(payload["n_communities"]),
            parameters=dict(payload["parameters"]),
        )

    def differences(self, other: Fingerprint) -> tuple[str, ...]:
        """Benennt die abweichenden Felder (leer, wenn beide Zustände vergleichbar sind)."""
        mine, theirs = self.to_dict(), other.to_dict()
        return tuple(
            f"{key}: {mine[key]} → {theirs[key]}" for key in mine if mine[key] != theirs[key]
        )


def read_fingerprint(
    db_path: str | Path, gold_set_version: str, parameters: Mapping[str, Any]
) -> Fingerprint:
    """Liest den Fingerprint aus dem Index selbst (keine gepflegten Zahlen).

    Die Funktion kennt weder Gold-Set noch Runner, sondern nur eine Version und ein
    Parameter-Mapping – dadurch ist sie für beide Messungen (Retrieval und Multi-Hop) gleich
    nutzbar, ohne dass ``baseline.py`` von ihnen abhängt.

    Args:
        db_path: Pfad zur SQLite-Index-Datei.
        gold_set_version: Version des gemessenen Gold-Sets.
        parameters: Messparameter des Laufs (serialisiert, stabile Reihenfolge).

    Returns:
        Der :class:`Fingerprint` des aktuellen Zustands.

    Raises:
        DomainError: ``not_found``, wenn die Index-Datei fehlt.
    """
    path = Path(db_path)
    if not path.exists():
        raise DomainError(ErrorCode.NOT_FOUND, f"Index-Datei nicht gefunden: {path}")
    connection = sqlite3.connect(str(path))
    try:
        row = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        n_papers = int(connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0])
        n_chunks = int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'communities'"
        ).fetchone()
        n_communities = (
            int(connection.execute("SELECT COUNT(*) FROM communities").fetchone()[0])
            if exists
            else 0
        )
    finally:
        connection.close()
    return Fingerprint(
        gold_set_version=gold_set_version,
        index_schema_version=str(row[0]) if row else "",
        n_papers=n_papers,
        n_chunks=n_chunks,
        n_communities=n_communities,
        parameters=dict(parameters),
    )


@dataclass(frozen=True)
class Baseline:
    """Eingefrorener Messstand: Fingerprint plus erster relevanter Rang je Ebene und Frage."""

    version: str
    created: str
    fingerprint: Fingerprint
    ranks: dict[str, dict[str, int | None]]

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Baseline (Dateiformat)."""
        return {
            "baseline_version": self.version,
            "created": self.created,
            "fingerprint": self.fingerprint.to_dict(),
            "ranks": {label: dict(scores) for label, scores in self.ranks.items()},
        }


def build_baseline(
    reports: Mapping[str, EvaluationReport], fingerprint: Fingerprint, created: str
) -> Baseline:
    """Friert die Ränge eines Laufs ein.

    Args:
        reports: Berichte je Ebene (Primitive und/oder Modi).
        fingerprint: Fingerprint des gemessenen Zustands.
        created: Erstellungsdatum als ``JJJJ-MM-TT`` (injiziert, damit Tests deterministisch
            bleiben).

    Returns:
        Die :class:`Baseline` zum Speichern.
    """
    return Baseline(
        version=BASELINE_VERSION,
        created=created,
        fingerprint=fingerprint,
        ranks={
            label: {score.qid: score.first_rank for score in report.scores}
            for label, report in reports.items()
        },
    )


def save_baseline(baseline: Baseline, path: str | Path) -> None:
    """Schreibt die Baseline als JSON (UTF-8, eingerückt, stabile Reihenfolge)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(baseline.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_baseline(path: str | Path) -> Baseline:
    """Liest eine eingefrorene Baseline.

    Args:
        path: Pfad zur Baseline-Datei.

    Returns:
        Die geladene :class:`Baseline`.

    Raises:
        DomainError: ``not_found``, wenn die Datei fehlt (kein stiller Vergleich gegen nichts).
    """
    source = Path(path)
    if not source.exists():
        raise DomainError(
            ErrorCode.NOT_FOUND,
            f"Baseline nicht gefunden: {source}. Zuerst mit '--write-baseline' einfrieren.",
        )
    payload = json.loads(source.read_text(encoding="utf-8"))
    return Baseline(
        version=str(payload["baseline_version"]),
        created=str(payload["created"]),
        fingerprint=Fingerprint.from_dict(payload["fingerprint"]),
        ranks={
            str(label): {
                str(qid): None if rank is None else int(rank) for qid, rank in scores.items()
            }
            for label, scores in payload["ranks"].items()
        },
    )


@dataclass(frozen=True)
class Change:
    """Eine Abweichung gegenüber der Baseline (eine Frage in einer Ebene)."""

    label: str
    qid: str
    before: int | None
    after: int | None
    severity: str


@dataclass(frozen=True)
class Comparison:
    """Ergebnis des Regressions-Checks."""

    comparable: bool
    reason: str
    changes: tuple[Change, ...]

    @property
    def regressions(self) -> tuple[Change, ...]:
        """Die Abweichungen, die einen verlorenen Treffer bedeuten."""
        return tuple(change for change in self.changes if change.severity == REGRESSION)

    @property
    def exit_code(self) -> int:
        """``0`` = unauffällig, ``1`` = Regression, ``2`` = nicht vergleichbar."""
        if not self.comparable:
            return 2
        return 1 if self.regressions else 0


def _severity(before: int | None, after: int | None) -> str | None:
    """Bewertet eine Rangänderung (``None``, wenn sich nichts geändert hat)."""
    if before == after:
        return None
    if after is None:  # gleichzeitig ``before is not None`` – sonst wären beide gleich
        return REGRESSION
    if before is None or after < before:
        return BETTER
    return WORSE


def precheck(baseline: Baseline, fingerprint: Fingerprint) -> Comparison | None:
    """Prüft die Vergleichbarkeit, **bevor** ein teurer Messlauf startet.

    Args:
        baseline: Die eingefrorene Baseline.
        fingerprint: Fingerprint des aktuellen Zustands (aus dem Index gelesen).

    Returns:
        ``None``, wenn verglichen werden darf; sonst die ablehnende :class:`Comparison`.
    """
    differences = baseline.fingerprint.differences(fingerprint)
    if differences:
        return Comparison(
            comparable=False,
            reason="Baseline passt nicht zum aktuellen Zustand – " + "; ".join(differences),
            changes=(),
        )
    return None


def compare(
    baseline: Baseline, reports: Mapping[str, EvaluationReport], fingerprint: Fingerprint
) -> Comparison:
    """Vergleicht einen Lauf qid-genau mit der eingefrorenen Baseline.

    Args:
        baseline: Die eingefrorene Baseline.
        reports: Berichte des aktuellen Laufs.
        fingerprint: Fingerprint des aktuellen Zustands.

    Returns:
        Eine :class:`Comparison`; bei abweichendem Fingerprint oder abweichenden Ebenen ist
        ``comparable`` ``False`` und ``changes`` leer – es wird bewusst **nicht** verglichen.
    """
    blocked = precheck(baseline, fingerprint)
    if blocked is not None:
        return blocked
    if set(baseline.ranks) != set(reports):
        return Comparison(
            comparable=False,
            reason=(
                f"Baseline deckt andere Ebenen ab: {sorted(baseline.ranks)} statt {sorted(reports)}"
            ),
            changes=(),
        )

    changes: list[Change] = []
    for label in baseline.ranks:
        current = {score.qid: score.first_rank for score in reports[label].scores}
        for qid, before in baseline.ranks[label].items():
            after = current.get(qid)
            severity = _severity(before, after)
            if severity is not None:
                changes.append(
                    Change(label=label, qid=qid, before=before, after=after, severity=severity)
                )
    return Comparison(comparable=True, reason="", changes=tuple(changes))
