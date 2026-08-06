"""Quantitative, offline Evaluation von Retrieval und Router (Phase 7 / A6 + A7).

Bündelt das versionierte Gold-Set mit seiner mechanisch nachrechenbaren Label-Regel, die
retrieval-freien Kennzahlen, die Ausführung gegen einen realen Index (geteilte Chunk-Primitive
**und** die Modi als Ganzes), das eingefrorene Baseline-Artefakt samt qid-genauem
Regressions-Check sowie die Textausgabe
(docs/adr/0014-hybrid-retrieval-bm25-tfidf-phase7.md,
docs/adr/0016-quantitative-retrieval-evaluation-phase7.md).

Dazu kommt mit :mod:`~research_graphrag.evaluation.routing` eine **zweite, bewusst getrennte**
Messung: die Contract-Treue des Query-Routers. Sie braucht keinen Index und wird nie auf
Hit@k/MRR optimiert (docs/adr/0017-router-hardening-phase7.md).

Mit :mod:`~research_graphrag.evaluation.multihop` tritt eine **dritte** Messung daneben: der
Fragetyp „Zitations-/Methodennetze" gegen die ``CITES``-Kanten – die einzige
**nicht-lexikalische** Label-Quelle des Repos, ebenfalls mit eigenem Gold-Set, eigenen Ebenen
und eigener Baseline (docs/adr/0023-multihop-citation-evaluation-phase10.md).
"""

from __future__ import annotations

from research_graphrag.evaluation.baseline import (
    BASELINE_VERSION,
    Baseline,
    Change,
    Comparison,
    Fingerprint,
    build_baseline,
    compare,
    load_baseline,
    precheck,
    read_fingerprint,
    save_baseline,
)
from research_graphrag.evaluation.gold import (
    CITATION_LABEL_SOURCE,
    CITATION_LABELS,
    MECHANICAL_LABELS,
    GoldQuestion,
    GoldSet,
    derive_expected_papers,
    load_gold_set,
    relabel_gold_set,
    save_gold_set,
    unlabelled_questions,
    verify_labels,
)
from research_graphrag.evaluation.metrics import (
    CoverageStats,
    EvaluationReport,
    QuestionScore,
    first_hit,
)
from research_graphrag.evaluation.multihop import (
    CITING_BUCKETS,
    DEFAULT_MULTIHOP_PARAMETERS,
    GRAPH,
    LEVELS,
    MULTIHOP_GOLD_VERSION,
    QUERY_FRAME,
    MultiHopGoldSet,
    MultiHopParameters,
    MultiHopQuestion,
    RecallBounds,
    build_multihop_gold,
    derive_questions,
    evaluate_level,
    evaluate_multihop,
    is_reference_section,
    load_multihop_gold,
    recall_bounds,
    save_multihop_gold,
    verify_questions,
)
from research_graphrag.evaluation.report import (
    render_comparison,
    render_modes,
    render_multihop_report,
    render_report,
    render_router_report,
)
from research_graphrag.evaluation.routing import (
    CONTRACT_MODES,
    RouterGoldSet,
    RouterQuestion,
    RouterReport,
    RouterScore,
    evaluate_router,
    load_router_gold,
    signal_coverage,
    verify_router_labels,
)
from research_graphrag.evaluation.runner import (
    LABELS,
    MODES,
    PRIMITIVE,
    RunParameters,
    evaluate_all,
    evaluate_mode,
    evaluate_primitive,
)

__all__ = [
    "BASELINE_VERSION",
    "CITATION_LABELS",
    "CITATION_LABEL_SOURCE",
    "CITING_BUCKETS",
    "CONTRACT_MODES",
    "DEFAULT_MULTIHOP_PARAMETERS",
    "GRAPH",
    "LABELS",
    "LEVELS",
    "MECHANICAL_LABELS",
    "MODES",
    "MULTIHOP_GOLD_VERSION",
    "PRIMITIVE",
    "QUERY_FRAME",
    "Baseline",
    "Change",
    "Comparison",
    "CoverageStats",
    "EvaluationReport",
    "Fingerprint",
    "GoldQuestion",
    "GoldSet",
    "MultiHopGoldSet",
    "MultiHopParameters",
    "MultiHopQuestion",
    "QuestionScore",
    "RecallBounds",
    "RouterGoldSet",
    "RouterQuestion",
    "RouterReport",
    "RouterScore",
    "RunParameters",
    "build_baseline",
    "build_multihop_gold",
    "compare",
    "derive_expected_papers",
    "derive_questions",
    "evaluate_all",
    "evaluate_level",
    "evaluate_mode",
    "evaluate_multihop",
    "evaluate_primitive",
    "evaluate_router",
    "first_hit",
    "is_reference_section",
    "load_baseline",
    "load_gold_set",
    "load_multihop_gold",
    "load_router_gold",
    "precheck",
    "read_fingerprint",
    "recall_bounds",
    "relabel_gold_set",
    "render_comparison",
    "render_modes",
    "render_multihop_report",
    "render_report",
    "render_router_report",
    "save_baseline",
    "save_gold_set",
    "save_multihop_gold",
    "signal_coverage",
    "unlabelled_questions",
    "verify_labels",
    "verify_questions",
    "verify_router_labels",
]
