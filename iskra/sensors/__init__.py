"""Датчики окружения (время, погода, RSS)."""

from iskra.sensors.world_poll import WorldRuntimeState, poll_world_sensors

__all__ = ["WorldRuntimeState", "poll_world_sensors"]
