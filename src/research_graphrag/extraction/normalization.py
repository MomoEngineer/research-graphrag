"""Normalisierung des extrahierten Seitentexts (Phase 7 / A5, Option B).

Repariert Artefakte, die ``pypdf`` aus der PDF-Typografie übernimmt, **bevor**
Struktur-Analyse, Chunking und Qualitäts-Gates darauf arbeiten. Grundsatz:
docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md.

- **Typografische Ligaturen** (``U+FB00``–``U+FB06``) werden in ihre Buchstabenfolge
  zurückgeführt. Sie tragen Inhalt: ``conﬁguration`` ist ohne Reparatur weder über TF-IDF noch
  über BM25 mit der Anfrage ``configuration`` auffindbar.
- **Glyph-Artefakte** ``/uniXXXXXXXX`` werden entfernt. Sie entstehen, wenn eine subsettierte
  Font keine Unicode-Zuordnung mitbringt; die Zeichen sind ohne die Font-CMap nicht
  rekonstruierbar und damit reines Rauschen.
- **Einzelne Surrogate** (``U+D800``–``U+DFFF``) werden entfernt. Dieselbe Ursache in anderer
  Gestalt: Eine defekte CMap liefert nur die obere Hälfte eines Zeichens außerhalb der BMP
  (real beobachtet: ``U+D835`` als Rest der mathematischen Alphanumerics). Ein solcher Rest ist
  nicht rekonstruierbar und **nicht nach UTF-8 kodierbar** – ohne Entfernung scheitert bereits
  das Schreiben des Canonical JSON.

Bewusst **kein** pauschales ``unicodedata.normalize("NFKC")``: NFKC bildet auch die
mathematischen Alphanumerics ``U+1D400``–``U+1D7FF`` auf ASCII ab (``𝑥`` → ``x``) und würde damit
die Pseudocode-Reject-Regel aus docs/adr/0013-chunking-refinement-phase7.md aushebeln.
"""

from __future__ import annotations

import re

LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}
"""Typografische Ligaturen des Unicode-Blocks *Alphabetic Presentation Forms*
(``U+FB00``–``U+FB06``)."""

_LIGATURE_TABLE = str.maketrans(LIGATURES)

_GLYPH_ARTIFACT = re.compile(r"/?uni[0-9A-Fa-f]{8}")
"""Nicht dekodierbarer Glyph-Verweis einer subsettierten Font (z. B. ``/uni00000013``)."""

_SURROGATE = re.compile("[\ud800-\udfff]")
"""Halbes Zeichen außerhalb der BMP aus einer defekten CMap – nicht UTF-8-kodierbar."""

_ARTIFACT = re.compile(f"{_GLYPH_ARTIFACT.pattern}|{_SURROGATE.pattern}")
"""Beide Artefaktformen in einem Durchlauf (gleiche Ursache, gleiche Konsequenz)."""

_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def normalize_text(text: str) -> str:
    """Repariert Ligaturen und entfernt Glyph-Artefakte sowie einzelne Surrogate.

    Die Zeilenstruktur bleibt erhalten (die Absatzlogik von
    :func:`research_graphrag.extraction.structure.analyze` arbeitet zeilenweise). Nur in Zeilen,
    aus denen Artefakte entfernt wurden, wird der zurückbleibende Leerraum verdichtet – sonst
    würden die Lücken die Tabellen-Heuristik (``looks_tabular``) auslösen.

    Args:
        text: Roher Seitentext aus der PDF-Extraktion.

    Returns:
        Den normalisierten Text; die Funktion ist idempotent und UTF-8-kodierbar.
    """
    repaired = text.translate(_LIGATURE_TABLE)
    if not _ARTIFACT.search(repaired):
        return repaired

    lines: list[str] = []
    for line in repaired.split("\n"):
        cleaned = _ARTIFACT.sub("", line)
        if cleaned != line:
            cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
        lines.append(cleaned)
    return "\n".join(lines)
