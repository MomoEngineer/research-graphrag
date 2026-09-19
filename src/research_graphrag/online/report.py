"""Append-only Bericht der Online-Kandidatensuche.

Hält das Ergebnis eines Laufs (:class:`DiscoveryReport`) und schreibt es **anhängend** nach
``data/online_candidates.md``. Der Bericht ist eine Empfehlung, **kein** Bestand: Der Weg in den
Korpus führt ausschließlich über ``new_papers/`` und den Intake
(docs/adr/0019-corpus-intake-new-papers-phase8.md).

Titel, Abstracts und Verweise stammen aus fremden Diensten und gelten als **nicht
vertrauenswürdige Eingabe**. Vor dem Schreiben werden sie deshalb entschärft
(:func:`escape_markdown`, :func:`safe_url`): Zeilenumbrüche und nicht druckbare Zeichen
entfallen, Markdown-Steuerzeichen werden maskiert, Längen begrenzt, und Verweise erscheinen nur
als Klartext mit ``http(s)``-Schema – nie als Markdown-Link mit fremdbestimmtem Ziel
(docs/adr/0020-online-candidate-search-phase9.md).

Über :func:`append_section` teilen sich drei Vorgänge denselben Anhänge-Mechanismus: die
Kandidatensuche (``data/online_candidates.md``), die Metadaten-Auflösung
(``data/metadata_log.md``, docs/adr/0026-online-metadata-resolution.md) und die Referenz-Auflösung
(``data/references_log.md``, docs/adr/0029-reference-stub-resolution-phase13.md).

Mit ``--download`` (Phase 9 / S2, docs/adr/0035-fulltext-download-phase9-s2.md) trägt jeder frische
Kandidat zusätzlich einen Download-Status; Identifikator und Link bleiben davon unabhängig immer
sichtbar. Ohne das Flag ist :attr:`DiscoveryReport.downloads` leer und der Bericht unverändert
gegenüber S1.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from research_graphrag.atomic_write import atomic_write_bytes

from .candidates import Candidate, KnownCandidate
from .download import DownloadOutcome, describe_outcome
from .metadata import Resolution
from .references import ACTION_SKIPPED, ACTION_WRITTEN, ReferenceOutcome
from .sources import SearchQuery, SourceResult

REPORT_NAME = "online_candidates.md"
"""Dateiname des Berichts unterhalb des Datenverzeichnisses."""

METADATA_REPORT_NAME = "metadata_log.md"
"""Dateiname des Protokolls der Metadaten-Auflösung (append-only)."""

REFERENCES_REPORT_NAME = "references_log.md"
"""Dateiname des Protokolls der Referenz-Auflösung (append-only, Phase 13 / R1)."""

RAW_DIR_NAME = "online_raw"
"""Verzeichnis der datierten Rohantworten (Reproduzierbarkeit)."""

MAX_TITLE_CHARS = 300
"""Längengrenze für Titel im Bericht."""

MAX_ABSTRACT_CHARS = 600
"""Längengrenze für den Abstract-Auszug im Bericht."""

MAX_URL_CHARS = 500
"""Längengrenze für Verweise; längere werden verworfen."""

_MARKDOWN_SPECIAL = "\\`*_[]<>|"
_ESCAPE_TABLE = str.maketrans({char: f"\\{char}" for char in _MARKDOWN_SPECIAL})

_HEADER = (
    "# Online-Kandidaten",
    "",
    "Append-only Bericht der Kandidatensuche (`python -m scripts.discover`, Phase 9 / S1).",
    "Die Einträge sind **Vorschläge, kein Bestand**: Der Weg in den Korpus führt ausschließlich",
    "über `new_papers/` und `python -m scripts.intake`.",
    "",
)

_METADATA_HEADER = (
    "# Metadaten-Auflösung",
    "",
    "Append-only Protokoll von `python -m scripts.resolve_metadata` (Phase 12 / K2).",
    "Jede Übernahme nennt Quelle, Belegart und Konfidenz; schwach belegte Einträge sind",
    "als solche markiert (docs/adr/0026-online-metadata-resolution.md).",
    "",
)

_REFERENCES_HEADER = (
    "# Referenz-Einträge",
    "",
    "Append-only Protokoll von `python -m scripts.resolve_references` (Phase 13 / R1).",
    "Erzeugt werden Stub-Dateien `*.refjson` im Eingangsordner – **kein** Bestand: Der Weg in",
    "den Korpus führt ausschließlich über `python -m scripts.intake`",
    "(docs/adr/0029-reference-stub-resolution-phase13.md).",
    "",
)


@dataclass(frozen=True)
class DiscoveryReport:
    """Ergebnis eines Suchlaufs.

    Attributes:
        timestamp: Zeitpunkt des Laufs (UTC, sortierbar).
        queries: Gestellte Anfragen.
        sources: Antworten je Quelle und Anfrage.
        fresh: Neue Kandidaten nach Dedup und Aktualitätsfilter.
        known: Kandidaten, die bereits im Korpus liegen (mit Beleg).
        found: Anzahl der zusammengeführten Treffer vor allen Filtern.
        dropped_old: Anzahl der wegen des Aktualitätsfilters verworfenen Kandidaten.
        min_year: Angewandte Jahresgrenze.
        raw_dir: Ablageort der Rohantworten, falls geschrieben.
        downloads: Download-Versuche je frischem Kandidaten (ADR 0035); leer, wenn ``--download``
            nicht gesetzt war – dann ändert sich am Bericht nichts gegenüber S1.
    """

    timestamp: str
    queries: tuple[SearchQuery, ...]
    sources: tuple[SourceResult, ...]
    fresh: tuple[Candidate, ...]
    known: tuple[KnownCandidate, ...]
    found: int
    dropped_old: int
    min_year: int
    raw_dir: Path | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    downloads: tuple[DownloadOutcome, ...] = field(default_factory=tuple)


def escape_markdown(text: str, *, limit: int) -> str:
    """Entschärft fremden Text für die Ausgabe in Markdown.

    Args:
        text: Rohtext aus einer externen Quelle.
        limit: Höchstlänge vor dem Maskieren.

    Returns:
        Einzeiliger, gekürzter und maskierter Text; leere Eingabe ergibt eine leere Zeichenkette.
    """
    collapsed = " ".join(text.split())
    printable = "".join(char for char in collapsed if char.isprintable())
    if len(printable) > limit:
        printable = printable[:limit].rstrip() + " …"
    return printable.translate(_ESCAPE_TABLE)


def safe_url(url: str) -> str:
    """Gibt einen Verweis nur zurück, wenn er unbedenklich als Klartext ausgegeben werden kann.

    Args:
        url: Verweis aus einer externen Quelle.

    Returns:
        Den bereinigten Verweis oder eine leere Zeichenkette, wenn Schema oder Länge nicht passen.
    """
    cleaned = "".join(char for char in url.strip() if char.isprintable() and not char.isspace())
    if not cleaned.startswith(("https://", "http://")) or len(cleaned) > MAX_URL_CHARS:
        return ""
    return cleaned.replace("`", "")


def render_report(report: DiscoveryReport) -> list[str]:
    """Rendert einen Lauf als Markdown-Abschnitt.

    Args:
        report: Das Laufergebnis.

    Returns:
        Die Zeilen des Abschnitts (ohne abschließenden Zeilenumbruch).
    """
    lines = [f"## Lauf {report.timestamp}", ""]
    for query in report.queries:
        terms = escape_markdown(", ".join(query.terms), limit=MAX_TITLE_CHARS)
        reason = escape_markdown(query.reason, limit=MAX_TITLE_CHARS)
        lines.append(f"- Anfrage `{query.query_id}`: {terms} — {reason}")
    for source in report.sources:
        note = f" ({escape_markdown(source.note, limit=200)})" if source.note else ""
        lines.append(f"- Quelle {source.source}: HTTP {source.status}{note}")
    lines.append(
        f"- Bilanz: {report.found} Treffer · {len(report.known)} bereits im Korpus · "
        f"{report.dropped_old} vor {report.min_year} · {len(report.fresh)} neu"
    )
    if report.raw_dir is not None:
        lines.append(f"- Rohantworten: `{_relative_raw_dir(report.raw_dir)}`")
    for note in report.notes:
        lines.append(f"- Hinweis: {escape_markdown(note, limit=300)}")
    lines.append("")

    outcomes = {item.candidate: item for item in report.downloads}
    if report.fresh:
        lines += ["### Neue Kandidaten", ""]
    for number, candidate in enumerate(report.fresh, start=1):
        lines += _render_candidate(number, candidate, outcomes.get(candidate))
    if report.known:
        lines += ["### Bereits im Korpus (nicht vorgeschlagen)", ""]
        for item in report.known:
            title = escape_markdown(item.candidate.title, limit=MAX_TITLE_CHARS)
            evidence = escape_markdown(item.evidence, limit=200)
            lines.append(f"- {title} — Beleg über {item.match}: `{evidence}`")
        lines.append("")
    if not report.fresh and not report.known:
        lines += ["*Keine Treffer.*", ""]
    return lines


def _relative_raw_dir(raw_dir: Path) -> str:
    """Kürzt den Ablageort auf ``online_raw/<Zeitstempel>``.

    Ein absoluter Pfad trüge den Benutzernamen in den Bericht und wäre auf einem anderen Rechner
    ohnehin wertlos. Die beiden letzten Segmente genügen, weil :func:`store_raw` immer unterhalb
    des Datenverzeichnisses ablegt.
    """
    parts = raw_dir.parts[-2:]
    return "/".join(parts) if parts else raw_dir.name


def _render_candidate(
    number: int, candidate: Candidate, download: DownloadOutcome | None
) -> list[str]:
    """Rendert einen Kandidaten samt Begründung und – sofern vorhanden – Download-Status."""
    identifier = escape_markdown(candidate.identifier, limit=200) or "(keiner)"
    year = str(candidate.year) if candidate.year else "unbekannt"
    url = safe_url(candidate.url)
    lines = [
        f"#### {number}. {escape_markdown(candidate.title, limit=MAX_TITLE_CHARS)}",
        "",
        f"- Identifikator: `{identifier}` · Jahr: {year}",
        f"- Quellen: {', '.join(candidate.sources)}",
        f"- Lizenz: {escape_markdown(candidate.license, limit=200) or '(nicht ausgewiesen)'}",
        f"- Volltext: {f'`{url}`' if url else '(keiner ausgewiesen)'}",
        f"- Vorgeschlagen wegen `{candidate.query_id}`: "
        f"{escape_markdown(candidate.reason, limit=MAX_TITLE_CHARS)}",
    ]
    if download is not None:
        label = describe_outcome(download.outcome)
        note = f" — {escape_markdown(download.note, limit=200)}" if download.note else ""
        lines.append(f"- Download: {label}{note}")
    lines.append("")
    abstract = escape_markdown(candidate.abstract, limit=MAX_ABSTRACT_CHARS)
    lines += [f"> {abstract}" if abstract else "> (kein Abstract)", ""]
    return lines


def append_report(data_path: Path, report: DiscoveryReport) -> Path:
    """Hängt einen Lauf an den Bericht an (byte-erhaltend und atomar).

    Args:
        data_path: Datenverzeichnis (üblicherweise ``data/``).
        report: Das anzuhängende Laufergebnis.

    Returns:
        Den Pfad des geschriebenen Berichts.
    """
    return append_section(data_path / REPORT_NAME, render_report(report), _HEADER)


def append_section(target: Path, lines: Sequence[str], header: Sequence[str]) -> Path:
    """Hängt einen Abschnitt an eine append-only Berichtsdatei an.

    Existiert die Datei noch nicht, wird sie mit der Kopfzeile angelegt. Bestehender Inhalt wird
    **binär** übernommen, damit vorhandene Zeilenenden unverändert bleiben; geschrieben wird
    atomar über :func:`research_graphrag.atomic_write.atomic_write_bytes` (Temporärdatei +
    ``os.replace`` mit Windows-Retry), damit ein Abbruch nichts Halbfertiges hinterlässt (Muster
    aus docs/adr/0010-drop-in-workflow-and-qa-phase6.md) und zwei nahezu gleichzeitige
    Schreibversuche nicht abstürzen (ADR 0039, Nachtrag).

    Args:
        target: Zieldatei des Berichts.
        lines: Die anzuhängenden Zeilen (ohne Zeilenumbrüche).
        header: Kopfzeilen, falls die Datei neu angelegt wird.

    Returns:
        Den Pfad der geschriebenen Datei.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_bytes() if target.is_file() else b""
    newline = b"\r\n" if b"\r\n" in existing else os.linesep.encode()
    if not existing:
        existing = newline.join(line.encode("utf-8") for line in header) + newline
    elif not existing.endswith((b"\n", b"\r")):
        existing += newline
    payload = newline.join(line.encode("utf-8") for line in lines) + newline
    atomic_write_bytes(target, existing + payload)
    return target


