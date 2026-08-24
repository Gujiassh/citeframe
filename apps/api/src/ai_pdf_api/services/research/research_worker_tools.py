
from functools import wraps
"""API compatibility facade for neutral Research tool persistence commands."""
from citeframe_research_persistence.lease import (
    _active_attempt_chain,
    _ledger_and_limits,
    _locked_attempt_chain,
)
from citeframe_research_persistence.tools import (
    ToolResultCallback,
    _tool_call_chain,
    begin_tool_call as _begin_tool_call,
    complete_tool_call as _complete_tool_call,
    restore_evidence_handles,
)
from citeframe_research_persistence.types import ToolCallReservation
from sqlalchemy.orm import Session


def _commit_command(db: Session, command, /, *args, **kwargs):
    try:
        result = command(db, *args, **kwargs)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@wraps(_begin_tool_call)
def begin_tool_call(db: Session, *args, **kwargs):
    return _commit_command(db, _begin_tool_call, *args, **kwargs)


@wraps(_complete_tool_call)
def complete_tool_call(db: Session, *args, **kwargs):
    return _commit_command(db, _complete_tool_call, *args, **kwargs)

__all__ = [
    "ToolCallReservation",
    "ToolResultCallback",
    "begin_tool_call",
    "complete_tool_call",
    "restore_evidence_handles",
]
