# Tool-Spezifikation: `<tool_name>`

> Vorlage für die Pro-Tool-Spezifikation. Kopiere diese Datei nach
> `src/research_graphrag/mcp_server/specs/<tool_name>.md` und fülle sie **vor** der
> Implementierung aus. Sie ist die Single Source of Truth für Tests und Contract-Checks.

---

## Metadaten

| Feld | Wert |
| --- | --- |
| **Tool-Name** | `<tool_name>` (z. B. `search_local`) |
| **Version** | `MAJOR.MINOR.PATCH` (siehe documentation-standards.md, Abschnitt 4.1) |
| **Capability-Schicht** | z. B. Retrieval (siehe README.md) |
| **Status** | Entwurf / Implementiert / Stabil / Veraltet |

---

## 1. Zweck

Ein bis zwei Sätze: Was leistet das Tool und warum existiert es? (Dient zugleich als MCP-Tool-Beschreibung.)

## 2. Input-Schema

| Parameter | Typ | Pflicht | Beschreibung / Wertebereich |
| --- | --- | --- | --- |
| `beispiel_param` | `str` | ja | ... |

## 3. Output-Schema

Struktur und Bedeutung der Rückgabe (Felder, Typen, Pflichtfelder). Beispiel als JSON-Skizze:

```json
{
  "feld": "Typ und Bedeutung"
}
```

> Input- und Output-Schema werden zusätzlich als **maschinenlesbares JSON-Schema** hinterlegt (Single Source of Truth für Contract-Tests, siehe documentation-standards.md, Abschnitt 2).

## 4. Annahmen und Vorbedingungen

- Erwartete Eingabeformate, Vorbedingungen, benötigte Ressourcen (z. B. „Index vorhanden").

## 5. Grenzen (Nicht-Ziele)

- Was tut das Tool bewusst **nicht**? Abgrenzung zu benachbarten Tools (Überschneidungsfreiheit).

## 6. Fehlerverhalten

- Definierte Fehlerfälle und wie darauf reagiert wird.
- Jeder Fehlerfall wird einer **Fehlerkategorie** aus `docs/error-model.md` zugeordnet (z. B. `invalid_input`, `parse_error`, `permission_denied`).

## 7. Provenienz

- Welche Herkunftsangaben liefert das Tool mit (Paper-ID, Abschnitt, Seite/Chunk, Score)?

## 8. Reproduzierbarkeit

- Seeds, Versionsabhängigkeiten, deterministische vs. stochastische Anteile.

## 9. Testabdeckung

- Verweis auf `tests/mcp_server/test_<tool_name>.py`.
- Geplante Contract-, Funktions- und Fehler-/Edge-Case-Tests (Kurzliste).
