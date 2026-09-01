"""Volltext-Download des Online-Modus (Phase 9 / S2): Lizenz-Whitelist, Inhaltsvalidierung.

Lädt **nur** dann automatisch, wenn ein Kandidat (a) eine Lizenz aus :data:`LICENSE_WHITELIST`
trägt **und** (b) der heruntergeladene Inhalt nachweislich zum Kandidaten gehört. Beides ist
bewusst eng gefasst (Präzision vor Recall, docs/adr/0035-fulltext-download-phase9-s2.md): arXiv
weist im Feed nie eine Lizenz aus (S0, ADR 0020) und besteht die Whitelist deshalb nur, wenn ein
OpenAlex-Treffer sie beigesteuert hat (:func:`~.candidates.merge_candidates`); alles außerhalb der
Whitelist bleibt ein Link im Bericht, **nie** ein Download-Versuch.

Die Inhaltsprüfung ist **keine** neue Heuristik, sondern derselbe Titel-Match-Mechanismus, den der
Intake für seine eigene Titel-Verdachtsstufe nutzt (:mod:`research_graphrag.intake`) – nur mit
vertauschten Rollen: viele Titelkandidaten aus dem heruntergeladenen PDF gegen **einen** bekannten
Kandidaten-Titel statt gegen viele Korpus-Titel. Eine volle Canonical-Extraktion (Chunking,
Qualitäts-Gates) findet hier **nicht** statt – das leistet der Intake ohnehin erneut, sobald die
Datei aus ``new_papers/`` übernommen wird.

Geschrieben wird ausschließlich nach ``new_papers/`` – **kein** zweiter Weg in den Korpus, das
Robustheits-Gate des Intake bleibt die eigentliche Absicherung gegen defekte oder textlose
Dateien.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from ..errors import DomainError
from ..indexing.citation_graph import MIN_TITLE_CHARS, MIN_TITLE_WORDS, normalize_title
from ..intake import (
    PDF_MAGIC,
    TITLE_SIMILARITY,
    best_title_match,
    read_front_pages,
    title_candidates,
)
from .candidates import Candidate
from .references import title_slug
from .transport import HttpClient

LICENSE_WHITELIST = frozenset({"public-domain", "cc-by", "cc-by-sa"})
"""Freie Lizenzen, bei denen automatisch geladen wird – CC0 (OpenAlex: ``public-domain``), CC-BY,
CC-BY-SA. Ausschließlich aus OpenAlex' ``primary_location.license`` befüllt (ADR 0035)."""

MAX_DOWNLOAD_BYTES = 104_857_600
"""Obergrenze einer heruntergeladenen Datei (100 MiB): größte Korpus-Datei zum Entscheidungs-
zeitpunkt (53.374.046 Bytes) × 2, gerundet (ADR 0035)."""

MIN_DOWNLOAD_PAGES = 2
"""Mindestseitenzahl; ein einzelnes Abstract-Blatt ist kein Volltext."""

DOWNLOAD_DELAY_SECONDS = 1.0
"""Pause zwischen aufeinanderfolgenden **Netzabrufen** eines Laufs – kein Bulk-Crawl."""

FILENAME_PREFIX = "online"
"""Präfix erzeugter Dateinamen – unterscheidet sie im Eingang von von Hand abgelegten PDFs."""

MAX_ID_SLUG_CHARS = 70
"""Längengrenze des Identifikator-Teils im Dateinamen (danach mit Kurz-Hash gekürzt)."""

OUTCOME_DOWNLOADED = "downloaded"
"""Ergebnis: Datei wurde geschrieben."""

OUTCOME_NO_LICENSE = "no_license"
"""Ergebnis: Der Kandidat weist keine Lizenz aus."""

OUTCOME_LICENSE_NOT_WHITELISTED = "license_not_whitelisted"
"""Ergebnis: Die ausgewiesene Lizenz steht nicht in :data:`LICENSE_WHITELIST`."""

OUTCOME_NO_URL = "no_url"
"""Ergebnis: Der Kandidat weist keinen (brauchbaren) Volltext-Link aus."""

OUTCOME_HTTP_ERROR = "http_error"
"""Ergebnis: Netzfehler oder Statuscode ≠ 200."""

OUTCOME_NOT_A_PDF = "not_a_pdf"
"""Ergebnis: Die Antwort trägt keine PDF-Signatur oder ist nicht parsebar."""

OUTCOME_TOO_SHORT = "too_short"
"""Ergebnis: Weniger als :data:`MIN_DOWNLOAD_PAGES` Seiten – kein Volltext."""

OUTCOME_TITLE_MISMATCH = "title_mismatch"
"""Ergebnis: Kein Titelkandidat aus dem PDF erreicht die Schwelle
:data:`~research_graphrag.intake.TITLE_SIMILARITY` gegen den Kandidaten-Titel."""

