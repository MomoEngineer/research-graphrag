"""CLI: Gezielte Themensuche "Router-Konfiguration über Templatesysteme".

Einmaliger Recherche-Lauf zur Anreicherung des Korpus um Literatur zur **template-basierten**
Konfiguration von Routern/Netzwerkgeräten (Jinja2/Ansible/NETCONF-YANG-Templates, PRESTO-artige
Configlet-Sprachen) – abgegrenzt von der bereits sehr gut abgedeckten **LLM-basierten**
Netzwerk-Konfigurationssynthese (Community 1 im Ähnlichkeitsgraphen, `python -m scripts.graph_info`)
und der generischen Cloud-IaC-Literatur zu Terraform/Ansible-Codequalität (Community 14). Wie
:mod:`scripts.jinja2_recherche` leitet dieser Lauf seine Anfragen **nicht** aus dem eigenen Bestand
ab (:mod:`scripts.discover`, ADR 0020), sondern aus handkuratierter Recherche zu einem im Korpus
noch nicht vertretenen Teilthema. Wiederverwendet werden dieselben, bereits getesteten Bausteine aus
``research_graphrag.online``: Quellenabfrage (arXiv/OpenAlex), Korpus-Abgleich (Intake-Logik),
Inhaltsprüfung beim Download und Bericht.

**Befund der Vorabrecherche** (arXiv/OpenAlex-Freitextsuche, siehe ``QUERIES``): Einzelbegriffe wie
"template"/"configuration" sind – wie schon bei der Jinja2-Recherche festgestellt – hochgradig
mehrdeutig (Neuronale-Netz-"Templates", Posit-Multiplikations-"Templates" o. Ä. dominieren die
Treffer); kein einziger Treffer war auf Anhieb einschlägig. Ergiebig war ausschließlich die
handkuratierte, gezielte Suche (``CURATED``) nach den etablierten Fachbegriffen des Teilgebiets
(PRESTO/Configlets, NETCONF/YANG-Templating, Zero-Touch-Provisioning-Konfigurationstemplates).

Zwei Kandidaten sind frei zugänglich (USENIX-Tagungsarchiv, seit jeher Open Access) und werden mit
``--download`` geladen, benannt nach dem **vollen Titel** (ADR 0030, wie bei
``jinja2_recherche.py``). Zwei weitere Kandidaten sind bei IEEE bzw. Springer **nicht** frei
zugänglich (OpenAlex weist ``oa_status: closed`` aus, geprüft am 2026-09-24) – für sie ist kein
PDF-Download vorgesehen; sie gehören stattdessen in ``new_papers/referenzen.txt`` (Phase 13,
``python -m scripts.resolve_references``), wo sie bereits eingetragen sind.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.router_template_recherche --dry-run
    python -m scripts.router_template_recherche --download
    python -m scripts.router_template_recherche --kuratiert --download

Bewusst wie ``scripts.discover``/``scripts.jinja2_recherche`` **kein** MCP-Werkzeug und immer von
Hand gestartet – Netzverkehr soll eine beobachtete Handlung bleiben.
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
    OUTCOME_NOT_A_PDF,
    OUTCOME_TITLE_MISMATCH,
    OUTCOME_TOO_SHORT,
    DownloadOutcome,
    _write_pdf,
    describe_outcome,
)
from research_graphrag.online.report import DiscoveryReport, append_report
from research_graphrag.online.search import discover
from research_graphrag.online.sources import DEFAULT_LIMIT, SearchQuery
from research_graphrag.online.transport import HttpClient, create_client

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_DATA = _REPO_ROOT / "data"
_DEFAULT_INBOX = _REPO_ROOT / "new_papers"

# Handkuratierte Freitext-Anfragen (Befund: unergiebig, s. Docstring) – zur Nachvollziehbarkeit
# dennoch dokumentiert, wie schon bei scripts.jinja2_recherche.
QUERIES: tuple[SearchQuery, ...] = (
    SearchQuery(
        query_id="R1",
        terms=("router", "configuration", "template"),
        reason="Kernbegriff: Router-Konfiguration über Templates",
    ),
    SearchQuery(
        query_id="R2",
        terms=("network", "configuration", "templating"),
        reason="Breiterer Begriff: Templating für Netzwerkkonfiguration",
    ),
    SearchQuery(
        query_id="R3",
        terms=("netconf", "yang", "template"),
        reason="Standardbasiertes Templating: NETCONF/YANG",
    ),
)

TRUST_INSTITUTIONAL_REPO = "institutional-repo"
"""Manueller Pfad (docs/online-recherche.md §6.2): Quelle ist ein geprüftes, seit jeher offenes
Verlags-/Tagungsarchiv (hier: USENIX) ohne OpenAlex-Lizenzfeld."""

# Von Hand recherchiert (WebSearch + OpenAlex-DOI-Abfrage, Gegenprobe der oa_status-Angabe) und
# geprüft. Jeder Eintrag ist über seine URL einzeln nachvollziehbar. Beide sind bei OpenAlex ohne
# registrierten DOI auffindbar (ältere USENIX-Tagungsbände) – deshalb Direktangabe von Titel/Jahr/
# URL statt einer DOI-/arXiv-Auflösung wie bei scripts.jinja2_recherche.
CURATED: tuple[dict[str, str], ...] = (
    {
        "title": "Configuration Management at Massive Scale: System Design and Experience",
        "year": "2007",
        "url": "https://www.usenix.org/legacy/events/usenix07/tech/full_papers/enck/enck.pdf",
        "reason": (
            "Enck, McDaniel, Sen, Sebos, Spoerel, Greenberg, Rao, Aiello (USENIX ATC 2007): "
            "PRESTO – Configlet-/Template-Sprache zur Router-Konfiguration im AT&T-Backbone. "
            "Grundlagenarbeit des Teilgebiets, im Korpus bislang nicht vertreten."
        ),
        "trust": TRUST_INSTITUTIONAL_REPO,
    },
    {
        "title": "Automating Network and Service Configuration Using NETCONF and YANG",
        "year": "2011",
        "url": "https://www.usenix.org/legacy/event/lisa11/tech/full_papers/Wallin.pdf",
        "reason": (
            "Wallin, Wikström (USENIX LISA 2011): Templating-Ansatz für NETCONF/YANG-basierte "
            "Netzwerkkonfiguration (Tail-f ConfD). Ergänzt die im Korpus vorhandene "
            "LLM-/Synthese-Literatur um den etablierten, nicht-generativen Ansatz."
        ),
        "trust": TRUST_INSTITUTIONAL_REPO,
    },
)

_FORBIDDEN_NAME_CHARS = '<>:"/\\|?*'
_MAX_NAME_CHARS = 120


def title_filename(title: str, suffix: str = ".pdf") -> str:
    """Bildet einen dateisystemsicheren Namen **aus dem vollen Titel** (ADR 0030: Name ist Titel).

    Dieselbe Filterung wie :func:`research_graphrag.intake.safe_stub_name` bzw.
    :func:`scripts.jinja2_recherche.title_filename`.
    """
    printable = "".join(
        " " if char in _FORBIDDEN_NAME_CHARS or not char.isprintable() else char for char in title
    )
    cleaned = " ".join(printable.split())[:_MAX_NAME_CHARS].strip(" .")
    return f"{cleaned or 'router-template-kandidat'}{suffix}"


def _candidate_from_curated(entry: dict[str, str], *, query_id: str) -> Candidate:
    """Baut einen :class:`Candidate` direkt aus einem ``CURATED``-Eintrag (kein DOI/arXiv)."""
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
    """Lädt einen kuratierten Kandidaten mit Titel-Benennung (institutional-repo-Vertrauensbasis).

    Kein Lizenz-Whitelist-Schritt (die Quelle selbst – USENIX-Tagungsarchiv – gilt bereits als
    geprüft offen, docs/online-recherche.md §6.2); Inhaltsprüfung (PDF-Signatur, Mindestseitenzahl,
    Titel-Rückvergleich) identisch zum automatischen Pfad.
    """
    if not candidate.url.startswith(("https://", "http://")):
        return DownloadOutcome(candidate, "no_url", "kein Volltext-Link ausgewiesen")
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


def _print_report(report: DiscoveryReport, target: Path) -> None:
    for query in report.queries:
        terms = ", ".join(query.terms)
        print(f"[router-template] Anfrage {query.query_id}: {terms} — {query.reason}")
    for source in report.sources:
        note = f" — {source.note}" if source.note else ""
        print(f"[router-template] {source.source}: HTTP {source.status}{note}")
    print(
        f"[router-template] {report.found} Treffer · {len(report.known)} bereits im Korpus · "
        f"{report.dropped_old} vor {report.min_year} · {len(report.fresh)} neu"
    )
    for verdict in report.known:
        title = verdict.candidate.title[:90]
        print(f"  bereits im Korpus ({verdict.match}: {verdict.evidence}): {title}")
    for candidate in report.fresh:
        print(f"  · {candidate.title[:100]}")
    print(f"[router-template] Bericht: {target}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Gezielte Themensuche 'Router-Konfiguration über Templatesysteme'."
    )
    parser.add_argument("--seit", type=int, default=2000, metavar="JAHR")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--proxy", help="Proxy als host:port (sonst RESEARCH_GRAPHRAG_PROXY)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ohne-rohdaten", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--kuratiert",
        action="store_true",
        help="Löst CURATED (von Hand recherchierte Kandidaten) statt QUERIES auf.",
    )
    parser.add_argument("--eingang", default=str(_DEFAULT_INBOX))
    parser.add_argument("--index", default=str(_DEFAULT_INDEX))
    parser.add_argument("--data", default=str(_DEFAULT_DATA))
    args = parser.parse_args()

    if args.dry_run:
        if args.kuratiert:
            for entry in CURATED:
                print(f"[router-template] {entry['title']} ({entry['year']}) — {entry['reason']}")
        else:
            for query in QUERIES:
                terms = ", ".join(query.terms)
                print(f"[router-template] Anfrage {query.query_id}: {terms} — {query.reason}")
        print("[router-template] Vorschau: keine Abfrage, kein Bericht, kein Kontingentverbrauch.")
        return 0

    if args.kuratiert:
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
            print(f"[router-template] bereits im Korpus ({evidence}): {title}")
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
            print(
                f"[router-template] Kuratiert: {downloaded} von {len(downloads)} geladen "
                "(Titel-Benennung)."
            )
        return 0

    try:
        client = create_client(proxy=args.proxy)
        report = discover(
            Path(args.index),
            Path(args.data),
            QUERIES,
            client,
            limit=args.limit,
            min_year=args.seit,
            keep_raw=not args.ohne_rohdaten,
        )
        target = append_report(Path(args.data), report)
    except DomainError as exc:
        print(f"[router-template] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    _print_report(report, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
