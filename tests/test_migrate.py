"""SQLite -> Lance migration (optional lancedb)."""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from iskra.core.config import (
    IntentConfig,
    IskraConfig,
    MemoryConfig,
    MemoryV2Config,
    StateConfig,
    StateVariableConfig,
    TriggerConfig,
    TriggerIntervalConfig,
    TriggerTypeConfig,
)
from iskra.memory.embeddings import make_hash_embedder


def test_hash_embedder_dim_and_normalized() -> None:
    e = make_hash_embedder(128)
    v = e("hello")
    assert len(v) == 128
    nrm = sum(x * x for x in v)
    assert math.isclose(nrm, 1.0, rel_tol=1e-5)


def test_migrate_sqlite_dummy_embeddings(tmp_path: Path) -> None:
    pytest.importorskip("lancedb")
    from iskra.migrate import migrate_sqlite_to_lance

    db_sql = tmp_path / "src.db"
    conn = sqlite3.connect(str(db_sql))
    conn.executescript(
        """
        CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            importance REAL NOT NULL,
            last_recall TEXT NOT NULL,
            recall_count INTEGER NOT NULL,
            decay_rate REAL NOT NULL
        );
        INSERT INTO memories VALUES (
            'a1', '2026-01-01T00:00:00+00:00', 'c', 'hello', 0.5,
            '2026-01-01T00:00:00+00:00', 0, 0.01
        );
        """
    )
    conn.commit()
    conn.close()

    ldir = tmp_path / "lance_out"
    state = StateConfig(
        variables={
            "x": StateVariableConfig(initial=0.5, mu=0.5, theta=0.1, sigma=0.1),
        },
        impulses={},
        feedback={},
    )
    trig = TriggerConfig(
        interval=TriggerIntervalConfig(min_seconds=1, max_seconds=10, modulated_by=None),
        types={"t": TriggerTypeConfig(base_weight=1.0)},
        random_topic_pool=[],
    )
    mem = MemoryConfig(
        backend="sqlite",
        settings={"db_path": str(db_sql)},
        v2=MemoryV2Config(enabled=False, db_path=str(ldir)),
    )
    intent = IntentConfig(system_prompt_template="s", user_prompts={"default": "d"})
    cfg = IskraConfig(schema_version=1, state=state, trigger=trig, memory=mem, intent=intent)

    n = migrate_sqlite_to_lance(cfg, dummy_embeddings=True, hash_embedding_dim=32)
    assert n == 1
