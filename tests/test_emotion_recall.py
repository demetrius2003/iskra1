"""Recall scoring vs emotional_valence."""

from __future__ import annotations

from pathlib import Path

import pytest

from iskra.core.config import MemoryConfig, MemoryRecallConfig, MemoryV2Config
from iskra.memory.sqlite_store import SQLiteMemoryStore


def test_sqlite_recall_valence_alignment(tmp_path: Path) -> None:
    cfg = MemoryConfig(
        backend="sqlite",
        settings={"db_path": str(tmp_path / "emo.db")},
        recall=MemoryRecallConfig(
            selection="top_n",
            emotion_enabled=True,
            emotion_valence_alignment_weight=0.6,
            emotion_nostalgia_positive_weight=0.0,
        ),
        v2=MemoryV2Config(enabled=False),
    )
    store = SQLiteMemoryStore(cfg)
    store.store("t", "dark memory", 0.5, emotional_valence=-0.95, arousal=0.4)
    store.store("t", "bright memory", 0.5, emotional_valence=0.95, arousal=0.6)
    state = {"valence": 0.98, "nostalgia": 0.0}
    picked = store.recall(category=None, n=1, state=state)
    assert len(picked) == 1
    assert picked[0].content == "bright memory"


@pytest.mark.parametrize(
    ("nostalgia", "expected_content"),
    [(0.95, "sweet"), (0.0, "bitter")],
)
def test_sqlite_recall_nostalgia_positive_pull(tmp_path: Path, nostalgia: float, expected_content: str) -> None:
    cfg = MemoryConfig(
        backend="sqlite",
        settings={"db_path": str(tmp_path / f"n_{nostalgia}.db")},
        recall=MemoryRecallConfig(
            selection="top_n",
            emotion_enabled=True,
            emotion_valence_alignment_weight=0.0,
            emotion_nostalgia_positive_weight=0.8,
        ),
        v2=MemoryV2Config(enabled=False),
    )
    store = SQLiteMemoryStore(cfg)
    store.store("t", "bitter", 0.55, emotional_valence=-0.5, arousal=0.5)
    store.store("t", "sweet", 0.45, emotional_valence=0.8, arousal=0.5)
    state = {"valence": 0.0, "nostalgia": nostalgia}
    picked = store.recall(category=None, n=1, state=state)
    assert picked[0].content == expected_content
