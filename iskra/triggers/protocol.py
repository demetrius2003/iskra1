"""Trigger type protocol."""

from typing import TYPE_CHECKING, Protocol

from iskra.models import MemoryRecord, StateSnapshot

if TYPE_CHECKING:
    from iskra.memory.protocol import MemoryStore


class TriggerType(Protocol):
    name: str
    base_weight: float

    def compute_weight(self, state: StateSnapshot) -> float: ...
    def generate_context(self, memory: MemoryStore) -> list[MemoryRecord]: ...