def store_raw(data_path: Path, timestamp: str, sources: tuple[SourceResult, ...]) -> Path:
    """Legt die Rohantworten datiert ab, damit ein Befund später nachvollziehbar bleibt.

    Args:
        data_path: Datenverzeichnis (üblicherweise ``data/``).
        timestamp: Zeitstempel des Laufs (wird zum Verzeichnisnamen).
        sources: Die Antworten des Laufs.

    Returns:
        Das angelegte Verzeichnis.
    """
    folder = data_path / RAW_DIR_NAME / timestamp
    folder.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(sources, start=1):
        suffix = "xml" if source.source.lower().startswith("arxiv") else "json"
        name = f"{index:02d}-{source.source.lower()}.{suffix}"
        (folder / name).write_bytes(source.raw)
    return folder


def render_resolutions(timestamp: str, resolutions: Sequence[Resolution]) -> list[str]:
    """Rendert einen Auflösungslauf als Markdown-Abschnitt.

    Der Abschnitt trennt **starke** von **schwachen** Belegen und nennt die nicht aufgelösten
    Paper mit Begründung – ohne diese Trennung wäre die automatische Übernahme nicht prüfbar
    (docs/adr/0026-online-metadata-resolution.md).

    Args:
        timestamp: Zeitpunkt des Laufs (UTC, sortierbar).
        resolutions: Die Ergebnisse des Laufs.

    Returns:
        Die Zeilen des Abschnitts (ohne abschließenden Zeilenumbruch).
    """
    resolved = [item for item in resolutions if item.resolved]
    strong = [
        item for item in resolved if item.record is not None and item.record.confidence == "strong"
    ]
    weak = [item for item in resolved if item not in strong]
    failed = [item for item in resolutions if not item.resolved]

    lines = [
        f"## Lauf {timestamp}",
        "",
        f"- Angefragt: {len(resolutions)} · übernommen: {len(resolved)} "
        f"(stark belegt {len(strong)}, schwach belegt {len(weak)}) · offen: {len(failed)}",
        "",
    ]
    if resolved:
        lines += ["### Übernommen", ""]
        for item in resolved:
            lines.append(_render_resolution(item))
        lines.append("")
    if failed:
        lines += ["### Nicht aufgelöst", ""]
        for item in failed:
            title = escape_markdown(item.target.title, limit=MAX_TITLE_CHARS) or "(ohne Titel)"
            note = escape_markdown(item.note, limit=300)
            lines.append(f"- `{item.target.paper_id}` {title} — {note}")
        lines.append("")
    if not resolutions:
        lines += ["*Nichts aufzulösen – alle Datensätze sind vollständig.*", ""]
    return lines


