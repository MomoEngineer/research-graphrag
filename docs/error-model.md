# Fehler-/Error-Modell

Dieses Dokument definiert, **wie MCP-Tools Fehler melden**. Ziel ist ein einheitliches, vorhersehbares Fehlerverhalten – als Grundlage für die Fehler-/Edge-Case-Tests ([testing.md](testing.md)) und konsistentes Logging ([documentation-standards.md](documentation-standards.md), Abschnitt 9).

> **Leitprinzip:** Fehler sind Teil des Vertrags eines Tools. Jeder zugesagte Fehlerfall wird definiert, getestet und einer Fehlerkategorie zugeordnet.
>
> Die Fehlertaxonomie ist unter `src/research_graphrag/errors.py` umgesetzt (cross-cutting; genutzt von Extraktion, Index, Retrieval und ab Phase 5 vom MCP-Server).

---

## 1. Zwei Fehlerebenen

| Ebene | Wann | Wie gemeldet |
| --- | --- | --- |
| **Protokoll-/Discovery-Fehler** | Tool existiert nicht, Parameter verletzen das Input-JSON-Schema | Über den MCP-Protokollfehlerkanal (JSON-RPC-Error), i. d. R. vom SDK |
| **Fachliche Tool-Fehler** | Eingabe ist schemakonform, aber fachlich nicht verarbeitbar | Als **strukturierte Fehlerausgabe im Tool-Ergebnis** (`isError = true`) |

Fachliche Fehler werden **nicht** als unbehandelte Exceptions geworfen, sondern abgefangen und in die strukturierte Ausgabe übersetzt.

---

## 2. Fehlertaxonomie

| Kategorie (`code`) | Bedeutung | Beispiel (research-graphrag) |
| --- | --- | --- |
| `invalid_input` | schemakonform, aber semantisch ungültig | leere Frage, unbekannter Suchmodus |
| `not_found` | angeforderte Ressource existiert nicht | unbekannte Paper-ID, fehlendes Index-Artefakt |
| `permission_denied` | Zugriff außerhalb erlaubter Grenzen | Pfad außerhalb `papers/` bzw. der Workspace-Roots |
| `parse_error` | Quelle nicht parsebar | korruptes PDF, ungültiges Canonical JSON |
| `dependency_error` | externer/vernetzter Dienst nicht verfügbar | Cloud-Backend (falls genutzt) nicht erreichbar |
| `constraint_violation` | fachliche Invariante verletzt | Abfrage angefordert, aber kein Index gebaut |
| `internal_error` | unerwarteter interner Fehler (Bug) | nicht abgefangene Ausnahme im Tool |

> **Abgrenzung `dependency_error` ↔ `internal_error`:** Fehler eines **eingebetteten, im Prozess laufenden** Stores (z. B. die lokale SQLite-Index-Datei) sind **kein** `dependency_error`, sondern `internal_error`. `dependency_error` ist ausschließlich für **externe/vernetzte** Dienste vorgesehen.

Neue Kategorien sind **ADR-pflichtig**, da sie das gesamte Tool-Portfolio betreffen.

---

## 3. Struktur der Fehlerausgabe

```json
{
  "error": {
    "code": "parse_error",
    "message": "PDF konnte nicht extrahiert werden: unlesbare Seite.",
    "details": {
      "uri": "file:///.../paper.pdf",
      "page": 12
    }
  }
}
```

- **`code`** – Pflicht, eine der Kategorien aus Abschnitt 2.
- **`message`** – Pflicht, präzise und handlungsleitend; keine Secrets/sensiblen Daten.
- **`details`** – optional, strukturierte Zusatzinformation (z. B. Provenienz-Anker `uri`/`page`).

---

## 4. Regeln für Tool-Autoren

1. **Jeder zugesagte Fehlerfall steht in der Tool-Spec** und wird einer Kategorie zugeordnet.
2. **Sicherheitsgrenzen zuerst prüfen:** Zugriffe außerhalb erlaubter Roots werden mit `permission_denied` abgewiesen, bevor Fachlogik läuft.
3. **Keine stillen Fehler:** immer eine definierte Kategorie, nie ein leeres/scheinbar erfolgreiches Ergebnis.
4. **Konsistenz mit Logging:** der gemeldete `code` wird auch im Log verwendet.
5. **`internal_error` ist ein Signal, kein Normalfall.**

---

## 5. Bezug zu den Tests

Der Fehler-/Edge-Case-Test jedes Tools prüft mindestens: erwartete **Fehlerkategorie** bei ungültiger Eingabe, Durchsetzung von `permission_denied`, und die **Struktur** der Fehlerausgabe.
