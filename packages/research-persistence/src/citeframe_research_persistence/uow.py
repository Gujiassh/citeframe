"""Session/UoW boundary for Research commands."""
from __future__ import annotations
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Self
from sqlalchemy.orm import Session

class ResearchUnitOfWork(AbstractContextManager[Session]):
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> Self:
        self.session = self._session_factory()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        assert self.session is not None
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
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
