# 0029 – Referenz-Einträge (Phase 13 / R1): Eingabeliste, `.refjson`-Stub und Online-Auflösung

- **Status:** Akzeptiert
- **Datum:** 2026-08-09

## Kontext

Ein Paper, von dem nur der Abstract öffentlich zugänglich ist, hat heute **keinen** Weg in den
Korpus: Der Intake liest ausschließlich `*.pdf`, und die einzige Ablage für einen solchen Fund ist
die kuratierte Tabelle [`Übersicht.md`](../../Übersicht.md) – kein Index, also weder auffindbar
noch zitierbar noch Ziel einer Zitationskante.

Die Vorabmessung **R0** (2026-08-09, Statusblock in [Roadmap.md](../../Roadmap.md#phase-13--referenz-einträge-ohne-volltext))
hat die drei offenen Fragen beantwortet und dabei zwei Vorgaben korrigiert:

1. **Ausbeute 93 %** (52 von 56 gültigen Kennungen mit Abstract, bei Werken hinter einer
   Bezahlschranke 6 von 7). Die Skepsis der Roadmap stammte aus **Crossref**; gemessen wurde der
   Weg, den dieser ADR tatsächlich nimmt – **OpenAlex** mit dem **arXiv-Feed als Rückfall**. Die
   Online-Auflösung bleibt damit der **Hauptweg**, der manuelle Weg die Ausnahme.
2. **Nutzen belegt:** 3371 tote DOI-/arXiv-Verweise im eigenen Referenzbestand, davon 702 von
   mindestens zwei Korpus-Papern zitiert; schon die zehn meistzitierten stiften **307** neue
   `CITES`-Kanten (Bestand 1481).
3. **Verdrängung eingetreten:** 13 qid-Regressionen mit echten Abstracts ⇒ die Guardrail aus R3
   ist gesetzt. Sie ist **nicht** Gegenstand dieses ADR.

Dieser ADR entscheidet ausschließlich den **ersten** Schritt: aus einer kuratierten Kennungsliste
wird je Kennung **eine Datei** im Eingangsordner. Er verändert **nichts** an Intake, Extraktion,
Index, Retrieval oder Contract – das ist R2/R3.

## Entscheidung

### 1. Eingabe: `new_papers/referenzen.txt`, tolerant gelesen, unverändert gelassen

Eine Kennung je Zeile. Akzeptiert werden **DOI und arXiv-ID** in allen gebräuchlichen
Schreibweisen (nackt, mit `doi:`/`arXiv:`-Präfix, als `https://doi.org/…`, `arxiv.org/abs/…`,
`…/pdf/…v2`), zusätzlich alte arXiv-Kennungen der Form `cs/0501001`. `#` leitet einen Kommentar
ein – auch **hinter** einer Kennung, damit die Liste ein kuratiertes Dokument bleiben kann
(„warum steht das hier?"). Eine nicht deutbare Zeile ist ein **Befund im Bericht**, kein Abbruch.

Der DataCite-DOI `10.48550/arXiv.X` wird beim Lesen zur arXiv-Kennung `X` normalisiert: Beide
bezeichnen dasselbe Werk, und ohne diese Normalisierung schlüge die Duplikatprüfung fehl.

Die Liste wird **nur gelesen**. Sie ist kein Arbeitsvorrat, den ein Skript abräumt – erledigte
Einträge bleiben stehen und werden beim nächsten Lauf über die Idempotenzprüfung erkannt.

### 2. Ausgabe: eine native Stub-Datei `*.refjson` je Kennung

Das Format ist **JSON** – dieselbe Familie wie `data/canonical/*.json` und
`metadata/paper_metadata.json`, lesbar mit der Standardbibliothek, deterministisch schreibbar und
für den manuellen Eingriff ausreichend handlich. Die Endung ist eigen, damit `papers/*.pdf`-Globs
unberührt bleiben und die Datei nie mit einem Canonical verwechselt wird.

Die Feldnamen sind **deckungsgleich mit `bibliography.model.MetadataRecord`** (`title`, `authors`,
`year`, `venue`, `doi`, `arxiv_id`, `url`) – flach, nicht in einem `identifiers`-Objekt
verschachtelt. Damit ist die Abbildung in R2 eine Zuweisung statt einer Übersetzung, und die
Zitierfähigkeit aus [ADR 0025](0025-citable-paper-metadata.md) erbt das Format ohne Zwischenschicht.

```json
{
  "schema_version": "0.1.0",
  "document_kind": "reference",
  "requested": "arxiv:2404.16130",
  "title": "…",
  "authors": ["…"],
  "year": 2024,
  "venue": "…",
  "doi": "10.48550/arXiv.2404.16130",
  "arxiv_id": "2404.16130",
  "url": "https://…",
  "source": "OpenAlex",
  "source_url": "https://api.openalex.org/works/doi:…",
  "retrieved_at": "2026-08-09T10:11:12Z",
  "note": "",
  "abstract": "…"
}
```

`document_kind` steht **schon jetzt** in der Datei, obwohl das Feld erst in R2 ins Canonical- und
Index-Schema wandert: Die Datei deklariert ihre Art selbst, statt dass ein späterer Leser sie aus
der Dateiendung erschließen muss. `abstract` steht bewusst am **Ende** – es ist das einzige Feld,
das von Hand nachgetragen wird. Die Feldreihenfolge ist im Code festgelegt (kein `sort_keys`),
damit die Datei deterministisch **und** lesbar ist.

### 3. Dateiname: selbst erzeugt, mit sprechendem Wort **und** stabilem Anker

`ref-<titelwort>-<kennung>.refjson`, zum Beispiel `ref-graphrag-arxiv-2404.16130.refjson`.

Der Titelteil entsteht aus dem Titel der Antwort: Steht vor dem ersten Doppelpunkt ein kurzer
Teil (bis vier Wörter), wird dieser genommen – die verbreitete Konvention „`GraphRAG: From Local
to Global`" macht damit den System-/Modellnamen sichtbar. Sonst werden die ersten
bedeutungstragenden Wörter des Titels verwendet.

**Abweichung von der Roadmap, bewusst und begründet:** Die Vorgabe verlangt einen Namen
„deterministisch aus dem Identifikator, nie aus einer Serverantwort". Die Sicherheitsauflage
dahinter ist der Schutz vor Pfad-Traversal – und die bleibt vollständig gewahrt: Der Name wird
**erzeugt**, nicht übernommen. Aus der Antwort wird ausschließlich über eine **Whitelist**
(`a`–`z`, `0`–`9`) ein Slug gebildet, längenbegrenzt; Punkte, Trennzeichen und alles Übrige
entfallen. Ein Serverwert kann den Namen also weder verlassen noch verlängern. Der
**Identifikator bleibt der eindeutige Anker** im Namen.

Die eigentliche Funktion der Vorgabe – Idempotenz – wird **nicht** über den Namen erfüllt,
sondern **inhaltsbasiert** (Abschnitt 4). Das ist strenger als die Vorgabe: Auch eine von Hand
umbenannte Stub-Datei wird wiedererkannt.

### 4. Idempotenz gegen drei Zustände – **vor** jeder Abfrage

Geprüft wird, bevor eine einzige Anfrage gestellt wird (sonst verbraucht ein Wiederholungslauf
fremdes Kontingent):

| Zustand | Grundlage |
| --- | --- |
| Korpus | `intake.load_corpus(data).identifier_to_paper` – die **bestehende**, gehärtete Grundlage aus [ADR 0019](0019-corpus-intake-new-papers-phase8.md), dieselbe wie in [ADR 0020](0020-online-candidate-search-phase9.md) |
| Eingang | `doi`/`arxiv_id`/`requested` **aus jeder** `new_papers/*.refjson` gelesen |
| Quarantäne | ebenso aus `new_papers/_duplikate/*.refjson` |

Eine unlesbare Stub-Datei wird protokolliert und übersprungen, statt den Lauf zu beenden – sie
darf einen ganzen Lauf nicht blockieren.

### 5. Auflösungsweg – genau der, den R0 gemessen hat

1. **OpenAlex über DOI** (`openalex_id_url`),
2. **OpenAlex über den DataCite-DOI** der arXiv-Kennung,
3. **arXiv-Feed** – als Rückfall, wenn OpenAlex nichts liefert, **und zusätzlich** dann, wenn
   OpenAlex zwar Metadaten, aber **keinen** Abstract liefert.

Punkt 3 ist kein Zusatzwunsch, sondern Voraussetzung dafür, die gemessenen 93 % zu reproduzieren:
R0 hat genau diese Kombination gemessen. Die Felder bleiben in diesem Fall von OpenAlex, ergänzt
wird nur der Abstract.

Neu gegenüber [ADR 0026](0026-online-metadata-resolution.md) ist allein, dass
`abstract_inverted_index` mit angefordert und über das vorhandene `sources._restore_abstract`
zurückgebaut wird. Der Netzzugang läuft ausschließlich über den injizierbaren Port aus
[ADR 0020](0020-online-candidate-search-phase9.md); alles Übrige ist offline getestet.

> **Am realen Dienst gefunden und behoben:** Der arXiv-Feed wurde bis dahin ausschließlich über
> `search_query=all:"…"` abgefragt – eine **Volltextsuche**. Nach einer Kennung gesucht liefert
> sie zuverlässig ein *fremdes* Paper (`1706.03762` → `2002.05202`). Neu sind deshalb
> `sources.arxiv_id_url` und `sources.fetch_arxiv_by_id`, die `id_list` verwenden. Ohne diese
> Korrektur wäre der Rückfall praktisch wirkungslos gewesen – und damit die in R0 gemessene
> Ausbeute nicht reproduzierbar.
>
> **Derselbe Defekt steckt in `metadata._by_arxiv_feed`** (Phase 12 / K2). Dort bleibt er ohne
> Schaden, weil die Identitätsprüfung den Fehltreffer verwirft – aber der Rückfall greift
> praktisch nie. Er wird hier **bewusst nicht mitkorrigiert**: Das änderte das Verhalten der
> Metadaten-Auflösung außerhalb dieses Schnitts. Der Befund ist notiert, die passende Funktion
> steht bereit.
>
> **Nachtrag (2026-08-10): inzwischen behoben.** Nach dem Abschluss von R3 wurde der Befund in
> einem eigenen Schnitt aufgegriffen – `metadata._by_arxiv_feed` nutzt jetzt `fetch_arxiv_by_id`
> und übernimmt die Autoren; Einzelheiten und die bezifferte Auswirkung stehen im Nachtrag zu
> [ADR 0026](0026-online-metadata-resolution.md).
>
> **Autoren kommen ebenfalls aus dem Feed** (`sources.authors_from_feed`). Ohne sie ist ein
> Eintrag nach [ADR 0025](0025-citable-paper-metadata.md) nicht zitierfähig – und OpenAlex
> schweigt gerade in den Fällen, in denen der Feed einspringt. Bewusst als eigene Funktion statt
> als weiteres Feld an `Candidate`: Die Kandidatensuche braucht keine Autoren.

### 6. Ein Titel ist Pflicht, ein Abstract nicht

- **Kein Abstract** ⇒ die Datei entsteht trotzdem, mit leerem `abstract`, einem Hinweis in `note`
  und einem Befund im Bericht. Der Abstract wird von Hand nachgetragen – über die **erzeugte
  Datei**, nicht über ein zweites Eingabeformat.
- **Kein Titel** ⇒ **keine** Datei, nur ein Befund. Das ist eine **Präzisierung der Roadmap**,
  die diesen Fall nicht regelt. Ein Eintrag ohne Titel wäre weder zitierfähig noch als Ziel einer
  Titel-Kante brauchbar (er unterschreitet `MIN_TITLE_CHARS`/`MIN_TITLE_WORDS`) und würde in R2
  ein sinnloses Korpus-Paper erzeugen. R0 hat gezeigt, dass der Fall real ist: 4 der 60 geprüften
  Kennungen waren abgeschnittene Extraktionsartefakte.

### 7. Determinismus, Sicherheit, Betrieb

- **Die Stub-Datei *ist* die eingefrorene Antwort.** Das Netz wird genau einmal befragt; jede
  spätere Verarbeitung ist deterministisch. `retrieved_at` dient der Provenienz und hat die
  ausgewiesene Folge, dass ein erneuter Abruf eine andere Datei mit anderem Hash ergäbe – genau
  das verhindert die Idempotenzprüfung.
- **Fremdtext ist nicht vertrauenswürdig:** Titel, Autoren, Venue und Abstract werden auf
  druckbare Zeichen reduziert, in Whitespace verdichtet und längenbegrenzt; `url` wird nur
  übernommen, wenn sie ein `http(s)`-Schema trägt und die Längengrenze hält. Die Härtung ist eine
  **eigene**, engere Funktion als `report.safe_url`: Ziel ist hier eine JSON-Datei, kein Markdown –
  eine Maskierung von Markdown-Steuerzeichen wäre hier falsch und würde den Wert verfälschen.
- **`--dry-run`** zeigt Auswahl und geplante Abfragen, ohne den Client überhaupt zu erzeugen –
  kein Netz, kein Kontingent, keine Datei (Muster aus `scripts.discover`).
- **`--limit`** begrenzt die Abfragen je Lauf (Default 25); OpenAlex rechnet 10 Einheiten von
  1000 je Anfrage.
- **Bericht** append-only nach `data/references_log.md` über den geteilten `append_section`; die
  Rohantworten liegen datiert unter `data/online_raw/<Zeitstempel>/` (abschaltbar mit
  `--ohne-rohdaten`).
- **Kein MCP-Werkzeug** – der Lauf braucht Netz **und** schreibt Dateien; beides gehört nicht in
  Agent-Reichweite (gleiche Begründung wie bei Intake und `scripts.resolve_metadata`). Der Server
  bleibt bei **neun** Werkzeugen.

### 8. Sicherungsumfang

`new_papers/referenzen.txt` und `data/references_log.md` werden in den Sicherungsumfang aus
[ADR 0027](0027-corpus-backup-phase11.md) aufgenommen: Die Liste ist kuratiert, das Protokoll ist
append-only – beides ist aus keiner Quelle rekonstruierbar. Die Roadmap ordnet diesen Punkt R3 zu;
vorgezogen wird er, weil die Datei **ab jetzt** existiert und eine Lücke im Sicherungsumfang keine
Ankündigungsfrist verträgt.

## Alternativen

**YAML statt JSON.** Für den manuellen Nachtrag eines Abstracts angenehmer (Block-Scalars), aber
`pyyaml` wäre eine zusätzliche Abhängigkeit gegen [ADR 0002](0002-venv-and-offline-dependency-strategy.md),
und fremde YAML-Eingaben verlangen zusätzliche Sorgfalt beim Parsen. Der Gewinn ist Komfort, der
Preis eine Abhängigkeit im einzigen netzberührten Pfad – **verworfen**.

**TOML.** Die Standardbibliothek kann TOML nur **lesen** (`tomllib`), nicht schreiben – ein
Schreiber wäre selbst zu bauen oder zu beschaffen. **Verworfen.**

**Markdown mit Frontmatter.** Zwei Parser, keiner in der Standardbibliothek, und der Inhalt ist
strukturierte Metadaten, kein Fließtext. **Verworfen.**

**Eine Sammeldatei (JSONL) für alle Stubs.** Widerspricht der Grundmechanik des Intake: Die
`paper_id` ist der sha256 **einer Datei**. Eine Sammeldatei erzwänge einen zweiten Weg in den
Korpus – genau das, was Abschnitt „Genau ein Weg in den Korpus" ausschließt. **Verworfen.**

**Synthetische PDF.** In der Roadmap bereits vorab verworfen: strukturierte Daten in ein PDF
schreiben, um sie per Heuristik wieder herauszuparsen, ist ein Verlustkanal ohne Gegenwert.

**Dateiname rein aus dem Identifikator** (Roadmap-Wortlaut). Erfüllt die Sicherheitsauflage
ebenso, ist aber im Eingangsordner nicht lesbar – `ref-doi-10.1145_3178876.3186111.refjson` sagt
einem Menschen nichts. Da die Idempotenz ohnehin inhaltsbasiert arbeitet, kostet der sprechende
Namensteil nichts; siehe Abschnitt 3.

**Bericht in `data/metadata_log.md` mitschreiben.** Spart eine Datei, vermischt aber zwei
Vorgänge mit unterschiedlicher Semantik (Anreicherung vorhandener Paper vs. Erzeugung neuer
Eingangsdateien). Der geteilte Mechanismus ist `append_section`, nicht die Datei. **Verworfen.**

**`metadata/paper_metadata.json` direkt mitschreiben.** Nicht möglich und nicht sinnvoll: Die
`paper_id` entsteht erst beim Intake aus dem sha256 der Datei. Die Metadaten leben bis dahin im
Stub; R2 zieht sie von dort.

## Konsequenzen

- **Positiv:** Aus einer kuratierten Kennungsliste entsteht mit **einem** Befehl ein
  reproduzierbares, eingefrorenes Artefakt je Paper. Rund 70 % der Mechanik sind Wiederverwendung
  ([ADR 0020](0020-online-candidate-search-phase9.md), [ADR 0026](0026-online-metadata-resolution.md));
  neu sind im Kern das Listenformat, das Stub-Format und die dreifache Idempotenzprüfung. Der
  Kern bleibt netzfrei, alles außer dem Transport ist offline getestet.
- **Negativ / Aufwand:** Bis R2 sind die erzeugten `.refjson`-Dateien **wirkungslos** – der Intake
  ignoriert sie, sie bleiben im Eingang liegen. Das ist der Preis des inkrementellen Schnitts und
  in der Anleitung ausdrücklich vermerkt.
- **Bewusst getragene Grenze:** Die Korpus-Prüfung nutzt den **gehärteten** Schlüsselsatz
  (Frontmatter-Beleg + Eindeutigkeit). Ein Korpus-Paper, dessen Identifikator diesen Guard nicht
  passiert, wird erneut als Stub erzeugt. Das ist dieselbe, in
  [ADR 0020](0020-online-candidate-search-phase9.md) dokumentierte Grenze: Die Prüfung hier ist
  Bequemlichkeit, die Absicherung ist der Intake (sha256 → Identifikator → Titel). Ein
  Regressionstest hält das Verhalten fest.
- **Zwei Schreibweisen desselben Werks in der Liste** (DOI *und* arXiv-ID) erzeugen zwei Abfragen;
  erkannt wird die Dublette erst über die im ersten Durchlauf geschriebene Datei bzw. spätestens
  durch den Intake. Nur der DataCite-Fall wird vorab zusammengeführt.
- **Folgeentscheidungen:** R2 (Intake und Extraktion für `.refjson`, `document_kind` im Canonical-
  und Index-Schema, Upgrade-Regel „Volltext schlägt Referenz-Eintrag") und R3 (Contract-Bruch bis
  in jeden Beleg, Ausschluss aus der Gold-Ableitung, Nachrangigkeits-Guardrail) bekommen eigene
  ADRs. Dieser ADR legt sie nicht fest.
