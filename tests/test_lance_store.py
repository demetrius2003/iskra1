"""Lance store (optional ``lancedb``)."""

from __future__ import annotations

import pytest

try:
    import lancedb  # noqa: F401
except ImportError:
    pytest.skip("lancedb not installed (pip install iskra[memory])", allow_module_level=True)

from iskra.core.config import MemoryConfig, MemoryRecallConfig, MemoryV2Config
from iskra.memory.lance_store import LanceMemoryStore, _lance_table_names


def test_lance_table_names_list_tables_response_object() -> None:
    class ListTablesResp:
        tables = ["memories", "other"]

    class FakeDB:
        def list_tables(self):
            return ListTablesResp()

    assert _lance_table_names(FakeDB()) == ["memories", "other"]


def _fake_embedder(dim: int = 4):
    def embed(text: str) -> list[float]:
        out = [0.0] * dim
        raw = text.encode("utf-8")
        for k in range(min(dim, len(raw))):
            out[k] = raw[k] / 255.0
        return out

    embed.__iskra_embedding_dim__ = dim  # type: ignore[attr-defined]
    return embed


def test_lance_store_hash_backend_no_torch(tmp_path) -> None:
    cfg = MemoryConfig(
        backend="lance",
        settings={},
        v2=MemoryV2Config(
            enabled=True,
            db_path=str(tmp_path / "lance_hash"),
            embeddings_backend="hash",
            hash_embedding_dim=16,
        ),
    )
    store = LanceMemoryStore(cfg)
    mid = store.store("c", "hello", 0.5)
    assert mid
    got = store.recall(category="c", n=1)
    assert len(got) == 1
    assert got[0].content == "hello"


def test_lance_store_roundtrip(tmp_path) -> None:
    cfg = MemoryConfig(
        backend="lance",
        settings={"db_path": str(tmp_path / "legacy.sqlite")},
        v2=MemoryV2Config(enabled=True, db_path=str(tmp_path / "lance_dir")),
    )
    store = LanceMemoryStore(cfg, embedder=_fake_embedder(4))
    mid = store.store("c1", "hello lance", 0.6)
    assert mid
    assert store.count() == 1
    got = store.recall(category="c1", n=2)
    assert len(got) == 1
    assert got[0].content == "hello lance"


def test_lance_link_and_graph_file(tmp_path) -> None:
    gpath = tmp_path / "mem_graph.json"
    cfg = MemoryConfig(
        backend="lance",
        v2=MemoryV2Config(
            enabled=True,
            db_path=str(tmp_path / "ld"),
            graph_edges_path=str(gpath),
        ),
    )
    store = LanceMemoryStore(cfg, embedder=_fake_embedder(4))
    a = store.store("c", "row a", 0.5)
    b = store.store("c", "row b", 0.5)
    assert a and b
    store.link_memories(a, [b])
    assert gpath.is_file()
    from iskra.memory.memory_graph import MemoryGraphSidecar

    g = MemoryGraphSidecar(gpath)
    assert b in g.neighbors(a)


def test_lance_recall_includes_graph_neighbor(tmp_path) -> None:
    gpath = tmp_path / "mem_graph2.json"
    cfg = MemoryConfig(
        backend="lance",
        v2=MemoryV2Config(
            enabled=True,
            db_path=str(tmp_path / "ld2"),
            graph_edges_path=str(gpath),
            recall_graph_extra=1,
        ),
        recall=MemoryRecallConfig(selection="top_n"),
    )
    store = LanceMemoryStore(cfg, embedder=_fake_embedder(8))
    hi = store.store("c", "important seed", 0.95)
    lo = store.store("c", "less important", 0.1)
    store.link_memories(hi, [lo])
    got = store.recall(category="c", n=1, context=None)
    ids = {r.id for r in got}
    assert hi in ids
    assert lo in ids


def test_lance_recall_prefers_stronger_graph_edge(tmp_path) -> None:
    """recall_graph_extra подмешивает соседа с большим весом ребра первым."""
    gpath = tmp_path / "mem_graph3.json"
    cfg = MemoryConfig(
        backend="lance",
        v2=MemoryV2Config(
            enabled=True,
            db_path=str(tmp_path / "ld3"),
            graph_edges_path=str(gpath),
            recall_graph_extra=1,
            graph_link_increment=1.0,
        ),
        recall=MemoryRecallConfig(selection="top_n"),
    )
    store = LanceMemoryStore(cfg, embedder=_fake_embedder(8))
    seed = store.store("c", "seed content", 0.95)
    weak = store.store("c", "weak neighbor", 0.05)
    strong = store.store("c", "strong neighbor", 0.05)
    store.link_memories(seed, [weak])
    store.link_memories(seed, [strong])
    store.link_memories(seed, [strong])
    store.link_memories(seed, [strong])
    got = store.recall(category="c", n=1, context=None)
    contents = [r.content for r in got]
    assert "seed content" in contents
    assert "strong neighbor" in contents
    assert "weak neighbor" not in contents


def test_lance_consolidate_duplicate_content(tmp_path) -> None:
    cfg = MemoryConfig(
        backend="lance",
        v2=MemoryV2Config(enabled=True, db_path=str(tmp_path / "ldc"), graph_enabled=False),
    )
    store = LanceMemoryStore(cfg, embedder=_fake_embedder(4))
    store.store("c", "dup text", 0.3)
    store.store("c", "dup text", 0.9)
    assert store.count() == 2
    store.consolidate()
    assert store.count() == 1
    got = store.recall(category="c", n=2)
    assert len(got) == 1
    assert got[0].importance == pytest.approx(0.9)


def test_lance_migrate_emotion_columns(tmp_path) -> None:
    """Таблица без emotional_valence/arousal получает колонки при открытии (БД до ~0.5)."""
    import lancedb

    db_path = tmp_path / "legacy_emotion"
    db_path.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(db_path))
    dim = 4
    db.create_table(
        LanceMemoryStore._TABLE,
        [
            {
                "id": "old1",
                "timestamp": "2020-01-01T00:00:00+00:00",
                "category": "c",
                "content": "legacy row",
                "importance": 0.5,
                "last_recall": "2020-01-01T00:00:00+00:00",
                "recall_count": 0,
                "decay_rate": 0.01,
                "vector": [0.1] * dim,
            },
        ],
    )
    cfg = MemoryConfig(
        backend="lance",
        v2=MemoryV2Config(enabled=True, db_path=str(db_path)),
    )
    store = LanceMemoryStore(cfg, embedder=_fake_embedder(dim))
    at = store._table.to_arrow()
    assert "emotional_valence" in at.column_names
    assert "arousal" in at.column_names
    mid = store.store("c", "after migrate", 0.7, emotional_valence=0.2, arousal=0.6)
    assert mid


def test_lance_vector_recall_with_context(tmp_path) -> None:
    """При непустом ``context`` используется векторный поиск (без проверки ранжирования)."""
    cfg = MemoryConfig(
        backend="lance",
        v2=MemoryV2Config(enabled=True, db_path=str(tmp_path / "v2")),
    )
    store = LanceMemoryStore(cfg, embedder=_fake_embedder(32))
    store.store("t", "single memory for vector path", 0.5)
    got = store.recall(category="t", n=1, context="vector query")
    assert len(got) == 1
    assert got[0].content == "single memory for vector path"
