"""Session/UoW boundary for Research commands."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from .repositories import ResearchRepository


class ResearchUnitOfWork(AbstractContextManager["ResearchUnitOfWork"]):
    """Own one Research command session and its commit/rollback lifecycle."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None
        self.repository: ResearchRepository | None = None

    def __enter__(self) -> Self:
        if self.session is not None:
            raise RuntimeError("ResearchUnitOfWork is already active")
        self.session = self._session_factory()
        self.repository = ResearchRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        del exc, tb
        db = self.db
        try:
            if exc_type is None:
                db.commit()
            else:
                db.rollback()
        finally:
            db.close()
            self.repository = None
            self.session = None
        return False

    @property
    def db(self) -> Session:
        if self.session is None:
            raise RuntimeError("ResearchUnitOfWork is not active")
        return self.session

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
