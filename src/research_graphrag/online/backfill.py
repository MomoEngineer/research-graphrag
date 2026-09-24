"""Nachtrag der Personenkennungen aus den abgelegten Rohantworten (Phase 17 / A2, Punkt 3).

Befund 5 der Phase-17-Planung: Die Personenkennung ist **schon heruntergeladen**. Die
OpenAlex-Rohantworten unter ``data/online_raw/`` enthalten je Autor ``author.id`` und ``orcid``;
gespeichert wurde bis Phase 17 nur der Name. Dieses Modul holt die Kennungen **ohne Netzzugriff**
nach (docs/adr/0041-author-identity-and-schema.md, Nachtrag):

* **Zuordnung über das Werk:** Eine Rohantwort gehört zu einem Paper, wenn ihre DOI der DOI des
  Papers entspricht. Für einen Preprint gilt der DataCite-DOI ``10.48550/arxiv.<ID>``.
* **Übernahme nur bei identischer Namensliste:** Die Namen der Rohantwort müssen Position für
  Position den gewonnenen Autoren des Papers entsprechen. Andernfalls ist die Zuordnung Kennung ↔
  Name nicht belegt, und es wird nichts übernommen.
* **Widersprüche werden ausgewiesen, nicht aufgelöst:** Liefern mehrere Rohantworten zu
  demselben Werk verschiedene Kennungen, bleibt das Paper ohne Kennung und steht als Konflikt
  im Bericht.

Die Rohantworten der arXiv-Schnittstelle (``*.xml``) tragen keine Kennung und bleiben
unberücksichtigt.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ..bibliography.model import CONFIDENCE_STRONG, ORIGIN_RESOLVED, MetadataRecord
from ..bibliography.store import upsert_records
from ..bibliography.triage import IndexedPaper
from .metadata import ARXIV_DOI_PREFIX, author_identifier_lists, authorships_of_work
from .report import escape_markdown

ACTION_UPDATED = "updated"
"""Der gespeicherte ``resolved``-Datensatz erhielt seine Kennungen."""

ACTION_ADDED = "added"
"""Ein Kennungs-Datensatz wurde ergänzt (kein gespeicherter ``resolved``-Datensatz vorhanden)."""

ACTION_CONFLICT = "conflict"
"""Mehrere Rohantworten liefern verschiedene Kennungen – nichts übernommen."""

ACTION_MISMATCH = "mismatch"
"""Der gespeicherte ``resolved``-Datensatz trägt eine andere Namensliste – nichts übernommen."""

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi:")


@dataclass(frozen=True)
class RawAuthorship:
    """Die Autorennennungen **eines** Werks aus **einer** Rohantwort.

    Attributes:
        names: Namen in der Schreibweise der Quelle (wie beim Auflösungslauf gelesen).
        author_ids: OpenAlex-Autor-IDs, positionsgleich (leer, wenn keine vorliegt).
        author_orcids: ORCIDs, positionsgleich (leer, wenn keine vorliegt).
        source: Datei der Rohantwort, relativ zum Ablageort (Beleg).
    """

    names: tuple[str, ...]
    author_ids: tuple[str, ...]
    author_orcids: tuple[str, ...]
    source: str

    @property
    def identifiers(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Die Kennungen als Vergleichsschlüssel (für die Konfliktprüfung)."""
        return (self.author_ids, self.author_orcids)


@dataclass(frozen=True)
class BackfillDecision:
    """Die Entscheidung für **ein** Paper."""

    paper_id: str
    action: str
    note: str


@dataclass(frozen=True)
class BackfillRun:
    """Ergebnis eines Nachtrags: neuer Datenstand (noch nicht gespeichert) und Entscheidungen."""

    records: tuple[MetadataRecord, ...]
    decisions: tuple[BackfillDecision, ...]
    n_raw_files: int
    n_unreadable: int

    def count(self, action: str) -> int:
        """Zahl der Entscheidungen einer Art."""
        return sum(1 for decision in self.decisions if decision.action == action)


