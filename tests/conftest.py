"""Gemeinsame Test-Fixtures.

Asynchrone Tests laufen über das ``anyio``-Pytest-Plugin (siehe
docs/adr/0003-offline-test-and-coverage-tooling.md); als Backend wird ``asyncio``
fixiert.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Fixiert das anyio-Backend auf ``asyncio`` für alle async-Tests."""
    return "asyncio"
