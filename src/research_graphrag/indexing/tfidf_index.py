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
"""

from __future__ import annotations

import json
import sqlite3
import threading
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer
from sklearn.metrics.pairwise import linear_kernel

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.extraction.model import DOCUMENT_KIND_FULL, DOCUMENT_KIND_REFERENCE
from research_graphrag.extraction.pdf import CanonicalPaper
from research_graphrag.indexing import bm25
from research_graphrag.indexing.fusion import fuse_rankings

Scoring = Literal["hybrid", "tfidf", "bm25"]
"""Wählbare Wertung: Rang-Fusion beider Verfahren, nur TF-IDF-Kosinus oder nur BM25."""

DEFAULT_SCORING: Scoring = "hybrid"
"""Standard-Wertung aller Chunk-Modi (docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md)."""

_SCORINGS: frozenset[str] = frozenset(("hybrid", "tfidf", "bm25"))

_CSR_DTYPE = np.int64
"""Fester Speichertyp der persistierten Zähl-Matrix (versionsunabhängig von scikit-learn/scipy)."""

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
    """Rekonstruiert die CSR-Zähl-Matrix bit-genau aus den gespeicherten Rohdaten."""
    return sp.csr_matrix(
        (
            np.frombuffer(data, dtype=_CSR_DTYPE),
            np.frombuffer(indices, dtype=_CSR_DTYPE),
            np.frombuffer(indptr, dtype=_CSR_DTYPE),
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

    def _ranking(self, scores: Any) -> list[int]:
        """Absteigende Rangliste der Zeilen mit positivem Score (Tie-Break ``chunk_id``)."""
        positive = [i for i in range(len(self._refs)) if float(scores[i]) > 0.0]
        positive.sort(key=lambda i: (-float(scores[i]), self._refs[i].chunk_id))
        return positive

    def _scores(self, query: str) -> tuple[Any, Any]:
        """Bewertet die Anfrage mit beiden Verfahren (eine Tokenisierung, zwei Wertungen)."""
        query_counts = self._vectorizer.transform([query])
        tfidf_scores = linear_kernel(
            self._transformer.transform(query_counts), self._matrix
        ).ravel()
        return tfidf_scores, bm25.score(self._bm25_weights, query_counts)

    def _all_scores(self, query: str, scoring: Scoring) -> tuple[dict[int, float], Any, Any]:
        """Berechnet Ranking und rohe Teil-Scores in einem Durchgang (ein Query-Vektor).

        Gemeinsamer Kern von :meth:`search` und :meth:`score_chunks_by_paper`. Das
        Ranking-Dict enthält den Wert der **gewählten** Wertung (Fusionswert bei ``hybrid``,
        sonst der Rohwert); die rohen TF-IDF-/BM25-Arrays bleiben daneben erhalten, weil
        ``search`` sie **unabhängig** von der gewählten Wertung für die Contract-Felder
        ``score_tfidf``/``score_bm25`` jedes Treffers braucht (docs/adr/0014).

        Raises:
            DomainError: ``invalid_input`` bei leerer Anfrage oder unbekannter Wertung.
        """
        if not query.strip():
            raise DomainError(ErrorCode.INVALID_INPUT, "Leere Suchanfrage.")
        if scoring not in _SCORINGS:
            raise DomainError(ErrorCode.INVALID_INPUT, f"Unbekannte Wertung: {scoring}")

        tfidf_scores, bm25_scores = self._scores(query)
        if scoring == "tfidf":
            order = self._ranking(tfidf_scores)
            ranked: dict[int, float] = {i: float(tfidf_scores[i]) for i in order}
        elif scoring == "bm25":
            order = self._ranking(bm25_scores)
            ranked = {i: float(bm25_scores[i]) for i in order}
        else:
            ranked = fuse_rankings([self._ranking(tfidf_scores), self._ranking(bm25_scores)])
        return ranked, tfidf_scores, bm25_scores

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
        ranked, _tfidf_scores, _bm25_scores = self._all_scores(query, scoring)
        by_paper: dict[str, list[float]] = {}
        for row_index, score in ranked.items():
            by_paper.setdefault(self._refs[row_index].paper_id, []).append(score)
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
            k: Maximale Trefferzahl (> 0).
            paper_ids: Optionaler Filter – nur Chunks dieser Paper werden berücksichtigt
                (z. B. Local-Fan-out je Nachbarpaper oder DRIFT innerhalb einer Community).
            scoring: ``hybrid`` (Default, Rang-Fusion aus BM25 und TF-IDF), ``tfidf``
                (nur Kosinus) oder ``bm25`` (nur BM25).

        Returns:
            Absteigend sortierte Treffer; ein Chunk erscheint nur, wenn mindestens eines der
            beteiligten Verfahren ihn positiv bewertet. Leere Liste ohne Übereinstimmung.
            **Referenz-Einträge stehen hinter den Volltext-Treffern** (siehe
            :func:`demote_references`).

        Raises:
            DomainError: ``invalid_input`` bei leerer Anfrage, ``k <= 0`` oder unbekannter
                Wertung.
        """
        if k <= 0:
            raise DomainError(ErrorCode.INVALID_INPUT, "k muss > 0 sein.")

        ranked, tfidf_scores, bm25_scores = self._all_scores(query, scoring)
        order = sorted(ranked, key=lambda i: (-ranked[i], self._refs[i].chunk_id))

        selected: list[tuple[_ChunkRef, float, float, float]] = []
        for i in order:
            if len(selected) >= k:
                break
            ref = self._refs[i]
            if paper_ids is not None and ref.paper_id not in paper_ids:
                continue
            selected.append((ref, ranked[i], float(tfidf_scores[i]), float(bm25_scores[i])))

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

        Args:
            chunk_id: Ausgangs-Chunk (muss im Index liegen).
            k: Maximale Nachbarzahl (> 0).

        Returns:
            Absteigend sortierte Nachbar-Treffer mit Score > 0; leer ohne Übereinstimmung.
            ``score`` und ``score_tfidf`` sind identisch, ``score_bm25`` ist ``0.0``.
            **Referenz-Einträge stehen hinter den Volltext-Nachbarn** (siehe
            :func:`demote_references`).

        Raises:
            DomainError: ``invalid_input`` bei ``k <= 0``; ``not_found`` wenn die ``chunk_id``
                unbekannt ist.
        """
        if k <= 0:
            raise DomainError(ErrorCode.INVALID_INPUT, "k muss > 0 sein.")
        seed_row = next((i for i, ref in enumerate(self._refs) if ref.chunk_id == chunk_id), None)
        if seed_row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"Chunk nicht gefunden: {chunk_id}")

        scores = linear_kernel(self._matrix[seed_row], self._matrix).ravel()
        order = sorted(
            range(len(self._refs)),
            key=lambda i: (-float(scores[i]), self._refs[i].chunk_id),
        )

        selected: list[tuple[_ChunkRef, float]] = []
        for i in order:
            if len(selected) >= k:
                break
            if i == seed_row:
                continue
            score = float(scores[i])
            if score <= 0.0:
                continue
            selected.append((self._refs[i], score))

        texts = self._fetch_texts(ref.chunk_id for ref, _score in selected)
        hits = [_hit(ref, score, texts[ref.chunk_id], score_tfidf=score) for ref, score in selected]
        return demote_references(hits)
