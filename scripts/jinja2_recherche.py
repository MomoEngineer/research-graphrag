"""CLI: Gezielte Themensuche „Jinja2" — Kandidaten sammeln und frei lizenzierte Volltexte laden.

Einmaliger Recherche-Lauf zur Anreicherung des Korpus um Templatesprachen-Wissen (konkret:
Jinja2). Anders als :mod:`scripts.discover` (ADR 0020) leitet dieser Lauf seine Anfragen **nicht**
aus dem eigenen Bestand ab, sondern aus einer handkuratierten Begriffsliste zum Thema Jinja2 – das
Thema existiert im Korpus noch nicht, ein Community- oder Seed-Bezug ist deshalb nicht möglich.
Wiederverwendet werden die bestehenden, bereits getesteten Bausteine aus
``research_graphrag.online``: Quellenabfrage (arXiv/OpenAlex), quellenübergreifende
Dublettenzusammenführung, Korpus-Abgleich, Lizenz-Whitelist-Download (ADR 0035) und Bericht.

Zwei Abweichungen von ``scripts.discover``:

1. Heruntergeladene Dateien werden nach dem **Titel** benannt (dieselbe Konvention wie beim
   Intake, ADR 0030: „der Dateiname ist der Titel"), nicht nach dem Muster
   ``online-<slug>-<id>.pdf``.
2. Der Aktualitätsfilter ist standardmäßig weit gefasst (``--seit 2000``), weil bei einer neuen
   Themensuche auch ältere Grundlagenarbeiten gefunden werden sollen.

Zwei Betriebsarten:

* **Freitext-Suche** (Standard, ``QUERIES``): dieselbe Mechanik wie ``scripts.discover``, nur mit
  Begriffen statt Community/Seed. **Befund aus dem ersten Lauf:** Einzelwörter wie „jinja"/
  „template"/„engine" sind bei arXiv/OpenAlex hochgradig mehrdeutig (die Stadt Jinja in Uganda,
  biometrische „Templates", genetische „Templates" …) – genau der Grund, warum ADR 0020 eine freie
  Volltextsuche für den Korpus-Bestand bewusst ausschließt. Das Verfahren bleibt hier als
  Explorationswerkzeug erhalten, ist aber **nicht** die Quelle der tatsächlich geladenen Dateien.
* **Kuratierte Liste** (``--kuratiert``, ``CURATED``): von Hand recherchierte und geprüfte
  DOI/arXiv-Kennungen (Titel-Suche bei OpenAlex, Abstract gelesen, Lizenz/Quelle bewertet). Jeder
  Eintrag trägt eine Vertrauensbasis (``trust``): ``openalex-license`` nutzt die reguläre
  Lizenz-Whitelist (ADR 0035) unverändert; ``arxiv-direct`` und ``institutional-repo`` sind die in
  docs/online-recherche.md §6.2 vorgesehenen **manuellen** Downloads (arXiv-Preprint bzw.
  Universitäts-Repositorium ohne OpenAlex-Lizenzfeld) – hier greift dieselbe Inhaltsprüfung
  (Titel-Rückvergleich, Mindestseitenzahl) wie im automatischen Pfad, nur ohne den
  Lizenz-Whitelist-Schritt, weil die Quelle selbst bereits als offen geprüft wurde.

Aufruf vom Repository-Wurzelverzeichnis:

    python -m scripts.jinja2_recherche --dry-run
    python -m scripts.jinja2_recherche --download
    python -m scripts.jinja2_recherche --kuratiert --download

Bewusst wie ``scripts.discover`` **kein** MCP-Werkzeug und immer von Hand gestartet – Netzverkehr
soll eine beobachtete Handlung bleiben.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace as _replace
from pathlib import Path

from research_graphrag.errors import DomainError
from research_graphrag.intake import load_corpus
from research_graphrag.online.candidates import Candidate, partition
from research_graphrag.online.download import (
    LICENSE_WHITELIST,
    OUTCOME_DOWNLOADED,
    DownloadOutcome,
    _content_mismatch,
    describe_outcome,
    download_candidate,
)
from research_graphrag.online.report import append_report, DiscoveryReport
from research_graphrag.online.search import discover
from research_graphrag.online.sources import DEFAULT_LIMIT, SearchQuery, fetch_arxiv_by_id
from research_graphrag.online.transport import create_client
from research_graphrag.intake import PDF_MAGIC

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INDEX = _REPO_ROOT / "data" / "index" / "index.sqlite"
_DEFAULT_DATA = _REPO_ROOT / "data"
_DEFAULT_INBOX = _REPO_ROOT / "new_papers"

# Handkuratierte Anfragen zum Thema Jinja2 (kein Bezug zum eigenen Bestand möglich, s. Docstring).
QUERIES: tuple[SearchQuery, ...] = (
    SearchQuery(
        query_id="J1",
        terms=("jinja2", "template", "engine"),
        reason="Kernbegriff: Jinja2 als Template-Engine",
    ),
    SearchQuery(
        query_id="J2",
        terms=("jinja2", "template injection", "security"),
        reason="Sicherheitsforschung: Server-Side Template Injection (SSTI) mit Jinja2",
    ),
    SearchQuery(
        query_id="J3",
        terms=("jinja2", "template", "code generation"),
        reason="Codegenerierung mit Jinja2-Templates",
    ),
    SearchQuery(
        query_id="J4",
        terms=("jinja", "template", "type checking"),
        reason="Statische Typprüfung von Jinja-Templates",
    ),
)

TRUST_OPENALEX_LICENSE = "openalex-license"
"""Regulärer Pfad: Download nur, wenn OpenAlex eine Whitelist-Lizenz ausweist (ADR 0035)."""

TRUST_ARXIV_DIRECT = "arxiv-direct"
"""Manueller Pfad (docs/online-recherche.md §6.2): arXiv weist im Feed nie eine Lizenz aus."""

TRUST_INSTITUTIONAL_REPO = "institutional-repo"
"""Manueller Pfad: Volltext aus einem geprüften Universitäts-/Institutsrepositorium."""

# Von Hand recherchiert (WebSearch + OpenAlex-Titelsuche, Abstract gelesen) und geprüft – siehe
# Gesprächsverlauf der Recherche. Jeder Eintrag ist einzeln nachvollziehbar über seine Kennung.
CURATED: tuple[dict[str, str], ...] = (
    {
        "kind": "doi",
        "value": "10.1145/3786583.3786905",
        "reason": "TypeJinja: statische Typprüfung von Jinja-Templates bei dbt Labs (ACM, 2026)",
        "trust": TRUST_OPENALEX_LICENSE,
    },
    {
        "kind": "arxiv",
        "value": "2107.07461",
        "reason": "Jinja2 als Werkzeug der Computeralgebra – Codegenerierung numerischer Verfahren",
        "trust": TRUST_OPENALEX_LICENSE,
    },
    {
        "kind": "doi",
        "value": "10.5281/zenodo.7513284",
        "reason": "Einsatz von Jinja-Templates zur Erstellung von E-Commerce-Prozessen (Django)",
        "trust": TRUST_OPENALEX_LICENSE,
        # OpenAlex' oa_url ist die Zenodo-Landing-Page (liefert HTTP 406 auf Accept: pdf);
        # der direkte Datei-Link kommt aus der Zenodo-API (files[].links.self). Zenodos
        # Datei-Endpunkt selbst besteht wiederum nur auf Accept: application/json oder */*.
        "url": "https://zenodo.org/api/records/7513284/files/B_Soliev%20-%20USING%20JINJA%20TEMPLATES%20TO%20CREATE%20E-COMMERCE%20PROCESSES.pdf/content",
        "accept": "*/*",
    },
    {
        "kind": "arxiv",
        "value": "2405.01118",
        "reason": "Survey zu übersehenen Sicherheitsrisiken von Template-Engines (SSTI), Jinja2 als Leitbeispiel",
        "trust": TRUST_ARXIV_DIRECT,
    },
    {
        "kind": "doi",
        "value": "10.71781/9794",
        "reason": "Survey of Template-Based Code Generation (Masterarbeit, Université de Montréal, 2017)",
        "trust": TRUST_INSTITUTIONAL_REPO,
        # OpenAlex' oa_url liefert HTTP 302 (der Client folgt Redirects bewusst nicht); Ziel von
        # Hand aufgelöst (Location-Header) und hier direkt hinterlegt.
        "url": "https://umontreal.scholaris.ca/server/api/core/bitstreams/0b325651-f92e-49d4-aa03-640e90b6c140/content",
    },
    # Runde 2 (erweiterte Suche: Testing-Methodik/Architekturen + andere Templatesprachen).
    {
        "kind": "arxiv",
        "value": "2602.04653",
        "reason": "Inference-Time Backdoors via Chat Templates — explizit Jinja2 als Angriffsfläche (LLM-Supply-Chain)",
        "trust": TRUST_OPENALEX_LICENSE,
    },
    {
        "kind": "arxiv",
        "value": "2606.18120",
        "reason": "Structural Role Injection in Handlebars-Templated LLM Prompts — übertragbares Wissen (Handlebars ↔ Jinja2, Escaping-Grenzen)",
        "trust": TRUST_OPENALEX_LICENSE,
    },
    {
        "kind": "doi",
        "value": "10.14419/ijet.v7i3.13.16337",
        "reason": "A Study of Ajax Template Injection in Web Applications — Testing-Methodik für Template-Injection",
        "trust": TRUST_OPENALEX_LICENSE,
    },
)

_FORBIDDEN_NAME_CHARS = '<>:"/\\|?*'
_MAX_NAME_CHARS = 120


def title_filename(title: str, suffix: str = ".pdf") -> str:
    """Bildet einen dateisystemsicheren Namen **aus dem vollen Titel** (ADR 0030: Name ist Titel).

    Dieselbe Filterung wie :func:`research_graphrag.intake.safe_stub_name`, nur mit ``.pdf``-Endung
    statt ``.refjson`` – Konsistenz zur bestehenden Namenskonvention des Korpus.
    """
    printable = "".join(
        " " if char in _FORBIDDEN_NAME_CHARS or not char.isprintable() else char for char in title
    )
    cleaned = " ".join(printable.split())[:_MAX_NAME_CHARS].strip(" .")
    return f"{cleaned or 'jinja2-kandidat'}{suffix}"


def _rename_to_title(outcome: DownloadOutcome) -> DownloadOutcome:
    """Benennt eine geladene Datei von ``online-…pdf`` nach dem vollen Titel um.

    Existiert der Zieltitel schon (z. B. erneuter Lauf), hängt ein aus der Kennung gebildeter
    Kurz-Hash an – über dieselbe Zeichen-Whitelist wie :func:`title_filename`, damit ein DOI mit
    ``/`` keinen ungültigen Dateinamen erzeugt.
    """
    if outcome.outcome != OUTCOME_DOWNLOADED or outcome.path is None:
        return outcome
    target = outcome.path.with_name(title_filename(outcome.candidate.title))
    if target != outcome.path and target.exists():
        import hashlib

        digest = hashlib.sha256(
            (outcome.candidate.identifier or "dup").encode("utf-8")
        ).hexdigest()[:8]
        target = target.with_name(title_filename(outcome.candidate.title, f"-{digest}.pdf"))
    if target != outcome.path:
        os.replace(outcome.path, target)
    return _replace(outcome, path=target)


def _openalex_work(client, doi_or_datacite: str) -> dict | None:
    """Fragt **ein** OpenAlex-Werk über seinen DOI ab (Volltitel, Lizenz, OA-Link)."""
    from urllib.parse import quote

    url = f"https://api.openalex.org/works/https://doi.org/{quote(doi_or_datacite, safe='/.')}"
    response = client.get(url, accept="application/json")
    if response.status != 200:
        return None
    return json.loads(response.body)


def _candidate_from_openalex(work: dict, *, query_id: str, reason: str) -> Candidate:
    access = work.get("open_access") or {}
    location = work.get("primary_location") or {}
    doi = str(work.get("doi") or "").removeprefix("https://doi.org/")
    return Candidate(
        title=" ".join(str(work.get("title") or "").split()),
        year=int(work.get("publication_year") or 0),
        sources=("OpenAlex",),
        doi=doi,
        abstract="",
        url=str(access.get("oa_url") or work.get("id") or ""),
        license=str(location.get("license") or ""),
        query_id=query_id,
        reason=reason,
    )


def resolve_curated(client, entries: tuple[dict[str, str], ...]) -> list[tuple[Candidate, str, str]]:
    """Löst die kuratierte Liste zu ``(Kandidat, Vertrauensbasis, Accept-Header)`` auf.

    arXiv-Kennungen werden zuerst über OpenAlex (DataCite-DOI) versucht – liefert das nichts
    (Paper noch nicht indexiert), tritt der arXiv-Feed selbst als Quelle an seine Stelle.
    """
    resolved: list[tuple[Candidate, str, str]] = []
    for entry in entries:
        query_id = f"K-{entry['value'][:16]}"
        if entry["kind"] == "doi":
            work = _openalex_work(client, entry["value"])
            if work is None:
                print(f"[jinja2] Kuratiert: DOI {entry['value']} nicht bei OpenAlex gefunden — übersprungen.")
                continue
            candidate = _candidate_from_openalex(work, query_id=query_id, reason=entry["reason"])
        else:
            work = _openalex_work(client, f"10.48550/arXiv.{entry['value']}")
            if work is not None:
                # OpenAlex' oa_url zeigt für arXiv-Werke oft nur auf den DOI-Resolver (der wiederum
                # per 302 auf arxiv.org verweist, dem der Client bewusst nicht folgt). Der direkte
                # PDF-Link ist bei arXiv immer https://arxiv.org/pdf/<id> — zuverlässiger als das
                # OpenAlex-Feld.
                candidate = _replace(
                    _candidate_from_openalex(work, query_id=query_id, reason=entry["reason"]),
                    arxiv_id=entry["value"],
                    url=f"https://arxiv.org/pdf/{entry['value']}",
                )
            else:
                query = SearchQuery(query_id=query_id, terms=(entry["value"],), reason=entry["reason"])
                source = fetch_arxiv_by_id(client, entry["value"], query)
                if not source.candidates:
                    print(f"[jinja2] Kuratiert: arXiv {entry['value']} ohne Treffer — übersprungen.")
                    continue
                candidate = source.candidates[0]
        if entry.get("url"):
            candidate = _replace(candidate, url=entry["url"])
        resolved.append((candidate, entry["trust"], entry.get("accept", "application/pdf")))
    return resolved


def download_curated(
    client, inbox: Path, candidate: Candidate, *, trust: str, accept: str = "application/pdf"
) -> DownloadOutcome:
    """Lädt einen kuratierten Kandidaten; Inhaltsprüfung immer, Lizenz-Whitelist nur bei Bedarf.

    Bei ``TRUST_OPENALEX_LICENSE`` gilt dieselbe Lizenz-Whitelist wie im automatischen Pfad von
    ``scripts.discover`` (ADR 0035). Bei ``TRUST_ARXIV_DIRECT``/``TRUST_INSTITUTIONAL_REPO`` gilt
    der manuelle Pfad aus docs/online-recherche.md §6.2: Die Quelle selbst (arXiv-Preprint bzw.
    Universitäts-Repositorium) gilt bereits als geprüft offen, die Lizenz-Whitelist entfällt.
    In beiden Fällen bleibt die Inhaltsprüfung (PDF-Signatur, Mindestseitenzahl,
    Titel-Rückvergleich) identisch – ``_content_mismatch`` wird unverändert wiederverwendet.
    ``accept`` erlaubt einen abweichenden Header für Quellen, die auf ``application/pdf`` mit
    HTTP 406 antworten (z. B. Zenodos Datei-Endpunkt).
    """
    from research_graphrag.online.download import (
        MAX_DOWNLOAD_BYTES,
        OUTCOME_HTTP_ERROR,
        OUTCOME_LICENSE_NOT_WHITELISTED,
        OUTCOME_NO_LICENSE,
        OUTCOME_NO_URL,
        OUTCOME_NOT_A_PDF,
        _write_pdf,
        is_whitelisted_license,
        pdf_filename,
    )

    if trust == TRUST_OPENALEX_LICENSE:
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
        response = client.get(candidate.url, accept=accept, max_bytes=MAX_DOWNLOAD_BYTES)
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


def _print_report(report: DiscoveryReport, downloads: tuple[DownloadOutcome, ...], target: Path) -> None:
    for query in report.queries:
        print(f"[jinja2] Anfrage {query.query_id}: {', '.join(query.terms)} — {query.reason}")
    for source in report.sources:
        note = f" — {source.note}" if source.note else ""
        print(f"[jinja2] {source.source}: HTTP {source.status}{note}")
    print(
        f"[jinja2] {report.found} Treffer · {len(report.known)} bereits im Korpus · "
        f"{report.dropped_old} vor {report.min_year} · {len(report.fresh)} neu"
    )
    outcomes = {item.candidate: item for item in downloads}
    for candidate in report.fresh:
        identifier = candidate.identifier or "(kein Identifikator)"
        print(f"  · {candidate.title[:100]}")
        print(
            f"     {identifier} · {candidate.year or 'Jahr unbekannt'} · "
            f"{', '.join(candidate.sources)} · Lizenz: {candidate.license or '(keine)'}"
        )
        outcome = outcomes.get(candidate)
        if outcome is not None:
            reason = f" — {outcome.note}" if outcome.note else ""
            path = f" -> {outcome.path.name}" if outcome.path else ""
            print(f"     Download: {describe_outcome(outcome.outcome)}{reason}{path}")
    if downloads:
        downloaded = sum(1 for item in downloads if item.outcome == OUTCOME_DOWNLOADED)
        print(f"[jinja2] Download: {downloaded} von {len(downloads)} geladen (Titel-Benennung)")
    print(f"[jinja2] Bericht: {target}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Gezielte Themensuche 'Jinja2' (kein Bezug zum eigenen Bestand nötig)."
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
        help="Löst CURATED (von Hand recherchierte DOI/arXiv-Kennungen) statt QUERIES auf.",
    )
    parser.add_argument("--eingang", default=str(_DEFAULT_INBOX))
    parser.add_argument("--index", default=str(_DEFAULT_INDEX))
    parser.add_argument("--data", default=str(_DEFAULT_DATA))
    args = parser.parse_args()

    if args.dry_run:
        if args.kuratiert:
            for entry in CURATED:
                print(f"[jinja2] {entry['kind']}:{entry['value']} ({entry['trust']}) — {entry['reason']}")
        else:
            for query in QUERIES:
                print(f"[jinja2] Anfrage {query.query_id}: {', '.join(query.terms)} — {query.reason}")
        print("[jinja2] Vorschau: keine Abfrage, kein Bericht, kein Kontingentverbrauch.")
        return 0

    if args.kuratiert:
        try:
            client = create_client(proxy=args.proxy)
            resolved = resolve_curated(client, CURATED)
            corpus = load_corpus(Path(args.data))
            candidates = [candidate for candidate, _, _ in resolved]
            fresh, known = partition(candidates, corpus)
            trust_by_candidate = {c: t for c, t, _ in resolved}
            accept_by_candidate = {c: a for c, _, a in resolved}
            inbox = Path(args.eingang)
            downloads: list[DownloadOutcome] = []
            for candidate in fresh:
                outcome = download_curated(
                    client,
                    inbox,
                    candidate,
                    trust=trust_by_candidate[candidate],
                    accept=accept_by_candidate[candidate],
                )
                downloads.append(_rename_to_title(outcome))
        except DomainError as exc:
            print(f"[jinja2] Fehler [{exc.code.value}]: {exc.message}")
            return 1

        for verdict in known:
            print(f"[jinja2] bereits im Korpus ({verdict.match}: {verdict.evidence}): {verdict.candidate.title[:90]}")
        for candidate, outcome in zip(fresh, downloads):
            print(f"  · {candidate.title}")
            print(
                f"     {candidate.identifier or '(kein Identifikator)'} · "
                f"{candidate.year or 'Jahr unbekannt'} · Lizenz: {candidate.license or '(keine, manueller Pfad)'} · "
                f"Vertrauensbasis: {trust_by_candidate[candidate]}"
            )
            note = f" — {outcome.note}" if outcome.note else ""
            path = f" -> {outcome.path.name}" if outcome.path else ""
            print(f"     Download: {describe_outcome(outcome.outcome)}{note}{path}")
        downloaded = sum(1 for item in downloads if item.outcome == OUTCOME_DOWNLOADED)
        print(f"[jinja2] Kuratiert: {downloaded} von {len(downloads)} geladen (Titel-Benennung).")
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
        downloads: tuple[DownloadOutcome, ...] = ()
        if args.download:
            inbox = Path(args.eingang)
            raw = tuple(
                download_candidate(client, inbox, candidate) for candidate in report.fresh
            )
            downloads = tuple(_rename_to_title(item) for item in raw)
            report = _replace(report, downloads=downloads)
        target = append_report(Path(args.data), report)
    except DomainError as exc:
        print(f"[jinja2] Fehler [{exc.code.value}]: {exc.message}")
        return 1

    _print_report(report, downloads, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
