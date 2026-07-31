"""Gemeinsame Test-Fixtures.

Asynchrone Tests laufen über das ``anyio``-Pytest-Plugin (siehe
docs/adr/0003-offline-test-and-coverage-tooling.md); als Backend wird ``asyncio``
fixiert. ``make_pdf`` erzeugt kleine PDF-Fixtures (reportlab) für Extraktions-Tests.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Fixiert das anyio-Backend auf ``asyncio`` für alle async-Tests."""
    return "asyncio"


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    """Factory: erzeugt ein PDF mit je einem Textblock pro Seite.

    Args:
        pages: Seitentexte (ein Eintrag pro Seite; Zeilenumbrüche je Seite erlaubt).
        name: Dateiname innerhalb des tmp-Verzeichnisses.

    Returns:
        Pfad zum erzeugten PDF.
    """

    def _make(pages: Sequence[str], name: str = "sample.pdf") -> Path:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(path), pagesize=A4)
        for page_text in pages:
            lines = page_text.splitlines() or [""]
            for index, line in enumerate(lines):
                pdf.drawString(72, 780 - index * 14, line)
            pdf.showPage()
        pdf.save()
        return path

    return _make
