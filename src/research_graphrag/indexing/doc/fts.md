# Modul-Doku: `fts.py`

| Feld | Wert |
| --- | --- |
| **Modul** | `src/research_graphrag/indexing/fts.py` |
| **Paket** | `indexing` – Index, Graphen und Metadaten |
| **Phase** | 17 / A3 (Übernahme durch Phase 16 / F2 vorgesehen) |
| **Grundlagen** | [ADR 0043](../../../../docs/adr/0043-author-index-and-person-tools.md) |

---

## 1. Zweck

Die **eine** Stelle für die Regeln, die jede FTS5-Nutzung im Repository teilt: die Namenssuche des
[Autorenindex](author_index.md) heute und die Phrasensuche über `chunks` aus Phase 16 / F2
künftig. Die Roadmap verlangt für F2 ausdrücklich: „FTS5-Anfragen sind Nutzereingaben“ und „eine
missglückte Anfrage endet als `invalid_input`“. Das Modul setzt beides einmal um.

## 2. Öffentliche Schnittstelle

| Symbol | Art | Aufgabe |
| --- | --- | --- |
| `tokenizer_available` | Funktion | Kann FTS5 mit diesem Tokenizer angelegt werden? (Probe in `temp`, Name per Whitelist geprüft) |
| `quote_tokens` | Funktion | Tokens als FTS5-String-Literale, verbunden durch implizites UND |
| `safe_match` | Funktion | `MATCH`-Abfrage ausführen; `OperationalError` wird zu `invalid_input` |
| `TRIGRAM_MIN_CHARS` | Konstante | 3 – kürzere Suchwörter findet `trigram` nicht |

## 3. Ablauf

Das Modul ist ein Werkzeug-Modul ohne mehrstufigen Ablauf. Entschärfung:

| Eingabe | Ausdruck | Wirkung |
| --- | --- | --- |
| `asai akari` | `"asai" "akari"` | beide Wörter müssen vorkommen |
| `asai OR x` | `"asai" "OR" "x"` | `OR` ist ein gewöhnliches Wort |
| `asai*` / `NEAR(a b)` / `wang:1` | als Literal | kein Präfix, kein NEAR, kein Spaltenfilter |
| `a"b` | `"a""b"` | inneres Anführungszeichen verdoppelt |

## 4. Zusammenspiel

`author_index` nutzt alle drei Funktionen. F2 übernimmt sie für die Chunk-Phrasensuche, statt eine
zweite Entschärfung zu bauen.

## 5. Fehler und Grenzfälle

| Situation | Verhalten |
| --- | --- |
| keine Tokens | `invalid_input` |
| FTS5-Syntaxfehler zur Laufzeit | `invalid_input` |
| Tokenizer-Name außerhalb `[a-z0-9_ ]` | `invalid_input` (wird in SQL eingesetzt) |
| FTS5 / Tokenizer fehlt | `tokenizer_available` liefert `False`; der Aufrufer nimmt seinen Rückfallweg |

## 6. Determinismus

Reine Funktionen; die Verfügbarkeitsprobe schreibt nur in die temporäre Datenbank der Verbindung.

## 7. Grenzen

- Keine Ranking-Logik (`bm25()` von FTS5 wird nicht genutzt). Ob FTS5 ins Ranking eingreift,
  entscheidet allein die Regel aus Phase 16 / F0.
