"""Seite-1-Beleg: gehört ein Metadaten-Datensatz zum PDF? (Phase 17 / A1)

Befund 3 der Phase-17-Planung: Bei 44 von 92 online aufgelösten ``weak``-Volltexten stehen weder
Titel noch Autoren des Treffers auf der ersten PDF-Seite. Alle sechs geprüften Fälle waren
**fremde** Paper, denn die aufgelöste Kennung stammte aus dem Literaturverzeichnis. Dieses Modul
prüft deshalb einen Datensatz **deterministisch** gegen die Titelseite des lokalen PDFs
(docs/adr/0042-title-page-evidence-and-rejections.md):

* **Titel** – derselbe Mechanismus wie im Intake und in S2 (``intake.title_candidates`` und
  ``intake.best_title_match`` mit ``intake.TITLE_SIMILARITY``). Eine zweite Ähnlichkeitslogik
  entsteht nicht.
* **Autoren** – Anteil der ersten :data:`MAX_CHECKED_SURNAMES` Nachnamen, die als ganzes Wort auf
  Seite 1 stehen.

Die Titelseite dient nur als **Beleg**, nie als **Quelle**: Aus dem PDF-Text wird kein Wert
übernommen (Roadmap Phase 17, „Bewusst ausgeschlossen“).

Die beiden Schwellen kalibriert A0, Punkt 3, an mindestens 30 von Hand geprüften Fällen. Bis
dahin stehen sie auf ``None``, und das Urteil lautet nie „bestätigt“ oder „fremd“, sondern
„unbestätigt“. Das ist der Rückfall aus dem A0-Abbruchkriterium: ohne automatische Aufwertung und
ohne automatische Ablehnung. Ein fälschlich ``strong`` ist schlimmer als ein ehrliches ``weak``.
Eine falsche Ablehnung würde zudem den richtigen Treffer dauerhaft sperren.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from research_graphrag.bibliography.model import (
    CONFIDENCE_STRONG,
    MetadataRecord,
    Rejection,
    ascii_fold,
    surname_of,
)
from research_graphrag.errors import DomainError
from research_graphrag.indexing.citation_graph import normalize_title
from research_graphrag.intake import (
    TITLE_SIMILARITY,
    best_title_match,
    read_front_pages,
    title_candidates,
)

MAX_CHECKED_SURNAMES = 10
"""Geprüft werden die ersten zehn Nachnamen (wie in der Planungsmessung, Befund 3).

Lange Kollaborationslisten stehen oft nicht vollständig auf Seite 1; die ersten Namen dagegen
fast immer."""


@dataclass(frozen=True)
class Calibration:
    """Die beiden in A0, Punkt 3, kalibrierten Schwellen des Seite-1-Belegs.

    Attributes:
        min_author_share: Mindestanteil belegter Nachnamen für die **Aufwertung** auf ``strong``
            (der Titel ist zusätzlich Pflicht). Kalibriert auf **0 falsch-positive**
            Aufwertungen in mindestens 30 von Hand geprüften Fällen. ``None`` = keine
            automatische Aufwertung.
        max_share_for_rejection: Höchstanteil belegter Nachnamen, bei dem ein Treffer **ohne**
            Titel auf Seite 1 verworfen wird. Die Ablehnung verlangt beides: Der Titel fehlt,
            **und** kaum ein Autor steht dort. Die Planung zählte 7 Fälle „Titel fehlt, Autoren
            stehen“; sie deuten auf eine unleserliche Titelzeile, nicht auf ein fremdes Paper.
            Kalibriert auf **0 falsche Ablehnungen**. ``None`` = keine automatische Ablehnung.
        source: Beleg der Kalibrierung (Datum, Stichprobe) – leer, solange nicht kalibriert.
    """

    min_author_share: float | None = None
    max_share_for_rejection: float | None = None
    source: str = ""

    @property
    def calibrated(self) -> bool:
        """``True``, wenn mindestens eine automatische Entscheidung freigeschaltet ist."""
        return self.min_author_share is not None or self.max_share_for_rejection is not None


CALIBRATION = Calibration()
"""Die geltende Kalibrierung. **Nicht kalibriert** bis A0, Punkt 3, beantwortet ist.

