"""Contract-Tests: ``document_kind`` reicht bis in jede Ausgabe (Phase 13 / R3).

Der Nachweis läuft über einen **echten** Mini-Index mit beiden Dokumentarten. Ein
Referenz-Eintrag ohne Volltext muss auf jeder Stufe erkennbar bleiben – im Treffer, im Zitat,
in der Paper-Referenz, in den Paper-Metadaten und im Beleg-Label der Synthese
(docs/adr/0031-reference-contract-and-guardrail-phase13.md).
"""

from __future__ import annotations

from pathlib import Path

from research_graphrag.extraction.model import (
    DOCUMENT_KIND_FULL,
    DOCUMENT_KIND_REFERENCE,
    Chunk,
    Section,
)
from research_graphrag.extraction.pdf import CanonicalPaper
from research_graphrag.generation.evidence import evidence_from_basic
from research_graphrag.generation.provider import DEFAULT_SYSTEM_PROMPT
from research_graphrag.indexing.tfidf_index import TfidfIndex, build_index
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.paper import get_paper
from research_graphrag.retrieval.provenance import (
    REFERENCE_EVIDENCE_MARKER,
    Citation,
    ProvenanceAssembler,
)

_FULL_TEXT = "graph anonymization protects social network structure against re-identification"
_STUB_TEXT = "Towards Identity Anonymization on Graphs\n\ngraph anonymization via k-isomorphism"


def _full_paper() -> CanonicalPaper:
    """Ein gewöhnliches Volltext-Paper mit einem Chunk."""
    return CanonicalPaper(
        paper_id="ffff0001",
        source_uri="file:///Volltext.pdf",
        source_sha256="0" * 64,
        n_pages=3,
        sections=(
            Section(
                section_id="s1", title="Methoden", kind="body", level=1, page_number=1, order=0
            ),
        ),
        chunks=(
            Chunk(
                chunk_id="ffff0001-c0000",
                paper_id="ffff0001",
                page_number=1,
                text=_FULL_TEXT,
                char_count=len(_FULL_TEXT),
                section_id="s1",
                section_title="Methoden",
                page_end=1,
            ),
        ),
        quality_flags=(),
    )


def _reference_paper() -> CanonicalPaper:
    """Ein Referenz-Eintrag: ein Chunk aus Titel und Abstract, ohne Seite."""
    return CanonicalPaper(
        paper_id="rrrr0002",
        source_uri="file:///Towards%20Identity%20Anonymization.refjson",
        source_sha256="1" * 64,
        n_pages=0,
        sections=(
            Section(
                section_id="s1", title="Abstract", kind="abstract", level=1, page_number=0, order=0
            ),
        ),
        chunks=(
            Chunk(
                chunk_id="rrrr0002-c0000",
                paper_id="rrrr0002",
                page_number=0,
                text=_STUB_TEXT,
                char_count=len(_STUB_TEXT),
                section_id="s1",
                section_title="Abstract",
                page_end=0,
            ),
        ),
        quality_flags=(),
        document_kind=DOCUMENT_KIND_REFERENCE,
    )


def _build(tmp_path: Path) -> Path:
    """Baut einen Index aus einem Volltext und einem Referenz-Eintrag."""
    db = tmp_path / "index" / "index.sqlite"
    build_index([_full_paper(), _reference_paper()], db)
    return db


def test_hit_carries_document_kind(tmp_path: Path) -> None:
    """Die Chunk-Primitive reicht die Dokumentart aus der Tabelle ``papers`` durch."""
    index = TfidfIndex.load(_build(tmp_path))
    kinds = {hit.paper_id: hit.document_kind for hit in index.search("anonymization", k=5)}

    assert kinds == {"ffff0001": DOCUMENT_KIND_FULL, "rrrr0002": DOCUMENT_KIND_REFERENCE}


def test_citation_exposes_document_kind(tmp_path: Path) -> None:
    """Jedes Zitat trägt die Dokumentart – im Objekt und im serialisierten Contract."""
    index = TfidfIndex.load(_build(tmp_path))
    hit = next(hit for hit in index.search("k-isomorphism", k=5) if hit.paper_id == "rrrr0002")
    citation = Citation.from_hit(hit)

    assert citation.document_kind == DOCUMENT_KIND_REFERENCE
    assert citation.to_dict()["document_kind"] == DOCUMENT_KIND_REFERENCE


def test_paper_ref_exposes_document_kind(tmp_path: Path) -> None:
    """Die Paper-Referenz (Global/DRIFT/Zitationen) weist Referenz-Einträge aus."""
    assembler = ProvenanceAssembler.load(_build(tmp_path))

    assert assembler.paper_ref("ffff0001").document_kind == DOCUMENT_KIND_FULL
    reference = assembler.paper_ref("rrrr0002")
    assert reference.document_kind == DOCUMENT_KIND_REFERENCE
    assert reference.to_dict()["document_kind"] == DOCUMENT_KIND_REFERENCE


def test_get_paper_exposes_document_kind(tmp_path: Path) -> None:
    """``get_paper`` trennt einen bewusst unvollständigen Eintrag von einem defekten PDF."""
    db = _build(tmp_path)
    payload = get_paper(db, "rrrr0002").to_dict()

    assert payload["document_kind"] == DOCUMENT_KIND_REFERENCE
    assert payload["n_pages"] == 0
    assert get_paper(db, "ffff0001").to_dict()["document_kind"] == DOCUMENT_KIND_FULL


def test_evidence_label_marks_reference_entry(tmp_path: Path) -> None:
    """Im Beleg-Label steht die Einschränkung, die das Modell in der Antwort nennen soll."""
    evidence = evidence_from_basic(search_basic(_build(tmp_path), "anonymization", k=5))
    labels = {item.paper_id: item.label for item in evidence.items}
    kinds = {item.paper_id: item.document_kind for item in evidence.items}

    assert REFERENCE_EVIDENCE_MARKER in labels["rrrr0002"]
    assert REFERENCE_EVIDENCE_MARKER not in labels["ffff0001"]
    assert kinds["rrrr0002"] == DOCUMENT_KIND_REFERENCE


def test_evidence_item_serializes_document_kind(tmp_path: Path) -> None:
    """Auch der serialisierte Beleg trägt die Dokumentart (Output-Schema)."""
    evidence = evidence_from_basic(search_basic(_build(tmp_path), "anonymization", k=5))
    payloads = {item["paper_id"]: item for item in evidence.to_dict()["items"]}

    assert payloads["rrrr0002"]["document_kind"] == DOCUMENT_KIND_REFERENCE
    assert payloads["ffff0001"]["document_kind"] == DOCUMENT_KIND_FULL


def test_citation_contract_names_the_incompleteness() -> None:
    """Der Antwort-Contract verlangt, die Unvollständigkeit im Antworttext zu benennen."""
    assert "Referenz-Eintrag ohne Volltext" in DEFAULT_SYSTEM_PROMPT
    assert "Titel und Abstract" in DEFAULT_SYSTEM_PROMPT
