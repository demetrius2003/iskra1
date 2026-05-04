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


def test_self_reflection_tick_skips_trigger_evaluate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """После N успешных тиков следующий тик строит событие self_reflection без evaluate()."""
    src = Path(__file__).parent / "minimal.yaml"
    raw = src.read_text(encoding="utf-8")
    raw = raw.replace("data/test_memory.db", (tmp_path / "mem.db").as_posix())
    raw = raw.replace("data/test_events.jsonl", (tmp_path / "ev.jsonl").as_posix())
    raw = raw.replace("data/test_iskra.pid", (tmp_path / "p.pid").as_posix())
    raw = raw.replace('data_dir: "data"', f'data_dir: "{tmp_path.as_posix()}"')
    raw = raw.replace(
        "decay_every_n_ticks: 100",
        "decay_every_n_ticks: 100\n  self_reflection_every_n_ticks: 1\n  self_reflection_recall_n: 2",
    )
    raw = raw.replace(
        'default: "Think: {{ context }}"',
        'default: "Think: {{ context }}"\n    self_reflection: "SR: {% for m in memories %}{{ m }};{% endfor %}"',
    )
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(raw, encoding="utf-8")

    cfg = load_config(cfg_path)
    ml = MainLoop(cfg)
    monkeypatch.setattr(ml, "_write_pid_file", lambda: None)
    monkeypatch.setattr(ml, "_remove_pid_file", lambda: None)

    ml.state_engine.apply_impulse("system_startup")
    ml.last_tick_time = time.monotonic() - 1.0

    eval_calls: list[str] = []
    real_eval = ml.trigger_engine.evaluate

    def counting_eval(state: dict[str, float]):
        eval_calls.append("eval")
        return real_eval(state)

    ml.trigger_engine.evaluate = counting_eval  # type: ignore[method-assign]

    asyncio.run(ml._process_tick())
    assert eval_calls == ["eval"]
    assert ml._thought_count == 1

    asyncio.run(ml._process_tick())
    assert eval_calls == ["eval"]
    assert ml._thought_count == 2

    lines = (tmp_path / "ev.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert "self_reflection" in lines[-1]


def test_run_dry_run_no_memory_writes(tmp_path: Path) -> None:
    src = Path(__file__).parent / "minimal.yaml"
    raw = src.read_text(encoding="utf-8")
    raw = raw.replace("data/test_memory.db", (tmp_path / "mem.db").as_posix())
    raw = raw.replace("data/test_events.jsonl", (tmp_path / "ev.jsonl").as_posix())
    raw = raw.replace('data_dir: "data"', f'data_dir: "{tmp_path.as_posix()}"')
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(raw, encoding="utf-8")

    cfg = load_config(cfg_path)
    ml = MainLoop(cfg)
    assert ml.memory_store.count() == 0
    asyncio.run(ml.run(dry_run=True))
    assert ml.memory_store.count() == 0
    assert ml._thought_count == 0
