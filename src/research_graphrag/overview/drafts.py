"""Entwurfszeilen für die kuratierte Literaturübersicht (Phase 2, Option B).

Erzeugt aus den Canonical-Papern **deterministische, extraktive Entwurfszeilen** für neue,
noch **nicht** gelistete Paper und hängt sie **append-only** an die kuratierte
[Übersicht.md](../../../Übersicht.md) an. Die wertenden Spalten (Relevanz, SRQ-Zuordnung,
Themenfokus) bleiben leer – sie füllt der Mensch.

Entwurfsinhalte ohne LLM (konform docs/adr/0005-graphrag-index-backend-open.md):

- **Name** = Dateiname-Stamm, **Interner Link** = ``papers/<url-encoded>``.
- **Externer Link** = DOI/arXiv aus den extrahierten Identifikatoren.
- **Keyword** = extraktive TF-IDF-Top-Terme (``scikit-learn``) im Korpus-Kontext.
- **Kompakte Zusammenfassung** = extraktiver Abstract-/Leadsatz (klar als ``ENTWURF`` markiert).

Der Lauf ist **idempotent** (bereits gelistete Paper werden übersprungen), **byte-erhaltend**
(bestehende Zeilen werden binär übernommen) und **atomar** (Temporärdatei + ``os.replace``).
Neue Zeilen bekommen eine eigene ID-Reihe ``Z1``, ``Z2``, …, weil die kuratierten IDs
Themencluster sind. Dass die Übersicht die **einzige** Senke ist (statt der früheren
Staging-Datei ``data/overview_drafts.md``), entscheidet
docs/adr/0019-corpus-intake-new-papers-phase8.md.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from sklearn.feature_extraction.text import TfidfVectorizer

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import (
    SECTION_KIND_ABSTRACT,
    CanonicalPaper,
)
from research_graphrag.keywords import filter_terms

_logger = logging.getLogger(__name__)

_KEYWORD_TOP_K = 6
_SUMMARY_MAX_LEN = 300
_TOKEN_PATTERN = r"(?u)\b[a-zA-Z][a-zA-Z]{2,}\b"
_LINK_TARGET = re.compile(r"\]\((.+)\)")
_MANUAL = "(manuell)"

DRAFT_ID_PREFIX = "Z"
"""Präfix der maschinell vergebenen ID-Reihe (kuratierte IDs sind Themencluster)."""

_DRAFT_ID = re.compile(rf"^{DRAFT_ID_PREFIX}(\d+)$")

_LEGACY_DRAFTS = "overview_drafts.md"
"""Frühere Staging-Datei (abgelöst, ADR 0019); wird nur noch **gelesen**."""

INTERNAL_LINK_COLUMN = 5
"""Erwarteter 0-basierter Spaltenindex von ``Interner Link`` in der kuratierten Übersicht."""


@dataclass(frozen=True)
class OverviewReport:
    """Zählwerte eines Entwurfs-Laufs."""

    n_papers: int
    skipped_known: int
    written: int
    target_path: str
    row_ids: tuple[str, ...]


def _split_row(line: str) -> list[str]:
    """Zerlegt eine Markdown-Tabellenzeile in ihre Zellen (Rand-Pipes entfernt)."""
    return line.strip().strip("|").split("|")


def link_column(markdown: str) -> int | None:
    """Ermittelt den 0-basierten Index der ``Interner Link``-Spalte (``None`` ohne Tabellenkopf)."""
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        for index, cell in enumerate(_split_row(line)):
            if cell.strip().lower() == "interner link":
                return index
    return None


def parse_internal_links(markdown: str) -> set[str]:
    """Sammelt die (dekodierten) ``papers/``-Dateinamen aus der ``Interner Link``-Spalte.

    Robust gegen Klammern im Dateinamen (greedy bis zur letzten ``)`` je Zelle, siehe
    Migrations-Erfahrung). Nicht-Tabellenzeilen und die Trennzeile werden ignoriert.
    """
    links: set[str] = set()
    column = link_column(markdown)
    if column is None:
        return links
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = _split_row(line)
        if column >= len(cells):
            continue
        match = _LINK_TARGET.search(cells[column])
        if match:
            target = match.group(1).strip()
            name = target.split("/", 1)[1] if "/" in target else target
            links.add(unquote(name))
    return links


def _filename_from_uri(uri: str) -> str:
    """Ermittelt den (dekodierten) Dateinamen aus einer ``file://``-Quell-URI."""
    return unquote(Path(urlparse(uri).path).name)


def _cell(text: str) -> str:
    """Bereitet Text als sichere Tabellenzelle auf (einzeilig, ``|`` maskiert)."""
    collapsed = " ".join(text.split())
    return collapsed.replace("|", r"\|")


