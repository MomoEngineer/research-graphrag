# Handprobe: Tool-Wahl mit Personen-Werkzeugen (Phase 17 / A6)

Prüft im **realen Client** (Copilot im Agent-Modus bzw. Claude), ob die vier Personen-Werkzeuge
gewählt werden, wenn eine Frage eine Person meint, und **nur** dann. Grundlage ist die Sorge aus
[ADR 0043](../docs/adr/0043-author-index-and-person-tools.md): Mehr Werkzeuge können die
Tool-Wahl verschlechtern (Jia et al. 2025, arXiv:2510.24563, S. 9).

> **Schwelle** (Roadmap Phase 17 / A6):
>
> - Bei mindestens **9 von 10** Personenfragen wählt der Client das richtige Personen-Werkzeug.
> - Bei den **5** Fragen bestehender Fragetypen verschlechtert sich nichts: Kein Personen-Werkzeug
>   wird gewählt, und das gewählte Werkzeug passt zum Fragetyp.
>
> Wird die Schwelle verfehlt, werden die **Beschreibungen geschärft**, nicht Werkzeuge gestrichen
> (Nachtrag zu ADR 0043).

## Vorbereitung

1. `python -m scripts.ingest`, damit der Index die Personenebene trägt.
2. Personen wählen: am besten dieselben wie in der Personen-Handprobe aus A0, Punkt 4. Mit
   `python -m scripts.authors suchen "<Name>"` prüfen, dass jede Person im Index steht. Für
   Frage P9 einen Nachnamen wählen, zu dem `suchen` **mehrere** Kandidaten liefert.
3. Platzhalter `<Person …>` unten durch die Namen ersetzen. Die Fragen **wörtlich** stellen, je
   Frage in einer **neuen** Unterhaltung, damit frühere Aufrufe die Wahl nicht beeinflussen.

## Bewertung

- **Richtig** ist eine Personenfrage, wenn die Aufrufkette beim erwarteten Werkzeug ankommt. Der
  Weg über `search_authors` (Name → `person_key`) ist dabei erwünscht, außer bei P9 und P10, wo
  `search_authors` selbst das Ziel ist.
- **Falsch** ist eine Personenfrage, wenn der Client stattdessen eine Inhaltssuche
  (`search_basic`, `search_local`, `answer_question` …) oder `get_citations` zur Beantwortung
  nutzt oder raten muss, weil er kein Werkzeug aufruft.
- **Richtig** ist eine Kontrollfrage, wenn kein Personen-Werkzeug aufgerufen wird und das gewählte
  Werkzeug zum Fragetyp der README passt (`answer_question` oder das Suchwerkzeug des Modus).

## Personenfragen

| ID | Frage | Erwartetes Werkzeug | Beobachtete Kette | Richtig? |
| --- | --- | --- | --- | --- |
| P1 | Welche Paper von `<Person A>` liegen im Korpus? | `get_author` | | |
| P2 | Mit wem hat `<Person B>` im Korpus gemeinsam publiziert? | `get_author` | | |
| P3 | Zu welchen Themen hat `<Person C>` im Korpus Arbeiten? | `get_author` | | |
| P4 | Was schreibt `<Person A>` über die Evaluation von Retrieval? | `search_author_papers` | | |
| P5 | Welche Datensätze werden in den Papern von `<Person D>` genannt? | `search_author_papers` | | |
| P6 | Wie beschreibt `<Person E>` die Grenzen von Graph-basiertem RAG? | `search_author_papers` | | |
| P7 | Welche Paper im Korpus zitieren Arbeiten von `<Person B>`? | `get_author_citations` | | |
| P8 | Auf welche Korpus-Paper stützen sich die Arbeiten von `<Person C>`? | `get_author_citations` | | |
| P9 | Gibt es im Korpus mehrere Personen mit dem Nachnamen `<Nachname>`? | `search_authors` | | |
| P10 | Ist `<Person F>` mit eigenen Arbeiten im Korpus vertreten? | `search_authors` | | |

## Kontrollfragen (bestehende Fragetypen)

Aus dem Prüf-Fragen-Set ([pruef-fragen.md](pruef-fragen.md), `QUESTIONS` in
[scripts/qa.py](../scripts/qa.py)), je Fragetyp eine.

| ID | Frage | Fragetyp → Modus | Beobachtetes Werkzeug | Richtig? |
| --- | --- | --- | --- | --- |
| D2 | What are the key stages of the GraphRAG workflow? | Detailfrage → Local/Basic | | |
| S1 | Which research directions emerge across the corpus? | Synthese → Global | | |
| N1 | Which papers build on knowledge graph methods? | Netze → Local + `get_citations` | | |
| F1 | What F1 score is reported for the evaluation? | Fakt → Basic | | |
| W1 | Compare vector and graph retrieval approaches. | Vergleich → DRIFT | | |

## Ergebnis

| Feld | Wert |
| --- | --- |
| Datum | |
| Client und Modell | |
| Index-Stand (`python -m scripts.status`) | |
| Personenfragen richtig | _ / 10 |
| Kontrollfragen richtig | _ / 5 |
| Schwelle erreicht? | |
| Nötige Schärfungen (Werkzeug, Befund) | |
