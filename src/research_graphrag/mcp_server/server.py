"""MCP-Server-Einstiegspunkt von research-graphrag (Transport ``stdio``).

Registriert die Retrieval-Modi aus Phase 4 (Basic/Local/Global/DRIFT), die Katalog-Tools
``get_paper`` und ``list_topics``, die Zitations-Abfrage ``get_citations``, die Literaturangabe
``get_reference`` sowie die belegte Antwort ``answer_question`` als MCP-Tools und startet den
``stdio``-Transport, über den VS Code den Server als lokalen Unterprozess betreibt (siehe
docs/vscode-integration.md).

Grundsätze (docs/adr/0009-mcp-server-stdio-phase5.md):

- Die Tools liefern **strukturierte Evidenz + Provenienz**; die natürlichsprachige Antwort
  formuliert der aufrufende Agent (Copilot) selbst – **kein** serverseitiges LLM-Sampling.
  Einzige, ausdrücklich **opt-in** Ausnahme: ``answer_question`` mit ``synthesize = true``
  (docs/adr/0012-llm-bridge-and-answer-synthesis-phase7.md).
- Fachliche Fehler (:class:`DomainError`) werden an der Server-Grenze in eine strukturierte
  Ausgabe mit ``isError = true`` übersetzt (docs/error-model.md).
- Logging erfolgt auf **stderr** – stdout ist beim ``stdio``-Transport dem MCP-Protokoll
  vorbehalten.
- Jede Antwort bleibt unter der 1-MB-MCP-Transportgrenze: eine geteilte Obergrenze
  (``research_graphrag.limits.MAX_RESULT_COUNT``) für alle Trefferzahl-Parameter plus ein
  Byte-Sicherheitsnetz in :func:`_guard`, das eine zu große Antwort nie ausliefert und nie
  mitten im Inhalt abschneidet (docs/adr/0037-mcp-tool-response-size-ceiling.md).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio.to_thread
import mcp.types as types
from mcp.server.fastmcp import Context, FastMCP

from research_graphrag.errors import DomainError, ErrorCode
from research_graphrag.generation.answer import AUTO_MODE, answer_question
from research_graphrag.generation.provider import NoopGenerationProvider
from research_graphrag.limits import MAX_RESULT_COUNT
from research_graphrag.mcp_server.sampling import provider_for
from research_graphrag.retrieval.basic import search_basic
from research_graphrag.retrieval.citations import get_citations
from research_graphrag.retrieval.drift import search_drift
from research_graphrag.retrieval.global_search import search_global
from research_graphrag.retrieval.local import search_local
from research_graphrag.retrieval.paper import get_paper
from research_graphrag.retrieval.reference import get_reference
from research_graphrag.retrieval.topics import DEFAULT_LIMIT, DEFAULT_MIN_SIZE, get_topic
from research_graphrag.retrieval.topics import list_topics as list_topics_overview

logging.basicConfig(
    level=os.environ.get("RESEARCH_GRAPHRAG_LOG_LEVEL", "INFO"),
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("research_graphrag.mcp_server")

_DEFAULT_INDEX = Path("data") / "index" / "index.sqlite"

_MAX_RESPONSE_BYTES = 900_000
"""Sicherheitsschwelle für eine serialisierte Tool-Antwort (ADR 0037).

