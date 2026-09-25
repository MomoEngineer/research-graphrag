"""Lexikalischer Chunk-Index über SQLite (Offline-Hybrid, Option B).

Die **SQLite-Datei ist die Source of Truth** (Papers + Chunks). Seit Phase 15 / G2 wird
zusätzlich der **fertig tokenisierte Zustand** (Vokabular + Zähl-Matrix) additiv persistiert –
das sind reine Zahlen (kein `pickle`, keine Bindung an eine `scikit-learn`-Version), aus denen
`TfidfTransformer` und BM25 beim Laden deterministisch **denselben** Raum rekonstruieren, den ein
frischer `CountVectorizer`-Fit über dieselben Texte ergäbe – nur ohne die teure Tokenisierung.
Grundsatz und Präzisierung: docs/adr/0005-graphrag-index-backend-open.md,
docs/adr/0033-response-latency-cache-and-persisted-tfidf-state-phase15.md.

Über **einer** Tokenisierung stehen zwei Wertungen: der bisherige **TF-IDF-Kosinus** (via
``TfidfTransformer`` – dieselbe Pipeline, die ``TfidfVectorizer`` intern bildet) und die
handimplementierte **BM25**-Wertung (:mod:`research_graphrag.indexing.bm25`). Beide werden per
Reciprocal Rank Fusion (:mod:`research_graphrag.indexing.fusion`) zur Standard-Wertung ``hybrid``
verbunden; siehe docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md. Der Klassenname
:class:`TfidfIndex` bleibt aus Gründen der Stabilität bestehen (er ist in Spezifikationen und
älteren ADRs referenziert).

Determinismus: Vektorisierer und Gewichte sind bei gleicher Eingabe/Konfiguration deterministisch;
Ties werden über die ``chunk_id`` stabil gebrochen. ``TfidfIndex.load`` cacht das Ergebnis
**pro Prozess**, ungültig gemacht über den **Zustand der Datei** (Größe + Änderungszeit), nie
über eine Zeitspanne – ein neu gebauter Index wirkt dadurch weiterhin ohne Neustart des
MCP-Servers (On-Read-Frische, docs/adr/0010-drop-in-workflow-and-qa-phase6.md).

Seit Phase 16 / F1 rechnet die Wertung **bit-identisch, aber ohne volle Matrixmultiplikation**
(docs/adr/0044-response-latency-bit-identical-scoring-and-fts5-phase16.md): Die Scores entstehen
spaltenweise nur über die Terme der Anfrage – in derselben Summationsfolge je Chunk wie das
bisherige Sparse-Produkt –, Ranglisten, Fusion und Top-*k* laufen vektorisiert mit identischem
Tie-Break, und die Wertung einer Anfrage wird am Index-Objekt gemerkt, sodass Seed-, Fan-out-
und DRIFT-Suchen derselben Anfrage sie teilen.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import warnings
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import DOCUMENT_KIND_FULL, DOCUMENT_KIND_REFERENCE
from research_graphrag.extraction.pdf import CanonicalPaper
from research_graphrag.indexing import bm25
from research_graphrag.indexing.fusion import RRF_K
from research_graphrag.limits import check_max_count

Scoring = Literal["hybrid", "tfidf", "bm25"]
"""Wählbare Wertung: Rang-Fusion beider Verfahren, nur TF-IDF-Kosinus oder nur BM25."""

DEFAULT_SCORING: Scoring = "hybrid"
"""Standard-Wertung aller Chunk-Modi (docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)."""

_SCORINGS: frozenset[str] = frozenset(("hybrid", "tfidf", "bm25"))

_CSR_DTYPE = np.int64
"""Fester Speichertyp der persistierten Zähl-Matrix (versionsunabhängig von scikit-learn/scipy)."""

SCORE_MEMO_SIZE = 4
"""Zahl der am Index-Objekt gemerkten Anfrage-Wertungen (Phase 16 / F1).

