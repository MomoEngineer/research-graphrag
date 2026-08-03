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
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .candidates import Candidate, KnownCandidate
from .sources import SearchQuery, SourceResult

REPORT_NAME = "online_candidates.md"
"""Dateiname des Berichts unterhalb des Datenverzeichnisses."""

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

    if report.fresh:
        lines += ["### Neue Kandidaten", ""]
    for number, candidate in enumerate(report.fresh, start=1):
        lines += _render_candidate(number, candidate)
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


def _render_candidate(number: int, candidate: Candidate) -> list[str]:
    """Rendert einen einzelnen Kandidaten samt Begründung."""
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
        "",
    ]
    abstract = escape_markdown(candidate.abstract, limit=MAX_ABSTRACT_CHARS)
    lines += [f"> {abstract}" if abstract else "> (kein Abstract)", ""]
    return lines


def append_report(data_path: Path, report: DiscoveryReport) -> Path:
    """Hängt einen Lauf an den Bericht an (byte-erhaltend und atomar).

    Existiert die Datei noch nicht, wird sie mit einer Kopfzeile angelegt. Bestehender Inhalt
    wird binär übernommen, damit vorhandene Zeilenenden unverändert bleiben; geschrieben wird über
    eine Temporärdatei mit :func:`os.replace`, damit ein Abbruch nichts Halbfertiges hinterlässt
    (Muster aus docs/adr/0010-drop-in-workflow-and-qa-phase6.md).

    Args:
        data_path: Datenverzeichnis (üblicherweise ``data/``).
        report: Das anzuhängende Laufergebnis.

    Returns:
        Den Pfad des geschriebenen Berichts.
    """
    target = data_path / REPORT_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_bytes() if target.is_file() else b""
    newline = b"\r\n" if b"\r\n" in existing else os.linesep.encode()
    if not existing:
        existing = newline.join(line.encode("utf-8") for line in _HEADER) + newline
    elif not existing.endswith((b"\n", b"\r")):
        existing += newline
    payload = newline.join(line.encode("utf-8") for line in render_report(report)) + newline
    tmp_path = target.with_name(target.name + ".tmp")
    try:
        tmp_path.write_bytes(existing + payload)
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)
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
