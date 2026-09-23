"""Frozen paired-case execution."""

from citeframe_evaluation.runtime.quick import run_quick_case
from citeframe_evaluation.runtime.research import run_research_case
from citeframe_evaluation.runtime.quick import run_quick_case_with_diagnostics
from citeframe_evaluation.runtime.research import run_research_case_with_diagnostics

__all__ = [
    "run_quick_case",
    "run_research_case",
    "run_quick_case_with_diagnostics",
    "run_research_case_with_diagnostics",
]
