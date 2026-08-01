"""Entwurfszeilen für die kuratierte Literaturübersicht (Phase 2, Option B).

Erzeugt aus den Canonical-Papern **deterministische, extraktive Entwurfszeilen** für neue,
noch **nicht kuratierte** Paper und schreibt sie **append-only** in eine separate Staging-Datei
(`data/overview_drafts.md`). Die kuratierte [Übersicht.md](../../../Übersicht.md) bleibt dabei
**unangetastet** – die wertenden Spalten (Relevanz, SRQ-Zuordnung, Themenfokus) füllt der Mensch.

Entwurfsinhalte ohne LLM (konform docs/adr/0005-graphrag-index-backend-open.md):

- **Name** = Dateiname-Stamm, **Interner Link** = ``papers/<url-encoded>``.
- **Externer Link** = DOI/arXiv aus den extrahierten Identifikatoren.
- **Keyword** = extraktive TF-IDF-Top-Terme (``scikit-learn``) im Korpus-Kontext.
- **Kompakte Zusammenfassung** = extraktiver Abstract-/Leadsatz (klar als ``ENTWURF`` markiert).

Der Lauf ist **idempotent**: bereits kuratierte oder bereits entworfene Paper werden übersprungen.
"""

from __future__ import annotations

import json
import logging
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

_DRAFT_COLUMNS = [
    "ID",
    "Name",
    "Themenfokus",
    "Keyword",
    "Kompakte Zusammenfassung",
    "Interner Link",
    "Relevanz fuer Expose",
    "SRQ-Zuordnung",
    "Externer Link/Indetifikator",
]

_DRAFTS_INTRO = "\n".join(
    [
        "# Übersicht – Entwürfe (unkuratiert)",
        "",
        "> **Automatisch erzeugte Staging-Datei** (`scripts/update_overview.py`, Phase 2).",
        "> Enthält **deterministische, extraktive Entwurfszeilen** für Paper, die noch **nicht**",
        "> in der kuratierten [Übersicht.md](../Übersicht.md) stehen. Sie wird **append-only**",
        "> fortgeschrieben und ist bewusst von der kuratierten Übersicht getrennt (siehe",
        "> docs/adr/0006-canonical-model-phase2-scope.md).",
        ">",
        "> **Workflow:** Zeile prüfen → wertende Spalten (`Relevanz fuer Expose`, `SRQ-Zuordnung`,",
        "> `Themenfokus`) ergänzen → in die kuratierte `Übersicht.md` übernehmen → hier entfernen.",
        "> Entwurfszeilen sind an `ID = ENTWURF` erkennbar; Keyword/Zusammenfassung sind",
        "> maschinell und **vor der Übernahme zu verifizieren**.",
        "",
        "",
    ]
)


def _table_header() -> str:
    """Baut Kopf- und Trennzeile der Entwurfstabelle (aus den Spaltennamen)."""
    header = "| " + " | ".join(_DRAFT_COLUMNS) + " |"
    separator = "| " + " | ".join(["---"] * len(_DRAFT_COLUMNS)) + " |"
    return f"{header}\n{separator}\n"


_DRAFTS_HEADER = _DRAFTS_INTRO + _table_header()


@dataclass(frozen=True)
class DraftReport:
    """Zählwerte eines Entwurfs-Laufs."""

    n_papers: int
    skipped_curated: int
    skipped_existing: int
    written: int
    drafts_path: str


def _split_row(line: str) -> list[str]:
    """Zerlegt eine Markdown-Tabellenzeile in ihre Zellen (Rand-Pipes entfernt)."""
    return line.strip().strip("|").split("|")


def parse_internal_links(markdown: str) -> set[str]:
    """Sammelt die (dekodierten) ``papers/``-Dateinamen aus der ``Interner Link``-Spalte.

    Robust gegen Klammern im Dateinamen (greedy bis zur letzten ``)`` je Zelle, siehe
    Migrations-Erfahrung). Nicht-Tabellenzeilen und die Trennzeile werden ignoriert.
    """
    links: set[str] = set()
    link_col: int | None = None
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = _split_row(line)
        if link_col is None:
            for index, cell in enumerate(cells):
                if cell.strip().lower() == "interner link":
                    link_col = index
            continue
        if all(set(cell.strip()) <= set("-: ") for cell in cells):
            continue
        if link_col < len(cells):
            match = _LINK_TARGET.search(cells[link_col])
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


def build_draft_row(filename: str, paper: CanonicalPaper, keywords: list[str]) -> str:
    """Baut eine 9-spaltige Markdown-Entwurfszeile (ID = ``ENTWURF``)."""
    name = filename[:-4] if filename.lower().endswith(".pdf") else filename
    internal = f"[Quelle](papers/{quote(filename)})"
    keyword_cell = _cell(", ".join(keywords)) if keywords else _MANUAL
    summary = extractive_summary(paper)
    summary_cell = f"ENTWURF: {_cell(summary)}" if summary else "ENTWURF"
    external = _cell(_external_link(dict(paper.identifiers)))
    columns = [
        "ENTWURF",
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


def generate_drafts(
    *,
    data_dir: str | Path,
    uebersicht_path: str | Path,
    drafts_path: str | Path,
) -> DraftReport:
    """Erzeugt Entwurfszeilen für nicht kuratierte Paper und hängt sie append-only an.

    Args:
        data_dir: Datenordner mit ``canonical/`` und optional ``manifest.json``.
        uebersicht_path: Pfad zur kuratierten ``Übersicht.md`` (nur gelesen).
        drafts_path: Ziel-Staging-Datei (wird bei Bedarf mit Kopf angelegt).

    Returns:
        Ein :class:`DraftReport` mit Zählwerten.

    Raises:
        DomainError: ``not_found`` wenn ``canonical/`` fehlt (siehe docs/error-model.md).
    """
    data_path = Path(data_dir)
    canonical_dir = data_path / "canonical"
    if not canonical_dir.is_dir():
        raise DomainError(ErrorCode.NOT_FOUND, f"canonical-Ordner fehlt: {canonical_dir}")

    uebersicht = Path(uebersicht_path)
    drafts = Path(drafts_path)
    if not uebersicht.is_file():
        _logger.warning(
            "Kuratierte Übersicht nicht gefunden (%s); alle Paper gelten als unkuratiert.",
            uebersicht,
        )
    curated = (
        parse_internal_links(uebersicht.read_text(encoding="utf-8"))
        if uebersicht.is_file()
        else set()
    )
    existing = (
        parse_internal_links(drafts.read_text(encoding="utf-8")) if drafts.is_file() else set()
    )

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

    skipped_curated = 0
    skipped_existing = 0
    new_rows: list[str] = []
    for filename, paper, terms in candidates:
        if filename in curated:
            skipped_curated += 1
            continue
        if filename in existing:
            skipped_existing += 1
            continue
        new_rows.append(build_draft_row(filename, paper, terms))

    if new_rows:
        drafts.parent.mkdir(parents=True, exist_ok=True)
        if not drafts.is_file():
            drafts.write_text(_DRAFTS_HEADER, encoding="utf-8")
        with drafts.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(new_rows) + "\n")

    return DraftReport(
        n_papers=len(papers),
        skipped_curated=skipped_curated,
        skipped_existing=skipped_existing,
        written=len(new_rows),
        drafts_path=str(drafts),
    )
