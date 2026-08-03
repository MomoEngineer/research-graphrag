"""Korpus-Zufluss: ``new_papers/`` → Duplikatprüfung → ``papers/`` → Ingest → Übersicht (Phase 8).

Übernimmt neue PDFs aus einem Eingangsordner in den Korpus und verhindert dabei **Doppelbestand**.
Geprüft wird in drei Stufen mit fallender Sicherheit – die Konsequenz hängt an der Sicherheit,
nicht am Verdacht (docs/adr/0019-corpus-intake-new-papers-phase8.md):

1. **sha256** identisch zu ``data/manifest.json`` → die Datei wird **gelöscht** (eine
   byte-identische Kopie liegt nachweislich in ``papers/``).
2. **DOI/arXiv** identisch zu einem *gehärteten* Korpus-Schlüssel → **Quarantäne**
   (``new_papers/_duplikate/``); gelöscht wird nur auf ausdrückliche Anforderung. Gehärtet heißt:
   Der Korpus-Wert muss auf der eigenen Titelseite belegt und im Korpus **eindeutig** sein, und
   auf der Eingangsseite wird ohne Volltext-Fallback gelesen.
3. **Titel-Ähnlichkeit** ≥ :data:`TITLE_SIMILARITY` → die Datei **bleibt liegen**, der Verdacht
   erscheint im Bericht. Verdacht ist kein Beweis.

Ohne Treffer wandert die Datei nach ``papers/``; danach läuft **ein** regulärer
:func:`research_graphrag.pipeline.ingest` (voller Re-Index mit atomarem Swap) und die kuratierte
Übersicht bekommt je neuem Paper eine Entwurfszeile. ``dry_run`` verändert **nichts**.
"""

from __future__ import annotations

import difflib
import hashlib
import io
import json
import logging
import shutil
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import SECTION_KIND_REFERENCES, CanonicalPaper
from research_graphrag.extraction.normalization import normalize_text
from research_graphrag.extraction.structure import extract_identifiers
from research_graphrag.indexing.citation_graph import (
    MIN_TITLE_CHARS,
    MIN_TITLE_WORDS,
    TITLE_PAGE_PAGES,
    normalize_title,
    title_of,
)
from research_graphrag.overview.drafts import (
    OverviewReport,
    append_overview_rows,
    ensure_overview_target,
)
from research_graphrag.pipeline import IngestReport, ingest

_logger = logging.getLogger(__name__)

QUARANTINE_DIR = "_duplikate"
"""Unterordner des Eingangsordners für Identifikator-Duplikate (umkehrbar statt gelöscht)."""

INTAKE_LOG = "intake_log.md"
"""Append-only Protokoll unter ``data/`` – forensische Spur der löschenden Operation."""

TITLE_SIMILARITY = 0.85
"""Schwelle der Titel-Verdachtsstufe (am realen Korpus ohne Fehlalarm, ADR 0019)."""

TITLE_CANDIDATE_LINES = 5
"""Zeilen der ersten Seite, aus denen Titelkandidaten gebildet werden."""

PDF_MAGIC = b"%PDF-"
"""Signatur einer PDF-Datei; alles andere wird nicht übernommen."""

ACTION_ACCEPTED = "accepted"
ACTION_DELETED = "deleted"
ACTION_QUARANTINED = "quarantined"
ACTION_KEPT = "kept"

REASON_NEW = "new"
REASON_DUPLICATE_SHA256 = "duplicate_sha256"
REASON_DUPLICATE_IDENTIFIER = "duplicate_identifier"
REASON_TITLE_SUSPICION = "title_suspicion"
REASON_NAME_COLLISION = "name_collision"
REASON_NOT_A_PDF = "not_a_pdf"
REASON_UNREADABLE = "unreadable"

_LOG_HEADER = "\n".join(
    [
        "# Intake-Protokoll",
        "",
        "> **Automatisch fortgeschrieben** (`scripts/intake.py`, append-only).",
        "> Dokumentiert jede Entscheidung des Korpus-Zuflusses – insbesondere jede **gelöschte**",
        "> Datei samt Hash (docs/adr/0019-corpus-intake-new-papers-phase8.md).",
        "",
        "| Zeitpunkt (UTC) | Aktion | Datei | sha256 | Grund |",
        "| --- | --- | --- | --- | --- |",
        "",
    ]
)


