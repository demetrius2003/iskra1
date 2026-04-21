"""Main loop smoke test (one tick, isolated paths)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from iskra.core.config import load_config
from iskra.core.main_loop import MainLoop


def test_process_one_tick(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = Path(__file__).parent / "minimal.yaml"
    raw = src.read_text(encoding="utf-8")
    raw = raw.replace("data/test_memory.db", (tmp_path / "mem.db").as_posix())
    raw = raw.replace("data/test_events.jsonl", (tmp_path / "ev.jsonl").as_posix())
    raw = raw.replace("data/test_iskra.pid", (tmp_path / "p.pid").as_posix())
    raw = raw.replace('data_dir: "data"', f'data_dir: "{tmp_path.as_posix()}"')
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(raw, encoding="utf-8")

    cfg = load_config(cfg_path)
    ml = MainLoop(cfg)
    monkeypatch.setattr(ml, "_write_pid_file", lambda: None)
    monkeypatch.setattr(ml, "_remove_pid_file", lambda: None)

    ml.state_engine.apply_impulse("system_startup")
    ml.last_tick_time = time.monotonic() - 1.0
    asyncio.run(ml._process_tick())

    assert ml._thought_count == 1
    evfile = tmp_path / "ev.jsonl"
    assert evfile.is_file()
    line = evfile.read_text(encoding="utf-8").strip().splitlines()[0]
    assert "new_topic" in line
    assert "llm_response" in line or "MOCK" in line
