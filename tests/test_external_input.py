"""Внешний текст из файла (general.external_input_file)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from iskra.core.config import IntentConfig, IskraConfig, load_config
from iskra.core.main_loop import MainLoop


def _intent_with_external() -> IntentConfig:
    return IntentConfig(
        system_prompt_template="STATE {{ external_input }}",
        user_prompts={
            "new_topic": "{{ context }} | внешнее: {{ external_input }}",
            "default": "d {{ external_input }}",
        },
        max_response_tokens=500,
    )


def _cfg(tmp_path: Path, ext_path: Path | None) -> IskraConfig:
    src = Path(__file__).parent / "minimal.yaml"
    raw = src.read_text(encoding="utf-8")
    raw = raw.replace("data/test_memory.db", (tmp_path / "mem.db").as_posix())
    raw = raw.replace("data/test_events.jsonl", (tmp_path / "ev.jsonl").as_posix())
    raw = raw.replace("data/test_iskra.pid", (tmp_path / "p.pid").as_posix())
    raw = raw.replace('data_dir: "data"', f'data_dir: "{tmp_path.as_posix()}"')
    p = tmp_path / "c.yaml"
    p.write_text(raw, encoding="utf-8")
    cfg = load_config(p)
    cfg = cfg.model_copy(update={"intent": _intent_with_external()})
    if ext_path is not None:
        g = cfg.general.model_copy(
            update={
                "external_input_file": str(ext_path),
                "external_input_clear_after_use": True,
            }
        )
        return cfg.model_copy(update={"general": g})
    return cfg


def test_external_input_in_prompts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    incoming = tmp_path / "in.txt"
    incoming.write_text("Сообщение с Марса: проверь антенну.\n", encoding="utf-8")
    cfg = _cfg(tmp_path, incoming)
    ml = MainLoop(cfg)
    monkeypatch.setattr(ml, "_write_pid_file", lambda: None)
    monkeypatch.setattr(ml, "_remove_pid_file", lambda: None)

    ml.state_engine.apply_impulse("system_startup")
    ml.last_tick_time = time.monotonic() - 1.0
    asyncio.run(ml._process_tick())

    line = (tmp_path / "ev.jsonl").read_text(encoding="utf-8")
    assert "Марса" in line
    assert "проверь антенну" in line
    # после успешного тика файл очищен
    assert incoming.read_text(encoding="utf-8").strip() == ""


def test_no_file_mars_not_in_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Без пути к файлу внешнего ввода — в промптах пустой external_input, без «Марс» и т.д."""
    cfg = _cfg(tmp_path, None)
    ml = MainLoop(cfg)
    monkeypatch.setattr(ml, "_write_pid_file", lambda: None)
    monkeypatch.setattr(ml, "_remove_pid_file", lambda: None)
    ml.state_engine.apply_impulse("system_startup")
    ml.last_tick_time = time.monotonic() - 1.0
    asyncio.run(ml._process_tick())
    line = (tmp_path / "ev.jsonl").read_text(encoding="utf-8")
    assert "Марса" not in line
    assert "проверь антенну" not in line