Deutlich unter der MCP-Transportgrenze von 1 MB: Bei korrekt bemessener
``research_graphrag.limits.MAX_RESULT_COUNT`` bleibt jede reguläre Antwort weit darunter (siehe
ADR 0037); dieses Netz fängt ausschließlich Unvorhergesehenes ab. Eine Antwort wird dabei **nie**
in der Mitte abgeschnitten – bei Überschreiten wird sie verworfen und stattdessen ein
strukturierter Fehler gemeldet."""

mcp = FastMCP("research-graphrag")


def _index_path() -> str:
    """Liefert den konfigurierten Index-Pfad (Env ``RESEARCH_GRAPHRAG_INDEX`` oder Default)."""
    return os.environ.get("RESEARCH_GRAPHRAG_INDEX", str(_DEFAULT_INDEX))


def _error_result(error: DomainError) -> types.CallToolResult:
    """Baut eine strukturierte MCP-Fehlerausgabe (``isError = true``).

    Der Fehler-Envelope (``{"error": {code, message[, details]}}``) wird sowohl als
    JSON-Text (``content``) als auch als ``structuredContent`` durchgereicht
    (siehe docs/error-model.md, Abschnitt 3).
    """
    envelope = error.to_envelope()
    return types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))],
        structuredContent=envelope,
    )


def _guard(
    tool_name: str, produce: Callable[[], dict[str, Any]]
) -> dict[str, Any] | types.CallToolResult:
    """Führt die Tool-Logik aus und übersetzt Fehler an der Server-Grenze.

    Fachliche :class:`DomainError` werden in eine strukturierte Fehlerausgabe übersetzt;
    unerwartete Ausnahmen werden als ``internal_error`` gemeldet. Als letzte Sicherung prüft
    ``_guard`` zusätzlich die serialisierte Größe einer erfolgreichen Antwort gegen
    :data:`_MAX_RESPONSE_BYTES` (ADR 0037) – eine Überschreitung wird nie ausgeliefert und nie
    mitten im Inhalt abgeschnitten, sondern als ``constraint_violation`` gemeldet.
    """
    try:
        result = produce()
    except DomainError as exc:
        logger.info("Fachlicher Fehler [%s]: %s", exc.code.value, exc.message)
        return _error_result(exc)
    except Exception:  # noqa: BLE001 - letzte Sicherung, in internal_error übersetzt
        logger.exception("Unerwarteter interner Fehler im Tool %s", tool_name)
        return _error_result(
            DomainError(ErrorCode.INTERNAL_ERROR, f"Interner Fehler im Tool {tool_name}.")
        )

    size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    if size > _MAX_RESPONSE_BYTES:
        logger.warning(
            "Antwort von %s überschreitet die Sicherheitsschwelle: %d Byte (Grenze: %d).",
            tool_name,
            size,
            _MAX_RESPONSE_BYTES,
        )
        return _error_result(
            DomainError(
                ErrorCode.CONSTRAINT_VIOLATION,
                f"Antwort von {tool_name} überschreitet die Sicherheitsschwelle von "
                f"{_MAX_RESPONSE_BYTES:,} Byte ({size:,} Byte) – Parameter wie k/limit "
                "verkleinern.",
            )
        )
    return result


@mcp.tool(
    name="search_basic",
    title="Basic Search (exakte Fakten)",
    description=(
        "Beantwortet exakte/faktische Fragen (DOI, Metrik, F1-Score, Abkürzung) über eine "
        "Top-k-TF-IDF-Suche auf Paper-Chunks und liefert belegte Zitate (Paper · Abschnitt · "
        "Seite · Chunk). Liefert nur Evidenz + Provenienz; die Antwort formuliert der Agent."
    ),
)
def search_basic_tool(query: str, k: int = 5) -> dict[str, Any]:
    """Top-k-Chunk-Zitate zu einer faktischen Anfrage (siehe specs/search_basic.md)."""
    return _guard(  # type: ignore[return-value]
        "search_basic", lambda: search_basic(_index_path(), query, k).to_dict()
    )


@mcp.tool(
    name="search_local",
    title="Local Search (Detailfrage & Multi-Hop)",
    description=(
        "Beantwortet Detailfragen zu einem Paper und Zitations-/Methodennetz-Fragen: Seed-Chunks, "
        "Chunk-Nachbarschaft und Paper-Fan-out über den Ähnlichkeitsgraphen. `fan_out=0` "
        "überspringt den Graph-Fan-out. Liefert nur Evidenz + Provenienz."
    ),
)
def search_local_tool(query: str, k: int = 5, fan_out: int = 5) -> dict[str, Any]:
    """Seeds + Chunk-Nachbarschaft + Paper-Fan-out (siehe specs/search_local.md)."""
    return _guard(  # type: ignore[return-value]
        "search_local",
        lambda: search_local(_index_path(), query, k=k, fan_out=fan_out).to_dict(),
    )


@mcp.tool(
    name="search_global",
    title="Global Search (Cross-Paper-Synthese)",
    description=(
        "Beantwortet corpusweite Themen-/Syntheses-Fragen über ein Ranking der "
        "Louvain-Communities (Keywords + Summary) mit repräsentativer Paper-Provenienz. "
        "Liefert nur Evidenz + Provenienz; die Antwort formuliert der Agent."
    ),
)
def search_global_tool(query: str, k: int = 5) -> dict[str, Any]:
    """Query-relevante Communities mit Vertreter-Papern (siehe specs/search_global.md)."""
    return _guard(  # type: ignore[return-value]
        "search_global", lambda: search_global(_index_path(), query, k).to_dict()
    )


@mcp.tool(
    name="search_drift",
    title="DRIFT Search (Widersprüche & Vergleiche)",
    description=(
        "Beantwortet Widerspruchs-/Vergleichsfragen über einen Global→Local-Hybrid: erst die "
        "thematisch passendsten Communities, dann fokussierte Chunk-Belege in der Vereinigung "
        "ihrer Paper. Ohne passende Community wird sichtbar auf die corpusweite Suche "
        "zurückgefallen (`fallback`). Liefert nur Evidenz + Provenienz; die Antwort formuliert "
        "der Agent."
    ),
)
def search_drift_tool(query: str, k: int = 6) -> dict[str, Any]:
    """Community-Kontext + lokale Chunk-Belege (siehe specs/search_drift.md)."""
    return _guard(  # type: ignore[return-value]
        "search_drift", lambda: search_drift(_index_path(), query, k=k).to_dict()
    )


@mcp.tool(
    name="get_paper",
    title="Paper-Metadaten (per paper_id)",
    description=(
        "Liefert die Metadaten eines Papers per stabiler `paper_id`: Quelle (source_uri), "
        "Identifikatoren (DOI/arXiv), Seiten-/Chunk-Umfang, Abschnittstitel und ein "
        "Leit-Snippet. Read-only aus dem Index; kein Datei-Pfad."
    ),
)
def get_paper_tool(paper_id: str) -> dict[str, Any]:
    """Paper-Detailabruf aus dem Index (siehe specs/get_paper.md)."""
    return _guard(  # type: ignore[return-value]
        "get_paper", lambda: get_paper(_index_path(), paper_id).to_dict()
    )


@mcp.tool(
    name="get_citations",
    title="Zitationen (Intra-Korpus)",
    description=(
        "Liefert die Zitationsbeziehungen eines Papers **innerhalb des Korpus**: `cites` "
        "(zitiert) und `cited_by` (wird zitiert von), jeweils mit Quelle und dem Kriterium "
        "des Treffers (doi/arxiv/title). Beantwortet 'welche Paper bauen auf X auf?'. "
        "Read-only aus dem Index; externe Referenzen werden nicht aufgelöst."
    ),
)
def get_citations_tool(paper_id: str) -> dict[str, Any]:
    """Intra-Korpus-Zitationen mit Provenienz (siehe specs/get_citations.md)."""
    return _guard(  # type: ignore[return-value]
        "get_citations", lambda: get_citations(_index_path(), paper_id).to_dict()
    )


@mcp.tool(
    name="answer_question",
    title="Belegte Antwort (Router + Evidenz, optional formuliert)",
    description=(
        "Beantwortet eine Frage in einem Aufruf: wählt den Suchmodus (`auto` = Heuristik-Router "
        "oder explizit basic/local/global/drift), sammelt die Belege und liefert sie als "
        "einheitliche, durchnummerierte Evidenz mit Zitier-Contract (`[1]`, `[2]` …). Bei `auto` "
        "begründet das Feld `routing` die Modus-Wahl (Konfidenz `strong`/`weak`/`none` plus "
        "auslösende Signale); bei `weak`/`none` lohnt ggf. ein expliziter Modus. Empfohlen "
        "für Agenten mit eigenem Modell: `synthesize=false` (Default) – formuliere die Antwort "
        "selbst und zitiere die Belegnummern. Mit `synthesize=true` formuliert der Server die "
        "Antwort über MCP-Sampling; ohne Sampling-Fähigkeit bleibt `generated=false`."
    ),
)
async def answer_question_tool(
    query: str,
    ctx: Context,  # type: ignore[type-arg]
    mode: str = AUTO_MODE,
    k: int = 5,
    synthesize: bool = False,
) -> dict[str, Any]:
    """Router + Evidenz, optional per Client-Sampling formuliert (specs/answer_question.md)."""
    provider = provider_for(ctx) if synthesize else NoopGenerationProvider()

    def produce() -> dict[str, Any]:
        return answer_question(_index_path(), query, mode=mode, k=k, provider=provider).to_dict()

    def guarded() -> dict[str, Any]:
        return _guard("answer_question", produce)  # type: ignore[return-value]

    # Die Kernlogik ist synchron; im Worker-Thread kann der Sampler per anyio in den
    # Event-Loop zurückrufen (Async-Brücke nur an der Servergrenze, ADR 0004/0012).
    return await anyio.to_thread.run_sync(guarded)


@mcp.tool(
    name="list_topics",
    title="Themencluster (Communities)",
    description=(
        "Listet die Themencluster des Korpus (Louvain-Communities) mit Größe, Keywords und "
        "Vertretern. Standardmäßig ohne Ein-Paper-Cluster (`min_size`, Default 2) und auf die "
        f"`limit` größten Communities begrenzt (Default/Maximum {MAX_RESULT_COUNT}). Für die "
        "volle Mitgliederliste einer einzelnen Community `community_id` angeben – dann werden "
        "`min_size`/`limit` ignoriert. Nützlich, um den Korpus zu überblicken oder eine "
        "Community für Global/DRIFT auszuwählen."
    ),
)
def list_topics_tool(
    min_size: int = DEFAULT_MIN_SIZE,
    limit: int = DEFAULT_LIMIT,
    community_id: int | None = None,
) -> dict[str, Any]:
    """Community-Übersicht oder Einzelabruf per `community_id` (siehe specs/list_topics.md)."""

    def produce() -> dict[str, Any]:
        if community_id is not None:
            return get_topic(_index_path(), community_id).to_dict()
        return list_topics_overview(_index_path(), min_size=min_size, limit=limit).to_dict()

    return _guard("list_topics", produce)  # type: ignore[return-value]


@mcp.tool(
    name="get_reference",
    title="Literaturangabe (Harvard & APA)",
    description=(
        "Liefert die fertige Literaturangabe eines Papers per stabiler `paper_id`: Autoren, "
        "Titel, Jahr, Venue, DOI/arXiv sowie die formatierten Angaben in **Harvard** und "
        "**APA** samt Kurzbeleg für den Fließtext. Nutze dies, wenn aus einem Suchtreffer "
        "zitiert werden soll. Ist der Datensatz unvollständig, weist `missing`/`note` das aus – "
        "fehlende Angaben werden nie geraten. Read-only aus dem Index."
    ),
)
def get_reference_tool(paper_id: str) -> dict[str, Any]:
    """Literaturangabe in beiden Stilen (siehe specs/get_reference.md)."""
    return _guard(  # type: ignore[return-value]
        "get_reference", lambda: get_reference(_index_path(), paper_id).to_dict()
    )


def main() -> None:
    """Startet den MCP-Server über den ``stdio``-Transport."""
    logger.info("Starte MCP-Server 'research-graphrag' (stdio) …")
    mcp.run()


if __name__ == "__main__":
    main()
