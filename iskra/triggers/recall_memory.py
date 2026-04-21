"""Recall from memory store."""

from __future__ import annotations

from iskra.core.config import MemoryConfig, TriggerTypeConfig
from iskra.memory.protocol import MemoryStore
from iskra.models import MemoryRecord, StateSnapshot


class RecallMemoryTrigger:
    name = "recall_memory"

    def __init__(self, config: TriggerTypeConfig, memory_config: MemoryConfig) -> None:
        self._cfg = config
        self._memory_config = memory_config

    def compute_weight(self, state: StateSnapshot) -> float:
        if self._cfg.modulated_by is None:
            return self._cfg.base_weight
        mod = state.get(self._cfg.modulated_by, 0.0)
        return self._cfg.base_weight * (1.0 + self._cfg.modulation_strength * mod)

    def generate_context(self, memory: MemoryStore) -> list[MemoryRecord]:
        n = self._memory_config.recall.default_n
        return memory.recall(category=None, n=n, context=None)
