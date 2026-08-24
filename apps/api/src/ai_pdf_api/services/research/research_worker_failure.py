
from functools import wraps
"""Legacy transaction facade for neutral Research failure commands."""
from sqlalchemy.orm import Session

from citeframe_research_persistence.failure import fail_research_step as _fail_research_step
from citeframe_research_persistence.policy import FailureDisposition


@wraps(_fail_research_step)
def fail_research_step(db: Session, **kwargs) -> FailureDisposition:
    try:
        result = _fail_research_step(db, **kwargs)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


__all__ = ["FailureDisposition", "fail_research_step"]