def _normalized_doi(value: object) -> str:
    """Bringt eine DOI in die Vergleichsform (ohne Präfix, klein)."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    lowered = text.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def work_keys(doi: str, arxiv_id: str) -> tuple[str, ...]:
    """Die Werk-Schlüssel eines Papers: eigene DOI und – für Preprints – der DataCite-DOI."""
    keys: list[str] = []
    if doi.strip():
        keys.append(_normalized_doi(doi))
    if arxiv_id.strip():
        keys.append(f"{ARXIV_DOI_PREFIX}{arxiv_id.strip()}".lower())
    return tuple(keys)


def load_raw_authorships(raw_dir: Path) -> tuple[dict[str, tuple[RawAuthorship, ...]], int, int]:
    """Liest alle OpenAlex-Rohantworten und ordnet die Nennungen je Werk-DOI zu.

    Gelesen werden Einzelwerke (DOI-Abfrage) **und** Trefferlisten (Titel-Suche). Eine
    unlesbare Datei ist ein Befund, kein Abbruch.

    Args:
        raw_dir: Ablageort der Rohantworten (``data/online_raw``).

    Returns:
        ``(Nennungen je Werk-DOI, Zahl der gelesenen JSON-Dateien, Zahl der unlesbaren)``.
    """
    index: dict[str, list[RawAuthorship]] = {}
    files = sorted(raw_dir.rglob("*.json")) if raw_dir.is_dir() else []
    unreadable = 0
    for path in files:
        try:
            data = json.loads(path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            unreadable += 1
            continue
        if not isinstance(data, dict):
            continue
        works = data.get("results") if isinstance(data.get("results"), list) else [data]
        for work in works or []:
            if not isinstance(work, dict):
                continue
            doi = _normalized_doi(work.get("doi"))
            identities = authorships_of_work(work)
            ids, orcids = author_identifier_lists(identities)
            if not doi or not (ids or orcids):
                continue
            index.setdefault(doi, []).append(
                RawAuthorship(
                    names=tuple(identity.name for identity in identities),
                    author_ids=ids,
                    author_orcids=orcids,
                    source=path.relative_to(raw_dir).as_posix(),
                )
            )
    return {key: tuple(value) for key, value in index.items()}, len(files), unreadable


def backfill_identities(
    papers: Sequence[IndexedPaper],
    records: Sequence[MetadataRecord],
    raw: Mapping[str, Sequence[RawAuthorship]],
    *,
    n_raw_files: int = 0,
    n_unreadable: int = 0,
) -> BackfillRun:
    """Trägt die Kennungen aus den Rohantworten nach, wo die Zuordnung belegt ist.

    Betrachtet werden Paper, deren gewonnene Autorenliste noch **keine** Kennung trägt. Der
    Datensatz, der die Kennungen erhält, ist der gespeicherte ``resolved``-Datensatz mit
    **derselben** Namensliste. Fehlt er, entsteht ein Kennungs-Datensatz, der nur Namen und
    Kennungen trägt. Über die Regel „identische Namensliste“ reichert er die gewonnene Liste an
    (siehe :func:`research_graphrag.bibliography.resolve.resolve_metadata`), ohne ein anderes
    Feld zu verändern.

    Args:
        papers: Die Paper des Index samt aufgelöster Metadaten.
        records: Die gespeicherten Datensätze.
        raw: Nennungen je Werk-DOI aus :func:`load_raw_authorships`.
        n_raw_files: Zahl der gelesenen Dateien (nur für den Bericht).
        n_unreadable: Zahl der unlesbaren Dateien (nur für den Bericht).

    Returns:
        Den neuen Datenstand und je betroffenem Paper eine Entscheidung.
    """
    stored = {(record.paper_id, record.origin): record for record in records}
    updates: list[MetadataRecord] = []
    decisions: list[BackfillDecision] = []
    for paper in sorted(papers, key=lambda item: item.paper_id):
        item = paper.metadata
        if not item.authors or item.author_ids or item.author_orcids:
            continue
        matches = [
            entry
            for key in work_keys(item.doi, item.arxiv_id)
            for entry in raw.get(key, ())
            if entry.names == item.authors
        ]
        if not matches:
            continue
        variants = {entry.identifiers for entry in matches}
        if len(variants) > 1:
            sources = ", ".join(sorted({entry.source for entry in matches}))
            decisions.append(
                BackfillDecision(
                    paper.paper_id,
                    ACTION_CONFLICT,
                    f"{len(variants)} verschiedene Kennungslisten in {sources}",
                )
            )
            continue
        entry = matches[0]
        evidence = f"Personenkennungen aus Rohantwort {entry.source}"
        current = stored.get((paper.paper_id, ORIGIN_RESOLVED))
        if current is None:
            updates.append(
                MetadataRecord(
                    paper_id=paper.paper_id,
                    origin=ORIGIN_RESOLVED,
                    authors=entry.names,
                    author_ids=entry.author_ids,
                    author_orcids=entry.author_orcids,
                    confidence=CONFIDENCE_STRONG,
                    evidence=evidence,
                )
            )
            decisions.append(BackfillDecision(paper.paper_id, ACTION_ADDED, evidence))
        elif current.authors == entry.names:
            if current.author_ids or current.author_orcids:
                continue
            updates.append(
                replace(current, author_ids=entry.author_ids, author_orcids=entry.author_orcids)
            )
            decisions.append(BackfillDecision(paper.paper_id, ACTION_UPDATED, evidence))
        else:
            decisions.append(
                BackfillDecision(
                    paper.paper_id,
                    ACTION_MISMATCH,
                    "gespeicherter resolved-Datensatz mit anderer Namensliste",
                )
            )
    return BackfillRun(
        records=upsert_records(records, updates),
        decisions=tuple(decisions),
        n_raw_files=n_raw_files,
        n_unreadable=n_unreadable,
    )


def render_backfill(timestamp: str, run: BackfillRun) -> list[str]:
    """Rendert einen Nachtrag als Abschnitt für ``data/metadata_log.md``."""
    lines = [
        f"## Nachtrag Personenkennungen {timestamp}",
        "",
        f"- Rohantworten gelesen: {run.n_raw_files} (unlesbar: {run.n_unreadable}) · "
        f"ergänzt: {run.count(ACTION_UPDATED) + run.count(ACTION_ADDED)} · "
        f"Konflikte: {run.count(ACTION_CONFLICT)} · "
        f"andere Namensliste: {run.count(ACTION_MISMATCH)}",
        "",
    ]
    for action, heading in (
        (ACTION_CONFLICT, "Konflikte (nichts übernommen)"),
        (ACTION_MISMATCH, "Andere Namensliste (nichts übernommen)"),
    ):
        chosen = [decision for decision in run.decisions if decision.action == action]
        if not chosen:
            continue
        lines += [f"### {heading}", ""]
        lines += [
            f"- `{decision.paper_id}` — {escape_markdown(decision.note, limit=300)}"
            for decision in chosen
        ]
        lines.append("")
    return lines