_NETWORK_OUTCOMES = frozenset(
    {
        OUTCOME_DOWNLOADED,
        OUTCOME_HTTP_ERROR,
        OUTCOME_NOT_A_PDF,
        OUTCOME_TOO_SHORT,
        OUTCOME_TITLE_MISMATCH,
    }
)
"""Ergebnisse, die einen tatsächlichen GET ausgelöst haben (für das Rate-Limit relevant)."""

_OUTCOME_LABELS = {
    OUTCOME_DOWNLOADED: "geladen",
    OUTCOME_NO_LICENSE: "nicht geladen (keine Lizenz ausgewiesen)",
    OUTCOME_LICENSE_NOT_WHITELISTED: "nicht geladen (Lizenz nicht in der Whitelist)",
    OUTCOME_NO_URL: "nicht geladen (kein Volltext-Link)",
    OUTCOME_HTTP_ERROR: "nicht geladen (Netzfehler)",
    OUTCOME_NOT_A_PDF: "nicht geladen (kein PDF)",
    OUTCOME_TOO_SHORT: "nicht geladen (zu kurz für einen Volltext)",
    OUTCOME_TITLE_MISMATCH: "nicht geladen (Inhalt passt nicht zum Kandidaten)",
}
"""Menschenlesbare Bezeichnung je ``OUTCOME_*``-Konstante – geteilt zwischen Bericht und CLI."""


def describe_outcome(outcome: str) -> str:
    """Übersetzt eine ``OUTCOME_*``-Konstante in eine menschenlesbare Bezeichnung."""
    return _OUTCOME_LABELS.get(outcome, outcome)


_ID_SLUG_ALLOWED = re.compile(r"[^a-z0-9._-]+")


@dataclass(frozen=True)
class DownloadOutcome:
    """Ergebnis eines Download-Versuchs für **einen** Kandidaten.

    Attributes:
        candidate: Der betroffene Kandidat – Identifikator und Link bleiben im Bericht unabhängig
            von diesem Ergebnis sichtbar.
        outcome: Eine der ``OUTCOME_*``-Konstanten.
        note: Klartext-Begründung (z. B. die tatsächliche Lizenzangabe, der HTTP-Status).
        path: Die geschriebene Datei, sofern ``outcome == OUTCOME_DOWNLOADED``.
    """

    candidate: Candidate
    outcome: str
    note: str = ""
    path: Path | None = None


def is_whitelisted_license(license_value: str) -> bool:
    """Prüft, ob eine Lizenzangabe in :data:`LICENSE_WHITELIST` steht."""
    return license_value.strip().lower() in LICENSE_WHITELIST


def pdf_filename(candidate: Candidate) -> str:
    """Bildet einen selbst erzeugten Dateinamen – nie aus der Serverantwort.

    Dasselbe Muster wie ``references.stub_filename`` (Titel-Slug über eine Whitelist von Zeichen
    plus Identifikator, Kurz-Hash bei Überlänge) – kein Pfad-Traversal möglich, weil kein Zeichen
    aus der Antwort in den Namen gelangt.

    Args:
        candidate: Der geladene Kandidat.

    Returns:
        Den Dateinamen inklusive ``.pdf``-Endung.
    """
    if candidate.arxiv_id:
        raw_identifier = f"arxiv-{candidate.arxiv_id}"
    elif candidate.doi:
        raw_identifier = f"doi-{candidate.doi}"
    else:
        raw_identifier = "kandidat"
    identifier = _ID_SLUG_ALLOWED.sub("_", raw_identifier.lower()).strip("_-")
    if len(identifier) > MAX_ID_SLUG_CHARS:
        digest = _short_digest(raw_identifier)
        identifier = f"{identifier[:MAX_ID_SLUG_CHARS]}-{digest}"
    slug = title_slug(candidate.title)
    parts = [FILENAME_PREFIX, slug, identifier] if slug else [FILENAME_PREFIX, identifier]
    return "-".join(parts) + ".pdf"


