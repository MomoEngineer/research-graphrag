"""Online-Modus (Phase 9 / S1): Kandidatensuche auf Metadatenebene.

Das Paket sucht zu Anfragen **aus dem eigenen Bestand** neue Literatur bei arXiv und OpenAlex,
dedupliziert die Treffer gegen den Korpus und schreibt einen append-only Bericht. Es lädt
**keine** Volltexte und schreibt weder nach ``papers/`` noch nach ``new_papers/`` – der einzige
Weg in den Korpus bleibt der Intake (docs/adr/0019-corpus-intake-new-papers-phase8.md).

Der Netzzugang liegt hinter dem injizierbaren Port :class:`~.transport.HttpClient`; alle übrigen
Module sind netzfrei und offline testbar
(docs/adr/0020-online-candidate-search-phase9.md).
"""
