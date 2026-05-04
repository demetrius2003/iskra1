"""Random topic trigger."""

from __future__ import annotations

import random
from datetime import UTC, datetime

from iskra.core.config import TriggerTypeConfig
from iskra.memory.protocol import MemoryStore
from iskra.models import MemoryRecord, StateSnapshot


class NewTopicTrigger:
    name = "new_topic"

    def __init__(self, config: TriggerTypeConfig, topic_pool: list[str]) -> None:
        self._cfg = config
        self._pool = topic_pool

    def compute_weight(self, state: StateSnapshot) -> float:
        if self._cfg.modulated_by is None:
            return self._cfg.base_weight
        mod = state.get(self._cfg.modulated_by, 0.0)
        return self._cfg.base_weight * (1.0 + self._cfg.modulation_strength * mod)

    def generate_context(
        self, memory: MemoryStore, *, state: StateSnapshot | None = None
    ) -> list[MemoryRecord]:
        del memory, state
        topic = random.choice(self._pool)
        now = datetime.now(UTC)
        return [
            MemoryRecord(
                id="",
                timestamp=now,
                category="topic_pool",
                content=topic,
                importance=0.0,
                last_recall=now,
                recall_count=0,
                decay_rate=0.0,
                emotional_valence=0.0,
                arousal=0.5,
            )
        ]
