"""SQLite-backed memory store."""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from iskra.core.config import MemoryConfig
from iskra.memory.recall_scoring import recall_emotion_bonus_from_vals
from iskra.models import MemoryRecord

logger = logging.getLogger("iskra.memory")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5,
    last_recall TEXT NOT NULL,
    recall_count INTEGER NOT NULL DEFAULT 0,
    decay_rate REAL NOT NULL DEFAULT 0.01,
    emotional_valence REAL NOT NULL DEFAULT 0.0,
    arousal REAL NOT NULL DEFAULT 0.5
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
"""


def _sqlite_ev_ar(row: sqlite3.Row) -> tuple[float, float]:
    keys = row.keys()
    ev = float(row["emotional_valence"]) if "emotional_valence" in keys else 0.0
    ar = float(row["arousal"]) if "arousal" in keys else 0.5
    return ev, ar


def _migrate_sqlite_emotion_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
    if "emotional_valence" not in cols:
        conn.execute(
            "ALTER TABLE memories ADD COLUMN emotional_valence REAL NOT NULL DEFAULT 0.0"
        )
    if "arousal" not in cols:
        conn.execute("ALTER TABLE memories ADD COLUMN arousal REAL NOT NULL DEFAULT 0.5")


class SQLiteMemoryStore:
    def __init__(self, config: MemoryConfig) -> None:
        self._config = config
        db_path = Path(config.settings.get("db_path", "data/memory.db"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            _migrate_sqlite_emotion_columns(self._conn)
            self._conn.commit()

    def store(
        self,
        category: str,
        content: str,
        importance: float,
        *,
        emotional_valence: float = 0.0,
        arousal: float = 0.5,
    ) -> str:
        if not content.strip():
            logger.warning("store skipped: empty content")
            return ""
        mid = str(uuid4())
        now = datetime.now(UTC).isoformat()
        imp = max(0.0, min(1.0, importance))
        ev = max(-1.0, min(1.0, float(emotional_valence)))
        ar = max(0.0, min(1.0, float(arousal)))
        base_rate = self._config.decay.base_rate
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT INTO memories
                    (id, timestamp, category, content, importance, last_recall, recall_count, decay_rate,
                     emotional_valence, arousal)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
                    (mid, now, category, content, imp, now, base_rate, ev, ar),
                )
                self._conn.commit()
        except sqlite3.Error as e:
            logger.warning("memory store failed: %s", e)
            return ""
        return mid

    def recall(
        self,
        category: str | None = None,
        n: int = 3,
        context: str | None = None,
        *,
        state: dict[str, float] | None = None,
    ) -> list[MemoryRecord]:
        del context  # семантический recall в SQLite не используется
        n = max(1, n)
        try:
            with self._lock:
                if category is None:
                    rows = self._conn.execute("SELECT * FROM memories").fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT * FROM memories WHERE category = ?", (category,)
                    ).fetchall()
        except sqlite3.Error as e:
            logger.warning("memory recall failed: %s", e)
            return []

        if not rows:
            return []

        now = datetime.now(UTC)
        iw = self._config.recall.importance_weight
        rw = self._config.recall.recency_weight
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            last_recall = datetime.fromisoformat(row["last_recall"])
            hours_since = (now - last_recall).total_seconds() / 3600.0
            recency = 1.0 / (1.0 + hours_since)
            ev, _ar = _sqlite_ev_ar(row)
            score = (
                row["importance"] * iw
                + recency * rw
                + recall_emotion_bonus_from_vals(ev, state, self._config.recall)
            )
            scored.append((score, row))

        selection = self._config.recall.selection
        import random

        if selection == "top_n":
            scored.sort(key=lambda x: -x[0])
            picked_rows = [r for _, r in scored[:n]]
        else:
            weights = [max(s, 1e-9) for s, _ in scored]
            picked_rows = random.choices([r for _, r in scored], weights=weights, k=min(n, len(scored)))

        records: list[MemoryRecord] = []
        now_iso = now.isoformat()
        with self._lock:
            for row in picked_rows:
                self._conn.execute(
                    """UPDATE memories SET last_recall = ?, recall_count = recall_count + 1
                    WHERE id = ?""",
                    (now_iso, row["id"]),
                )
                records.append(self._row_to_record(row))
            self._conn.commit()
        return records

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        ev, ar = _sqlite_ev_ar(row)
        return MemoryRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            category=row["category"],
            content=row["content"],
            importance=row["importance"],
            last_recall=datetime.fromisoformat(row["last_recall"]),
            recall_count=row["recall_count"],
            decay_rate=row["decay_rate"],
            emotional_valence=ev,
            arousal=ar,
        )

    def decay(self) -> None:
        if not self._config.decay.enabled:
            return
        now = datetime.now(UTC)
        min_imp = self._config.decay.min_importance
        prot = self._config.decay.recall_protection
        try:
            with self._lock:
                rows = self._conn.execute("SELECT * FROM memories").fetchall()
                for row in rows:
                    last_recall = datetime.fromisoformat(row["last_recall"])
                    hours_since = max(0.0, (now - last_recall).total_seconds() / 3600.0)
                    protection = 1.0 / (1.0 + row["recall_count"] / prot)
                    effective_rate = row["decay_rate"] * protection
                    new_imp = row["importance"] * (1.0 - effective_rate * hours_since / 24.0)
                    new_imp = max(min_imp, new_imp)
                    self._conn.execute(
                        "UPDATE memories SET importance = ? WHERE id = ?",
                        (new_imp, row["id"]),
                    )
                self._conn.commit()
        except sqlite3.Error as e:
            logger.warning("memory decay failed: %s", e)

    def count(self) -> int:
        try:
            with self._lock:
                row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
                return int(row["c"]) if row else 0
        except sqlite3.Error:
            return 0

    def update_importance(self, memory_id: str, importance: float) -> bool:
        imp = max(0.0, min(1.0, importance))
        try:
            with self._lock:
                cur = self._conn.execute(
                    "UPDATE memories SET importance = ? WHERE id = ?",
                    (imp, memory_id),
                )
                self._conn.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.warning("memory update_importance failed: %s", e)
            return False

    def link_memories(self, source_id: str, target_ids: list[str]) -> None:
        del source_id, target_ids
        logger.debug("link_memories: SQLite backend — граф не поддерживается")

    def delete_memory(self, memory_id: str) -> bool:
        try:
            with self._lock:
                cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                self._conn.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.warning("memory delete failed: %s", e)
            return False

    def consolidate(self) -> None:
        """SQLite: заглушка."""
        return
