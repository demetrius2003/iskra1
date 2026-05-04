"""Interval and stochastic trigger selection."""

from __future__ import annotations

import logging
import random

from iskra.core.config import TriggerConfig
from iskra.memory.protocol import MemoryStore
from iskra.models import SparkEvent, StateSnapshot

logger = logging.getLogger("iskra.core.trigger")


class DefaultTriggerEngine:
    def __init__(
        self,
        config: TriggerConfig,
        trigger_types: list,
        memory_store: MemoryStore,
        tick_jitter: float,
    ) -> None:
        self._cfg = config
        self._types = list(trigger_types)
        self._memory = memory_store
        self._tick_jitter = tick_jitter

    def next_interval(self, state: StateSnapshot) -> float:
        interval_cfg = self._cfg.interval
        min_s = float(interval_cfg.min_seconds)
        max_s = float(interval_cfg.max_seconds)
        mod_key = interval_cfg.modulated_by
        if mod_key is None or mod_key not in state:
            modulator = 0.5
        else:
            modulator = state[mod_key]
        base = max_s - (max_s - min_s) * modulator
        jitter = self._tick_jitter
        jitter_factor = 1.0 + random.uniform(-jitter, jitter)
        return max(1.0, base * jitter_factor)

    def evaluate(self, state_before: StateSnapshot) -> SparkEvent | None:
        if not self._types:
            logger.warning("no trigger types registered")
            return None

        weights: list[float] = []
        for t in self._types:
            try:
                w = t.compute_weight(state_before)
                weights.append(max(w, 1e-9))
            except Exception as e:
                logger.warning("compute_weight failed for %s: %s", getattr(t, "name", t), e)
                weights.append(1e-9)

        chosen = random.choices(self._types, weights=weights, k=1)[0]
        name = chosen.name

        try:
            mem_ctx = chosen.generate_context(self._memory, state=state_before)
        except Exception as e:
            logger.warning("generate_context failed for %s: %s", name, e)
            mem_ctx = []

        from datetime import UTC, datetime
        from uuid import uuid4

        return SparkEvent(
            id=str(uuid4()),
            trigger_type=name,
            state_snapshot=dict(state_before),
            memory_context=mem_ctx,
            timestamp=datetime.now(UTC),
            metadata={},
        )
