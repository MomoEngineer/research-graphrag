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
:func:`research_graphrag.pipeline.ingest` (voller Re-Index mit atomarem Swap). Seit Phase 15 / G4
bekommt die kuratierte Übersicht dabei **keine** Entwurfszeile mehr – sie ist außer Dienst
gesetzt, das einzige menschliche Relevanzurteil (Themenfokus, Relevanz, SRQ-Zuordnung) liegt
maschinenlesbar in ``metadata/curation.json``
(docs/adr/0034-decommission-uebersicht-and-inflow-stop-rule-phase15.md). Nur eine bereits
bestehende Zeile wird beim Stub-Upgrade weiterhin **umgebogen** (nicht neu angelegt), damit sie
nicht auf eine gelöschte Datei zeigt. ``dry_run`` verändert **nichts**.

Seit Phase 13 / R2 nimmt der Eingang **zwei Dokumenttypen** an: ``*.pdf`` und ``*.refjson``
(Referenz-Einträge ohne Volltext). Die drei Prüfstufen gelten unverändert für beide – nur die
Eingangsseite unterscheidet sich: Für einen Stub kommen Titel und Identifikatoren **aus der
Datei**, nicht aus einer Heuristik über die Titelseite. Neu ist eine Regel, ohne die das
Standardverhalten falsch wäre: **Volltext schlägt Referenz-Eintrag**
(docs/adr/0030-reference-entries-in-corpus-phase13.md).
"""

from __future__ import annotations

import difflib
import hashlib
import io
import json
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import (
    DOCUMENT_KIND_REFERENCE,
    CanonicalPaper,
)
from research_graphrag.extraction.normalization import normalize_text
from research_graphrag.extraction.refstub import STUB_SUFFIX, ReferenceStub, parse_stub
from research_graphrag.extraction.structure import extract_identifiers
from research_graphrag.indexing.citation_graph import (
    MIN_TITLE_CHARS,
    MIN_TITLE_WORDS,
    TITLE_PAGE_PAGES,
    front_matter_text,
    normalize_title,
    title_from_uri,
    title_of,
)
from research_graphrag.overview.drafts import (
    OverviewReport,
    ensure_overview_target,
    retarget_overview_row,
)
from research_graphrag.pipeline import IngestReport, forget_source, ingest

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

MAX_STUB_NAME_CHARS = 120
"""Längengrenze des aus dem Titel erzeugten Stub-Dateinamens (ohne Endung)."""

_FORBIDDEN_NAME_CHARS = '<>:"/\\|?*'

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
REASON_INVALID_STUB = "invalid_stub"
"""Grund: Die ``*.refjson`` ist kein brauchbarer Referenz-Eintrag (Formatprüfung)."""

REASON_UPGRADE = "upgrade_from_reference"
"""Grund: Ein Volltext-PDF ersetzt einen vorhandenen Referenz-Eintrag."""

REASON_SUPERSEDED = "superseded_by_full_text"
"""Grund der Gegenbuchung: Der Referenz-Eintrag wurde durch den Volltext abgelöst."""

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
    """Entscheidung über **eine** Datei des Eingangsordners.

    Attributes:
        filename: Name der Eingangsdatei.
        sha256: Hash der Eingangsdatei.
        action: Eine der ``ACTION_*``-Konstanten.
        reason: Eine der ``REASON_*``-Konstanten.
        detail: Klartext-Begründung.
        flags: Qualitäts-Flags des übernommenen Papers (erst nach dem Ingest bekannt).
        target_name: Name im Korpus, falls er vom Eingangsnamen abweicht – ein Referenz-Eintrag
            wird nach seinem **Titel** benannt, damit die Konvention „Dateiname = Titel" gilt.
        replaces: Name des abgelösten Referenz-Eintrags in ``papers/`` (Upgrade-Pfad).
        superseded_sha256: Hash des abgelösten Referenz-Eintrags – die forensische Spur der
            einzigen Löschung, die in ``papers/`` stattfindet.
    """

    filename: str
    sha256: str
    action: str
    reason: str
    detail: str
    flags: tuple[str, ...] = ()
    target_name: str = ""
    replaces: str = ""
    superseded_sha256: str = ""

    @property
    def corpus_name(self) -> str:
        """Der Name, unter dem die Datei im Korpus liegt (bzw. läge)."""
        return self.target_name or self.filename

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Entscheidung (stabile Schlüssel für Bericht und Tests)."""
        return {
            "filename": self.filename,
            "sha256": self.sha256,
            "action": self.action,
            "reason": self.reason,
            "detail": self.detail,
            "flags": list(self.flags),
            "target_name": self.target_name,
            "replaces": self.replaces,
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
        reference_papers: ``paper_id`` → Dateiname der **Referenz-Einträge** im Korpus. Nur sie
            dürfen von einem eintreffenden Volltext abgelöst werden
            (docs/adr/0030-reference-entries-in-corpus-phase13.md).
    """

    sha256_to_name: dict[str, str]
    identifier_to_paper: dict[tuple[str, str], str]
    titles: dict[str, str]
    reference_papers: dict[str, str] = field(default_factory=dict)


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


def _identifier_keys(papers: list[CanonicalPaper]) -> dict[tuple[str, str], str]:
    """Baut die **gehärteten** Duplikat-Schlüssel ``(art, wert) → paper_id``.

    Zwei Bedingungen, beide am realen Korpus begründet
    (docs/adr/0019-corpus-intake-new-papers-phase8.md):

    1. **Frontmatter-Beleg** – der Wert steht auf der eigenen Titelseite außerhalb der
       Bibliografie. Ohne diese Bedingung zeigen fehl-extrahierte, *zitierte* fremde
       Identifikatoren auf das falsche Paper. Genutzt wird derselbe Guard wie im
       Zitationsgraphen – er kennt auch den Sonderfall des Referenz-Eintrags, dessen
       Identifikatoren aus der Datei selbst stammen.
    2. **Eindeutigkeit** – Werte mit mehreren Trägern (z. B. der unausgefüllte
       ACM-Vorlagen-Platzhalter) sind **kein** Duplikat-Kriterium.
    """
    owners: dict[tuple[str, str], set[str]] = {}
    for paper in papers:
        front = front_matter_text(paper)
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


def _reference_papers(papers: list[CanonicalPaper]) -> dict[str, str]:
    """Bildet ``paper_id → Dateiname`` für alle Referenz-Einträge des Korpus."""
    return {
        paper.paper_id: unquote(Path(urlparse(paper.source_uri).path).name)
        for paper in papers
        if paper.document_kind == DOCUMENT_KIND_REFERENCE
    }


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
        reference_papers=_reference_papers(papers),
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


def safe_stub_name(title: str) -> str:
    """Bildet aus dem Titel einen dateisystemsicheren Namen für einen Referenz-Eintrag.

    Der Titel ist eine fremde Zeichenkette, der Name entsteht deshalb über eine **Filterung**:
    Pfadtrennzeichen und die unter Windows verbotenen Zeichen entfallen, Whitespace wird
    verdichtet, die Länge begrenzt. Damit gilt für Stubs dieselbe Konvention wie für PDFs –
    **der Dateiname ist der Titel** (docs/adr/0030-reference-entries-in-corpus-phase13.md).

    Args:
        title: Titel aus der Stub-Datei.

    Returns:
        Den Dateinamen inklusive :data:`~research_graphrag.extraction.refstub.STUB_SUFFIX`.
    """
    printable = "".join(
        " " if char in _FORBIDDEN_NAME_CHARS or not char.isprintable() else char for char in title
    )
    cleaned = " ".join(printable.split())[:MAX_STUB_NAME_CHARS].strip(" .")
    return f"{cleaned or 'Referenz-Eintrag'}{STUB_SUFFIX}"


def _decision(
    filename: str,
    sha256: str,
    action: str,
    reason: str,
    detail: str,
    *,
    target_name: str = "",
    replaces: str = "",
) -> IntakeDecision:
    """Baut eine Entscheidung (Hilfsform, damit die Zweige lesbar bleiben)."""
    return IntakeDecision(
        filename=filename,
        sha256=sha256,
        action=action,
        reason=reason,
        detail=detail,
        target_name=target_name,
        replaces=replaces,
    )


def _classify_identifiers(
    identifiers: dict[str, str], corpus: CorpusView, *, is_full_text: bool
) -> tuple[str, str, str] | None:
    """Prüft die Identifikatoren gegen den Korpus (Stufe 2).

    Trifft ein **Volltext** auf einen **Referenz-Eintrag**, ist die Antwort nicht „Duplikat",
    sondern „Upgrade": Ohne diese Unterscheidung wanderte das echte Paper in die Quarantäne,
    während der Abstract-Stub im Korpus bliebe – genau verkehrt herum.

    Returns:
        ``(Grund, Detail, abgelöster Dateiname)`` – der dritte Wert ist nur beim Upgrade gesetzt;
        ``None``, wenn kein Identifikator im Korpus liegt.
    """
    for kind, value in sorted(identifiers.items()):
        owner = corpus.identifier_to_paper.get((kind, value.lower()))
        if owner is None:
            continue
        stub_name = corpus.reference_papers.get(owner)
        if is_full_text and stub_name is not None:
            return (
                REASON_UPGRADE,
                f"{kind}:{value} ersetzt den Referenz-Eintrag {stub_name}",
                stub_name,
            )
        return (
            REASON_DUPLICATE_IDENTIFIER,
            f"{kind}:{value} bereits im Korpus (Paper {owner})",
            "",
        )
    return None


def _classify_pdf(
    path: Path, raw: bytes, sha256: str, corpus: CorpusView, papers_path: Path
) -> IntakeDecision:
    """Entscheidet über eine eingehende PDF – rein lesend, ohne Seiteneffekt."""
    if not raw.startswith(PDF_MAGIC):
        return _decision(
            path.name, sha256, ACTION_KEPT, REASON_NOT_A_PDF, "Datei trägt keine PDF-Signatur"
        )
    try:
        front_pages = read_front_pages(raw)
    except DomainError as exc:
        return _decision(path.name, sha256, ACTION_KEPT, REASON_UNREADABLE, exc.message)

    verdict = _classify_identifiers(
        extract_identifiers("\n".join(front_pages)), corpus, is_full_text=True
    )
    if verdict is not None:
        reason, detail, replaced = verdict
        if reason == REASON_UPGRADE:
            return _decision(
                path.name, sha256, ACTION_ACCEPTED, REASON_UPGRADE, detail, replaces=replaced
            )
        return _decision(path.name, sha256, ACTION_QUARANTINED, reason, detail)

    # Die Namenskollision wird **vor** der Verdachtsstufe geprüft: Sie ist eine Tatsache über den
    # Zielort, keine Vermutung – und sie ist die handlungsleitendere Meldung.
    if (papers_path / path.name).exists():
        return _decision(
            path.name,
            sha256,
            ACTION_KEPT,
            REASON_NAME_COLLISION,
            f"papers/{path.name} existiert mit anderem Inhalt",
        )

    ratio, matched = best_title_match(title_candidates(path.name, front_pages), corpus.titles)
    if ratio >= TITLE_SIMILARITY:
        return _decision(
            path.name,
            sha256,
            ACTION_KEPT,
            REASON_TITLE_SUSPICION,
            f"Titel zu {ratio:.2f} ähnlich zu '{matched}'",
        )
    return _decision(path.name, sha256, ACTION_ACCEPTED, REASON_NEW, f"neu → papers/{path.name}")


def _classify_stub(
    path: Path, raw: bytes, sha256: str, corpus: CorpusView, papers_path: Path
) -> IntakeDecision:
    """Entscheidet über einen eingehenden Referenz-Eintrag.

    Die Eingangsseite ist hier **genauer** als bei einem PDF: Titel und Identifikatoren stehen in
    der Datei, es braucht keine Heuristik über eine Titelseite. Die drei Prüfstufen bleiben
    dieselben.
    """
    try:
        stub: ReferenceStub = parse_stub(raw)
    except DomainError as exc:
        return _decision(path.name, sha256, ACTION_KEPT, REASON_INVALID_STUB, exc.message)

    verdict = _classify_identifiers(stub.identifiers, corpus, is_full_text=False)
    if verdict is not None:
        reason, detail, _ = verdict
        return _decision(path.name, sha256, ACTION_QUARANTINED, reason, detail)

    target_name = safe_stub_name(stub.title)
    if (papers_path / target_name).exists():
        return _decision(
            path.name,
            sha256,
            ACTION_KEPT,
            REASON_NAME_COLLISION,
            f"papers/{target_name} existiert mit anderem Inhalt",
            target_name=target_name,
        )

    normalized = normalize_title(stub.title)
    candidates = (
        [normalized]
        if len(normalized) >= MIN_TITLE_CHARS and len(normalized.split()) >= MIN_TITLE_WORDS
        else []
    )
    ratio, matched = best_title_match(candidates, corpus.titles)
    if ratio >= TITLE_SIMILARITY:
        return _decision(
            path.name,
            sha256,
            ACTION_KEPT,
            REASON_TITLE_SUSPICION,
            f"Titel zu {ratio:.2f} ähnlich zu '{matched}'",
            target_name=target_name,
        )
    return _decision(
        path.name,
        sha256,
        ACTION_ACCEPTED,
        REASON_NEW,
        f"neu → papers/{target_name}",
        target_name=target_name,
    )


def _classify(
    path: Path, raw: bytes, sha256: str, corpus: CorpusView, papers_path: Path
) -> IntakeDecision:
    """Entscheidet über **eine** Eingangsdatei – rein lesend, ohne Seiteneffekt.

    Stufe 1 (sha256) ist dateiformatunabhängig und gilt deshalb vor der Typunterscheidung: Wird
    eine Datei aus ``papers/`` entfernt, ohne neu zu indizieren, zeigt der Manifest-Eintrag ins
    Leere – und die einzige verbliebene Kopie würde vernichtet. Deshalb wird der Beleg am
    Dateisystem nachgerechnet (Existenz **und** Hash), bevor gelöscht wird.
    """
    known_name = corpus.sha256_to_name.get(sha256)
    if known_name is not None and _same_file(papers_path / known_name, sha256):
        return _decision(
            path.name,
            sha256,
            ACTION_DELETED,
            REASON_DUPLICATE_SHA256,
            f"byte-identisch zu papers/{known_name}",
        )
    if path.suffix.lower() == STUB_SUFFIX:
        return _classify_stub(path, raw, sha256, corpus, papers_path)
    return _classify_pdf(path, raw, sha256, corpus, papers_path)


def _apply(
    decision: IntakeDecision, path: Path, papers_path: Path, *, delete_duplicates: bool
) -> None:
    """Führt die zu einer Entscheidung gehörende Dateioperation aus."""
    if decision.action == ACTION_DELETED:
        path.unlink()
    elif decision.action == ACTION_QUARANTINED:
        if delete_duplicates:
            path.unlink()
        else:
            quarantine = path.parent / QUARANTINE_DIR
            quarantine.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(quarantine / path.name))
    elif decision.action == ACTION_ACCEPTED:
        shutil.move(str(path), str(papers_path / decision.corpus_name))
        if decision.replaces:
            # „Volltext schlägt Referenz-Eintrag": die einzige Löschung in ``papers/`` – und die
            # einzige, die konstruktionsbedingt unbedenklich ist, weil ein Stub aus
            # ``new_papers/referenzen.txt`` jederzeit neu entsteht.
            (papers_path / decision.replaces).unlink(missing_ok=True)


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
        replace(item, flags=flags_by_name.get(item.corpus_name, ()))
        if item.action == ACTION_ACCEPTED
        else item
        for item in decisions
    ]


def _superseded_entry(decision: IntakeDecision, papers_path: Path) -> tuple[str, str] | None:
    """Liefert ``(Dateiname, sha256)`` des abgelösten Referenz-Eintrags – **vor** dem Löschen.

    Der Hash ist der Kern der forensischen Spur: Nur mit ihm ist im Nachhinein belegbar, welche
    Datei genau verschwunden ist (docs/adr/0019-corpus-intake-new-papers-phase8.md).
    """
    if not decision.replaces:
        return None
    stub_path = papers_path / decision.replaces
    if not stub_path.is_file():
        return None
    return (decision.replaces, hashlib.sha256(stub_path.read_bytes()).hexdigest())


def _write_log(data_path: Path, decisions: list[IntakeDecision]) -> None:
    """Schreibt die Entscheidungen append-only nach ``data/intake_log.md``."""
    if not decisions:
        return
    log_path = data_path / INTAKE_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    rows: list[str] = []
    for item in decisions:
        rows.append(
            f"| {stamp} | {item.action} | {item.corpus_name} | {item.sha256} "
            f"| {item.reason}: {item.detail} |"
        )
        # Der Upgrade-Pfad löscht eine Datei in ``papers/`` – diese Löschung bekommt eine eigene
        # Zeile mit eigenem Hash, statt in der Begründung des Nachfolgers unterzugehen.
        if item.superseded_sha256:
            rows.append(
                f"| {stamp} | {ACTION_DELETED} | {item.replaces} | {item.superseded_sha256} "
                f"| {REASON_SUPERSEDED}: abgelöst durch {item.corpus_name} |"
            )
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
    on_file: Callable[[str, int, int], None] | None = None,
    on_ingest_start: Callable[[], None] | None = None,
) -> IntakeReport:
    """Übernimmt neue Dateien aus dem Eingangsordner in den Korpus.

    Angenommen werden ``*.pdf`` und ``*.refjson`` (Referenz-Einträge ohne Volltext). Trifft ein
    Volltext auf einen vorhandenen Referenz-Eintrag, wird er **übernommen** und der Stub
    abgelöst (docs/adr/0030-reference-entries-in-corpus-phase13.md).

    Args:
        inbox_dir: Eingangsordner (``new_papers/``); wird **nicht** rekursiv gelesen, die
            Quarantäne bleibt damit außen vor.
        papers_dir: Zielordner des Korpus (``papers/``).
        data_dir: Datenordner mit ``canonical/``, ``manifest.json`` und ``index/``.
        uebersicht_path: Außer Dienst gestellte ``Übersicht.md`` (Phase 15 / G4) – bekommt
            **keine** neuen Zeilen mehr; eine bereits bestehende Zeile wird beim Stub-Upgrade
            weiterhin umgebogen, damit sie nicht auf eine gelöschte Datei zeigt.
        dry_run: Wenn ``True``, wird **nichts** verändert – weder Dateien noch Index oder
            Protokoll.
        delete_identifier_duplicates: Löscht Identifikator-Duplikate hart, statt sie in die
            Quarantäne zu verschieben (ausdrückliches Opt-in, ADR 0019).

    Returns:
        Ein :class:`IntakeReport` mit einer Entscheidung je Datei sowie dem Ingest-Bericht.
        ``overview`` ist seit G4 immer ``None`` – das Feld bleibt aus Kompatibilitätsgründen
        bestehen, wird aber nicht mehr befüllt.

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
    sources = sorted(
        [*inbox_path.glob("*.pdf"), *inbox_path.glob(f"*{STUB_SUFFIX}")],
        key=lambda item: item.name,
    )
    total = len(sources)
    for i, source in enumerate(sources):
        if on_file is not None:
            on_file(source.name, i + 1, total)
        raw = source.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        decision = _classify(source, raw, sha256, corpus, papers_path)
        # Der Hash des abzulösenden Stubs muss **vor** der Dateioperation feststehen.
        superseded = _superseded_entry(decision, papers_path)
        if superseded is not None:
            decision = replace(decision, superseded_sha256=superseded[1])
        decisions.append(decision)
        if not dry_run:
            _apply(decision, source, papers_path, delete_duplicates=delete_identifier_duplicates)

    if dry_run:
        return IntakeReport(decisions=tuple(decisions), dry_run=True, ingest=None, overview=None)

    # Das Protokoll dokumentiert die **Dateischicksale** und wird daher vor dem Index-Neubau
    # geschrieben: Ein Fehler im Ingest darf die Spur der bereits ausgeführten Löschungen und
    # Verschiebungen nicht verschlucken.
    _write_log(data_path, decisions)
    n_accepted = sum(1 for item in decisions if item.action == ACTION_ACCEPTED)
    if not n_accepted:
        return IntakeReport(decisions=tuple(decisions), dry_run=False, ingest=None, overview=None)

    if on_ingest_start is not None:
        on_ingest_start()
    # Der abgelöste Referenz-Eintrag muss **vor** dem Re-Index vergessen werden: Sein Canonical
    # bliebe sonst als Waise liegen und das Paper erschiene doppelt.
    for item in decisions:
        if item.action == ACTION_ACCEPTED and item.replaces:
            forget_source(data_path, item.replaces)
    ingest_report = ingest(papers_path, data_path)
    # Umbiegen statt Neuanlage: Die Übersicht ist außer Dienst (G4), eine bestehende Zeile darf
    # aber nicht auf eine gelöschte Datei zeigen.
    for item in decisions:
        if item.action == ACTION_ACCEPTED and item.replaces:
            retarget_overview_row(
                uebersicht_path,
                old_filename=item.replaces,
                new_filename=item.corpus_name,
                new_name=title_from_uri(item.corpus_name),
            )
    _logger.info("Intake: %d Paper übernommen.", n_accepted)
    return IntakeReport(
        decisions=tuple(_attach_flags(decisions, data_path)),
        dry_run=False,
        ingest=ingest_report,
        overview=None,
    )
