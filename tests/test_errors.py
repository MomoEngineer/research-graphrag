"""Tests für die gemeinsame Fehlertaxonomie (docs/error-model.md)."""

from __future__ import annotations

import pytest

from research_graphrag.errors import DomainError, ErrorCode


def test_error_codes_match_taxonomy() -> None:
    """Die Kategorien entsprechen exakt der Taxonomie aus docs/error-model.md."""
    assert {code.value for code in ErrorCode} == {
        "invalid_input",
        "not_found",
        "permission_denied",
        "parse_error",
        "dependency_error",
        "constraint_violation",
        "internal_error",
    }


def test_envelope_without_details() -> None:
    """Ohne details enthält der Envelope nur code und message."""
    err = DomainError(ErrorCode.INVALID_INPUT, "leere Eingabe")
    assert err.to_envelope() == {"error": {"code": "invalid_input", "message": "leere Eingabe"}}


def test_envelope_with_details() -> None:
    """Mit details wird der Provenienz-Anker mitgeliefert."""
    err = DomainError(ErrorCode.PARSE_ERROR, "kaputt", {"uri": "file:///x.pdf", "page": 2})
    envelope = err.to_envelope()
    assert envelope["error"]["code"] == "parse_error"
    assert envelope["error"]["details"] == {"uri": "file:///x.pdf", "page": 2}


def test_domain_error_is_raisable_and_carries_code() -> None:
    """DomainError ist eine Exception und trägt die Kategorie mit."""
    with pytest.raises(DomainError) as excinfo:
        raise DomainError(ErrorCode.NOT_FOUND, "fehlt")
    assert excinfo.value.code is ErrorCode.NOT_FOUND
