"""Integrations-Regression: Eine Korrektur wirkt erst nach dem nächsten Ingest (ADR 0039).

Nutzt die **echte** Pipeline (`pipeline.ingest`), nicht nur die tiefer liegenden Bausteine, um
den in ADR 0039 zugesagten Effekt end-to-end zu belegen: `correct_paper_metadata` schreibt
ausschließlich `metadata/paper_metadata.json`; `get_reference` liest bibliografische Daten aber
aus der im Index gebauten Tabelle `paper_metadata`, die erst der nächste
`python -m scripts.ingest`-Lauf (hier: ein zweiter `ingest()`-Aufruf) neu baut.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from research_graphrag.bibliography.corrections import apply_manual_correction
from research_graphrag.pipeline import ingest
from research_graphrag.retrieval.reference import get_reference

MakePdf = Callable[..., Path]


def _single_paper_id(data: Path) -> str:
    """Liest die (einzige) paper_id aus dem Manifest nach dem ersten Ingest."""
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    (entry,) = manifest.values()
    return str(entry["paper_id"])


def test_correction_is_invisible_until_the_next_ingest(make_pdf: MakePdf, tmp_path: Path) -> None:
    """Vor dem Re-Ingest bleibt get_reference unverändert; danach zeigt es die Korrektur."""
    make_pdf(["quantum entanglement transformer network topic overview"], "papers/a.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    metadata = tmp_path / "metadata" / "paper_metadata.json"
    index = data / "index" / "index.sqlite"

    ingest(papers, data)
    paper_id = _single_paper_id(data)

    before = get_reference(index, paper_id)
    assert before.metadata.doi == ""

    apply_manual_correction(
        index, metadata, data, paper_id, {"doi": "10.9999/korrigiert"}, "Test-Beleg"
    )

    # Noch VOR dem Re-Ingest: derselbe Index, dieselbe (fehlende) DOI.
    still_before = get_reference(index, paper_id)
    assert still_before.metadata.doi == ""

    # Re-Ingest liest metadata/paper_metadata.json neu und baut die Tabelle paper_metadata neu.
    ingest(papers, data, metadata_file=metadata)

    after = get_reference(index, paper_id)
    assert after.metadata.doi == "10.9999/korrigiert"
    assert after.metadata.origins["doi"] == "manual"


def test_explicit_clear_survives_reingest_and_outranks_extracted(
    make_pdf: MakePdf, tmp_path: Path
) -> None:
    """Ein per clear_fields geleertes Feld gewinnt nach dem Re-Ingest gegen extracted (ADR 0040).

    Regressionstest für den in ADR 0040 gemessenen Fall: Eine per Regex extrahierte arXiv-ID
    (hier durch eine im Volltext eingebettete Kennung simuliert) ist ein Fehltreffer; erst ein
    expliziter ``clear_fields``-Aufruf verhindert, dass sie nach dem Re-Ingest weiterhin gewinnt.
    """
    make_pdf(
        ["this work builds on a related preprint arxiv:2406.12934 cited in the body text"],
        "papers/a.pdf",
    )
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    metadata = tmp_path / "metadata" / "paper_metadata.json"
    index = data / "index" / "index.sqlite"

    ingest(papers, data)
    paper_id = _single_paper_id(data)

    apply_manual_correction(
        index,
        metadata,
        data,
        paper_id,
        {},
        "arXiv-ID gehört zu einem im Volltext zitierten Fremdpaper, nicht zu diesem Dokument",
        clear_fields=["arxiv_id"],
    )
    ingest(papers, data, metadata_file=metadata)

    after = get_reference(index, paper_id)
    assert after.metadata.arxiv_id == ""
    assert after.metadata.origins["arxiv_id"] == "manual"


def test_reingest_without_new_pdf_still_picks_up_the_correction(
    make_pdf: MakePdf, tmp_path: Path
) -> None:
    """Ein Re-Ingest ohne neue/geänderte PDFs (Extraktion wird übersprungen) baut die
    Metadaten-Tabelle trotzdem neu – die Korrektur wirkt auch dann."""
    make_pdf(["graph neural network message passing baseline"], "papers/a.pdf")
    papers = tmp_path / "papers"
    data = tmp_path / "data"
    metadata = tmp_path / "metadata" / "paper_metadata.json"
    index = data / "index" / "index.sqlite"

    first = ingest(papers, data)
    paper_id = _single_paper_id(data)
    apply_manual_correction(index, metadata, data, paper_id, {"venue": "ACM SIGCOMM"}, "Beleg")

    second = ingest(papers, data, metadata_file=metadata)

    assert first.extracted == 1
    assert second.extracted == 0  # unverändertes PDF: Extraktion übersprungen
    assert second.skipped == 1
    assert get_reference(index, paper_id).metadata.venue == "ACM SIGCOMM"
