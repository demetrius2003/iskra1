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


def test_preflight_missing_initial_memories_file(tmp_path: Path) -> None:
    missing = tmp_path / "no_seed.yaml"
    p = _minimal_cfg_path(tmp_path)
    raw = p.read_text(encoding="utf-8")
    raw = raw.replace("initial_memories_file: null", f'initial_memories_file: "{missing.as_posix()}"')
    p.write_text(raw, encoding="utf-8")
    cfg = load_config(p)
    ml = MainLoop(cfg)
    with pytest.raises(PreflightError, match="initial_memories_file"):
        asyncio.run(preflight(ml))


def test_preflight_external_input_path_ok(tmp_path: Path) -> None:
    incoming = tmp_path / "in.txt"
    incoming.write_text("hi", encoding="utf-8")
    p = _minimal_cfg_path(tmp_path)
    raw = p.read_text(encoding="utf-8")
    raw = raw.replace(
        "general:\n  decay_every_n_ticks:",
        f'general:\n  external_input_file: "{incoming.as_posix()}"\n  decay_every_n_ticks:',
    )
    p.write_text(raw, encoding="utf-8")
    cfg = load_config(p)
    ml = MainLoop(cfg)
    asyncio.run(preflight(ml))


def test_preflight_lance_probes_embeddings_and_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("lancedb")
    pytest.importorskip("networkx")
    from iskra.core import main_loop as main_loop_mod
    from iskra.memory.lance_store import LanceMemoryStore

    def fake_embed(text: str) -> list[float]:
        del text
        return [0.0] * 8

    fake_embed.__iskra_embedding_dim__ = 8  # type: ignore[attr-defined]

    real_create = main_loop_mod.create_memory_store

    def create_store(mem_cfg):
        if mem_cfg.backend == "lance":
            return LanceMemoryStore(mem_cfg, embedder=fake_embed)
        return real_create(mem_cfg)

    monkeypatch.setattr(main_loop_mod, "create_memory_store", create_store)

    src = Path(__file__).parent / "minimal.yaml"
    raw = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    ldb = (tmp_path / "lance_pf").as_posix()
    gj = (tmp_path / "pf_graph.json").as_posix()
    raw = raw.replace(
        "memory:\n  backend: sqlite\n  settings:\n    db_path: \"data/test_memory.db\"\n  initial_memories_file: null",
        f'memory:\n  backend: lance\n  settings: {{}}\n  initial_memories_file: null\n  v2:\n    enabled: true\n    db_path: "{ldb}"\n    graph_enabled: true\n    graph_edges_path: "{gj}"',
    )
    raw = raw.replace("data/test_events.jsonl", (tmp_path / "ev.jsonl").as_posix())
    raw = raw.replace("data/test_iskra.pid", (tmp_path / "p.pid").as_posix())
    raw = raw.replace('data_dir: "data"', f'data_dir: "{tmp_path.as_posix()}"')
    cfg_path = tmp_path / "lance_preflight.yaml"
    cfg_path.write_text(raw, encoding="utf-8")
    cfg = load_config(cfg_path)
    ml = MainLoop(cfg)
    asyncio.run(preflight(ml))


def test_preflight_lance_graph_missing_sidecar_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("lancedb")
    pytest.importorskip("networkx")
    from iskra.core import main_loop as main_loop_mod
    from iskra.memory.lance_store import LanceMemoryStore

    def fake_embed(text: str) -> list[float]:
        del text
        return [0.0] * 8

    fake_embed.__iskra_embedding_dim__ = 8  # type: ignore[attr-defined]

    real_create = main_loop_mod.create_memory_store

    def create_store(mem_cfg):
        if mem_cfg.backend == "lance":
            return LanceMemoryStore(mem_cfg, embedder=fake_embed)
        return real_create(mem_cfg)

    monkeypatch.setattr(main_loop_mod, "create_memory_store", create_store)

    src = Path(__file__).parent / "minimal.yaml"
    raw = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    ldb = (tmp_path / "lance_pf2").as_posix()
    gj = (tmp_path / "pf_graph2.json").as_posix()
    raw = raw.replace(
        "memory:\n  backend: sqlite\n  settings:\n    db_path: \"data/test_memory.db\"\n  initial_memories_file: null",
        f'memory:\n  backend: lance\n  settings: {{}}\n  initial_memories_file: null\n  v2:\n    enabled: true\n    db_path: "{ldb}"\n    graph_enabled: true\n    graph_edges_path: "{gj}"',
    )
    raw = raw.replace("data/test_events.jsonl", (tmp_path / "ev.jsonl").as_posix())
    raw = raw.replace("data/test_iskra.pid", (tmp_path / "p.pid").as_posix())
    raw = raw.replace('data_dir: "data"', f'data_dir: "{tmp_path.as_posix()}"')
    cfg_path = tmp_path / "lance_pf2.yaml"
    cfg_path.write_text(raw, encoding="utf-8")
    cfg = load_config(cfg_path)
    ml = MainLoop(cfg)
    ml.memory_store._graph = None  # type: ignore[attr-defined]
    with pytest.raises(PreflightError, match="граф"):
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
