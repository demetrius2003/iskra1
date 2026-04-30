"""Trigger type protocol."""

from __future__ import annotations

from typing import Protocol

from iskra.memory.protocol import MemoryStore
from iskra.models import MemoryRecord, StateSnapshot


class TriggerType(Protocol):
    name: str
    base_weight: float

    def compute_weight(self, state: StateSnapshot) -> float: ...
    def generate_context(self, memory: MemoryStore) -> list[MemoryRecord]: ...
