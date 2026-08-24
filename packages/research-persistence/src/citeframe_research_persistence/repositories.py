"""Small DB-only Research repositories; commands own transition semantics."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from citeframe_persistence.models import ResearchRun, ResearchStep, ResearchStepAttempt

class ResearchRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_run(self, run_id: str) -> ResearchRun | None:
        return self.db.get(ResearchRun, run_id)

    def get_step(self, step_id: str) -> ResearchStep | None:
        return self.db.get(ResearchStep, step_id)

    def get_attempt(self, attempt_id: str) -> ResearchStepAttempt | None:
        return self.db.get(ResearchStepAttempt, attempt_id)

    def queued_steps(self) -> list[ResearchStep]:
        return list(self.db.scalars(select(ResearchStep).where(ResearchStep.status == "queued").order_by(ResearchStep.queued_at, ResearchStep.created_at, ResearchStep.id)).all())
