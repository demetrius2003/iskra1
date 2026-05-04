"""Дополнительные члены score при recall (эмоциональный контекст состояния)."""

from __future__ import annotations

from iskra.core.config import MemoryRecallConfig
from iskra.models import MemoryRecord, StateSnapshot


def recall_emotion_bonus_from_vals(
    emotional_valence: float,
    state: StateSnapshot | None,
    cfg: MemoryRecallConfig,
) -> float:
    if state is None or not cfg.emotion_enabled:
        return 0.0
    sv = float(state.get("valence", 0.0))
    sn = float(state.get("nostalgia", 0.0))
    ev = emotional_valence
    bonus = cfg.emotion_valence_alignment_weight * sv * ev
    bonus += cfg.emotion_nostalgia_positive_weight * sn * max(0.0, ev)
    return bonus


def recall_emotion_bonus(
    record: MemoryRecord,
    state: StateSnapshot | None,
    cfg: MemoryRecallConfig,
) -> float:
    return recall_emotion_bonus_from_vals(record.emotional_valence, state, cfg)