Eine Local-Anfrage wertet dieselbe Anfrage bis zu sechsmal (Seed + Fan-out), DRIFT zwei- bis
dreimal; wenige Einträge genügen deshalb. Jeder Eintrag hält drei Arrays je Chunk."""

SCHEMA_VERSION = "0.6.0"
"""Version des Index-Schemas. ``0.5.0 -> 0.6.0``: neue Tabelle ``tfidf_state`` – Vokabular und
Zähl-Matrix (CSR) werden beim Bau **einmal** tokenisiert und persistiert, statt bei **jedem**
Laden aus den Chunk-Texten neu gefittet zu werden (Phase 15 / G2,
docs/adr/0033-response-latency-cache-and-persisted-tfidf-state-phase15.md). ``0.4.0 -> 0.5.0``:
``papers`` um ``document_kind`` erweitert –
ein Referenz-Eintrag ohne Volltext ist eine **Eigenschaft des Dokuments**, kein Qualitäts-Flag
(siehe docs/adr/0030-reference-entries-in-corpus-phase13.md). ``0.3.0 -> 0.4.0``: ``chunks`` um
``page_end`` erweitert – die
Seite ist keine Chunk-Grenze mehr, sondern eine Provenienz-Range (siehe
docs/adr/0013-chunking-refinement-phase7.md). ``0.2.0 -> 0.3.0``: ``papers`` um die JSON-Spalte
``identifiers`` (DOI/arXiv) erweitert, damit ``get_paper`` zitierfähige Identifikatoren aus der
Source of Truth liefert (siehe docs/adr/0009-mcp-server-stdio-phase5.md). ``0.1.0 -> 0.2.0``:
Chunk-Provenienz um ``section_title`` ergänzt (siehe
docs/adr/0008-retrieval-and-query-router-phase4.md). Voller Re-Index genügt (keine Migration)."""

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE papers (
    paper_id      TEXT PRIMARY KEY,
    source_uri    TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    n_pages       INTEGER NOT NULL,
    identifiers   TEXT NOT NULL DEFAULT '{}',
    document_kind TEXT NOT NULL DEFAULT 'full'
);
CREATE TABLE chunks (
    chunk_id      TEXT PRIMARY KEY,
    paper_id      TEXT NOT NULL,
    page_number   INTEGER NOT NULL,
    page_end      INTEGER NOT NULL DEFAULT 0,
    text          TEXT NOT NULL,
    char_count    INTEGER NOT NULL,
    section_title TEXT NOT NULL DEFAULT '',
    row_index     INTEGER NOT NULL,
    FOREIGN KEY (paper_id) REFERENCES papers (paper_id)
);
CREATE TABLE tfidf_state (
    id           INTEGER PRIMARY KEY CHECK (id = 0),
    n_docs       INTEGER NOT NULL,
    n_features   INTEGER NOT NULL,
    vocabulary   TEXT NOT NULL,
    counts_data    BLOB NOT NULL,
    counts_indices BLOB NOT NULL,
    counts_indptr  BLOB NOT NULL
);
"""


@dataclass(frozen=True)
class Hit:
    """Ein Retrieval-Treffer mit Provenienz (``page_number`` = Start-, ``page_end`` = Endseite).

    ``score`` ist der Wert der **verwendeten** Wertung: bei ``hybrid`` der Fusionswert (ein
    Rangmaß, **keine** Ähnlichkeit), sonst der Rohwert des gewählten Verfahrens.
    ``score_tfidf``/``score_bm25`` weisen die Beiträge beider Verfahren aus
    (docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).

    ``identifiers`` und ``citation_key`` stammen aus der Tabelle ``paper_metadata`` und machen
    jeden Treffer **extern auflösbar** (docs/adr/0025-citable-paper-metadata.md); sie sind leer,
    wenn zu dem Paper nichts bekannt ist oder der Index vor Phase 12 gebaut wurde.

    ``document_kind`` weist aus, ob der Treffer aus einem Volltext oder aus einem
    **Referenz-Eintrag** (nur Titel und Abstract) stammt. Er ist Pflichtbestandteil des
    Contracts: Ein Beleg ohne Volltext muss als solcher erkennbar sein, sonst wirkt ein
    Abstract-Zitat wie ein Volltext-Beleg
    (docs/adr/0031-reference-contract-and-guardrail-phase13.md).
    """

    chunk_id: str
    paper_id: str
    page_number: int
    score: float
    snippet: str
    source_uri: str
    section_title: str = ""
    page_end: int = 0
    score_tfidf: float = 0.0
    score_bm25: float = 0.0
    identifiers: Mapping[str, str] = field(default_factory=dict)
    citation_key: str = ""
    document_kind: str = DOCUMENT_KIND_FULL


@dataclass(frozen=True)
class _ChunkRef:
    """Interne Chunk-Referenz inkl. Provenienz (Reihenfolge = TF-IDF-Zeile).

    Trägt bewusst **keinen** Chunk-Text: Für die Wertung genügen Kennungen und Gewichte: Der
    Text wird erst für die tatsächlichen Top-*k*-Treffer nachgeladen (Phase 15 / G2) – bei
    Tausenden von Chunks wäre das Halten aller Texte im Speicher der größte, aber am wenigsten
    genutzte Speicheranteil.
    """

    chunk_id: str
    paper_id: str
    page_number: int
    source_uri: str
    section_title: str = ""
    page_end: int = 0
    identifiers: Mapping[str, str] = field(default_factory=dict)
    citation_key: str = ""
    document_kind: str = DOCUMENT_KIND_FULL


