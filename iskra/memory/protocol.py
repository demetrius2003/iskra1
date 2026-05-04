"""MemoryStore protocol."""

from typing import Protocol

from iskra.models import MemoryRecord


class MemoryStore(Protocol):
    def store(
        self,
        category: str,
        content: str,
        importance: float,
        *,
        emotional_valence: float = 0.0,
        arousal: float = 0.5,
    ) -> str: ...
    def recall(
        self,
        category: str | None = None,
        n: int = 3,
        context: str | None = None,
        *,
        state: dict[str, float] | None = None,
    ) -> list[MemoryRecord]: ...
    def decay(self) -> None: ...
    def count(self) -> int: ...
    def update_importance(self, memory_id: str, importance: float) -> bool: ...
    def link_memories(self, source_id: str, target_ids: list[str]) -> None: ...
    def delete_memory(self, memory_id: str) -> bool: ...
    def consolidate(self) -> None: ...
