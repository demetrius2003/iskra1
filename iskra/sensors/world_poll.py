"""Один проход опроса сенсоров мира (async httpx)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from iskra.core.config import IskraConfig
from iskra.core.state_engine import OUStateEngine
from iskra.memory.protocol import MemoryStore
from iskra.sensors import rss_sensor
from iskra.sensors.time_sensor import compute_time_slot, maybe_apply_time_slot
from iskra.sensors.weather_sensor import fetch_weather_summary
from iskra.sensors.world_context import build_world_context_text

logger = logging.getLogger("iskra.sensors.world_poll")


@dataclass
class WorldRuntimeState:
    """Состояние между тиками (держит MainLoop)."""

    last_slot: str | None = None
    last_time_check_mono: float = 0.0
    last_weather_mono: float | None = None
    last_rss_mono: float | None = None
    weather_line: str = ""
    rss_preview_lines: list[str] = field(default_factory=list)
    rss_dedupe_keys: set[str] = field(default_factory=set)

    def init_rss_dedupe(self, data_dir: str) -> None:
        path = rss_sensor.dedupe_file_path(data_dir)
        self.rss_dedupe_keys = rss_sensor.load_dedupe_keys(path)


async def poll_world_sensors(
    *,
    cfg: IskraConfig,
    state_engine: OUStateEngine,
    memory_store: MemoryStore,
    runtime: WorldRuntimeState,
    monotonic_now: float,
    client: httpx.AsyncClient,
) -> str:
    """Обновляет время/погоду/RSS по интервалам; возвращает текст для промпта."""
    wc = cfg.world

    runtime.last_slot, runtime.last_time_check_mono = maybe_apply_time_slot(
        state_engine=state_engine,
        cfg=wc.time_sensor,
        last_slot=runtime.last_slot,
        monotonic_now=monotonic_now,
        last_check_mono=runtime.last_time_check_mono,
    )

    slot_name = compute_time_slot(datetime.now().astimezone())

    w_cfg = wc.weather
    weather_key_ok = w_cfg.provider == "open_meteo" or bool(
        w_cfg.api_key and str(w_cfg.api_key).strip()
    )
    weather_due = (
        w_cfg.enabled
        and weather_key_ok
        and (
            runtime.last_weather_mono is None
            or (monotonic_now - runtime.last_weather_mono) >= float(w_cfg.update_interval_seconds)
        )
    )
    if weather_due:
        runtime.last_weather_mono = monotonic_now
        res = await fetch_weather_summary(
            provider=w_cfg.provider,
            api_key=(w_cfg.api_key or "").strip(),
            city=w_cfg.city,
            lat=w_cfg.lat,
            lon=w_cfg.lon,
            client=client,
        )
        if res:
            deltas, summary = res
            if deltas:
                state_engine.apply_variable_deltas(deltas)
            runtime.weather_line = summary
            logger.info("weather_sensor: %s", summary)
        else:
            runtime.weather_line = "погода недоступна"
    elif not w_cfg.enabled:
        runtime.weather_line = ""

    r_cfg = wc.rss
    rss_due = r_cfg.enabled and (
        runtime.last_rss_mono is None
        or (monotonic_now - runtime.last_rss_mono) >= float(r_cfg.update_interval_seconds)
    )
    if rss_due:
        runtime.last_rss_mono = monotonic_now
        try:
            lines = await rss_sensor.refresh_rss_feeds(
                cfg=r_cfg,
                data_dir=cfg.general.data_dir,
                memory_store=memory_store,
                dedupe_keys=runtime.rss_dedupe_keys,
                client=client,
            )
            runtime.rss_preview_lines = list(lines) if lines else []
        except Exception as e:
            logger.warning("rss refresh failed: %s", e)

    return build_world_context_text(
        slot_name=slot_name,
        weather_line=runtime.weather_line,
        rss_lines=runtime.rss_preview_lines,
        max_chars=wc.context_max_chars,
    )