def keyword_table(corpus: list[str], top_k: int = _KEYWORD_TOP_K) -> list[list[str]]:
    """Bestimmt je Dokument die extraktiven TF-IDF-Top-Terme (deterministisch, Tie-Break Term).

    Rausch-Terme werden über :func:`research_graphrag.keywords.filter_terms` **vor** dem
    Anschnitt entfernt – dieselbe Politik wie bei den Community-Keywords
    (docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md).
    """
    empty: list[list[str]] = [[] for _ in corpus]
    if not any(doc.strip() for doc in corpus):
        return empty
    vectorizer = TfidfVectorizer(stop_words="english", token_pattern=_TOKEN_PATTERN)
    try:
        matrix = vectorizer.fit_transform(corpus)
    except ValueError:
        return empty
    features = vectorizer.get_feature_names_out()
    result: list[list[str]] = []
    for index in range(len(corpus)):
        row = matrix[index].tocoo()
        pairs = sorted(
            zip(row.col.tolist(), row.data.tolist(), strict=True),
            key=lambda item: (-item[1], features[item[0]]),
        )
        result.append(filter_terms((str(features[col]) for col, _ in pairs), top_k))
    return result


def extractive_summary(paper: CanonicalPaper, max_len: int = _SUMMARY_MAX_LEN) -> str:
    """Wählt extraktiven Kurztext: bevorzugt Abstract, sonst ersten Fließtext-Chunk."""
    abstract_ids = {
        section.section_id for section in paper.sections if section.kind == SECTION_KIND_ABSTRACT
    }
    text = ""
    for chunk in paper.chunks:
        if chunk.section_id in abstract_ids:
            text = chunk.text
            break
    if not text:
        non_front = [chunk for chunk in paper.chunks if chunk.section_title]
        source = non_front or list(paper.chunks)
        text = source[0].text if source else ""
    collapsed = " ".join(text.split())
    if len(collapsed) > max_len:
        collapsed = collapsed[: max_len - 1].rstrip() + "…"
    return collapsed


def _external_link(identifiers: dict[str, str]) -> str:
    """Baut die externe Identifikator-Spalte aus DOI/arXiv (sonst Platzhalter)."""
    doi = identifiers.get("doi")
    if doi:
        return f"[DOI:{doi}](https://doi.org/{doi})"
    arxiv = identifiers.get("arxiv")
    if arxiv:
        return f"[arXiv:{arxiv}](https://arxiv.org/abs/{arxiv})"
    return "(zu ergänzen)"


def build_draft_row(row_id: str, filename: str, paper: CanonicalPaper, keywords: list[str]) -> str:
    """Baut eine 9-spaltige Markdown-Entwurfszeile in der Spaltenordnung der Übersicht.

    Spalten: ``ID``, ``Name``, ``Themenfokus``, ``Keyword``, ``Kompakte Zusammenfassung``,
    ``Interner Link``, ``Relevanz fuer Expose``, ``SRQ-Zuordnung``,
    ``Externer Link/Indetifikator``. Die drei wertenden Spalten bleiben ``(manuell)``.
    """
    name = filename[:-4] if filename.lower().endswith(".pdf") else filename
    internal = f"[Quelle](papers/{quote(filename)})"
    keyword_cell = _cell(", ".join(keywords)) if keywords else _MANUAL
    summary = extractive_summary(paper)
    summary_cell = f"ENTWURF: {_cell(summary)}" if summary else "ENTWURF"
    external = _cell(_external_link(dict(paper.identifiers)))
    columns = [
        row_id,
        _cell(name),
        _MANUAL,
        keyword_cell,
        summary_cell,
        internal,
        _MANUAL,
        _MANUAL,
        external,
    ]
    return "| " + " | ".join(columns) + " |"


def next_draft_number(markdown: str) -> int:
    """Ermittelt die nächste freie Nummer der maschinellen ID-Reihe (``Z1``, ``Z2``, …)."""
    highest = 0
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        match = _DRAFT_ID.match(_split_row(line)[0].strip())
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _known_links(markdown: str, data_path: Path) -> set[str]:
    """Sammelt die bereits gelisteten ``papers/``-Dateinamen (Ziel **und** Alt-Staging).

    Die abgelöste Staging-Datei ``data/overview_drafts.md`` wird weiterhin gelesen, damit ein
    noch nicht übernommener Altbestand nicht ein zweites Mal in der Übersicht landet
    (docs/adr/0019-corpus-intake-new-papers-phase8.md).
    """
    known = parse_internal_links(markdown)
    legacy = data_path / _LEGACY_DRAFTS
    if legacy.is_file():
        known |= parse_internal_links(legacy.read_text(encoding="utf-8"))
    return known


