"""Локальное время суток: слоты и импульсы только при смене слота."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iskra.core.config import WorldTimeSensorConfig
    from iskra.core.state_engine import OUStateEngine

logger = logging.getLogger("iskra.sensors.time")

# ТЗ v0.7.0 § время суток (имена слотов)
SLOT_DELTAS: dict[str, dict[str, float]] = {
    "morning": {"curiosity": 0.10, "restlessness": 0.15, "valence": 0.10},
    "midday": {"restlessness": 0.05},
    "evening": {"curiosity": 0.05, "restlessness": -0.10, "valence": 0.05},
    "night": {"curiosity": -0.10, "restlessness": -0.20, "valence": -0.05},
}


def compute_time_slot(local_dt: datetime) -> str:
    h = local_dt.hour
    if 6 <= h < 10:
        return "morning"
    if 12 <= h < 15:
        return "midday"
    if 18 <= h < 22:
        return "evening"
    if h >= 23 or h <= 5:
        return "night"
    return "neutral"


def slot_display_name_ru(slot: str) -> str:
    return {
        "morning": "утро",
        "midday": "полдень",
        "evening": "вечер",
        "night": "ночь",
        "neutral": "день (между окнами)",
    }.get(slot, slot)


def maybe_apply_time_slot(
    *,
    state_engine: OUStateEngine,
    cfg: WorldTimeSensorConfig,
    last_slot: str | None,
    monotonic_now: float,
    last_check_mono: float,
) -> tuple[str | None, float]:
    """Если прошёл интервал и слот сменился — применить дельты. Возвращает (новый last_slot, новый last_check_mono)."""
    if not cfg.enabled:
        return last_slot, last_check_mono

    if monotonic_now - last_check_mono < float(cfg.check_interval_seconds):
        return last_slot, last_check_mono

    slot = compute_time_slot(datetime.now().astimezone())
    new_check = monotonic_now

    if last_slot is None:
        logger.debug("time_sensor: начальный слот %s (импульс не на старте)", slot)
        return slot, new_check

    if slot == last_slot:
        return last_slot, new_check

    deltas = SLOT_DELTAS.get(slot)
    if deltas:
        state_engine.apply_variable_deltas(deltas)
        logger.info(
            "time_sensor: смена слота %s → %s, импульсы %s",
            last_slot,
            slot,
            deltas,
        )
    else:
        logger.info("time_sensor: смена слота %s → %s (нейтрально, без импульсов)", last_slot, slot)

    return slot, new_check
