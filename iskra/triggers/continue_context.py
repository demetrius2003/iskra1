"""Continue last LLM context."""

from __future__ import annotations

from iskra.core.config import TriggerTypeConfig
from iskra.memory.protocol import MemoryStore
from iskra.models import MemoryRecord, StateSnapshot


class ContinueContextTrigger:
    name = "continue_context"

    def __init__(self, config: TriggerTypeConfig) -> None:
        self._cfg = config

    def compute_weight(self, state: StateSnapshot) -> float:
        if self._cfg.modulated_by is None:
            return self._cfg.base_weight
        mod = state.get(self._cfg.modulated_by, 0.0)
        return self._cfg.base_weight * (1.0 + self._cfg.modulation_strength * mod)

    def generate_context(self, memory: MemoryStore) -> list[MemoryRecord]:
        return memory.recall(category="last_context", n=1, context=None)
