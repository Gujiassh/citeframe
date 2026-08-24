"""Composition ports for non-DB Research capabilities."""
from __future__ import annotations
from collections.abc import Callable
from typing import Protocol

class ProviderConfigResolver(Protocol):
    def __call__(self, retrieval_top_k: int) -> str: ...

class ResearchArtifactStore(Protocol):
    def upload(self, *, object_key: str, content: bytes, content_type: str) -> None: ...
    def delete(self, *, object_key: str) -> None: ...

ProviderResolver = Callable[[int], str]