def _render_resolution(item: Resolution) -> str:
    """Rendert eine einzelne Übernahme mit Belegart, Konfidenz und Herkunftsangabe."""
    record = item.record
    assert record is not None  # noqa: S101 - durch den Aufrufer garantiert
    title = escape_markdown(record.title, limit=MAX_TITLE_CHARS) or "(ohne Titel)"
    authors = escape_markdown(", ".join(record.authors), limit=MAX_TITLE_CHARS) or "(keine)"
    venue = escape_markdown(record.venue, limit=200) or "(keine)"
    year = str(record.year) if record.year else "unbekannt"
    marker = " **(schwach belegt)**" if record.confidence != "strong" else ""
    return (
        f"- `{item.target.paper_id}` {title}{marker}\n"
        f"    - Autoren: {authors} · Jahr: {year} · Venue: {venue}\n"
        f"    - Beleg: {escape_markdown(record.evidence, limit=300)} (`{item.match}`)"
    )


def append_resolutions(data_path: Path, timestamp: str, resolutions: Sequence[Resolution]) -> Path:
    """Hängt einen Auflösungslauf an ``data/metadata_log.md`` an (byte-erhaltend, atomar)."""
    return append_section(
        data_path / METADATA_REPORT_NAME,
        render_resolutions(timestamp, resolutions),
        _METADATA_HEADER,
    )


