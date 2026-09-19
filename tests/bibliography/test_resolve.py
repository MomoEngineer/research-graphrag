"""Tests für die feldweise Auflösung der Metadaten (Phase 12 / K1, ADR 0025)."""

from __future__ import annotations

from research_graphrag.bibliography.model import (
    CONFIDENCE_NONE,
    CONFIDENCE_STRONG,
    CONFIDENCE_WEAK,
    ORIGIN_CURATED,
    ORIGIN_EXTRACTED,
    ORIGIN_MANUAL,
    ORIGIN_RESOLVED,
    MetadataRecord,
)
from research_graphrag.bibliography.resolve import resolve_all, resolve_metadata


def _record(origin: str, **fields: object) -> MetadataRecord:
    """Baut einen Datensatz einer Herkunft mit den angegebenen Feldern."""
    return MetadataRecord(paper_id="p1", origin=origin, **fields)  # type: ignore[arg-type]


def test_resolution_is_field_wise_not_record_wise() -> None:
    """Komplementäre Quellen ergänzen sich: DOI kuratiert, Autoren aus der Auflösung."""
    resolved = resolve_metadata(
        "p1",
        [
            _record(ORIGIN_CURATED, doi="10.1145/publisher", confidence=CONFIDENCE_STRONG),
            _record(
                ORIGIN_RESOLVED,
                doi="10.48550/arXiv.2401.1",
                authors=("Anna Beispiel",),
                year=2024,
                venue="Proceedings",
                confidence=CONFIDENCE_STRONG,
            ),
            _record(ORIGIN_EXTRACTED, title="Dateiname als Titel", arxiv_id="2401.00001"),
        ],
    )

    assert resolved.doi == "10.1145/publisher"
    assert resolved.authors == ("Anna Beispiel",)
    assert resolved.venue == "Proceedings"
    assert resolved.title == "Dateiname als Titel"
    assert resolved.arxiv_id == "2401.00001"


def test_origins_document_the_winning_source_per_field() -> None:
    """Zu jedem gefüllten Feld ist die gewinnende Herkunft nachvollziehbar."""
    resolved = resolve_metadata(
        "p1",
        [
            _record(ORIGIN_EXTRACTED, title="Aus dem Dateinamen", doi="10.1/falsch"),
            _record(ORIGIN_CURATED, doi="10.1/richtig"),
        ],
    )

    assert resolved.origins == {"title": ORIGIN_EXTRACTED, "doi": ORIGIN_CURATED}
    assert resolved.doi == "10.1/richtig"


def test_manual_outranks_every_other_origin() -> None:
    """Handpflege gewinnt gegen kuratiert, aufgelöst und extrahiert."""
    resolved = resolve_metadata(
        "p1",
        [
            _record(ORIGIN_CURATED, title="kuratiert"),
            _record(ORIGIN_RESOLVED, title="aufgelöst"),
            _record(ORIGIN_EXTRACTED, title="extrahiert"),
            _record(ORIGIN_MANUAL, title="von Hand"),
        ],
    )

    assert resolved.title == "von Hand"
    assert resolved.origins["title"] == ORIGIN_MANUAL


def test_confidence_is_the_weakest_contributing_source() -> None:
    """Eine Angabe ist nur so verlässlich wie ihr schwächster verwendeter Bestandteil."""
    resolved = resolve_metadata(
        "p1",
        [
            _record(ORIGIN_CURATED, title="Titel", confidence=CONFIDENCE_STRONG),
            _record(ORIGIN_EXTRACTED, doi="10.1/x", confidence=CONFIDENCE_WEAK),
        ],
    )

    assert resolved.confidence == CONFIDENCE_WEAK


def test_a_source_without_own_contribution_does_not_lower_the_confidence() -> None:
    """Wer kein Feld beisteuert, beeinflusst die Konfidenz nicht."""
    resolved = resolve_metadata(
        "p1",
        [
            _record(ORIGIN_CURATED, title="Titel", doi="10.1/x", confidence=CONFIDENCE_STRONG),
            _record(ORIGIN_EXTRACTED, title="Titel", doi="10.1/x", confidence=CONFIDENCE_WEAK),
        ],
    )

    assert resolved.confidence == CONFIDENCE_STRONG


def test_manual_explicit_clear_wins_over_a_lower_precedence_value() -> None:
    """Ein explizit geleertes manual-Feld gewinnt gegen einen (falschen) extrahierten Wert."""
    resolved = resolve_metadata(
        "p1",
        [
            _record(
                ORIGIN_MANUAL,
                arxiv_id="",
                cleared_fields=frozenset({"arxiv_id"}),
                confidence=CONFIDENCE_STRONG,
            ),
            _record(ORIGIN_EXTRACTED, arxiv_id="2406.12934"),
        ],
    )

    assert resolved.arxiv_id == ""
    assert resolved.origins["arxiv_id"] == ORIGIN_MANUAL
    assert resolved.confidence == CONFIDENCE_STRONG


def test_manual_empty_field_without_explicit_clear_still_falls_through() -> None:
    """Ohne ``cleared_fields`` bleibt ein leeres manual-Feld "keine Meinung" (Regression)."""
    resolved = resolve_metadata(
        "p1",
        [
            _record(ORIGIN_MANUAL, arxiv_id="", confidence=CONFIDENCE_STRONG),
            _record(ORIGIN_EXTRACTED, arxiv_id="2406.12934"),
        ],
    )

    assert resolved.arxiv_id == "2406.12934"
    assert resolved.origins["arxiv_id"] == ORIGIN_EXTRACTED


def test_unknown_origin_is_ranked_last_but_still_used() -> None:
    """Ein unbekannter Herkunftsname verdrängt keine bekannte Quelle, geht aber nicht verloren."""
    resolved = resolve_metadata(
        "p1",
        [
            _record("irgendwas", title="unbekannt", venue="Nur hier"),
            _record(ORIGIN_EXTRACTED, title="extrahiert"),
        ],
    )

    assert resolved.title == "extrahiert"
    assert resolved.venue == "Nur hier"


def test_records_of_other_papers_are_ignored() -> None:
    """Fremde Datensätze fließen nicht ein."""
    other = MetadataRecord(paper_id="p2", origin=ORIGIN_MANUAL, title="fremd")

    assert resolve_metadata("p1", [other]).title == ""
    assert resolve_metadata("p1", []).confidence == CONFIDENCE_NONE


def test_resolve_all_covers_papers_without_any_record() -> None:
    """Jedes angefragte Paper erscheint im Ergebnis – notfalls leer."""
    resolved = resolve_all([_record(ORIGIN_MANUAL, title="Titel")], ["p1", "p2"])

    assert set(resolved) == {"p1", "p2"}
    assert resolved["p1"].title == "Titel"
    assert resolved["p2"].title == ""
    assert resolved["p2"].paper_id == "p2"
