# Modul-Doku: `fts.py`

| Feld | Wert |
| --- | --- |
| **Modul** | `src/research_graphrag/indexing/fts.py` |
| **Paket** | `indexing` – Index, Graphen und Metadaten |
| **Phase** | 17 / A3 (eingeführt), 16 / F2 (Phrase, Präfix, Nähe) |
| **Grundlagen** | [ADR 0043](../../../../docs/adr/0043-author-index-and-person-tools.md), [ADR 0044](../../../../docs/adr/0044-response-latency-bit-identical-scoring-and-fts5-phase16.md) |

---

## 1. Zweck

Die **eine** Stelle für die Regeln, die jede FTS5-Nutzung im Repository teilt: die Namenssuche des
[Autorenindex](author_index.md) und die Phrasen-, Präfix- und Nähe-Suche über `chunks` aus
Phase 16 / F2 ([chunk_fts](chunk_fts.md)). Die Roadmap verlangt für F2 ausdrücklich: „FTS5-Anfragen sind Nutzereingaben“ und „eine
missglückte Anfrage endet als `invalid_input`“. Das Modul setzt beides einmal um.

## 2. Öffentliche Schnittstelle

| Symbol | Art | Aufgabe |
| --- | --- | --- |
| `tokenizer_available` | Funktion | Kann FTS5 mit diesem Tokenizer angelegt werden? (Probe in `temp`, Name per Whitelist geprüft) |
| `quote_tokens` | Funktion | Tokens als FTS5-String-Literale, verbunden durch implizites UND |
| `quote_phrase` | Funktion | Ein Text als **eine** Phrase (String-Literal); leer → `invalid_input` |
| `quote_prefix` | Funktion | Phrase mit Präfix auf dem letzten Wort (`"…" *`) |
| `quote_near` | Funktion | `NEAR("a" "b", n)`: mindestens zwei Begriffe, Abstand als geprüfte Ganzzahl |
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
| Phrase `retrieval (augmented) OR x` | `"retrieval (augmented) OR x"` | eine Wortfolge; Klammern und `OR` wirkungslos |
| Präfix `retriev` | `"retriev" *` | nur das letzte Wort als Präfix |
| Nähe `lewis`, `graph`, 5 | `NEAR("lewis" "graph", 5)` | Abstand stammt nie als Text aus der Eingabe |

## 4. Zusammenspiel

`author_index` nutzt `tokenizer_available`, `quote_tokens` und `safe_match`; [chunk_fts](chunk_fts.md)
(Phase 16 / F2) nutzt `tokenizer_available`, die drei Phrasen-Funktionen und `safe_match` – eine
zweite Entschärfung gibt es nicht.

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

- Keine Ranking-Logik für das Retrieval: FTS5 greift in keinen der vier Suchmodi ein. Die Regel aus
  Phase 16 / F0 hat die Vorauswahl verworfen (langsamer als die exakte Wertung, nicht
  bit-identisch; ADR 0044). `chunk_fts` ordnet nur seine eigenen Fundstellen nach FTS5-Relevanz.
