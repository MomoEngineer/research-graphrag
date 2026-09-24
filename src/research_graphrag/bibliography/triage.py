"""Triage der schwach belegten Datensätze: Seite-1-Beleg über den Bestand (Phase 17 / A1).

Befund 3 der Phase-17-Planung zeigt, dass ``weak`` oft ein **fremdes** Paper verdeckt. Dieses
Modul wendet den Seite-1-Beleg aus :mod:`research_graphrag.bibliography.titlepage` auf die bereits
gespeicherten ``resolved``-Datensätze an (docs/adr/0042-title-page-evidence-and-rejections.md):

* **bestätigt** ⇒ Aufwertung auf ``strong``; die Herkunft bleibt ``resolved``, der Beleg nennt
  „Titel und Autoren auf S. 1 belegt“.
* **fremd** ⇒ Der Datensatz wird entfernt, und ein **Ablehnungsvermerk** verhindert, dass ein
  späterer Auflösungslauf denselben Treffer wieder einspielt. Das Paper fällt damit auf seine
  übrigen Herkünfte zurück und wird beim nächsten ``resolve_metadata``-Lauf neu aufgelöst.
* **sonst** ⇒ unverändert; der Befund geht in die Arbeitsliste
  (:mod:`research_graphrag.bibliography.worklist`).

Das Modul greift nicht aufs Netz zu. Es liest den Index, die Metadatendatei und die Titelseiten
der lokalen PDFs. Gespeichert wird über ``bibliography.store.save_records``, und zwar Datensätze
und Vermerke in **einem** atomaren Schreibvorgang.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from research_graphrag.bibliography.model import (
    CONFIDENCE_WEAK,
    ORIGIN_RESOLVED,
    MetadataRecord,
    PaperMetadata,
    PaperReview,
)
from research_graphrag.bibliography.store import add_rejection
from research_graphrag.bibliography.titlepage import (
    VERDICT_CONFIRMED,
    VERDICT_FOREIGN,
    Calibration,
    TitlePageCheck,
    check_pdf,
    pdf_path_for,
    rejection_for,
    upgrade,
)
from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import DOCUMENT_KIND_FULL
from research_graphrag.indexing.metadata_index import load_paper_metadata
from research_graphrag.online.report import escape_markdown

ACTION_UPGRADED = "upgraded"
"""Der Datensatz wurde über den Seite-1-Beleg ``strong``."""

ACTION_REJECTED = "rejected"
"""Der Datensatz war fremd: entfernt, Ablehnungsvermerk gesetzt."""

ACTION_UNCHANGED = "unchanged"
"""Weder bestätigt noch verworfen – der Befund geht in die Arbeitsliste."""

ACTION_NOT_CHECKABLE = "not_checkable"
"""Nicht prüfbar: kein gespeicherter ``resolved``-Datensatz oder kein lokales PDF."""

PdfChecker = Callable[[Path, str, Sequence[str]], TitlePageCheck]
"""Prüft Titel und Autoren gegen ein PDF (injizierbar für Tests)."""


@dataclass(frozen=True)
class IndexedPaper:
    """Ein Paper, wie der Index es kennt: Quelle, Dokumentart und aufgelöste Metadaten."""

    paper_id: str
    source_uri: str
    document_kind: str
    metadata: PaperMetadata


@dataclass(frozen=True)
class TriageDecision:
    """Die Entscheidung für **ein** Paper.

    Attributes:
        paper_id: Stabile Paper-ID.
        title: Titel des geprüften Datensatzes (zur Anzeige).
        action: Ein Wert aus ``ACTION_*``.
        check: Der Seite-1-Beleg; ``None``, wenn nicht prüfbar.
        verdict: Das Urteil des Belegs; leer, wenn nicht prüfbar.
        note: Klartext-Begründung.
    """

    paper_id: str
    title: str
    action: str
    check: TitlePageCheck | None = None
    verdict: str = ""
    note: str = ""


@dataclass(frozen=True)
class TriageRun:
    """Ergebnis eines Triage-Laufs: neuer Datenstand und die Entscheidungen."""

    records: tuple[MetadataRecord, ...]
    reviews: dict[str, PaperReview]
    decisions: tuple[TriageDecision, ...]

    def count(self, action: str) -> int:
        """Zahl der Entscheidungen einer Art."""
        return sum(1 for decision in self.decisions if decision.action == action)


def load_indexed_papers(db_path: str | Path) -> tuple[IndexedPaper, ...]:
    """Liest Quelle, Dokumentart und Metadaten aller Paper aus dem Index.

    Raises:
        DomainError: ``not_found``, wenn die Index-Datei fehlt.
    """
    path = Path(db_path)
    metadata = load_paper_metadata(path)
    connection = sqlite3.connect(str(path))
    try:
        rows = connection.execute(
            "SELECT paper_id, source_uri, document_kind FROM papers ORDER BY paper_id"
        ).fetchall()
    except sqlite3.Error as exc:
        raise DomainError(ErrorCode.INTERNAL_ERROR, f"Index nicht lesbar: {exc}") from exc
    finally:
        connection.close()
    return tuple(
        IndexedPaper(
            paper_id=str(row[0]),
            source_uri=str(row[1]),
            document_kind=str(row[2]),
            metadata=metadata.get(str(row[0]), PaperMetadata(paper_id=str(row[0]))),
        )
        for row in rows
    )


def open_weak(
    papers: Iterable[IndexedPaper], reviews: Mapping[str, PaperReview]
) -> tuple[IndexedPaper, ...]:
    """Die schwach belegten Paper **ohne** ausgewiesenen Status – das, was A1 abarbeiten muss.

    „Kein stilles ``weak``“: Ein Paper verlässt diese Menge nur als ``strong``, über eine
    ``manual``-Korrektur, die alle schwachen Felder überdeckt, oder mit einem ausgewiesenen Status.
    """
    return tuple(
        paper
        for paper in papers
        if paper.metadata.confidence == CONFIDENCE_WEAK
        and not (paper.paper_id in reviews and reviews[paper.paper_id].status)
    )


def triage_stored_records(
    records: Sequence[MetadataRecord],
    reviews: Mapping[str, PaperReview],
    papers: Sequence[IndexedPaper],
    *,
    papers_dir: Path | None,
    today: str,
    calibration: Calibration | None = None,
    checker: PdfChecker = check_pdf,
) -> TriageRun:
    """Prüft die gespeicherten ``resolved``-Datensätze der übergebenen Paper gegen Seite 1.

    Args:
        records: Alle gespeicherten Datensätze der Metadatendatei.
        reviews: Der gespeicherte Prüfstand.
        papers: Die zu prüfenden Paper (üblicherweise :func:`open_weak`). Nur Volltexte sind
            prüfbar; ein Referenz-Eintrag hat keine Titelseite.
        papers_dir: Korpus-Ordner zum Auffinden der PDFs (Rückfall: ``source_uri``).
        today: Datum neuer Vermerke (ISO).
        calibration: Schwellen des Belegs; ``None`` = die geltende Kalibrierung.
        checker: Prüffunktion gegen ein PDF (injizierbar).

    Returns:
        Den neuen Datenstand (noch **nicht** gespeichert) und je Paper eine Entscheidung.
    """
    by_key: dict[tuple[str, str], MetadataRecord] = {
        (record.paper_id, record.origin): record for record in records
    }
    new_reviews = dict(reviews)
    decisions: list[TriageDecision] = []
    for paper in sorted(papers, key=lambda item: item.paper_id):
        title = paper.metadata.title
        stored = by_key.get((paper.paper_id, ORIGIN_RESOLVED))
        if paper.document_kind != DOCUMENT_KIND_FULL:
            decisions.append(
                TriageDecision(
                    paper.paper_id, title, ACTION_NOT_CHECKABLE, note="kein Volltext (keine S. 1)"
                )
            )
            continue
        if stored is None:
            decisions.append(
                TriageDecision(
                    paper.paper_id,
                    title,
                    ACTION_NOT_CHECKABLE,
                    note="kein gespeicherter resolved-Datensatz – zuerst resolve_metadata",
                )
            )
            continue
        pdf = pdf_path_for(paper.source_uri, papers_dir)
        if pdf is None:
            decisions.append(
                TriageDecision(
                    paper.paper_id, stored.title, ACTION_NOT_CHECKABLE, note="PDF nicht gefunden"
                )
            )
            continue
        check = checker(pdf, stored.title, stored.authors)
        verdict = check.verdict(calibration)
        if verdict == VERDICT_CONFIRMED:
            by_key[(paper.paper_id, ORIGIN_RESOLVED)] = upgrade(stored, check)
            action = ACTION_UPGRADED
        elif verdict == VERDICT_FOREIGN:
            rejection = rejection_for(stored, check, today)
            del by_key[(paper.paper_id, ORIGIN_RESOLVED)]
            new_reviews = add_rejection(new_reviews, paper.paper_id, rejection)
            action = ACTION_REJECTED
        else:
            action = ACTION_UNCHANGED
        decisions.append(
            TriageDecision(
                paper.paper_id,
                stored.title,
                action,
                check=check,
                verdict=verdict,
                note=check.summary(),
            )
        )
    return TriageRun(
        records=tuple(by_key.values()), reviews=new_reviews, decisions=tuple(decisions)
    )


_ACTION_TITLES: tuple[tuple[str, str], ...] = (
    (ACTION_UPGRADED, "Aufgewertet (Titel und Autoren auf S. 1 belegt)"),
    (ACTION_REJECTED, "Verworfen (Fremd-Paper, Ablehnungsvermerk gesetzt)"),
    (ACTION_UNCHANGED, "Unverändert (für die Arbeitsliste)"),
    (ACTION_NOT_CHECKABLE, "Nicht prüfbar"),
)


def render_triage(timestamp: str, run: TriageRun, calibration: Calibration) -> list[str]:
    """Rendert einen Triage-Lauf als Abschnitt für ``data/metadata_log.md``.

    Args:
        timestamp: Zeitpunkt des Laufs (UTC, sortierbar).
        run: Das Ergebnis des Laufs.
        calibration: Die angewandte Kalibrierung (wird mit ausgewiesen).

    Returns:
        Die Zeilen des Abschnitts.
    """
    state = (
        f"kalibriert ({calibration.source})"
        if calibration.calibrated
        else "**nicht kalibriert** – keine automatische Aufwertung oder Ablehnung"
    )
    lines = [
        f"## Seite-1-Prüfung {timestamp}",
        "",
        f"- Geprüft: {len(run.decisions)} · aufgewertet: {run.count(ACTION_UPGRADED)} · "
        f"verworfen: {run.count(ACTION_REJECTED)} · unverändert: {run.count(ACTION_UNCHANGED)} · "
        f"nicht prüfbar: {run.count(ACTION_NOT_CHECKABLE)}",
        f"- Kalibrierung: {state}",
        "",
    ]
    for action, heading in _ACTION_TITLES:
        chosen = [decision for decision in run.decisions if decision.action == action]
        if not chosen:
            continue
        lines += [f"### {heading}", ""]
        for decision in chosen:
            title = escape_markdown(decision.title, limit=200) or "(ohne Titel)"
            note = escape_markdown(decision.note, limit=200)
            lines.append(f"- `{decision.paper_id}` {title} — {note}")
        lines.append("")
    return lines
