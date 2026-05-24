"""Классификация погоды и конфиг провайдера без сети."""

from __future__ import annotations

from pathlib import Path

from iskra.core.config import load_config, validate_cross_config
from iskra.sensors.weather_sensor import classify_wmo_weather_code, classify_weather


def test_classify_wmo_clear_and_storm() -> None:
    d, s = classify_wmo_weather_code(0)
    assert "ясно" in s
    assert "valence" in d
    d2, s2 = classify_wmo_weather_code(95)
    assert "гроза" in s2
    assert d2.get("arousal", 0) > 0


def test_openweather_mapping_parity_sample() -> None:
    d, s = classify_weather("Clear", 800)
    assert "ясно" in s
    d2, s2 = classify_wmo_weather_code(0)
    assert ("valence" in d) == ("valence" in d2)


def test_validate_cross_open_meteo_without_api_key(tmp_path: Path) -> None:
    src = Path(__file__).parent / "minimal.yaml"
    raw = src.read_text(encoding="utf-8")
    raw = raw.replace("data/test_memory.db", (tmp_path / "mem.db").as_posix())
    raw = raw.replace("data/test_events.jsonl", (tmp_path / "ev.jsonl").as_posix())
    raw = raw.replace("data/test_iskra.pid", (tmp_path / "p.pid").as_posix())
    raw = raw.replace('data_dir: "data"', f'data_dir: "{tmp_path.as_posix()}"')
    raw += """

world:
  weather:
    enabled: true
    provider: open_meteo
    city: "Moscow"
"""
    p = tmp_path / "cfg.yaml"
    p.write_text(raw, encoding="utf-8")
    cfg = load_config(p)
    validate_cross_config(cfg)
    assert cfg.world.weather.provider == "open_meteo"
    assert cfg.world.weather.api_key is None
