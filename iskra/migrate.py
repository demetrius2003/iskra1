"""Однократная миграция SQLite → Lance (см. docs/CONFIG_SCHEMA.md)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from iskra.core.config import IskraConfig, load_config
from iskra.memory.embeddings import make_embedder, make_hash_embedder
from iskra.memory.lance_store import LanceMemoryStore

logger = logging.getLogger("iskra.migrate")


def migrate_sqlite_to_lance(
    config: IskraConfig,
    *,
    dummy_embeddings: bool = False,
    hash_embedding_dim: int = 384,
) -> int:
    """Прочитать SQLite ``memory.settings.db_path``, записать в ``memory.v2.db_path``. Исходный файл не удаляется."""
    sqlite_rel = config.memory.settings.get("db_path", "data/memory.db")
    sqlite_path = Path(sqlite_rel)
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite не найден: {sqlite_path}")

    mem = config.memory.model_copy(deep=True)
    mem.backend = "lance"
    mem.v2.enabled = True

    if dummy_embeddings:
        logger.warning(
            "migrate: используются --dummy-embeddings (хеш), без sentence-transformers. "
            "Векторный recall по смыслу работать не будет; позже перенесите данные с нормальной средой или той же dim."
        )
        embedder = make_hash_embedder(hash_embedding_dim)
    elif mem.v2.embeddings_backend == "hash":
        logger.info(
            "migrate: memory.v2.embeddings_backend=hash (как при py -m iskra)"
        )
        embedder = make_hash_embedder(mem.v2.hash_embedding_dim)
    else:
        embedder = make_embedder(mem.v2.embeddings_model)
    lance = LanceMemoryStore(mem, embedder=embedder)

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM memories").fetchall()
    finally:
        conn.close()

    n = 0
    for row in rows:
        content = str(row["content"])
        if not content.strip():
            continue
        vec = embedder(content)
        payload = {
            "id": str(row["id"]),
            "timestamp": str(row["timestamp"]),
            "category": str(row["category"]),
            "content": content,
            "importance": float(row["importance"]),
            "last_recall": str(row["last_recall"]),
            "recall_count": int(row["recall_count"]),
            "decay_rate": float(row["decay_rate"]),
            "vector": vec,
        }
        lance.put_raw(payload)
        n += 1
        if n % 50 == 0:
            logger.info("migrate: перенесено %d записей", n)

    logger.info("migrate: готово, всего %d записей → %s", n, mem.v2.db_path)
    return n


def run_migrate(
    config_path: str | Path,
    *,
    dummy_embeddings: bool = False,
    hash_embedding_dim: int = 384,
) -> int:
    if hash_embedding_dim < 8 or hash_embedding_dim > 4096:
        raise ValueError("hash_embedding_dim must be between 8 and 4096")
    cfg = load_config(config_path)
    return migrate_sqlite_to_lance(
        cfg,
        dummy_embeddings=dummy_embeddings,
        hash_embedding_dim=hash_embedding_dim,
    )
