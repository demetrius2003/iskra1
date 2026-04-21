"""MemoryStore protocol."""

from typing import Protocol

from iskra.models import MemoryRecord


class MemoryStore(Protocol):
    def store(self, category: str, content: str, importance: float) -> str: ...
    def recall(
        self, category: str | None = None, n: int = 3, context: str | None = None
    ) -> list[MemoryRecord]: ...
    def decay(self) -> None: ...
    def count(self) -> int: ...