Nach der Kalibrierung werden hier beide Werte samt Beleg eingetragen (ein Commit, kein
Laufzeitparameter). So bleibt jede Aufwertung auf einen versionierten Stand rückführbar."""

VERDICT_CONFIRMED = "confirmed"
"""Titel und Autoren stehen auf Seite 1 – der Datensatz wird ``strong``."""

VERDICT_FOREIGN = "foreign"
"""Weder Titel noch (nennenswert) Autoren auf Seite 1 – der Treffer wird verworfen."""

VERDICT_UNCONFIRMED = "unconfirmed"
"""Weder bestätigt noch verworfen – der Datensatz bleibt und geht in die Arbeitsliste."""

VERDICT_UNREADABLE = "unreadable"
"""Die Titelseite liefert keinen Text – ein Urteil ist nicht möglich."""

EVIDENCE_TITLE_PAGE = "Titel und Autoren auf S. 1 belegt"
"""Belegklasse der Aufwertung (neue Zeile der Konfidenztabelle aus ADR 0026, siehe ADR 0042)."""

_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class TitlePageCheck:
    """Das Messergebnis des Seite-1-Belegs für **einen** Datensatz.

    Attributes:
        readable: ``False``, wenn Seite 1 keinen Text liefert (Scan, defektes PDF).
        title_ratio: Beste Titel-Ähnlichkeit auf Seite 1 (0–1).
        surnames_checked: Zahl der geprüften Nachnamen (höchstens :data:`MAX_CHECKED_SURNAMES`).
        surnames_found: Davon auf Seite 1 als ganzes Wort gefunden.
    """

    readable: bool
    title_ratio: float = 0.0
    surnames_checked: int = 0
    surnames_found: int = 0

    @property
    def title_found(self) -> bool:
        """``True``, wenn der Titel die Intake-Schwelle erreicht."""
        return self.title_ratio >= TITLE_SIMILARITY

    @property
    def author_share(self) -> float:
        """Anteil der gefundenen unter den geprüften Nachnamen (``0.0`` ohne Autoren)."""
        if not self.surnames_checked:
            return 0.0
        return self.surnames_found / self.surnames_checked

    def verdict(self, calibration: Calibration | None = None) -> str:
        """Leitet das Urteil aus den Messwerten und den (kalibrierten) Schwellen ab.

        Args:
            calibration: Die Schwellen; ``None`` nimmt die geltende :data:`CALIBRATION` (zum
                Aufrufzeitpunkt gelesen).

        Returns:
            Einen Wert aus ``VERDICT_*``.
        """
        active = calibration if calibration is not None else CALIBRATION
        min_author_share = active.min_author_share
        max_share_for_rejection = active.max_share_for_rejection
        if not self.readable:
            return VERDICT_UNREADABLE
        if (
            self.title_found
            and self.surnames_checked
            and min_author_share is not None
            and self.author_share >= min_author_share
        ):
            return VERDICT_CONFIRMED
        if (
            not self.title_found
            and self.surnames_checked
            and max_share_for_rejection is not None
            and self.author_share <= max_share_for_rejection
        ):
            return VERDICT_FOREIGN
        return VERDICT_UNCONFIRMED

    def summary(self) -> str:
        """Kurzform für Beleg und Protokoll, z. B. ``"Titel 0.93, Autoren 4/5 auf S. 1"``."""
        if not self.readable:
            return "S. 1 ohne lesbaren Text"
        return (
            f"Titel {self.title_ratio:.2f}, Autoren {self.surnames_found}/{self.surnames_checked}"
            " auf S. 1"
        )


def _words(text: str) -> list[str]:
    """Zerlegt Text in gefaltete, kleingeschriebene Wörter (dieselbe Faltung wie überall)."""
    return _WORD.findall(ascii_fold(text).lower())


def check_front_pages(
    front_pages: Sequence[str], title: str, authors: Sequence[str]
) -> TitlePageCheck:
    """Prüft Titel und Autoren eines Datensatzes gegen die Titelseite (rein funktional).

    Args:
        front_pages: Normalisierte Seitentexte aus ``intake.read_front_pages``. Geprüft wird nur
            Seite 1.
        title: Titel des Datensatzes.
        authors: Autoren des Datensatzes (Schreibweise der Quelle).

    Returns:
        Das Messergebnis; ohne Text auf Seite 1 ist ``readable`` ``False``.
    """
    page = front_pages[0] if front_pages else ""
    if not page.strip():
        return TitlePageCheck(readable=False)

    normalized = normalize_title(title)
    ratio = 0.0
    if normalized:
        ratio, _ = best_title_match(title_candidates("", [page]), {normalized: title})

    page_words = set(_words(page))
    checked = 0
    found = 0
    for author in authors[:MAX_CHECKED_SURNAMES]:
        surname_words = _words(surname_of(author))
        if not surname_words:
            continue
        checked += 1
        if all(word in page_words for word in surname_words):
            found += 1
    return TitlePageCheck(
        readable=True, title_ratio=ratio, surnames_checked=checked, surnames_found=found
    )


def check_pdf(path: Path, title: str, authors: Sequence[str]) -> TitlePageCheck:
    """Prüft einen Datensatz gegen die Titelseite eines lokalen PDFs.

    Ein nicht lesbares oder nicht parsebares PDF ist kein Fehler, sondern ein Befund
    (``readable = False``). Der Lauf soll an einem defekten PDF nicht scheitern.
    """
    try:
        front_pages = read_front_pages(path.read_bytes())
    except (OSError, DomainError):
        return TitlePageCheck(readable=False)
    return check_front_pages(front_pages, title, authors)


def pdf_path_for(source_uri: str, papers_dir: Path | None = None) -> Path | None:
    """Findet das lokale PDF eines Papers.

    Bevorzugt wird ``papers_dir / <Dateiname>``: Der Korpus kann seit der Extraktion umgezogen
    sein, der Dateiname bleibt dabei gleich. Rückfall ist der Pfad aus der ``file://``-URI.

    Returns:
        Den Pfad einer vorhandenen ``*.pdf`` oder ``None``.
    """
    parts = urlsplit(source_uri)
    name = unquote(parts.path.rsplit("/", 1)[-1])
    candidates: list[Path] = []
    if papers_dir is not None and name:
        candidates.append(papers_dir / name)
    if parts.scheme == "file":
        netloc = f"//{parts.netloc}" if parts.netloc else ""
        candidates.append(Path(url2pathname(netloc + parts.path)))
    for candidate in candidates:
        if candidate.suffix.lower() == ".pdf" and candidate.is_file():
            return candidate
    return None


def upgrade(record: MetadataRecord, check: TitlePageCheck) -> MetadataRecord:
    """Wertet einen Datensatz über den Seite-1-Beleg auf ``strong`` auf.

    Die Herkunft bleibt ``resolved``. Der Beleg wird ergänzt, nicht ersetzt, damit erkennbar
    bleibt, **wie** der Treffer gefunden wurde.
    """
    evidence = f"{record.evidence}; {EVIDENCE_TITLE_PAGE} ({check.summary()})".lstrip("; ")
    return replace(record, confidence=CONFIDENCE_STRONG, evidence=evidence)


def rejection_for(record: MetadataRecord, check: TitlePageCheck, date: str) -> Rejection:
    """Baut den Ablehnungsvermerk für einen als fremd erkannten Treffer."""
    return Rejection(
        doi=record.doi,
        arxiv_id=record.arxiv_id,
        title=record.title,
        reason=f"Fremd-Paper laut Seite-1-Beleg ({check.summary()})",
        date=date,
    )


def is_rejected(record: MetadataRecord, rejections: Iterable[Rejection]) -> bool:
    """Prüft, ob ein Treffer einem Ablehnungsvermerk entspricht.

    Verglichen wird über DOI (ohne Groß-/Kleinschreibung), arXiv-ID und den normalisierten Titel.
    Schon **ein** gemeinsamer Schlüssel genügt: Derselbe fremde Treffer kann über jeden dieser
    Wege zurückkehren.
    """
    doi = record.doi.strip().lower()
    arxiv_id = record.arxiv_id.strip().lower()
    title = normalize_title(record.title)
    for entry in rejections:
        if doi and doi == entry.doi.strip().lower():
            return True
        if arxiv_id and arxiv_id == entry.arxiv_id.strip().lower():
            return True
        if title and title == normalize_title(entry.title):
            return True
    return False
