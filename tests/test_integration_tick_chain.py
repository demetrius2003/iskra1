"""Цепочка одного тика: эмоции в store и recall со state."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from iskra.core.config import load_config
from iskra.core.main_loop import MainLoop


def test_one_tick_memory_emotion_and_recall_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    assert ml.memory_store.count() >= 1
    snap = ml.state_engine.snapshot()
    assert "valence" in snap and "arousal" in snap
    recalled = ml.memory_store.recall(category=None, n=5, state=snap)
    assert isinstance(recalled, list)
def test_one_tick_lance_hash_embeddings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("lancedb")
    src = Path(__file__).parent / "minimal.yaml"
    raw = src.read_text(encoding="utf-8")
    raw = raw.replace(
        'memory:\n  backend: sqlite\n  settings:\n    db_path: "data/test_memory.db"\n  initial_memories_file: null',
        (
            "memory:\n"
            "  backend: lance\n"
            "  settings:\n"
            f'    db_path: "{(tmp_path / "mem_legacy.db").as_posix()}"\n'
            "  recall:\n"
            "    default_n: 3\n"
            "    importance_weight: 0.7\n"
            "    recency_weight: 0.3\n"
            "    selection: stochastic\n"
            "    emotion_enabled: true\n"
            "  decay:\n"
            "    enabled: true\n"
            "    base_rate: 0.01\n"
            "    min_importance: 0.01\n"
            "    recall_protection: 1.5\n"
            "  initial_memories_file: null\n"
            "  v2:\n"
            "    enabled: true\n"
            f'    db_path: "{(tmp_path / "mv2").as_posix()}"\n'
            "    embeddings_backend: hash\n"
            "    hash_embedding_dim: 64\n"
            "    graph_enabled: false\n"
        ),
    )
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

    assert ml.memory_store.count() >= 1
    snap = ml.state_engine.snapshot()
    recalled = ml.memory_store.recall(category=None, n=5, state=snap)
    assert isinstance(recalled, list)
