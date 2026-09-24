"""CLI: Gezielte Themensuche "Konfiguration von Systemen, speziell Routern".

Einmaliger Recherche-Lauf zur Anreicherung des Korpus um die **klassische, empirische und
grundlegende** Literatur zur Konfiguration von Systemen – mit Schwerpunkt Router/Netzwerkgeräte:
Fehlkonfigurationsstudien, Komplexitätsmessung und die Ursprünge des Konfigurationsmanagements als
Forschungsfeld. Abgegrenzt von den bereits gut abgedeckten Nachbarthemen im Korpus
(`python -m scripts.graph_info`): Community 1 (LLM-basierte Netzwerk-Konfigurationssynthese/
-verifikation), Community 14 (Cloud-IaC-Codequalität) und dem separaten, ebenfalls bereits
umgesetzten Lauf :mod:`scripts.router_template_recherche` (Template-/Configlet-Systeme wie PRESTO
und NETCONF/YANG). Dieser Lauf ergänzt zwei Aspekte, die dort **nicht** vertreten waren:

1. **Empirische Fehlkonfigurationsstudien** – wie oft, warum und mit welcher Wirkung
   Router-/Netzwerkkonfigurationen in der Praxis fehlschlagen (Mahajan et al. 2002, Kim et al.
   2011, Benson et al. 2009, Yin et al. 2011).
2. **Die Gründungsarbeit des Konfigurationsmanagements** als eigenes Forschungsfeld (Burgess 1995,
   Cfengine) – im Korpus bislang nur über nachgelagerte Werkzeuge (Ansible, Terraform, Puppet)
   vertreten, nie über ihren gemeinsamen Ursprung.

Wie :mod:`scripts.jinja2_recherche`/:mod:`scripts.router_template_recherche` leitet dieser Lauf
seine Anfragen **nicht** aus dem eigenen Bestand ab (:mod:`scripts.discover`, ADR 0020), sondern aus
handkuratierter Recherche. Wiederverwendet werden dieselben, bereits getesteten Bausteine aus
``research_graphrag.online``: Korpus-Abgleich (Intake-Logik), Inhaltsprüfung beim Download und
Bericht.

**Befund der Vorabrecherche:** Alle fünf kuratierten Kandidaten sind vor der ACM/IEEE-Paywall-Ära
bzw. über die **eigene, seit jeher offene Archiv-Seite** ihres Verlags/ihrer Tagung frei zugänglich
(USENIX-, ACM-SIGCOMM- bzw. ACM-SIGOPS-eigenes Archiv, oder die Autoren-Homepage) – anders als bei
``router_template_recherche.py`` war hier **kein** Kandidat hinter einer Paywall ohne freien
Zugang, daher entfällt ein Eintrag in ``new_papers/referenzen.txt``.

**Zwei Kandidaten mit sehr kurzem Titel** ("Understanding BGP Misconfiguration",
"A Site Configuration Engine" – je drei bis vier inhaltstragende Wörter) unterschreiten
``MIN_TITLE_WORDS`` (5) aus ``research_graphrag.intake`` und lösen deshalb **immer**
``OUTCOME_TITLE_MISMATCH`` aus ("Kandidaten-Titel zu kurz für einen belastbaren Vergleich") – die
Inhaltsprüfung verweigert bei solchen Titeln bewusst ein automatisches Urteil, statt eines mit
unzuverlässiger Grundlage. Für diese zwei Fälle wurde die Übereinstimmung von Hand geprüft (PDF-
Signatur, Autorennamen und Titel im extrahierten Fronttext, Abgleich mit OpenAlex/DOI) und die
Datei anschließend direkt über ``research_graphrag.online.download._write_pdf`` abgelegt statt über
``download_curated`` – nachvollziehbar in der Commit-Historie dieses Laufs, nicht automatisiert
wiederholbar.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.router_config_recherche --dry-run
    python -m scripts.router_config_recherche --download

Bewusst wie ``scripts.discover``/``scripts.jinja2_recherche``/``scripts.router_template_recherche``
**kein** MCP-Werkzeug und immer von Hand gestartet – Netzverkehr soll eine beobachtete Handlung
bleiben.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from research_graphrag.errors import DomainError
from research_graphrag.indexing.citation_graph import (
    MIN_TITLE_CHARS,
    MIN_TITLE_WORDS,
    normalize_title,
)
from research_graphrag.intake import (
    PDF_MAGIC,
    TITLE_SIMILARITY,
    best_title_match,
    load_corpus,
    read_front_pages,
    title_candidates,
)
from research_graphrag.online.candidates import Candidate, partition
from research_graphrag.online.download import (
    MAX_DOWNLOAD_BYTES,
    OUTCOME_DOWNLOADED,
    OUTCOME_HTTP_ERROR,
    OUTCOME_NO_URL,
    OUTCOME_NOT_A_PDF,
    OUTCOME_TITLE_MISMATCH,
    OUTCOME_TOO_SHORT,
    DownloadOutcome,
    _write_pdf,
    describe_outcome,
)
from research_graphrag.online.transport import HttpClient, create_client

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA = _REPO_ROOT / "data"
_DEFAULT_INBOX = _REPO_ROOT / "new_papers"

# Von Hand recherchiert (WebSearch + OpenAlex-DOI-Gegenprobe der oa_status-Angabe, 2026-09-24) und
# geprüft. Jeder Eintrag ist über seine URL einzeln nachvollziehbar; keiner trägt einen DOI-/
# arXiv-Auflösungsschritt, da alle Volltext-URLs bereits direkt first-party (Verlags-/
# Tagungsarchiv oder Autoren-Homepage) und geprüft frei zugänglich sind.
CURATED: tuple[dict[str, str], ...] = (
    {
        "title": "Understanding BGP Misconfiguration",
        "year": "2002",
        "url": "https://homes.cs.washington.edu/~tom/pubs/misconfig.pdf",
        "reason": (
            "Mahajan, Wetherall, Anderson (ACM SIGCOMM 2002): erste quantitative Studie zu "
            "BGP-Fehlkonfigurationen im Internet-Backbone – die Gründungsarbeit der empirischen "
            "Router-Fehlkonfigurationsforschung. DOI 10.1145/633025.633027, bei OpenAlex "
            "oa_status: gold; hier von der Autoren-Homepage geladen."
        ),
    },
    {
        "title": "The Evolution of Network Configuration",
        "year": "2011",
        "url": "https://conferences.sigcomm.org/imc/2011/docs/p499.pdf",
        "reason": (
            "Kim, Benson, Akella, Feamster (ACM IMC 2011, Untertitel „A Tale of Two Campuses“): "
            "fünf Jahre Router-/Switch-/Firewall-Konfigurationshistorie zweier Campusnetze aus "
            "Versionskontroll-Logs. DOI 10.1145/2068816.2068863, bei OpenAlex oa_status: closed "
            "– hier vom eigenen, seit jeher offenen Archiv der Tagung (ACM SIGCOMM) geladen."
        ),
    },
    {
        "title": "Unraveling the Complexity of Network Management",
        "year": "2009",
        "url": "https://www.usenix.org/legacy/event/nsdi09/tech/full_papers/benson/benson.pdf",
        "reason": (
            "Benson, Akella, Maltz (USENIX NSDI 2009): Komplexitätsmodelle für Routing-Design "
            "und -Konfiguration, gemessen gegen reale Netzwerkkonfigurationen."
        ),
    },
    {
        "title": "An Empirical Study on Configuration Errors in Commercial and Open Source Systems",
        "year": "2011",
        "url": "https://www.sigops.org/s/conferences/sosp/2011/current/2011-Cascais/printable/12-yin.pdf",
        "reason": (
            "Yin, Ma, Zheng, Zhou, Bairavasundaram, Pasupathy (ACM SOSP 2011): 546 reale "
            "Fehlkonfigurationen aus einem kommerziellen Speichersystem und vier verbreiteten "
            "Open-Source-Systemen – Referenzarbeit für Konfigurationsfehler jenseits von "
            "Netzwerkgeräten. DOI 10.1145/2043556.2043572, bei OpenAlex oa_status: closed – "
            "hier vom eigenen Archiv der Tagung (ACM SIGOPS) geladen."
        ),
    },
    {
        "title": "A Site Configuration Engine",
        "year": "1995",
        "url": "https://www.usenix.org/legacy/publications/compsystems/1995/sum_burgess.pdf",
        "reason": (
            "Burgess (USENIX Computing Systems, Vol. 8 No. 3, 1995; als „Cfengine“ zitiert, "
            "der Titel auf dem Dokument selbst trägt den Werkzeugnamen nicht): Gründungsarbeit "
            "des deklarativen, konvergenten Konfigurationsmanagements – der gemeinsame Vorläufer "
            "von Puppet/Chef/Ansible, im Korpus bislang nur über deren Nachfolger vertreten."
        ),
    },
)

_FORBIDDEN_NAME_CHARS = '<>:"/\\|?*'
_MAX_NAME_CHARS = 120


def title_filename(title: str, suffix: str = ".pdf") -> str:
    """Bildet einen dateisystemsicheren Namen **aus dem vollen Titel** (ADR 0030: Name = Titel)."""
    printable = "".join(
        " " if char in _FORBIDDEN_NAME_CHARS or not char.isprintable() else char for char in title
    )
    cleaned = " ".join(printable.split())[:_MAX_NAME_CHARS].strip(" .")
    return f"{cleaned or 'router-config-kandidat'}{suffix}"


def _candidate_from_curated(entry: dict[str, str], *, query_id: str) -> Candidate:
    """Baut einen :class:`Candidate` direkt aus einem ``CURATED``-Eintrag (kein DOI/arXiv nötig)."""
    return Candidate(
        title=entry["title"],
        year=int(entry["year"]),
        sources=("manuell",),
        url=entry["url"],
        query_id=query_id,
        reason=entry["reason"],
    )


def _content_mismatch(raw: bytes, candidate: Candidate) -> tuple[str, str] | None:
    """Identisch zu ``online.download._content_mismatch`` (dort nicht exportiert)."""
    try:
        n_pages = len(PdfReader(io.BytesIO(raw)).pages)
    except (PyPdfError, KeyError, ValueError) as exc:
        return (OUTCOME_NOT_A_PDF, f"PDF nicht lesbar: {exc}")
    if n_pages < 2:
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


def download_curated(client: HttpClient, inbox: Path, candidate: Candidate) -> DownloadOutcome:
    """Lädt einen kuratierten Kandidaten mit Titel-Benennung.

    Kein Lizenz-Whitelist-Schritt (jede Quelle ist ein first-party Verlags-/Tagungsarchiv oder eine
    Autoren-Homepage, docs/online-recherche.md §6.2); Inhaltsprüfung (PDF-Signatur,
    Mindestseitenzahl, Titel-Rückvergleich) identisch zum automatischen Pfad.
    """
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
    filename = title_filename(candidate.title)
    target = inbox / filename
    if target.exists():
        digest = hashlib.sha256(candidate.url.encode("utf-8")).hexdigest()[:8]
        filename = title_filename(candidate.title, f"-{digest}.pdf")
    path = _write_pdf(inbox, response.body, filename)
    return DownloadOutcome(candidate, OUTCOME_DOWNLOADED, f"{len(response.body)} Bytes", path)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Gezielte Themensuche 'Konfiguration von Systemen, speziell Routern'."
    )
    parser.add_argument("--proxy", help="Proxy als host:port (sonst RESEARCH_GRAPHRAG_PROXY)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--eingang", default=str(_DEFAULT_INBOX))
    parser.add_argument("--data", default=str(_DEFAULT_DATA))
    args = parser.parse_args()

    if args.dry_run:
        for entry in CURATED:
            print(f"[router-config] {entry['title']} ({entry['year']}) — {entry['reason']}")
        print("[router-config] Vorschau: keine Abfrage, kein Kontingentverbrauch.")
        return 0

    candidates = [
        _candidate_from_curated(entry, query_id=f"K{index}")
        for index, entry in enumerate(CURATED, start=1)
    ]
    corpus = load_corpus(Path(args.data))
    fresh, known = partition(candidates, corpus)
    inbox = Path(args.eingang)
    client = create_client(proxy=args.proxy) if args.download else None
    downloads: list[DownloadOutcome] = []
    for candidate in fresh:
        if client is None:
            continue
        downloads.append(download_curated(client, inbox, candidate))

    for verdict in known:
        title = verdict.candidate.title[:90]
        evidence = f"{verdict.match}: {verdict.evidence}"
        print(f"[router-config] bereits im Korpus ({evidence}): {title}")
    outcomes = {item.candidate: item for item in downloads}
    for candidate in fresh:
        print(f"  · {candidate.title}")
        print(f"     {candidate.year or 'Jahr unbekannt'} · {candidate.reason}")
        outcome = outcomes.get(candidate)
        if outcome is not None:
            note = f" — {outcome.note}" if outcome.note else ""
            path = f" -> {outcome.path.name}" if outcome.path else ""
            print(f"     Download: {describe_outcome(outcome.outcome)}{note}{path}")
    if downloads:
        downloaded = sum(1 for item in downloads if item.outcome == OUTCOME_DOWNLOADED)
        print(f"[router-config] {downloaded} von {len(downloads)} geladen (Titel-Benennung).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
