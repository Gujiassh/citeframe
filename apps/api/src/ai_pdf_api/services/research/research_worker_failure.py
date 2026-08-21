"""Compatibility facade for neutral Research failure commands."""
from citeframe_research_persistence.failure import fail_research_step
from citeframe_research_persistence.policy import FailureDisposition
__all__ = ["FailureDisposition", "fail_research_step"]
