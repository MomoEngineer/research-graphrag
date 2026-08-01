"""Kuratierte Keyword-Politik (Phase 7 / A5, Option B).

Bündelt die Domänen-Stopwords und den Token-Filter für alle **extraktiven Keyword-Listen**:
Community-Keywords (:mod:`research_graphrag.indexing.graph_index`) und Entwurfszeilen der
Literaturübersicht (:mod:`research_graphrag.overview.drafts`). Grundsatz:
docs/adr/0015-noise-reduction-keywords-and-sections-phase7.md.

Hintergrund: Terme wie ``et``, ``al`` oder ``arxiv`` stehen in nahezu jedem Paper (Dokumentfrequenz
142–143 von 145) und tragen deshalb kaum zur paarweisen Ähnlichkeit bei. Die Keyword-Auswahl
summiert jedoch über alle Paper einer Community – dort schlägt ihre hohe Termfrequenz durch und
verdrängt echte Themenbegriffe. Der Filter setzt daher genau an der **Auswahl** an; der
Vektorraum des Ähnlichkeitsgraphen bleibt unangetastet.

**Nicht** für das Retrieval: Der ``CountVectorizer`` in
:mod:`research_graphrag.indexing.tfidf_index` arbeitet bewusst ohne Stopwords, damit Fakt-Anfragen
nach Jahreszahlen, DOIs oder Abkürzungen weiterhin treffen
(docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

DOMAIN_STOPWORDS = frozenset(
    {
        # Zitations- und Bibliografie-Vokabular
        "et",
        "al",
        "arxiv",
        "preprint",
        "doi",
        "isbn",
        "issn",
        "eds",
        "pp",
        "vol",
        "url",
        # Web-/Linkfragmente
        "http",
        "https",
        "www",
        "org",
        "com",
        "html",
        "pdf",
        # inhaltsleere Wissenschaftsfüller (nicht in der englischen Liste von scikit-learn)
        "based",
    }
)
"""Kuratierte Domänen-Stopwords; bewusst minimal und nur durch Stichproben erweitert."""

_GLYPH_ARTIFACT = re.compile(r"^uni[0-9a-f]{8}$", re.IGNORECASE)
"""Rest eines nicht dekodierbaren Glyph-Verweises (defensiv für ältere Canonical-Daten)."""


def is_noise_term(term: str) -> bool:
    """Prüft, ob ein Term für eine extraktive Keyword-Liste inhaltsleer ist.

    Args:
        term: Einzelner Term aus einer TF-IDF-Rangfolge.

    Returns:
        ``True`` für Domänen-Stopwords, rein numerische Token (inklusive Jahreszahlen) und
        Glyph-Artefakte; ``False`` für Signal-Terme wie ``7b`` oder ``gpt``.
    """
    normalized = term.strip().lower()
    if not normalized:
        return True
    if normalized in DOMAIN_STOPWORDS:
        return True
    if normalized.isdigit():
        return True
    return bool(_GLYPH_ARTIFACT.match(normalized))


def filter_terms(terms: Iterable[str], limit: int | None = None) -> list[str]:
    """Entfernt Rausch-Terme aus einer nach Relevanz sortierten Termfolge.

    Der Filter greift **vor** dem Anschnitt: verdrängte Rausch-Slots werden durch nachrückende
    Terme aufgefüllt, statt die Liste zu verkürzen.

    Args:
        terms: Terme in absteigender Relevanz.
        limit: Maximale Anzahl der Ergebnisse; ``None`` liefert alle Signal-Terme.

    Returns:
        Die gefilterten Terme in unveränderter Reihenfolge.
    """
    selected: list[str] = []
    for term in terms:
        if is_noise_term(term):
            continue
        selected.append(term)
        if limit is not None and len(selected) >= limit:
            break
    return selected
