"""Gemeinsame Fehlertaxonomie (siehe docs/error-model.md).

Cross-cutting genutzt von Extraktion, Indexierung, Retrieval und – ab Phase 5 – vom
MCP-Server. Fachliche Fehler werden als :class:`DomainError` geworfen und an der
MCP-Grenze in eine strukturierte Fehlerausgabe (``isError = true``) übersetzt.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Fehlerkategorien gemäß docs/error-model.md, Abschnitt 2."""

    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    PARSE_ERROR = "parse_error"
    DEPENDENCY_ERROR = "dependency_error"
    CONSTRAINT_VIOLATION = "constraint_violation"
    INTERNAL_ERROR = "internal_error"


class DomainError(Exception):
    """Fachlicher Fehler mit definierter Kategorie.

    Attributes:
        code: Eine der Kategorien aus :class:`ErrorCode`.
        message: Präzise, handlungsleitende Meldung (keine Secrets/sensiblen Daten).
        details: Optionale, strukturierte Zusatzinformation (z. B. Provenienz-Anker).
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = details or {}

    def to_envelope(self) -> dict[str, Any]:
        """Erzeugt die strukturierte Fehlerausgabe (docs/error-model.md, Abschnitt 3).

        Returns:
            ``{"error": {"code", "message"[, "details"]}}`` – ``details`` nur, wenn gesetzt.
        """
        error: dict[str, Any] = {"code": self.code.value, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"error": error}