def _append_rows(target: Path, rows: list[str]) -> None:
    """Hängt Zeilen **byte-erhaltend und atomar** an eine bestehende Markdown-Datei an.

    Der vorhandene Inhalt wird binär übernommen (kein Umschreiben von Zeilenenden – ``write_text``
    würde unter Windows CRLF erzeugen und damit jede kuratierte Zeile verändern); geschrieben wird
    über eine Temporärdatei mit :func:`os.replace`, damit ein Abbruch die Datei nicht halbfertig
    zurücklässt (Muster aus docs/adr/0010-drop-in-workflow-and-qa-phase6.md).
    """
    existing = target.read_bytes()
    newline = b"\r\n" if b"\r\n" in existing else b"\n"
    if existing and not existing.endswith((b"\n", b"\r")):
        existing += newline
    payload = newline.join(row.encode("utf-8") for row in rows) + newline
    tmp_path = target.with_name(target.name + ".tmp")
    try:
        tmp_path.write_bytes(existing + payload)
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)


def ensure_overview_target(target_path: str | Path) -> Path:
    """Prüft die Zieldatei **vorab** und liefert ihren Pfad.

    Vorbedingung für jeden Schreibvorgang – auch für den Korpus-Intake, der sie **vor** der ersten
    Dateioperation aufruft. Andernfalls würden PDFs verschoben und der Index neu gebaut, nur damit
    der Lauf danach an einem falschen Pfad scheitert.

    Args:
        target_path: Pfad zur kuratierten ``Übersicht.md``.

    Returns:
        Den geprüften Pfad.

    Raises:
        DomainError: ``not_found`` wenn die Datei fehlt; ``constraint_violation`` wenn die Tabelle
            nicht das erwartete Spaltenlayout hat (siehe docs/error-model.md).
    """
    target = Path(target_path)
    if not target.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"Übersicht nicht gefunden: {target}")
    if link_column(target.read_text(encoding="utf-8")) != INTERNAL_LINK_COLUMN:
        raise DomainError(
            ErrorCode.CONSTRAINT_VIOLATION,
            f"Unerwartetes Spaltenlayout in {target}: 'Interner Link' muss die "
            f"{INTERNAL_LINK_COLUMN + 1}. Spalte sein.",
        )
    return target


def append_overview_rows(
    *,
    data_dir: str | Path,
    target_path: str | Path,
) -> OverviewReport:
    """Hängt Entwurfszeilen für noch nicht gelistete Paper an die kuratierte Übersicht an.

    Args:
        data_dir: Datenordner mit ``canonical/`` und optional ``manifest.json``.
        target_path: Pfad zur kuratierten ``Übersicht.md`` (wird append-only ergänzt).

    Returns:
        Ein :class:`OverviewReport` mit Zählwerten und den vergebenen IDs.

    Raises:
        DomainError: ``not_found`` wenn ``canonical/`` oder die Zieldatei fehlt;
            ``constraint_violation`` wenn die Zieltabelle nicht das erwartete Spaltenlayout hat
            (siehe docs/error-model.md).
    """
    data_path = Path(data_dir)
    canonical_dir = data_path / "canonical"
    if not canonical_dir.is_dir():
        raise DomainError(ErrorCode.NOT_FOUND, f"canonical-Ordner fehlt: {canonical_dir}")

    target = ensure_overview_target(target_path)
    markdown = target.read_text(encoding="utf-8")
    known = _known_links(markdown, data_path)

    manifest_path = data_path / "manifest.json"
    paper_id_to_name: dict[str, str] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, entry in manifest.items():
            paper_id_to_name.setdefault(str(entry["paper_id"]), str(name))

    papers = [CanonicalPaper.load_json(path) for path in sorted(canonical_dir.glob("*.json"))]
    filenames = [
        paper_id_to_name.get(paper.paper_id) or _filename_from_uri(paper.source_uri)
        for paper in papers
    ]
    keywords = keyword_table([" ".join(chunk.text for chunk in paper.chunks) for paper in papers])

    candidates = sorted(
        zip(filenames, papers, keywords, strict=True),
        key=lambda item: item[0].lower(),
    )

    skipped_known = 0
    new_rows: list[str] = []
    row_ids: list[str] = []
    number = next_draft_number(markdown)
    for filename, paper, terms in candidates:
        if filename in known:
            skipped_known += 1
            continue
        row_id = f"{DRAFT_ID_PREFIX}{number}"
        number += 1
        row_ids.append(row_id)
        new_rows.append(build_draft_row(row_id, filename, paper, terms))

    if new_rows:
        _append_rows(target, new_rows)
        _logger.info("Übersicht um %d Entwurfszeile(n) ergänzt: %s", len(new_rows), target)

    return OverviewReport(
        n_papers=len(papers),
        skipped_known=skipped_known,
        written=len(new_rows),
        target_path=str(target),
        row_ids=tuple(row_ids),
    )
