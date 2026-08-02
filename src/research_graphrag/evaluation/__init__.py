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
    MECHANICAL_LABELS,
    GoldQuestion,
    GoldSet,
    derive_expected_papers,
    load_gold_set,
    verify_labels,
)
from research_graphrag.evaluation.metrics import (
    CoverageStats,
    EvaluationReport,
    QuestionScore,
    first_hit,
)
from research_graphrag.evaluation.report import (
    render_comparison,
    render_modes,
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
    "CONTRACT_MODES",
    "LABELS",
    "MECHANICAL_LABELS",
    "MODES",
    "PRIMITIVE",
    "Baseline",
    "Change",
    "Comparison",
    "CoverageStats",
    "EvaluationReport",
    "Fingerprint",
    "GoldQuestion",
    "GoldSet",
    "QuestionScore",
    "RouterGoldSet",
    "RouterQuestion",
    "RouterReport",
    "RouterScore",
    "RunParameters",
    "build_baseline",
    "compare",
    "derive_expected_papers",
    "evaluate_all",
    "evaluate_mode",
    "evaluate_primitive",
    "evaluate_router",
    "first_hit",
    "load_baseline",
    "load_gold_set",
    "load_router_gold",
    "precheck",
    "read_fingerprint",
    "render_comparison",
    "render_modes",
    "render_report",
    "render_router_report",
    "save_baseline",
    "signal_coverage",
    "verify_labels",
    "verify_router_labels",
]
