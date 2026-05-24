"""v0.7.0: время слотами, песочница файлов, лимит sandbox-тегов."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from iskra.core.config import MemoryConfig, MemoryV2Config, SandboxConfig, WorldTimeSensorConfig
from iskra.core.sandbox_tags import apply_sandbox_tags, parse_sandbox_tags
from iskra.memory.sqlite_store import SQLiteMemoryStore
from iskra.sandbox import SandboxManager
from iskra.sandbox.file_ops import SandboxPathError, resolve_under_root
from iskra.sensors.time_sensor import SLOT_DELTAS, compute_time_slot, maybe_apply_time_slot


def test_compute_time_slot_boundaries() -> None:
    assert compute_time_slot(datetime(2026, 4, 25, 6, 0)) == "morning"
    assert compute_time_slot(datetime(2026, 4, 25, 9, 59)) == "morning"
    assert compute_time_slot(datetime(2026, 4, 25, 12, 0)) == "midday"
    assert compute_time_slot(datetime(2026, 4, 25, 18, 0)) == "evening"
    assert compute_time_slot(datetime(2026, 4, 25, 23, 0)) == "night"
    assert compute_time_slot(datetime(2026, 4, 25, 3, 0)) == "night"
    assert compute_time_slot(datetime(2026, 4, 25, 11, 0)) == "neutral"


def test_maybe_apply_time_slot_no_impulse_on_first_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, float]] = []

    class Eng:
        def apply_variable_deltas(self, d: dict[str, float]) -> None:
            calls.append(d)

    monkeypatch.setattr("iskra.sensors.time_sensor.compute_time_slot", lambda _dt: "morning")
    cfg = WorldTimeSensorConfig(enabled=True, check_interval_seconds=10)
    slot, _ = maybe_apply_time_slot(
        state_engine=Eng(),
        cfg=cfg,
        last_slot=None,
        monotonic_now=10.0,
        last_check_mono=0.0,
    )
    assert slot == "morning"
    assert calls == []


def test_maybe_apply_time_slot_impulse_when_slot_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, float]] = []

    class Eng:
        def apply_variable_deltas(self, d: dict[str, float]) -> None:
            calls.append(d)

    seq = iter(["morning", "midday"])

    def fake_slot(_dt: datetime) -> str:
        return next(seq)

    monkeypatch.setattr("iskra.sensors.time_sensor.compute_time_slot", fake_slot)
    cfg = WorldTimeSensorConfig(enabled=True, check_interval_seconds=10)
    eng = Eng()
    slot, chk = maybe_apply_time_slot(
        state_engine=eng,
        cfg=cfg,
        last_slot=None,
        monotonic_now=10.0,
        last_check_mono=0.0,
    )
    assert slot == "morning"
    assert calls == []

    slot2, _ = maybe_apply_time_slot(
        state_engine=eng,
        cfg=cfg,
        last_slot=slot,
        monotonic_now=25.0,
        last_check_mono=chk,
    )
    assert slot2 == "midday"
    assert calls == [SLOT_DELTAS["midday"]]


@pytest.mark.parametrize(
    "filename",
    ["../outside.txt", "..\\secret", "a/../../../etc/passwd"],
)
def test_resolve_under_root_rejects_escape(tmp_path, filename: str) -> None:
    root = tmp_path / "sb"
    root.mkdir()
    with pytest.raises(SandboxPathError):
        resolve_under_root(root, filename)


def _sqlite(tmp_path) -> SQLiteMemoryStore:
    cfg = MemoryConfig(
        backend="sqlite",
        settings={"db_path": str(tmp_path / "sbmem.db")},
        v2=MemoryV2Config(enabled=False),
    )
    return SQLiteMemoryStore(cfg)


def test_apply_sandbox_tags_respects_max_ops(tmp_path) -> None:
    root = tmp_path / "sandbox"
    root.mkdir()
    sb_cfg = SandboxConfig(enabled=True, path=str(root), max_tag_ops_per_tick=2)
    mgr = SandboxManager(sb_cfg)
    store = _sqlite(tmp_path)
    raw = (
        '[WRITE_FILE] filename: "a.txt" content: "1"\n'
        '[WRITE_FILE] filename: "b.txt" content: "2"\n'
        '[WRITE_FILE] filename: "c.txt" content: "3"\n'
    )
    ops = parse_sandbox_tags(raw)
    assert len(ops) == 3

    asyncio.run(
        apply_sandbox_tags(ops, manager=mgr, memory_store=store, max_ops=2)
    )

    assert (root / "a.txt").read_text(encoding="utf-8") == "1"
    assert (root / "b.txt").read_text(encoding="utf-8") == "2"
    assert not (root / "c.txt").is_file()


def test_parse_sandbox_python_block() -> None:
    raw = "[PYTHON_CODE]\nx = 40 + 2\n[/PYTHON_CODE]"
    ops = parse_sandbox_tags(raw)
    assert len(ops) == 1
    assert ops[0].code.strip() == "x = 40 + 2"

