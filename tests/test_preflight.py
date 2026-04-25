"""Предстартовая самодиагностика."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from iskra.core.config import load_config
from iskra.core.main_loop import MainLoop
from iskra.core.preflight import PreflightError, preflight


def _minimal_cfg_path(tmp_path: Path) -> Path:
    src = Path(__file__).parent / "minimal.yaml"
    raw = src.read_text(encoding="utf-8")
    raw = raw.replace("data/test_memory.db", (tmp_path / "mem.db").as_posix())
    raw = raw.replace("data/test_events.jsonl", (tmp_path / "ev.jsonl").as_posix())
    raw = raw.replace("data/test_iskra.pid", (tmp_path / "p.pid").as_posix())
    raw = raw.replace('data_dir: "data"', f'data_dir: "{tmp_path.as_posix()}"')
    p = tmp_path / "cfg.yaml"
    p.write_text(raw, encoding="utf-8")
    return p


def test_preflight_mock_ok(tmp_path: Path) -> None:
    cfg = load_config(_minimal_cfg_path(tmp_path))
    assert cfg.llm.adapter == "mock"
    ml = MainLoop(cfg)
    asyncio.run(preflight(ml))


def test_preflight_ollama_unreachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = Path(__file__).parent / "minimal_ollama.yaml"
    raw = src.read_text(encoding="utf-8")
    raw = raw.replace("MEM_DB_PLACEHOLDER", (tmp_path / "mem.db").as_posix())
    raw = raw.replace("EVLOG_PLACEHOLDER", (tmp_path / "ev.jsonl").as_posix())
    raw = raw.replace("DATA_DIR_PLACEHOLDER", tmp_path.as_posix())
    raw = raw.replace("PID_PLACEHOLDER", (tmp_path / "p.pid").as_posix())
    p = tmp_path / "ollama.yaml"
    p.write_text(raw, encoding="utf-8")
    cfg = load_config(p)
    ml = MainLoop(cfg)
    monkeypatch.setattr(ml.llm_adapter, "is_available", lambda: False)
    with pytest.raises(PreflightError, match="Ollama"):
        asyncio.run(preflight(ml))