def _short_digest(text: str) -> str:
    """Kurzer, stabiler Hash für gekürzte Dateinamen."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _content_mismatch(raw: bytes, candidate: Candidate) -> tuple[str, str] | None:
    """Prüft, ob der heruntergeladene Inhalt zum Kandidaten passt.

    Args:
        raw: Rumpf der Antwort (bereits als PDF signiert erkannt).
        candidate: Der angefragte Kandidat.

    Returns:
        ``None`` bei bestandener Prüfung, sonst ``(Outcome, Begründung)``.
    """
    try:
        n_pages = len(PdfReader(io.BytesIO(raw)).pages)
    except (PyPdfError, KeyError, ValueError) as exc:
        return (OUTCOME_NOT_A_PDF, f"PDF nicht lesbar: {exc}")
    if n_pages < MIN_DOWNLOAD_PAGES:
        return (OUTCOME_TOO_SHORT, f"nur {n_pages} Seite(n) – kein Volltext")

    try:
        front_pages = read_front_pages(raw)
    except DomainError as exc:
        return (OUTCOME_NOT_A_PDF, exc.message)

    normalized_title = normalize_title(candidate.title)
    if len(normalized_title) < MIN_TITLE_CHARS or len(normalized_title.split()) < MIN_TITLE_WORDS:
        return (OUTCOME_TITLE_MISMATCH, "Kandidaten-Titel zu kurz für einen belastbaren Vergleich")

    guesses = title_candidates("", front_pages)
    ratio, _ = best_title_match(guesses, {normalized_title: candidate.title})
    if ratio < TITLE_SIMILARITY:
        return (
            OUTCOME_TITLE_MISMATCH,
            f"Titel-Ähnlichkeit {ratio:.2f} < {TITLE_SIMILARITY} – vermutlich falsches PDF",
        )
    return None


def download_candidate(client: HttpClient, inbox: Path, candidate: Candidate) -> DownloadOutcome:
    """Prüft und lädt **einen** Kandidaten, sofern Lizenz und Inhalt es zulassen.

    Reihenfolge bewusst so gewählt, dass aussichtslose Fälle vor jedem Netzzugriff enden (kein
    Kontingent-/Zeitverbrauch für ohnehin verworfene Kandidaten).

    Args:
        client: Injizierter Transport-Port.
        inbox: Eingangsordner (üblicherweise ``new_papers/``).
        candidate: Der zu ladende Kandidat.

    Returns:
        Das Ergebnis; bei Erfolg mit dem Pfad der geschriebenen Datei.
    """
    if not candidate.license:
        return DownloadOutcome(candidate, OUTCOME_NO_LICENSE, "keine Lizenz ausgewiesen")
    if not is_whitelisted_license(candidate.license):
        return DownloadOutcome(
            candidate,
            OUTCOME_LICENSE_NOT_WHITELISTED,
            f"Lizenz {candidate.license!r} nicht in der Whitelist",
        )
    if not candidate.url.startswith(("https://", "http://")):
        return DownloadOutcome(candidate, OUTCOME_NO_URL, "kein Volltext-Link ausgewiesen")

    try:
        response = client.get(candidate.url, accept="application/pdf", max_bytes=MAX_DOWNLOAD_BYTES)
    except DomainError as exc:
        return DownloadOutcome(candidate, OUTCOME_HTTP_ERROR, exc.message)
    if response.status != 200:
        return DownloadOutcome(candidate, OUTCOME_HTTP_ERROR, f"HTTP {response.status}")
    if not response.body.startswith(PDF_MAGIC):
        return DownloadOutcome(candidate, OUTCOME_NOT_A_PDF, "Antwort trägt keine PDF-Signatur")

    mismatch = _content_mismatch(response.body, candidate)
    if mismatch is not None:
        return DownloadOutcome(candidate, mismatch[0], mismatch[1])

    path = _write_pdf(inbox, response.body, pdf_filename(candidate))
    return DownloadOutcome(candidate, OUTCOME_DOWNLOADED, f"{len(response.body)} Bytes", path)


def _write_pdf(inbox: Path, data: bytes, filename: str) -> Path:
    """Schreibt eine PDF-Datei atomar in den Eingangsordner."""
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / filename
    tmp_path = target.with_name(target.name + ".tmp")
    try:
        tmp_path.write_bytes(data)
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)
    return target


def download_all(
    client: HttpClient, inbox: Path, candidates: Sequence[Candidate]
) -> tuple[DownloadOutcome, ...]:
    """Versucht für jeden übergebenen Kandidaten einen Download.

    Ein Fehlschlag bei einem Kandidaten bricht den Lauf **nicht** ab. Die Pause aus
    :data:`DOWNLOAD_DELAY_SECONDS` steht nur **zwischen** tatsächlichen Netzabrufen – ein
    Kandidat, der schon am Lizenz- oder Link-Check scheitert, verzögert die folgenden nicht.

    Args:
        client: Injizierter Transport-Port.
        inbox: Eingangsordner (üblicherweise ``new_papers/``).
        candidates: Die zu versuchenden Kandidaten (üblicherweise ``report.fresh``).

    Returns:
        Ein Ergebnis je Kandidat, in derselben Reihenfolge.
    """
    outcomes: list[DownloadOutcome] = []
    did_network = False
    for candidate in candidates:
        if did_network:
            time.sleep(DOWNLOAD_DELAY_SECONDS)
        outcome = download_candidate(client, inbox, candidate)
        did_network = outcome.outcome in _NETWORK_OUTCOMES
        outcomes.append(outcome)
    return tuple(outcomes)
