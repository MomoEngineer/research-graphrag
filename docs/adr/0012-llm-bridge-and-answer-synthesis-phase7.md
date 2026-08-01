# 0012 – LLM-Bridge & optionale Antwort-Synthese (Phase 7 / A1)

- **Status:** Akzeptiert
- **Datum:** 2026-08-01

## Kontext

[ADR 0004](0004-llm-bridge-via-mcp-sampling.md) beschreibt die LLM-Bridge (injizierbarer Generierungs-Port, `SamplingGenerationProvider`/`NoopGenerationProvider`, Async-Brücke nur an der Servergrenze) – **im Code existierte davon nichts**. Antworten bestehen heute ausschließlich aus Evidenz + Provenienz; die Formulierung übernimmt der aufrufende Agent. Die [Roadmap](../../Roadmap.md) führt das als Phase-7-Punkt **A1**.

Zwei Rahmenbedingungen prägen die Entscheidung:

1. **Der Standard-Client ist selbst ein Modell.** GitHub Copilot formuliert die Antwort ohnehin aus den Tool-Ergebnissen. Ließe der Server *zusätzlich* per Sampling formulieren, entstünde eine **doppelte Generierung** (Latenz, Tokens, Nichtdeterminismus) ohne Qualitätsgewinn – genau deshalb hat [ADR 0009](0009-mcp-server-stdio-phase5.md) serverseitiges Sampling ausgeschlossen.
2. **Die CLI hat offline kein Modell.** Ein reiner CLI-Synthesepfad bliebe dauerhaft im Noop-Fallback; er belegt die Architektur, stiftet aber allein keinen Nutzen.

Gleichzeitig ist die heutige Tool-Landschaft für einen Agenten unnötig sperrig: Vier Suchmodi mit **vier verschiedenen Ergebnisschemata** erzwingen eine Modus-Wahl und eine Schema-Fallunterscheidung, bevor überhaupt zitiert werden kann.

## Entscheidung

1. **Neues Paket `generation/`** realisiert [ADR 0004](0004-llm-bridge-via-mcp-sampling.md) im Code: `GenerationProvider` (Protocol, synchron) mit `NoopGenerationProvider` (Fallback → `generated = false`) und `SamplingGenerationProvider` (adaptiert einen injizierten, synchronen Sampler).
2. **Mode-agnostische Evidenz.** `Evidence`/`EvidenceItem` bilden die vier Modus-Ergebnisse auf **eine** deterministisch nummerierte Beleg-Liste ab (`[1] … [n]`, je mit Paper, Abschnitt/Seite, Quelle). Die Adapter liegen in `generation/evidence.py`; `generation/synthesis.py` importiert **keine** Retrieval-Typen (Schichtentrennung, offline testbar).
3. **Strikter Antwort-Contract.** Der System-Prompt bindet die Antwort ausschließlich an die gelieferten Belege, verlangt `[n]`-Zitatmarker, untersagt Wissen außerhalb der Evidenz und schreibt „nicht belegt" statt einer Vermutung vor; Antwortsprache ist Deutsch. Sampling läuft mit `temperature = 0` (Reproduzierbarkeit best effort, [ADR 0004](0004-llm-bridge-via-mcp-sampling.md)).
4. **Genau ein neues MCP-Tool `answer_question`** – mit `synthesize = false` als **Default**. Im Standardfall liefert es damit ein deterministisches **Evidenz-Bündel in einem Aufruf** (Router-Wahl, einheitliches Schema, nummerierte Belege, Zitier-Contract) und erzwingt **keine** zweite Generierung. Die sechs bestehenden Tools bleiben unverändert.
5. **Sampling ist opt-in und lebt an der Servergrenze.** Bei `synthesize = true` fordert der Server die Completion über die Client-Session an (`session.create_message`). Die Kernlogik bleibt **synchron**; die Async-Brücke wird über `anyio` gebaut und beschränkt sich auf die Servergrenze: Der Tool-Wrapper in `mcp_server/server.py` schiebt die synchrone Logik per `to_thread` in einen Worker-Thread, der Sampler in `mcp_server/sampling.py` ruft per `from_thread` in den Event-Loop zurück. **Modellzugriff** gibt es ausschließlich in `mcp_server/sampling.py`.
6. **Sichtbare Degradation statt Scheitern.** Kann der Client kein Sampling (Capability-Prüfung), liefert er eine leere Completion oder ist die Evidenz leer, bleibt `generated = false` und die **vollständige Evidenz** erhalten. Ein Sampling-Fehler bricht das Tool nicht ab.
7. **CLI `python -m scripts.ask --synthese`** nutzt den `NoopGenerationProvider` (offline kein Modell) und macht den Fallback beobachtbar: volle Belege, `generated = false`.

## Geltungsbereich / Abgrenzung

[ADR 0009](0009-mcp-server-stdio-phase5.md), Punkt 1 („kein serverseitiges LLM-Sampling") gilt **unverändert für alle Evidenz-Tools** (`search_*`, `get_paper`, `get_citations`, `list_topics`) – sie bleiben deterministisch und modellfrei. `answer_question` ist die **einzige, ausdrücklich opt-in** Ausnahme; ohne `synthesize = true` verhält sich auch dieses Tool modellfrei. Der Index-Bau bleibt LLM-frei ([ADR 0005](0005-graphrag-index-backend-open.md)).

## Alternativen

- **Nur Port + CLI, kein Tool:** minimal-invasiv, erfüllt die Roadmap-Akzeptanz wörtlich – bliebe aber praktisch wirkungslos (offline nie ein Modell im CLI) und damit totes Gerüst → verworfen.
- **Sampling als Default (oder in allen Tools):** erzwingt die doppelte Generierung bei Copilot, macht Tool-Ergebnisse nichtdeterministisch und bricht den Contract der Evidenz-Tools → verworfen.
- **Gebundenes lokales Modell (Ollama o. ä.) für die Synthese:** offline nicht beschaffbar; würde Modell-Agnostik und Secret-Freiheit aufweichen ([ADR 0004](0004-llm-bridge-via-mcp-sampling.md)) → verworfen.
- **Vollständig asynchrone Kernlogik:** würde Sampling sauber tragen, aber Retrieval, CLI und Tests ohne Not asynchron machen; ADR 0004 verlangt ausdrücklich eine schmale Brücke an der Grenze → verworfen.

## Konsequenzen

- **Positiv:** Die LLM-Bridge existiert real und ist testbar; ein Agent bekommt Modus-Routing, einheitliches Evidenz-Schema und Zitier-Contract in **einem** Aufruf; Clients **ohne** eigenes Modell können sich eine belegte Antwort formulieren lassen; die Evidenz bleibt in jedem Fall deterministisch und vollständig.
- **Negativ / Aufwand:** Der Synthese-Pfad ist **nicht deterministisch** und hängt an der Sampling-Fähigkeit des Clients (in VS Code mit Nutzer-Zustimmung/Modellwahl); die Async-Brücke ist zusätzliche, wenn auch eng begrenzte Komplexität; die Qualität der Antwort hängt vom Client-Modell ab.
- **Folgeentscheidungen:** keine offenen; weitere Phase-7-Punkte (A3–A8) bleiben unabhängig ziehbar ([Roadmap](../../Roadmap.md)).