@dataclass(frozen=True)
class IntakeDecision:
    """Entscheidung über **eine** Datei des Eingangsordners."""

    filename: str
    sha256: str
    action: str
    reason: str
    detail: str
    flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Entscheidung (stabile Schlüssel für Bericht und Tests)."""
        return {
            "filename": self.filename,
            "sha256": self.sha256,
            "action": self.action,
            "reason": self.reason,
            "detail": self.detail,
            "flags": list(self.flags),
        }


@dataclass(frozen=True)
class IntakeReport:
    """Ergebnis eines Intake-Laufs (Entscheidungen + Folgeschritte)."""

    decisions: tuple[IntakeDecision, ...]
    dry_run: bool
    ingest: IngestReport | None
    overview: OverviewReport | None

    def by_action(self, action: str) -> tuple[IntakeDecision, ...]:
        """Filtert die Entscheidungen nach Aktion (Eingangsreihenfolge bleibt erhalten)."""
        return tuple(item for item in self.decisions if item.action == action)

    @property
    def accepted(self) -> tuple[IntakeDecision, ...]:
        """Die übernommenen Dateien."""
        return self.by_action(ACTION_ACCEPTED)


@dataclass(frozen=True)
class CorpusView:
    """Read-only Prüfgrundlage: Hashes, gehärtete Identifikator-Schlüssel und Titel.

    Öffentlich, weil auch die Online-Kandidatensuche gegen **dieselbe** Grundlage prüft
    (docs/adr/0020-online-candidate-search-phase9.md); zwei Wahrheiten darüber, ob ein Paper
    bereits im Korpus liegt, wären eine Fehlerquelle.

    Attributes:
        sha256_to_name: Dateihash → Dateiname aus ``manifest.json``.
        identifier_to_paper: Gehärteter ``(Art, Wert)``-Schlüssel → ``paper_id``.
        titles: Normalisierter Titel → Originaltitel.
    """

    sha256_to_name: dict[str, str]
    identifier_to_paper: dict[tuple[str, str], str]
    titles: dict[str, str]


def _manifest_hashes(data_path: Path) -> dict[str, str]:
    """Liest ``manifest.json`` als sha256 → Dateiname (leer, wenn nicht vorhanden)."""
    manifest_path = data_path / "manifest.json"
    if not manifest_path.is_file():
        return {}
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes: dict[str, str] = {}
    for name, entry in raw.items():
        hashes.setdefault(str(entry["sha256"]).lower(), str(name))
    return hashes


def _front_matter(paper: CanonicalPaper) -> str:
    """Liefert den Titelseiten-Text eines Korpus-Papers **ohne** Referenzabschnitt."""
    ref_ids = {
        section.section_id for section in paper.sections if section.kind == SECTION_KIND_REFERENCES
    }
    return " ".join(
        chunk.text
        for chunk in paper.chunks
        if chunk.page_end <= TITLE_PAGE_PAGES and chunk.section_id not in ref_ids
    ).lower()


def _identifier_keys(papers: list[CanonicalPaper]) -> dict[tuple[str, str], str]:
    """Baut die **gehärteten** Duplikat-Schlüssel ``(art, wert) → paper_id``.

    Zwei Bedingungen, beide am realen Korpus begründet
    (docs/adr/0019-corpus-intake-new-papers-phase8.md):

    1. **Frontmatter-Beleg** – der Wert steht auf der eigenen Titelseite außerhalb der
       Bibliografie. Ohne diese Bedingung zeigen fehl-extrahierte, *zitierte* fremde
       Identifikatoren auf das falsche Paper (derselbe Guard wie im Zitationsgraphen).
    2. **Eindeutigkeit** – Werte mit mehreren Trägern (z. B. der unausgefüllte
       ACM-Vorlagen-Platzhalter) sind **kein** Duplikat-Kriterium.
    """
    owners: dict[tuple[str, str], set[str]] = {}
    for paper in papers:
        front = _front_matter(paper)
        for kind, value in paper.identifiers.items():
            if value and value.lower() in front:
                owners.setdefault((kind, value.lower()), set()).add(paper.paper_id)
    return {key: next(iter(pids)) for key, pids in sorted(owners.items()) if len(pids) == 1}


def _corpus_titles(papers: list[CanonicalPaper]) -> dict[str, str]:
    """Bildet ``normalisierter Titel → Originaltitel`` (Mindestmaße wie im Zitationsgraphen)."""
    titles: dict[str, str] = {}
    for paper in papers:
        original = title_of(paper)
        normalized = normalize_title(original)
        if len(normalized) >= MIN_TITLE_CHARS and len(normalized.split()) >= MIN_TITLE_WORDS:
            titles.setdefault(normalized, original)
    return titles


def load_corpus(data_path: Path) -> CorpusView:
    """Lädt die Prüfgrundlage aus ``manifest.json`` und den Canonical-Papern.

    Args:
        data_path: Datenverzeichnis mit ``manifest.json`` und ``canonical/``.

    Returns:
        Die Prüfgrundlage; fehlende Artefakte führen zu leeren Teilmengen, nicht zu einem Fehler.
    """
    canonical_dir = data_path / "canonical"
    papers = (
        [CanonicalPaper.load_json(path) for path in sorted(canonical_dir.glob("*.json"))]
        if canonical_dir.is_dir()
        else []
    )
    return CorpusView(
        sha256_to_name=_manifest_hashes(data_path),
        identifier_to_paper=_identifier_keys(papers),
        titles=_corpus_titles(papers),
    )


def read_front_pages(raw: bytes) -> list[str]:
    """Liest den normalisierten Text der ersten :data:`TITLE_PAGE_PAGES` Seiten.

    Bewusst **ohne** den Volltext-Fallback der regulären Extraktion: Genau dieser Fallback
    erzeugt die fehl-extrahierten Identifikatoren, gegen die der Intake gehärtet ist.

    Args:
        raw: Dateiinhalt der PDF.

    Returns:
        Normalisierte Seitentexte (höchstens :data:`TITLE_PAGE_PAGES` Einträge).

    Raises:
        DomainError: ``parse_error`` wenn das PDF nicht parsebar ist.
    """
    try:
        reader = PdfReader(io.BytesIO(raw))
        return [
            normalize_text(page.extract_text() or "").strip()
            for page in reader.pages[:TITLE_PAGE_PAGES]
        ]
    except (PyPdfError, KeyError, ValueError) as exc:
        raise DomainError(ErrorCode.PARSE_ERROR, f"PDF nicht parsebar: {exc}") from exc


def title_candidates(filename: str, front_pages: list[str]) -> list[str]:
    """Bildet normalisierte Titelkandidaten aus Dateiname **und** Titelseite.

    Der Dateiname allein trägt bei heruntergeladenen PDFs (``2310.11511v1.pdf``) keine
    Information; umgekehrt ist die erste Textzeile nicht zwingend der Titel. Deshalb werden beide
    Quellen angeboten und je Zeile auch die Verbindung mit der Folgezeile geprüft (Titel brechen
    oft um). Kandidaten unterhalb der Mindestmaße des Titel-Matchings
    (:data:`MIN_TITLE_CHARS`/:data:`MIN_TITLE_WORDS`) entfallen.

    Args:
        filename: Dateiname der Eingangsdatei.
        front_pages: Seitentexte der Titelseite(n) aus :func:`read_front_pages`.

    Returns:
        Deduplizierte, normalisierte Kandidaten in Fundreihenfolge.
    """
    stem = filename[:-4] if filename.lower().endswith(".pdf") else filename
    lines = [line.strip() for line in (front_pages[0] if front_pages else "").splitlines()]
    lines = [line for line in lines if line][:TITLE_CANDIDATE_LINES]
    raw_candidates = [stem, *lines, *(f"{a} {b}" for a, b in zip(lines, lines[1:], strict=False))]

    candidates: list[str] = []
    for candidate in raw_candidates:
        normalized = normalize_title(candidate)
        if (
            len(normalized) >= MIN_TITLE_CHARS
            and len(normalized.split()) >= MIN_TITLE_WORDS
            and normalized not in candidates
        ):
            candidates.append(normalized)
    return candidates


def best_title_match(candidates: list[str], corpus_titles: dict[str, str]) -> tuple[float, str]:
    """Liefert die höchste Titel-Ähnlichkeit und den zugehörigen Korpus-Titel."""
    best_ratio = 0.0
    best_title = ""
    for candidate in candidates:
        for normalized, original in corpus_titles.items():
            ratio = difflib.SequenceMatcher(None, candidate, normalized).ratio()
            if ratio > best_ratio:
                best_ratio, best_title = ratio, original
    return best_ratio, best_title


def _same_file(path: Path, sha256: str) -> bool:
    """Prüft, ob unter ``path`` tatsächlich eine Datei mit genau diesem Hash liegt."""
    if not path.is_file():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == sha256


def _classify(
    pdf: Path, raw: bytes, sha256: str, corpus: CorpusView, papers_path: Path
) -> IntakeDecision:
    """Entscheidet über **eine** Eingangsdatei – rein lesend, ohne Seiteneffekt."""

    def decision(action: str, reason: str, detail: str) -> IntakeDecision:
        return IntakeDecision(
            filename=pdf.name, sha256=sha256, action=action, reason=reason, detail=detail
        )

    if not raw.startswith(PDF_MAGIC):
        return decision(ACTION_KEPT, REASON_NOT_A_PDF, "Datei trägt keine PDF-Signatur")

    # Der Manifest-Treffer allein rechtfertigt die Löschung **nicht**: Wird eine PDF aus
    # ``papers/`` entfernt, ohne neu zu indizieren, zeigt der Eintrag ins Leere – und die
    # einzige verbliebene Kopie würde vernichtet. Deshalb wird der Beleg am Dateisystem
    # nachgerechnet (Existenz **und** Hash), bevor gelöscht wird.
    known_name = corpus.sha256_to_name.get(sha256)
    if known_name is not None and _same_file(papers_path / known_name, sha256):
        return decision(
            ACTION_DELETED, REASON_DUPLICATE_SHA256, f"byte-identisch zu papers/{known_name}"
        )

    try:
        front_pages = read_front_pages(raw)
    except DomainError as exc:
        return decision(ACTION_KEPT, REASON_UNREADABLE, exc.message)

    identifiers = extract_identifiers("\n".join(front_pages))
    for kind, value in sorted(identifiers.items()):
        owner = corpus.identifier_to_paper.get((kind, value.lower()))
        if owner is not None:
            return decision(
                ACTION_QUARANTINED,
                REASON_DUPLICATE_IDENTIFIER,
                f"{kind}:{value} bereits im Korpus (Paper {owner})",
            )

    # Die Namenskollision wird **vor** der Verdachtsstufe geprüft: Sie ist eine Tatsache über den
    # Zielort, keine Vermutung – und sie ist die handlungsleitendere Meldung.
    if (papers_path / pdf.name).exists():
        return decision(
            ACTION_KEPT, REASON_NAME_COLLISION, f"papers/{pdf.name} existiert mit anderem Inhalt"
        )

    ratio, matched = best_title_match(title_candidates(pdf.name, front_pages), corpus.titles)
    if ratio >= TITLE_SIMILARITY:
        return decision(
            ACTION_KEPT, REASON_TITLE_SUSPICION, f"Titel zu {ratio:.2f} ähnlich zu '{matched}'"
        )

    return decision(ACTION_ACCEPTED, REASON_NEW, f"neu → papers/{pdf.name}")


def _apply(
    decision: IntakeDecision, pdf: Path, papers_path: Path, *, delete_duplicates: bool
) -> None:
    """Führt die zu einer Entscheidung gehörende Dateioperation aus."""
    if decision.action == ACTION_DELETED:
        pdf.unlink()
    elif decision.action == ACTION_QUARANTINED:
        if delete_duplicates:
            pdf.unlink()
        else:
            quarantine = pdf.parent / QUARANTINE_DIR
            quarantine.mkdir(parents=True, exist_ok=True)
            shutil.move(str(pdf), str(quarantine / pdf.name))
    elif decision.action == ACTION_ACCEPTED:
        shutil.move(str(pdf), str(papers_path / pdf.name))


def _attach_flags(decisions: list[IntakeDecision], data_path: Path) -> list[IntakeDecision]:
    """Ergänzt die Qualitäts-Flags der übernommenen Paper (Robustheits-Gate sichtbar machen)."""
    report_path = data_path / "quality_report.json"
    if not report_path.is_file():
        return decisions
    report = json.loads(report_path.read_text(encoding="utf-8"))
    flags_by_name = {
        unquote(Path(urlparse(str(entry["source_uri"])).path).name): tuple(entry["flags"])
        for entry in report.get("papers", [])
    }
    return [
        replace(item, flags=flags_by_name.get(item.filename, ()))
        if item.action == ACTION_ACCEPTED
        else item
        for item in decisions
    ]


def _write_log(data_path: Path, decisions: list[IntakeDecision]) -> None:
    """Schreibt die Entscheidungen append-only nach ``data/intake_log.md``."""
    if not decisions:
        return
    log_path = data_path / INTAKE_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    rows = [
        f"| {stamp} | {item.action} | {item.filename} | {item.sha256} "
        f"| {item.reason}: {item.detail} |"
        for item in decisions
    ]
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        if log_path.stat().st_size == 0:
            handle.write(_LOG_HEADER)
        handle.write("\n".join(rows) + "\n")


def run_intake(
    *,
    inbox_dir: str | Path,
    papers_dir: str | Path,
    data_dir: str | Path,
    uebersicht_path: str | Path,
    dry_run: bool = False,
    delete_identifier_duplicates: bool = False,
) -> IntakeReport:
    """Übernimmt neue PDFs aus dem Eingangsordner in den Korpus.

    Args:
        inbox_dir: Eingangsordner (``new_papers/``); wird **nicht** rekursiv gelesen, die
            Quarantäne bleibt damit außen vor.
        papers_dir: Zielordner des Korpus (``papers/``).
        data_dir: Datenordner mit ``canonical/``, ``manifest.json`` und ``index/``.
        uebersicht_path: Kuratierte ``Übersicht.md`` (wird append-only ergänzt).
        dry_run: Wenn ``True``, wird **nichts** verändert – weder Dateien noch Index, Übersicht
            oder Protokoll.
        delete_identifier_duplicates: Löscht Identifikator-Duplikate hart, statt sie in die
            Quarantäne zu verschieben (ausdrückliches Opt-in, ADR 0019).

    Returns:
        Ein :class:`IntakeReport` mit einer Entscheidung je Datei sowie den Berichten von Ingest
        und Übersicht-Anhang (``None`` bei ``dry_run`` oder wenn nichts übernommen wurde).

    Raises:
        DomainError: ``not_found`` wenn Eingangs- oder ``papers``-Ordner oder die Übersicht
            fehlen; ``constraint_violation`` bei unerwartetem Spaltenlayout der Übersicht
            (siehe docs/error-model.md). Beide Prüfungen laufen **vor** der ersten
            Dateioperation.
    """
    inbox_path = Path(inbox_dir)
    papers_path = Path(papers_dir)
    data_path = Path(data_dir)
    if not inbox_path.is_dir():
        raise DomainError(ErrorCode.NOT_FOUND, f"Eingangsordner fehlt: {inbox_path}")
    if not papers_path.is_dir():
        raise DomainError(ErrorCode.NOT_FOUND, f"papers-Ordner fehlt: {papers_path}")
    ensure_overview_target(uebersicht_path)

    corpus = load_corpus(data_path)
    decisions: list[IntakeDecision] = []
    for pdf in sorted(inbox_path.glob("*.pdf")):
        raw = pdf.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        decision = _classify(pdf, raw, sha256, corpus, papers_path)
        decisions.append(decision)
        if not dry_run:
            _apply(decision, pdf, papers_path, delete_duplicates=delete_identifier_duplicates)

    if dry_run:
        return IntakeReport(decisions=tuple(decisions), dry_run=True, ingest=None, overview=None)

    # Das Protokoll dokumentiert die **Dateischicksale** und wird daher vor dem Index-Neubau
    # geschrieben: Ein Fehler im Ingest darf die Spur der bereits ausgeführten Löschungen und
    # Verschiebungen nicht verschlucken.
    _write_log(data_path, decisions)
    n_accepted = sum(1 for item in decisions if item.action == ACTION_ACCEPTED)
    if not n_accepted:
        return IntakeReport(decisions=tuple(decisions), dry_run=False, ingest=None, overview=None)

    ingest_report = ingest(papers_path, data_path)
    overview_report = append_overview_rows(data_dir=data_path, target_path=uebersicht_path)
    _logger.info(
        "Intake: %d Paper übernommen, %d Übersicht-Zeile(n) ergänzt.",
        n_accepted,
        overview_report.written,
    )
    return IntakeReport(
        decisions=tuple(_attach_flags(decisions, data_path)),
        dry_run=False,
        ingest=ingest_report,
        overview=overview_report,
    )