def render_references(timestamp: str, outcomes: Sequence[ReferenceOutcome]) -> list[str]:
    """Rendert einen Lauf der Referenz-Auflösung als Markdown-Abschnitt.

    Der Abschnitt trennt die **geschriebenen** Stub-Dateien von den übersprungenen und den nicht
    aufgelösten Kennungen. Ein Stub ohne Abstract wird ausdrücklich markiert – er verlangt den
    manuellen Nachtrag (docs/adr/0029-reference-stub-resolution-phase13.md).

    Args:
        timestamp: Zeitpunkt des Laufs (UTC, sortierbar).
        outcomes: Die Ergebnisse des Laufs.

    Returns:
        Die Zeilen des Abschnitts (ohne abschließenden Zeilenumbruch).
    """
    written = [item for item in outcomes if item.action == ACTION_WRITTEN]
    skipped = [item for item in outcomes if item.action == ACTION_SKIPPED]
    open_items = [item for item in outcomes if item.action not in (ACTION_WRITTEN, ACTION_SKIPPED)]
    without_abstract = [item for item in written if not item.has_abstract]

    lines = [
        f"## Lauf {timestamp}",
        "",
        f"- Gelesen: {len(outcomes)} Einträge · geschrieben: {len(written)} "
        f"(davon {len(without_abstract)} ohne Abstract) · übersprungen: {len(skipped)} · "
        f"offen: {len(open_items)}",
        "",
    ]
    if written:
        lines += ["### Stub-Dateien erzeugt", ""]
        for item in written:
            marker = "" if item.has_abstract else " **(ohne Abstract – bitte nachtragen)**"
            name = item.path.name if item.path is not None else ""
            lines.append(
                f"- `{escape_markdown(item.request.label, limit=200)}` → "
                f"`{escape_markdown(name, limit=200)}`{marker}\n"
                f"    - {escape_markdown(item.title, limit=MAX_TITLE_CHARS) or '(ohne Titel)'}"
            )
        lines.append("")
    if skipped:
        lines += ["### Übersprungen (keine Abfrage gestellt)", ""]
        for item in skipped:
            lines.append(
                f"- `{escape_markdown(item.request.label, limit=200)}` — "
                f"{escape_markdown(item.reason, limit=100)}: "
                f"{escape_markdown(item.note, limit=300)}"
            )
        lines.append("")
    if open_items:
        lines += ["### Nicht aufgelöst", ""]
        for item in open_items:
            lines.append(
                f"- Zeile {item.request.line_number} "
                f"`{escape_markdown(item.request.label, limit=200)}` — "
                f"{escape_markdown(item.note, limit=300)}"
            )
        lines.append("")
    if not outcomes:
        lines += ["*Nichts zu tun – die Kennungsliste enthält keine offenen Einträge.*", ""]
    return lines


def append_references(
    data_path: Path, timestamp: str, outcomes: Sequence[ReferenceOutcome]
) -> Path:
    """Hängt einen Lauf an ``data/references_log.md`` an (byte-erhaltend, atomar)."""
    return append_section(
        data_path / REFERENCES_REPORT_NAME,
        render_references(timestamp, outcomes),
        _REFERENCES_HEADER,
    )
