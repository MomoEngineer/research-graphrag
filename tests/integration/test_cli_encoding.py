"""Regression: Die CLI-Skripte überleben eine cp1252-Konsole (Windows-Pipe).

Korpus-Texte enthalten Zeichen außerhalb von cp1252 (Ligaturen, ``∗``, OCR-Artefakte). Ohne
``sys.stdout.reconfigure(encoding="utf-8")`` bricht ein Skript beim **Pipen** der Ausgabe mit
``UnicodeEncodeError`` ab – genau das ist bei ``scripts.graph_info`` aufgetreten. Der Test
erzwingt die enge Konsolen-Codepage über ``PYTHONIOENCODING`` und prüft, dass die Skripte
sauber durchlaufen.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from research_graphrag.extraction.pdf import CanonicalPaper, Chunk
from research_graphrag.indexing.graph_index import build_graph
from research_graphrag.indexing.tfidf_index import build_index

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Enthält Zeichen, die cp1252 NICHT abbilden kann (∗ = U+2217, ﬁ = U+FB01).
_TEXTS = {
    "aaaa0001": [
        "graph retrieval ∗ evaluation ﬁnetuning transformer attention",
        "attention transformer ∗ encoder ﬁgure benchmark",
    ],
    "aaaa0002": [
        "transformer attention ∗ architecture ﬁnetuning heads",
        "encoder attention ∗ pretraining ﬁgure language",
    ],
}


def _paper(paper_id: str, texts: Sequence[str]) -> CanonicalPaper:
    chunks = tuple(
        Chunk(
            chunk_id=f"{paper_id}-c{index + 1:04d}",
            paper_id=paper_id,
            page_number=index + 1,
            text=text,
            char_count=len(text),
            section_title="Introduction",
        )
        for index, text in enumerate(texts)
    )
    return CanonicalPaper(
        paper_id=paper_id,
        source_uri=f"file:///{paper_id}.pdf",
        source_sha256="0" * 64,
        n_pages=len(texts),
        chunks=chunks,
        quality_flags=(),
    )


@pytest.fixture
def index_db(tmp_path: Path) -> Path:
    """Kleiner Index mit Nicht-cp1252-Zeichen in Texten, Keywords und Zusammenfassungen."""
    db = tmp_path / "index" / "index.sqlite"
    papers = [_paper(pid, texts) for pid, texts in _TEXTS.items()]
    build_index(papers, db)
    build_graph(papers, db)
    return db


@pytest.mark.parametrize(
    "module, arguments",
    [
        ("scripts.graph_info", []),
        ("scripts.ask", ["graph retrieval evaluation", "--mode", "basic", "-k", "2"]),
        ("scripts.ask", ["graph retrieval evaluation", "-k", "2", "--synthese"]),
        ("scripts.citations", ["aaaa0001"]),
    ],
)
def test_cli_survives_cp1252_stdout(index_db: Path, module: str, arguments: list[str]) -> None:
    """Auch bei cp1252-Ausgabe laufen die Skripte fehlerfrei durch."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    if module == "scripts.citations":
        from research_graphrag.indexing.citation_graph import build_citation_graph

        build_citation_graph([_paper(pid, texts) for pid, texts in _TEXTS.items()], index_db)

    completed = subprocess.run(
        [sys.executable, "-m", module, *arguments, "--index", str(index_db)],
        cwd=_REPO_ROOT,
        capture_output=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert b"UnicodeEncodeError" not in completed.stderr


def test_status_survives_cp1252_stdout(index_db: Path, tmp_path: Path) -> None:
    """Auch der Status-Report läuft mit enger Konsolen-Codepage durch."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.status",
            "--data",
            str(tmp_path),
            "--papers",
            str(tmp_path / "papers"),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
