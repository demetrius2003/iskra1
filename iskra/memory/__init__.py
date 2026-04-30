"""Memory stores."""

from iskra.core.config import MemoryConfig
from iskra.memory.protocol import MemoryStore
from iskra.memory.sqlite_store import SQLiteMemoryStore


def create_memory_store(config: MemoryConfig) -> MemoryStore:
    if config.backend == "sqlite":
        return SQLiteMemoryStore(config)
    if config.backend == "lance":
        from iskra.memory.lance_store import LanceMemoryStore

        return LanceMemoryStore(config)
    raise ValueError(f"Unknown memory backend: {config.backend}")
