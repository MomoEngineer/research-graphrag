"""Literaturangaben in Harvard und APA (Phase 12 / K1).

Erzeugt aus einem aufgelösten :class:`~research_graphrag.bibliography.model.PaperMetadata`
**deterministisch** die Referenz- und die In-Text-Form – ohne LLM und ohne Netz, konform zu
docs/adr/0005-graphrag-index-backend-open.md.

Umgesetzt sind zwei feste Ausprägungen (docs/adr/0025-citable-paper-metadata.md, Punkt 6):

* :data:`STYLE_APA` folgt **APA 7**: ``Nachname, A. A., & Nachname, B. B. (2023). Titel. Venue.
  https://doi.org/…``
* :data:`STYLE_HARVARD` folgt **Cite Them Right**: ``Nachname, A.A. and Nachname, B.B. (2023)
  'Titel', Venue. Available at: https://doi.org/…``

Ein **Zugriffsdatum** wird bewusst nicht ergänzt: Es wäre vom Ausführungstag abhängig und würde
den Determinismus brechen, auf dem alle Vergleichsläufe des Repositories beruhen. Fehlende
Angaben werden nach den Regeln des jeweiligen Stils gekennzeichnet (``n.d.`` bzw. ``no date``)
und **nie** geraten.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from research_graphrag.bibliography.model import PaperMetadata, surname_of
from research_graphrag.errors import DomainError, ErrorCode

STYLE_HARVARD = "harvard"
"""Harvard-Stil in der Ausprägung *Cite Them Right*."""

STYLE_APA = "apa"
"""APA-Stil in der 7. Auflage."""

STYLES: tuple[str, ...] = (STYLE_HARVARD, STYLE_APA)
"""Unterstützte Zitationsstile (Reihenfolge = Ausgabereihenfolge)."""

APA_MAX_AUTHORS = 20
"""Ab dem 21. Autor kürzt APA 7 mit einer Auslassung."""

HARVARD_MAX_AUTHORS = 3
"""Ab dem 4. Autor kürzt Cite Them Right mit ``et al.``."""

_NO_DATE = {STYLE_APA: "n.d.", STYLE_HARVARD: "no date"}
_UNTITLED = "Ohne Titel"


def _given_names(author: str) -> str:
    """Liefert die Vornamen einer Autorenangabe (beide Schreibweisen werden unterstützt)."""
    cleaned = " ".join(author.split())
    if not cleaned:
        return ""
    if "," in cleaned:
        return cleaned.split(",", 1)[1].strip()
    head, _, _tail = cleaned.rpartition(" ")
    return head.strip()


def _initials(given: str, *, separator: str) -> str:
    """Bildet die Initialen der Vornamen (``"Anna Maria"`` → ``"A. M."`` bzw. ``"A.M."``)."""
    initials = [part[0].upper() + "." for part in given.replace(".", " ").split() if part]
    return separator.join(initials)


def _author_apa(author: str) -> str:
    """Formatiert einen Autor nach APA (``Nachname, A. A.``)."""
    surname = surname_of(author)
    initials = _initials(_given_names(author), separator=" ")
    return f"{surname}, {initials}" if initials else surname


def _author_harvard(author: str) -> str:
    """Formatiert einen Autor nach Cite Them Right (``Nachname, A.A.``)."""
    surname = surname_of(author)
    initials = _initials(_given_names(author), separator="")
    return f"{surname}, {initials}" if initials else surname


def _authors_apa(authors: Sequence[str]) -> str:
    """Baut die APA-Autorenliste (``&`` vor dem letzten Namen, Auslassung ab 21 Autoren)."""
    formatted = [_author_apa(author) for author in authors if author.strip()]
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) > APA_MAX_AUTHORS:
        return ", ".join(formatted[: APA_MAX_AUTHORS - 1]) + ", ..., " + formatted[-1]
    return ", ".join(formatted[:-1]) + ", & " + formatted[-1]


def _authors_harvard(authors: Sequence[str]) -> str:
    """Baut die Harvard-Autorenliste (``and`` vor dem letzten Namen, ``et al.`` ab 4 Autoren)."""
    formatted = [_author_harvard(author) for author in authors if author.strip()]
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) > HARVARD_MAX_AUTHORS:
        return f"{formatted[0]} et al."
    return ", ".join(formatted[:-1]) + " and " + formatted[-1]


def _period(text: str) -> str:
    """Schließt ein Segment mit genau einem Satzzeichen ab (verhindert ``A. A..``)."""
    stripped = text.strip()
    if not stripped or stripped[-1] in ".!?":
        return stripped
    return f"{stripped}."


def _check_style(style: str) -> str:
    """Prüft den Stilnamen (Kleinschreibung) und meldet unbekannte Werte fachlich."""
    normalized = style.strip().lower()
    if normalized not in STYLES:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            f"Unbekannter Zitationsstil: {style!r}. Erlaubt: {', '.join(STYLES)}.",
        )
    return normalized


def _year_text(metadata: PaperMetadata, style: str) -> str:
    """Liefert die Jahresangabe bzw. die stiltypische Kennzeichnung eines fehlenden Jahres."""
    return str(metadata.year) if metadata.year else _NO_DATE[style]


def _reference_apa(metadata: PaperMetadata) -> str:
    """Baut die APA-7-Referenz."""
    title = metadata.title.strip() or _UNTITLED
    authors = _authors_apa(metadata.authors)
    segments = [_period(authors)] if authors else [_period(title)]
    segments.append(f"({_year_text(metadata, STYLE_APA)}).")
    if authors:
        segments.append(_period(title))
    if metadata.venue.strip():
        segments.append(_period(metadata.venue))
    if metadata.preferred_url:
        segments.append(metadata.preferred_url)
    return " ".join(segment for segment in segments if segment)


def _reference_harvard(metadata: PaperMetadata) -> str:
    """Baut die Harvard-Referenz (Cite Them Right)."""
    title = metadata.title.strip() or _UNTITLED
    authors = _authors_harvard(metadata.authors)
    # Kein Abschneiden eines Schlusspunktes: Er gehört hier zu den Initialen (``A.M.``).
    segments = [authors or title]
    segments.append(f"({_year_text(metadata, STYLE_HARVARD)})")
    if authors:
        segments.append(f"'{title}',")
    if metadata.venue.strip():
        segments.append(_period(metadata.venue))
    if metadata.preferred_url:
        segments.append(f"Available at: {metadata.preferred_url}")
    return " ".join(segment for segment in segments if segment)


def format_reference(metadata: PaperMetadata, style: str) -> str:
    """Erzeugt die vollständige Literaturangabe im gewünschten Stil.

    Args:
        metadata: Aufgelöster Metadaten-Datensatz.
        style: :data:`STYLE_HARVARD` oder :data:`STYLE_APA` (Groß-/Kleinschreibung egal).

    Returns:
        Die Literaturangabe als einzeiliger Text.

    Raises:
        DomainError: ``invalid_input`` bei unbekanntem Stil (siehe docs/error-model.md).
    """
    normalized = _check_style(style)
    if normalized == STYLE_APA:
        return _reference_apa(metadata)
    return _reference_harvard(metadata)


def format_in_text(metadata: PaperMetadata, style: str) -> str:
    """Erzeugt das Kurzbeleg-/In-Text-Zitat (``(Müller et al., 2023)``).

    Args:
        metadata: Aufgelöster Metadaten-Datensatz.
        style: :data:`STYLE_HARVARD` oder :data:`STYLE_APA`.

    Returns:
        Den Kurzbeleg in Klammern.

    Raises:
        DomainError: ``invalid_input`` bei unbekanntem Stil (siehe docs/error-model.md).
    """
    normalized = _check_style(style)
    year = _year_text(metadata, normalized)
    surnames = [surname_of(author) for author in metadata.authors if author.strip()]
    if not surnames:
        head = metadata.title.strip() or _UNTITLED
    elif len(surnames) == 1:
        head = surnames[0]
    elif len(surnames) == 2:
        joiner = "&" if normalized == STYLE_APA else "and"
        head = f"{surnames[0]} {joiner} {surnames[1]}"
    else:
        head = f"{surnames[0]} et al."
    return f"({head}, {year})"


def reference_payload(metadata: PaperMetadata) -> dict[str, Any]:
    """Serialisiert den Datensatz **inklusive** beider Stile (Ausgabeform der Werkzeuge).

    Ergänzt :meth:`~research_graphrag.bibliography.model.PaperMetadata.to_dict` um die
    Schlüssel ``harvard``, ``apa`` und ``in_text``. Damit bleibt das Datenmodell frei von
    Formatierungswissen und die Werkzeuge liefern trotzdem eine fertige Angabe.
    """
    payload = metadata.to_dict()
    payload["harvard"] = format_reference(metadata, STYLE_HARVARD)
    payload["apa"] = format_reference(metadata, STYLE_APA)
    payload["in_text"] = {style: format_in_text(metadata, style) for style in STYLES}
    return payload