@dataclass(frozen=True)
class _Scored:
    """Wertung **einer** Anfrage über alle Zeilen – gemeinsam genutzt (Phase 16 / F1).

    Attributes:
        values: Wert der gewählten Wertung je Zeile (Fusionswert bei ``hybrid``, sonst Rohwert);
            außerhalb von ``members`` ohne Bedeutung.
        members: Zeilen mit Wert – bei ``hybrid`` alle, die mindestens ein Verfahren positiv
            bewertet, sonst die mit positivem Rohwert (aufsteigend).
        tfidf: Roher TF-IDF-Kosinus je Zeile (Contract-Feld ``score_tfidf``).
        bm25: Roher BM25-Wert je Zeile (Contract-Feld ``score_bm25``).
        insertion: Die Mitgliedszeilen in der Reihenfolge, in der die frühere
            ``fuse_rankings``-Rechnung sie einfügte (erst TF-IDF-Rangliste, dann neue Zeilen aus
            der BM25-Rangliste); Grundlage der Listenreihenfolge in :meth:`score_chunks_by_paper`.
    """

    values: Any
    members: Any
    tfidf: Any
    bm25: Any
    insertion: Any


def _snippet(text: str, limit: int = 200) -> str:
    """Erzeugt einen einzeiligen, gekürzten Ausschnitt (für die Antwort-Anzeige)."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _hit(
    ref: _ChunkRef, score: float, text: str, *, score_tfidf: float = 0.0, score_bm25: float = 0.0
) -> Hit:
    """Bildet eine interne Chunk-Referenz, ihren (separat nachgeladenen) Text und ihre Scores
    auf einen :class:`Hit` ab."""
    return Hit(
        chunk_id=ref.chunk_id,
        paper_id=ref.paper_id,
        page_number=ref.page_number,
        score=score,
        snippet=_snippet(text),
        source_uri=ref.source_uri,
        section_title=ref.section_title,
        page_end=ref.page_end,
        score_tfidf=score_tfidf,
        score_bm25=score_bm25,
        identifiers=ref.identifiers,
        citation_key=ref.citation_key,
        document_kind=ref.document_kind,
    )


_NO_CITATION_DATA: tuple[Mapping[str, str], str] = ({}, "")


def demote_references(hits: list[Hit]) -> list[Hit]:
    """Sortiert Referenz-Einträge **hinter** die Volltext-Treffer derselben Liste.

    Die Guardrail der Chunk-Suche: Ein Referenz-Eintrag besteht nur aus Titel und Abstract und
    wird von den längennormierenden Wertungen (BM25, TF-IDF) systematisch bevorzugt – sein Score
    ist deshalb mit dem eines Volltext-Chunks **nicht vergleichbar**.

    Sie wirkt **nachrangig, nicht ausschließend**: Die *Auswahl* der Top-k bleibt unverändert,
    nur ihre *Reihenfolge* ändert sich. Gibt es keinen passenden Volltext, steht der
    Referenz-Eintrag weiterhin ganz vorn – genau der Fall, für den er existiert. Die Sortierung
    ist stabil, innerhalb beider Gruppen bleibt die Wertungsreihenfolge erhalten.

    Messgrundlage und verworfene Varianten:
    docs/adr/0031-reference-contract-and-guardrail-phase13.md.

    Args:
        hits: Trefferliste in Wertungsreihenfolge.

    Returns:
        Dieselben Treffer, Volltext zuerst.
    """
    return sorted(hits, key=lambda hit: hit.document_kind == DOCUMENT_KIND_REFERENCE)


def _load_citation_data(
    connection: sqlite3.Connection,
) -> dict[str, tuple[Mapping[str, str], str]]:
    """Liest Identifikatoren und Zitierschlüssel je Paper aus ``paper_metadata``.

    Die Tabelle ist ein **additives** Teilschema (docs/adr/0025-citable-paper-metadata.md); ein
    vor Phase 12 gebauter Index kennt sie nicht. Ihr Fehlen ist deshalb kein Fehler – die
    Treffer tragen dann schlicht keine Zitationsdaten.
    """
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'paper_metadata'"
    ).fetchone()
    if exists is None:
        return {}
    data: dict[str, tuple[Mapping[str, str], str]] = {}
    for paper_id, doi, arxiv_id, url, citation_key in connection.execute(
        "SELECT paper_id, doi, arxiv_id, url, citation_key FROM paper_metadata"
    ):
        values = {"doi": str(doi), "arxiv": str(arxiv_id), "url": str(url)}
        data[str(paper_id)] = (
            {key: value for key, value in values.items() if value},
            str(citation_key),
        )
    return data


def _serialize_counts(counts: Any) -> tuple[bytes, bytes, bytes]:
    """Serialisiert eine Zähl-Matrix als CSR-Rohdaten (fester Speichertyp, :data:`_CSR_DTYPE`)."""
    csr = counts.tocsr()
    return (
        csr.data.astype(_CSR_DTYPE).tobytes(),
        csr.indices.astype(_CSR_DTYPE).tobytes(),
        csr.indptr.astype(_CSR_DTYPE).tobytes(),
    )


def _deserialize_counts(
    data: bytes, indices: bytes, indptr: bytes, n_docs: int, n_features: int
) -> Any:
    """Rekonstruiert die CSR-Zähl-Matrix bit-genau aus den gespeicherten Rohdaten.

    Die Arrays werden kopiert, weil ``np.frombuffer`` schreibgeschützte Sichten liefert und der
    Lader die Zeilen anschließend in place sortiert (Phase 16 / F1).
    """
    return sp.csr_matrix(
        (
            np.frombuffer(data, dtype=_CSR_DTYPE).copy(),
            np.frombuffer(indices, dtype=_CSR_DTYPE).copy(),
            np.frombuffer(indptr, dtype=_CSR_DTYPE).copy(),
        ),
        shape=(n_docs, n_features),
    )


def build_index(papers: Sequence[CanonicalPaper], db_path: str | Path) -> int:
    """Baut den Index (voller Re-Index) aus den nicht-leeren Chunks der Papers.

    Tokenisiert die Chunk-Texte **einmal** (``CountVectorizer``) und persistiert Vokabular und
    Zähl-Matrix additiv (``tfidf_state``) – ``TfidfIndex.load`` muss sie danach nur noch
    deserialisieren statt neu zu fitten (Phase 15 / G2).

    Args:
        papers: Extrahierte Papers (siehe :mod:`research_graphrag.extraction.pdf`).
        db_path: Zielpfad der SQLite-Index-Datei; Elternordner wird angelegt.

    Returns:
        Anzahl der indexierten (nicht-leeren) Chunks.

    Raises:
        DomainError: ``invalid_input``, wenn keine indexierbaren (nicht-leeren) Chunks
            vorhanden sind (siehe docs/error-model.md).
    """
    indexable = [(chunk, paper) for paper in papers for chunk in paper.chunks if chunk.text.strip()]
    if not indexable:
        raise DomainError(ErrorCode.INVALID_INPUT, "Keine indexierbaren (nicht-leeren) Chunks.")

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()  # voller Re-Index (Standard, siehe Roadmap.md)

    vectorizer = CountVectorizer()
    counts = vectorizer.fit_transform([chunk.text for chunk, _paper in indexable])
    vocabulary = {term: int(index) for term, index in vectorizer.vocabulary_.items()}
    counts_data, counts_indices, counts_indptr = _serialize_counts(counts)

    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,)
        )
        seen_papers: set[str] = set()
        for _chunk, paper in indexable:
            if paper.paper_id in seen_papers:
                continue
            seen_papers.add(paper.paper_id)
            connection.execute(
                "INSERT INTO papers "
                "(paper_id, source_uri, source_sha256, n_pages, identifiers, document_kind) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    paper.paper_id,
                    paper.source_uri,
                    paper.source_sha256,
                    paper.n_pages,
                    json.dumps(
                        {key: paper.identifiers[key] for key in sorted(paper.identifiers)},
                        ensure_ascii=False,
                    ),
                    paper.document_kind,
                ),
            )
        for row_index, (chunk, _paper) in enumerate(indexable):
            connection.execute(
                "INSERT INTO chunks "
                "(chunk_id, paper_id, page_number, page_end, text, char_count, section_title, "
                "row_index) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk.chunk_id,
                    chunk.paper_id,
                    chunk.page_number,
                    chunk.page_end,
                    chunk.text,
                    chunk.char_count,
                    chunk.section_title,
                    row_index,
                ),
            )
        connection.execute(
            "INSERT INTO tfidf_state "
            "(id, n_docs, n_features, vocabulary, counts_data, counts_indices, counts_indptr) "
            "VALUES (0, ?, ?, ?, ?, ?, ?)",
            (
                counts.shape[0],
                counts.shape[1],
                json.dumps(vocabulary, ensure_ascii=False),
                counts_data,
                counts_indices,
                counts_indptr,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return len(indexable)


_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[int, int, TfidfIndex]] = {}
"""Prozess-Cache: aufgelöster Pfad -> ((mtime_ns, Größe), Index). Ungültig über den Dateizustand,
nie über eine Zeitspanne (Phase 15 / G2, Weg C)."""


class TfidfIndex:
    """Geladener Index: TF-IDF- und BM25-Raum über einer gemeinsamen Tokenisierung."""

    def __init__(
        self,
        refs: tuple[_ChunkRef, ...],
        vectorizer: Any,
        transformer: Any,
        matrix: Any,
        bm25_weights: Any,
        db_path: str,
    ) -> None:
        self._refs = refs
        self._vectorizer = vectorizer
        self._transformer = transformer
        self._matrix = matrix
        self._bm25_weights = bm25_weights
        self._db_path = db_path
        # Phase 16 / F1: abgeleitete Hilfsstrukturen, einmal je geladenem Index. Sie hängen am
        # Objekt und verfallen damit zusammen mit ihm über den Dateizustand (ADR 0033).
        chunk_ids = [ref.chunk_id for ref in refs]
        order = sorted(range(len(chunk_ids)), key=chunk_ids.__getitem__)
        self._chunk_rank = np.empty(len(chunk_ids), dtype=np.int64)
        self._chunk_rank[order] = np.arange(len(chunk_ids), dtype=np.int64)
        self._row_of = {chunk_id: row for row, chunk_id in enumerate(chunk_ids)}
        self._paper_number: dict[str, int] = {}
        self._paper_of_row = np.fromiter(
            (self._paper_number.setdefault(ref.paper_id, len(self._paper_number)) for ref in refs),
            dtype=np.int64,
            count=len(refs),
        )
        self._matrix_by_term = matrix.tocsc()
        self._bm25_by_term = bm25_weights.tocsc()
        self._memo: OrderedDict[tuple[str, str], _Scored] = OrderedDict()
        self._memo_lock = threading.Lock()

    @property
    def size(self) -> int:
        """Anzahl der indexierten Chunks."""
        return len(self._refs)

    @classmethod
    def load(cls, db_path: str | Path) -> TfidfIndex:
        """Lädt den Index, sofern nötig – sonst liefert der Prozess-Cache dasselbe Objekt.

        Der Cache ist über den **Dateizustand** (Größe + Änderungszeit) ungültig gemacht, nie
        über eine Zeitspanne: Ein neu gebauter Index (z. B. nach ``ingest``, atomarer Swap via
        ``os.replace``) wirkt beim nächsten Aufruf sofort, ohne Neustart (Phase 15 / G2, Weg C;
        docs/adr/0033-response-latency-cache-and-persisted-tfidf-state-phase15.md).
        """
        path = Path(db_path)
        if not path.is_file():
            raise DomainError(ErrorCode.NOT_FOUND, f"Index nicht gefunden: {path}")

        resolved = str(path.resolve())
        stat = path.stat()
        with _CACHE_LOCK:
            cached = _CACHE.get(resolved)
            if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
                return cached[2]

        index = cls._build_from_db(path, resolved)
        with _CACHE_LOCK:
            _CACHE[resolved] = (stat.st_mtime_ns, stat.st_size, index)
        return index

    @classmethod
    def _build_from_db(cls, path: Path, resolved: str) -> TfidfIndex:
        """Baut ein :class:`TfidfIndex`-Objekt aus der persistierten Vokabular-/Zähl-Matrix.

        Aus **einem** ``CountVectorizer``-Vokabular entstehen die TF-IDF-Matrix (über
        ``TfidfTransformer`` – identisch zum früheren ``TfidfVectorizer``) und die
        BM25-Gewichte. Beide teilen damit Vokabular und Tokenisierung. Die Chunk-Texte selbst
        werden **nicht** geladen (siehe :class:`_ChunkRef`) – nur die für Wertung und
        Provenienz nötigen Spalten.

        Raises:
            DomainError: ``constraint_violation`` wenn der Index keine Chunks oder keinen
                persistierten Vokabular-Zustand enthält (siehe docs/error-model.md).
        """
        connection = sqlite3.connect(str(path))
        try:
            rows = connection.execute(
                "SELECT c.chunk_id, c.paper_id, c.page_number, p.source_uri, "
                "c.section_title, c.page_end, p.document_kind "
                "FROM chunks c JOIN papers p ON p.paper_id = c.paper_id "
                "ORDER BY c.row_index"
            ).fetchall()
            citation_data = _load_citation_data(connection)
            has_state_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'tfidf_state'"
            ).fetchone()
            state_row = (
                connection.execute(
                    "SELECT n_docs, n_features, vocabulary, counts_data, counts_indices, "
                    "counts_indptr FROM tfidf_state WHERE id = 0"
                ).fetchone()
                if has_state_table
                else None
            )
        finally:
            connection.close()

        if not rows:
            raise DomainError(ErrorCode.CONSTRAINT_VIOLATION, "Index enthält keine Chunks.")
        if state_row is None:
            raise DomainError(
                ErrorCode.CONSTRAINT_VIOLATION,
                "Index enthält keinen tokenisierten Zustand (voller Re-Index nötig).",
            )

        refs = tuple(
            _ChunkRef(
                chunk_id=str(row[0]),
                paper_id=str(row[1]),
                page_number=int(row[2]),
                source_uri=str(row[3]),
                section_title=str(row[4]),
                page_end=int(row[5]),
                identifiers=citation_data.get(str(row[1]), _NO_CITATION_DATA)[0],
                citation_key=citation_data.get(str(row[1]), _NO_CITATION_DATA)[1],
                document_kind=str(row[6]),
            )
            for row in rows
        )

        n_docs, n_features, vocabulary_json, counts_data, counts_indices, counts_indptr = state_row
        vocabulary = json.loads(vocabulary_json)
        # Das Vokabular stammt aus einem regulären Fit (siehe build_index) und ist dadurch bereits
        # vollständig normalisiert; sklearn warnt bei vorgegebenem Vokabular dennoch pauschal auf
        # Unicode-Einzelfälle, die vom Vergleich mit .lower() nicht erfasst werden (kein Bug,
        # keine abweichenden Ergebnisse – siehe Byte-Identitätsnachweis in Roadmap.md, Phase 15/G2).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            vectorizer = CountVectorizer(vocabulary=vocabulary)
            vectorizer.fit([])  # finalisiert den Fit-Zustand, ohne das Vokabular zu verändern
        counts = _deserialize_counts(
            counts_data, counts_indices, counts_indptr, int(n_docs), int(n_features)
        )
        # Die persistierten Spaltenindizes sind je Zeile nicht sortiert. Bisher sortierte sie
        # scikit-learn beim Fit nebenbei in place; die spaltenweise Wertung (Phase 16 / F1) setzt
        # sortierte Zeilen voraus, deshalb geschieht es hier ausdrücklich – die Werte beider
        # Matrizen bleiben bitgleich (Nachweis: Roadmap.md, Phase 16 / F0).
        counts.sort_indices()
        transformer = TfidfTransformer()
        matrix = transformer.fit_transform(counts)
        return cls(
            refs=refs,
            vectorizer=vectorizer,
            transformer=transformer,
            matrix=matrix,
            bm25_weights=bm25.build_weights(counts),
            db_path=resolved,
        )

    def _fetch_texts(self, chunk_ids: Iterable[str]) -> dict[str, str]:
        """Lädt die Texte der übergebenen Chunk-IDs nach (nur für die endgültigen Treffer)."""
        ids = list(dict.fromkeys(chunk_ids))
        if not ids:
            return {}
        connection = sqlite3.connect(self._db_path)
        try:
            placeholders = ",".join("?" for _ in ids)
            rows = connection.execute(
                f"SELECT chunk_id, text FROM chunks WHERE chunk_id IN ({placeholders})", ids
            ).fetchall()
        finally:
            connection.close()
        return {str(chunk_id): str(text) for chunk_id, text in rows}

    def _order(self, rows: Any, values: Any) -> Any:
        """Ordnet Zeilen absteigend nach Wert, Tie-Break aufsteigende ``chunk_id``.

        Entspricht ``sorted(rows, key=lambda i: (-values[i], chunk_id))``: Der vorab berechnete
        Rang der ``chunk_id`` (:attr:`_chunk_rank`) bildet den Python-Stringvergleich nach.
        """
        return rows[np.lexsort((self._chunk_rank[rows], -values[rows]))]

    def _top(self, rows: Any, values: Any, k: int) -> Any:
        """Die ersten ``k`` Zeilen von :meth:`_order` – ohne alle Zeilen zu sortieren.

        Behalten werden alle Zeilen, deren Wert mindestens den ``k``-größten erreicht; Gleichstände
        an der Grenze bleiben damit vollständig im Rennen, und der Tie-Break entscheidet exakt
        wie bei einer vollständigen Sortierung.
        """
        if rows.size > k:
            threshold = np.partition(values[rows], rows.size - k)[rows.size - k]
            rows = rows[values[rows] >= threshold]
        return self._order(rows, values)[:k]

    @staticmethod
    def _by_term(by_term: Any, n_rows: int, terms: Any, weights: Any) -> Any:
        """Summiert ``weights[t] * Spalte t`` über die Terme – in der gegebenen Reihenfolge.

        Das ist das Sparse-Produkt ``Zeile · Matrixᵀ`` bzw. ``Matrix · Spalte``, aber nur über
        die Spalten der beteiligten Terme statt über die ganze Matrix. Die Summation je Zeile
        beginnt bei ``0.0`` und folgt der Termreihenfolge – genau der Folge, in der scipys
        ``csr_matmat`` akkumuliert. Das Ergebnis ist deshalb **bitgleich**, nicht nur numerisch
        gleich (Nachweis: Roadmap.md, Phase 16 / F0; Test in ``test_tfidf_index.py``).
        """
        total = np.zeros(n_rows, dtype=np.float64)
        indptr, indices, data = by_term.indptr, by_term.indices, by_term.data
        for term, weight in zip(terms.tolist(), weights.tolist(), strict=True):
            start, end = indptr[term], indptr[term + 1]
            if start != end:
                total[indices[start:end]] += data[start:end] * weight
        return total

    def _scores(self, query: str) -> tuple[Any, Any]:
        """Bewertet die Anfrage mit beiden Verfahren (eine Tokenisierung, zwei Wertungen).

        TF-IDF-Kosinus: die Terme in der gespeicherten Folge des Anfragevektors (so iteriert das
        frühere ``linear_kernel``). BM25: die Terme aufsteigend, denn das frühere
        ``weights @ query.T`` iteriert je Zeile über deren sortierte Spalten.
        """
        query_counts = self._vectorizer.transform([query])
        query_tfidf = self._transformer.transform(query_counts)
        n_rows = len(self._refs)
        tfidf_scores = self._by_term(
            self._matrix_by_term, n_rows, query_tfidf.indices, query_tfidf.data
        )
        ascending = np.argsort(query_counts.indices, kind="stable")
        bm25_scores = self._by_term(
            self._bm25_by_term,
            n_rows,
            query_counts.indices[ascending],
            query_counts.data[ascending].astype(np.float64),
        )
        return tfidf_scores, bm25_scores

    def _ranking(self, scores: Any) -> Any:
        """Absteigende Rangliste der Zeilen mit positivem Score (Tie-Break ``chunk_id``)."""
        return self._order(np.flatnonzero(scores > 0.0), scores)

    def _scored(self, query: str, scoring: Scoring) -> _Scored:
        """Wertet eine Anfrage einmal aus – und merkt sich das Ergebnis am Index-Objekt.

        Gemeinsamer Kern von :meth:`search` und :meth:`score_chunks_by_paper`. Die Fusion rechnet
        wie :func:`research_graphrag.indexing.fusion.fuse_rankings`: je Zeile ``0.0`` plus
        ``1 / (RRF_K + Rang)`` erst aus der TF-IDF-, dann aus der BM25-Rangliste. Die rohen
        TF-IDF-/BM25-Arrays bleiben daneben erhalten, weil jeder Treffer sie **unabhängig** von der
        gewählten Wertung für ``score_tfidf``/``score_bm25`` braucht (docs/adr/0014).

        Seed-, Fan-out- und DRIFT-Suchen derselben Anfrage teilen die Wertung (bis zu
        :data:`SCORE_MEMO_SIZE` Anfragen). Der Merker hängt am Objekt und verfällt mit ihm über
        den Zustand der Index-Datei (docs/adr/0033).

        Raises:
            DomainError: ``invalid_input`` bei leerer Anfrage oder unbekannter Wertung.
        """
        if not query.strip():
            raise DomainError(ErrorCode.INVALID_INPUT, "Leere Suchanfrage.")
        if scoring not in _SCORINGS:
            raise DomainError(ErrorCode.INVALID_INPUT, f"Unbekannte Wertung: {scoring}")

        key = (query, scoring)
        with self._memo_lock:
            cached = self._memo.get(key)
            if cached is not None:
                self._memo.move_to_end(key)
                return cached

        tfidf_scores, bm25_scores = self._scores(query)
        if scoring == "tfidf":
            insertion = self._ranking(tfidf_scores)
            values = tfidf_scores
        elif scoring == "bm25":
            insertion = self._ranking(bm25_scores)
            values = bm25_scores
        else:
            by_tfidf = self._ranking(tfidf_scores)
            by_bm25 = self._ranking(bm25_scores)
            values = np.zeros(len(self._refs), dtype=np.float64)
            for ranking in (by_tfidf, by_bm25):
                values[ranking] += 1.0 / (RRF_K + np.arange(1, ranking.size + 1))
            seen = np.zeros(len(self._refs), dtype=bool)
            seen[by_tfidf] = True
            insertion = np.concatenate([by_tfidf, by_bm25[~seen[by_bm25]]])
        scored = _Scored(
            values=values,
            members=np.sort(insertion),
            tfidf=tfidf_scores,
            bm25=bm25_scores,
            insertion=insertion,
        )
        with self._memo_lock:
            self._memo[key] = scored
            while len(self._memo) > SCORE_MEMO_SIZE:
                self._memo.popitem(last=False)
        return scored

    def score_chunks_by_paper(
        self, query: str, *, scoring: Scoring = DEFAULT_SCORING
    ) -> dict[str, list[float]]:
        """Bewertet alle Chunks der Anfrage, gruppiert nach Paper – ohne Text-Fetch.

        Liefert dieselben Scores wie :meth:`search`, aber für **jeden** positiv bewerteten
        Chunk statt nur die Top-k, und ohne den Chunk-Text nachzuladen. Grundlage für
        Aggregationen über Chunk-Mengen, z. B. das Community-Ranking aus den Mitglieds-Chunks
        (``retrieval.global_search.rank_communities``, Phase 10 / V4).

        Args:
            query: Natürlichsprachige Anfrage (nicht leer).
            scoring: ``hybrid`` (Default, Rang-Fusion aus BM25 und TF-IDF), ``tfidf``
                (nur Kosinus) oder ``bm25`` (nur BM25).

        Returns:
            Abbildung Paper-ID → Liste der positiven Chunk-Scores dieses Papers (unsortiert).
            Paper ohne einen einzigen positiv bewerteten Chunk fehlen im Ergebnis.

        Raises:
            DomainError: ``invalid_input`` bei leerer Anfrage oder unbekannter Wertung.
        """
        scored = self._scored(query, scoring)
        by_paper: dict[str, list[float]] = {}
        refs = self._refs
        rows = scored.insertion
        for row, score in zip(rows.tolist(), scored.values[rows].tolist(), strict=True):
            by_paper.setdefault(refs[row].paper_id, []).append(score)
        return by_paper

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        paper_ids: set[str] | None = None,
        scoring: Scoring = DEFAULT_SCORING,
    ) -> list[Hit]:
        """Liefert die Top-k-Chunks der gewählten Wertung mit Provenienz.

        Args:
            query: Natürlichsprachige Anfrage.
            k: Maximale Trefferzahl (``0 < k <= MAX_RESULT_COUNT``).
            paper_ids: Optionaler Filter – nur Chunks dieser Paper werden berücksichtigt
                (z. B. Local-Fan-out je Nachbarpaper oder DRIFT innerhalb einer Community). Der
                Filter wirkt **nach** der Wertung über den ganzen Korpus und **vor** der
                Sortierung; die Werte (bei ``hybrid`` die korpusweiten Ränge) bleiben dadurch
                dieselben wie ohne Filter.
            scoring: ``hybrid`` (Default, Rang-Fusion aus BM25 und TF-IDF), ``tfidf``
                (nur Kosinus) oder ``bm25`` (nur BM25).

        Returns:
            Absteigend sortierte Treffer; ein Chunk erscheint nur, wenn mindestens eines der
            beteiligten Verfahren ihn positiv bewertet. Leere Liste ohne Übereinstimmung.
            **Referenz-Einträge stehen hinter den Volltext-Treffern** (siehe
            :func:`demote_references`).

        Raises:
            DomainError: ``invalid_input`` bei leerer Anfrage, ``k <= 0``,
                ``k > MAX_RESULT_COUNT`` (ADR 0037) oder unbekannter Wertung.
        """
        if k <= 0:
            raise DomainError(ErrorCode.INVALID_INPUT, "k muss > 0 sein.")
        check_max_count("k", k)

        scored = self._scored(query, scoring)
        rows = scored.members
        if paper_ids is not None:
            wanted = [self._paper_number[p] for p in paper_ids if p in self._paper_number]
            rows = rows[np.isin(self._paper_of_row[rows], wanted)]
        chosen = self._top(rows, scored.values, k).tolist()

        selected = [
            (self._refs[i], float(scored.values[i]), float(scored.tfidf[i]), float(scored.bm25[i]))
            for i in chosen
        ]
        texts = self._fetch_texts(ref.chunk_id for ref, *_ in selected)
        hits = [
            _hit(ref, score, texts[ref.chunk_id], score_tfidf=score_tfidf, score_bm25=score_bm25)
            for ref, score, score_tfidf, score_bm25 in selected
        ]
        return demote_references(hits)

    def neighbors_of_chunk(self, chunk_id: str, k: int = 5) -> list[Hit]:
        """Liefert die nächsten Chunks zu einem gegebenen Chunk (Chunk↔Chunk-Kosinus).

        Grundlage der Local-Search-Chunk-Nachbarschaft: bewertet die Ähnlichkeit des
        angegebenen Chunks zu allen anderen Chunks und liefert die Top-k **ohne** den
        Chunk selbst, absteigend sortiert (Tie-Break über ``chunk_id``). Bewusst **ohne**
        BM25: Das ist ein Anfrage-Dokument-Modell und für Ähnlichkeit zwischen zwei
        Dokumenten nicht gedacht (docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).
        Gerechnet wird wie in :meth:`_scores` nur über die Terme des Chunks (Phase 16 / F1).

        Args:
            chunk_id: Ausgangs-Chunk (muss im Index liegen).
            k: Maximale Nachbarzahl (``0 < k <= MAX_RESULT_COUNT``).

        Returns:
            Absteigend sortierte Nachbar-Treffer mit Score > 0; leer ohne Übereinstimmung.
            ``score`` und ``score_tfidf`` sind identisch, ``score_bm25`` ist ``0.0``.
            **Referenz-Einträge stehen hinter den Volltext-Nachbarn** (siehe
            :func:`demote_references`).

        Raises:
            DomainError: ``invalid_input`` bei ``k <= 0`` oder ``k > MAX_RESULT_COUNT``
                (ADR 0037); ``not_found`` wenn die ``chunk_id`` unbekannt ist.
        """
        if k <= 0:
            raise DomainError(ErrorCode.INVALID_INPUT, "k muss > 0 sein.")
        check_max_count("k", k)
        seed_row = self._row_of.get(chunk_id)
        if seed_row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"Chunk nicht gefunden: {chunk_id}")

        seed = self._matrix[seed_row]
        scores = self._by_term(self._matrix_by_term, len(self._refs), seed.indices, seed.data)
        rows = np.flatnonzero(scores > 0.0)
        rows = rows[rows != seed_row]
        chosen = self._top(rows, scores, k).tolist()

        selected = [(self._refs[i], float(scores[i])) for i in chosen]
        texts = self._fetch_texts(ref.chunk_id for ref, _score in selected)
        hits = [_hit(ref, score, texts[ref.chunk_id], score_tfidf=score) for ref, score in selected]
        return demote_references(hits)
