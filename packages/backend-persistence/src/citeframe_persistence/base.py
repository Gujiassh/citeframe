"""The single SQLAlchemy declarative base for API and Worker persistence."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
