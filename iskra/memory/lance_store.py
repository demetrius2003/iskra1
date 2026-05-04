"""LanceDB + embeddings memory store (расширенный режим)."""

from __future__ import annotations

import logging
import random
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.compute as pc

from iskra.core.config import MemoryConfig
from iskra.memory.embeddings import embedding_dim, make_embedder, make_hash_embedder
from iskra.memory.recall_scoring import recall_emotion_bonus_from_vals
from iskra.models import MemoryRecord

logger = logging.getLogger("iskra.memory.lance")


def _sql_id_literal(memory_id: str) -> str:
    return memory_id.replace("'", "''")


def _lance_table_names(db: object) -> list[str]:
    """Имена таблиц в каталоге LanceDB.

    В новых версиях ``list_tables()`` возвращает объект с полем ``tables``, а не ``list[str]``.
    """
    if hasattr(db, "list_tables"):
        raw = db.list_tables()
    elif hasattr(db, "table_names"):
        raw = db.table_names()
    else:
        return []
    items = getattr(raw, "tables", raw)
    if items is None:
        return []
    if isinstance(items, str):
        return [items]
    out: list[str] = []
    for x in items:
        if isinstance(x, str):
            out.append(x)
        else:
            name = getattr(x, "name", None)
            out.append(str(name) if name is not None else str(x))
    return out


def _record_from_table(at: pa.Table, idx: int) -> MemoryRecord:
    names = set(at.column_names)

    def col_float(col_name: str, default: float) -> float:
        if col_name not in names:
            return default
        return float(at.column(col_name)[idx].as_py())

    ev = col_float("emotional_valence", 0.0)
    ar = col_float("arousal", 0.5)
    return MemoryRecord(
        id=at.column("id")[idx].as_py(),
        timestamp=datetime.fromisoformat(at.column("timestamp")[idx].as_py()),
        category=at.column("category")[idx].as_py(),
        content=at.column("content")[idx].as_py(),
        importance=float(at.column("importance")[idx].as_py()),
        last_recall=datetime.fromisoformat(at.column("last_recall")[idx].as_py()),
        recall_count=int(at.column("recall_count")[idx].as_py()),
        decay_rate=float(at.column("decay_rate")[idx].as_py()),
        emotional_valence=ev,
        arousal=ar,
    )


class LanceMemoryStore:
    """Векторный recall при непустом ``context``; иначе стохастика по всем строкам."""

    _TABLE = "memories"

    def __init__(
        self,
        config: MemoryConfig,
        embedder: Callable[[str], list[float]] | None = None,
    ) -> None:
        try:
            import lancedb
        except ImportError as e:
            raise ImportError(
                "backend lance требует lancedb. Установите: pip install iskra[memory]"
            ) from e

        self._config = config
        self._lancedb = lancedb
        self._db_path = Path(config.v2.db_path)
        self._db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self._db_path))
        if embedder is not None:
            self._embedder = embedder
        elif config.v2.embeddings_backend == "hash":
            self._embedder = make_hash_embedder(config.v2.hash_embedding_dim)
        else:
            self._embedder = make_embedder(config.v2.embeddings_model)
        self._dim = embedding_dim(self._embedder)
        self._lock = threading.Lock()
        self._ensure_table()
        self._graph = self._open_graph()

    @property
    def memory_graph_sidecar(self) -> object | None:
        """Граф ассоциаций или ``None`` (выключен / нет NetworkX)."""
        return self._graph

    def preflight_embedding_probe(self) -> int:
        """Один вызов эмбеддера для предстартовой проверки модели и размерности."""
        vec = self._embedder("iskra preflight")
        if len(vec) != self._dim:
            raise RuntimeError(
                f"длина вектора эмбеддинга {len(vec)} != ожидаемой {self._dim}"
            )
        return self._dim

    def _open_graph(self) -> object | None:
        if not self._config.v2.graph_enabled:
            return None
        try:
            from iskra.memory.memory_graph import MemoryGraphSidecar
        except ImportError:
            logger.warning("memory graph: networkx недоступен, граф отключён")
            return None
        gp = self._config.v2.graph_edges_path
        path = Path(gp) if gp else self._db_path / "memory_graph.json"
        v2 = self._config.v2
        return MemoryGraphSidecar(
            path,
            link_increment=v2.graph_link_increment,
            max_edge_weight=v2.graph_max_edge_weight,
        )

    def _ensure_table(self) -> None:
        with self._lock:
            if self._TABLE in _lance_table_names(self._db):
                self._table = self._db.open_table(self._TABLE)
                self._migrate_emotion_columns_if_needed()
                return
            vec = [0.0] * self._dim
            now = datetime.now(UTC).isoformat()
            bootstrap = {
                "id": "__iskra_bootstrap__",
                "timestamp": now,
                "category": "_system",
                "content": "",
                "importance": 0.0,
                "last_recall": now,
                "recall_count": 0,
                "decay_rate": self._config.decay.base_rate,
                "emotional_valence": 0.0,
                "arousal": 0.5,
                "vector": vec,
            }
            try:
                t = self._db.create_table(self._TABLE, data=[bootstrap])
            except ValueError as e:
                if "already exists" in str(e).lower():
                    self._table = self._db.open_table(self._TABLE)
                    return
                raise
            t.delete("id = '__iskra_bootstrap__'")
            self._table = t

    def _migrate_emotion_columns_if_needed(self) -> None:
        """Таблицы до появления эмоций в схеме — без колонок; Lance не делает это сам."""
        try:
            schema = self._table.schema
        except Exception as e:
            logger.warning("lance migrate: не прочитать schema: %s", e)
            return
        names = {f.name for f in schema}
        transforms: dict[str, str] = {}
        if "emotional_valence" not in names:
            transforms["emotional_valence"] = "0.0"
        if "arousal" not in names:
            transforms["arousal"] = "0.5"
        if not transforms:
            return
        add_fn = getattr(self._table, "add_columns", None)
        if add_fn is None:
            logger.warning(
                "lance migrate: у таблицы нет колонок %s; обновите lancedb или пересоздайте каталог memory.v2.db_path",
                ", ".join(transforms.keys()),
            )
            return
        try:
            add_fn(transforms)
            logger.info(
                "lance migrate: добавлены колонки %s к таблице %s",
                ", ".join(transforms.keys()),
                self._TABLE,
            )
        except Exception as e:
            logger.warning("lance migrate add_columns failed: %s", e)

    def _row_dict(
        self,
        mid: str,
        now: str,
        category: str,
        content: str,
        imp: float,
        base_rate: float,
        vector: list[float],
        *,
        emotional_valence: float = 0.0,
        arousal: float = 0.5,
    ) -> dict:
        return {
            "id": mid,
            "timestamp": now,
            "category": category,
            "content": content,
            "importance": imp,
            "last_recall": now,
            "recall_count": 0,
            "decay_rate": base_rate,
            "emotional_valence": emotional_valence,
            "arousal": arousal,
            "vector": vector,
        }

    def _record_by_id(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            try:
                at = self._table.to_arrow()
            except Exception as e:
                logger.warning("record_by_id: %s", e)
                return None
        filt = at.filter(pc.equal(at.column("id"), pa.scalar(memory_id)))
        if filt.num_rows == 0:
            return None
        return _record_from_table(filt, 0)

    def _expand_with_graph_neighbors(
        self,
        seeds: list[MemoryRecord],
        category: str | None,
    ) -> list[MemoryRecord]:
        extra_n = self._config.v2.recall_graph_extra
        if extra_n <= 0 or not self._graph:
            return seeds
        seen: set[str] = {r.id for r in seeds}
        out_extra: list[MemoryRecord] = []
        for seed in seeds:
            if len(out_extra) >= extra_n:
                break
            for nb in self._graph.neighbors_by_weight(seed.id):
                if nb in seen:
                    continue
                rec = self._record_by_id(nb)
                if rec is None:
                    continue
                if category is not None and rec.category != category:
                    continue
                out_extra.append(rec)
                seen.add(nb)
                if len(out_extra) >= extra_n:
                    break
        return seeds + out_extra

    def link_memories(self, source_id: str, target_ids: list[str]) -> None:
        if not self._graph:
            logger.warning("link_memories: граф отключён или недоступен")
            return
        with self._lock:
            try:
                at = self._table.to_arrow()
            except Exception as e:
                logger.warning("link_memories: %s", e)
                return
        ids = set(at.column("id").to_pylist())
        if source_id not in ids:
            logger.warning("link_memories: неизвестный source id=%s", source_id)
            return
        ok = [t for t in target_ids if t in ids and t != source_id]
        if not ok:
            return
        self._graph.link(source_id, ok)

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
            vec = self._embedder(content)
        except Exception as e:
            logger.warning("embedding failed: %s", e)
            return ""
        row = self._row_dict(mid, now, category, content, imp, base_rate, vec, emotional_valence=ev, arousal=ar)
        try:
            with self._lock:
                self._table.add([row])
        except Exception as e:
            logger.warning("lance store failed: %s", e)
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
        n = max(1, n)
        with self._lock:
            try:
                at = self._table.to_arrow()
            except Exception as e:
                logger.warning("lance recall read failed: %s", e)
                return []

        if at.num_rows == 0:
            return []

        if category is not None:
            at = at.filter(pc.equal(at.column("category"), pa.scalar(category)))

        if at.num_rows == 0:
            return []

        now = datetime.now(UTC)
        iw = self._config.recall.importance_weight
        rw = self._config.recall.recency_weight
        selection = self._config.recall.selection

        if context and context.strip():
            try:
                qvec = self._embedder(context)
            except Exception as e:
                logger.warning("recall embedding failed: %s", e)
                qvec = None
            if qvec is not None:
                with self._lock:
                    try:
                        res = self._table.search(qvec).limit(
                            min(at.num_rows, max(n * 8, 32))
                        ).to_arrow()
                    except Exception as e:
                        logger.warning("lance vector search failed: %s", e)
                        res = None
                if res is not None and res.num_rows > 0:
                    if category is not None:
                        res = res.filter(pc.equal(res.column("category"), pa.scalar(category)))
                    if res.num_rows > 0:
                        names = [res.schema.field(i).name for i in range(res.num_columns)]
                        if "_distance" in names:
                            dists = res.column("_distance").to_pylist()
                        else:
                            dists = [0.0] * res.num_rows
                        scored: list[tuple[float, int]] = []
                        for i in range(res.num_rows):
                            imp = float(res.column("importance")[i].as_py())
                            lr = datetime.fromisoformat(res.column("last_recall")[i].as_py())
                            hours_since = (now - lr).total_seconds() / 3600.0
                            recency = 1.0 / (1.0 + hours_since)
                            dist = float(dists[i]) if i < len(dists) else 0.0
                            sem = 1.0 / (1.0 + dist)
                            r_ev = _record_from_table(res, i).emotional_valence
                            score = (
                                imp * iw
                                + recency * rw
                                + sem * 0.15
                                + recall_emotion_bonus_from_vals(
                                    r_ev, state, self._config.recall
                                )
                            )
                            scored.append((score, i))
                        if selection == "top_n":
                            scored.sort(key=lambda x: -x[0])
                            pick_idx = [i for _, i in scored[:n]]
                        else:
                            weights = [max(s, 1e-9) for s, _ in scored]
                            pick_idx = [
                                scored[j][1]
                                for j in random.choices(
                                    range(len(scored)), weights=weights, k=min(n, len(scored))
                                )
                            ]
                        picked_recs = [_record_from_table(res, i) for i in pick_idx]
                        picked_recs = self._expand_with_graph_neighbors(picked_recs, category)
                        return self._bump_recall(picked_recs)

        indices = list(range(at.num_rows))
        scored = []
        for i in indices:
            row = _record_from_table(at, i)
            lr = row.last_recall
            hours_since = (now - lr).total_seconds() / 3600.0
            recency = 1.0 / (1.0 + hours_since)
            score = (
                row.importance * iw
                + recency * rw
                + recall_emotion_bonus_from_vals(
                    row.emotional_valence, state, self._config.recall
                )
            )
            scored.append((score, i))

        if selection == "top_n":
            scored.sort(key=lambda x: -x[0])
            picked = [i for _, i in scored[:n]]
        else:
            weights = [max(s, 1e-9) for s, _ in scored]
            picked = random.choices([i for _, i in scored], weights=weights, k=min(n, len(scored)))

        records = [_record_from_table(at, i) for i in picked]
        records = self._expand_with_graph_neighbors(records, category)
        return self._bump_recall(records)

    def _bump_recall(self, records: list[MemoryRecord]) -> list[MemoryRecord]:
        now_iso = datetime.now(UTC).isoformat()
        out: list[MemoryRecord] = []
        with self._lock:
            for rec in records:
                try:
                    at = self._table.to_arrow()
                    idx = pc.equal(at.column("id"), pa.scalar(rec.id))
                    filt = at.filter(idx)
                    if filt.num_rows == 0:
                        continue
                    row = filt.slice(0, 1)
                    mr_src = _record_from_table(row, 0)
                    mid = mr_src.id
                    self._table.delete(f"id = '{_sql_id_literal(str(mid))}'")
                    vec = row.column("vector")[0].as_py()
                    rc = mr_src.recall_count + 1
                    payload = {
                        "id": mid,
                        "timestamp": mr_src.timestamp.isoformat(),
                        "category": mr_src.category,
                        "content": mr_src.content,
                        "importance": mr_src.importance,
                        "last_recall": now_iso,
                        "recall_count": rc,
                        "decay_rate": mr_src.decay_rate,
                        "emotional_valence": mr_src.emotional_valence,
                        "arousal": mr_src.arousal,
                        "vector": vec,
                    }
                    self._table.add([payload])
                    out.append(
                        MemoryRecord(
                            id=mid,
                            timestamp=mr_src.timestamp,
                            category=mr_src.category,
                            content=mr_src.content,
                            importance=mr_src.importance,
                            last_recall=datetime.fromisoformat(now_iso),
                            recall_count=rc,
                            decay_rate=mr_src.decay_rate,
                            emotional_valence=mr_src.emotional_valence,
                            arousal=mr_src.arousal,
                        )
                    )
                except Exception as e:
                    logger.warning("bump_recall failed for %s: %s", rec.id, e)
        return out

    def decay(self) -> None:
        if not self._config.decay.enabled:
            return
        now = datetime.now(UTC)
        min_imp = self._config.decay.min_importance
        prot = self._config.decay.recall_protection
        with self._lock:
            try:
                at = self._table.to_arrow()
            except Exception as e:
                logger.warning("lance decay read failed: %s", e)
                return
            for i in range(at.num_rows):
                row = _record_from_table(at, i)
                last_recall = row.last_recall
                hours_since = max(0.0, (now - last_recall).total_seconds() / 3600.0)
                protection = 1.0 / (1.0 + row.recall_count / prot)
                effective_rate = row.decay_rate * protection
                new_imp = row.importance * (1.0 - effective_rate * hours_since / 24.0)
                new_imp = max(min_imp, new_imp)
                if abs(new_imp - row.importance) < 1e-9:
                    continue
                try:
                    vec = at.column("vector")[i].as_py()
                    mid = row.id
                    self._table.delete(f"id = '{_sql_id_literal(mid)}'")
                    self._table.add(
                        [
                            {
                                "id": mid,
                                "timestamp": row.timestamp.isoformat(),
                                "category": row.category,
                                "content": row.content,
                                "importance": new_imp,
                                "last_recall": row.last_recall.isoformat(),
                                "recall_count": row.recall_count,
                                "decay_rate": row.decay_rate,
                                "emotional_valence": row.emotional_valence,
                                "arousal": row.arousal,
                                "vector": vec,
                            }
                        ]
                    )
                except Exception as e:
                    logger.warning("lance decay row %s: %s", row.id, e)

    def count(self) -> int:
        try:
            with self._lock:
                return int(self._table.count_rows())
        except Exception:
            return 0

    def put_raw(self, payload: dict) -> None:
        """Атомарно заменить строку по ``id`` (миграция; payload включает vector)."""
        mid = str(payload["id"])
        lit = _sql_id_literal(mid)
        with self._lock:
            try:
                self._table.delete(f"id = '{lit}'")
            except Exception:
                pass
            self._table.add([payload])

    def update_importance(self, memory_id: str, importance: float) -> bool:
        imp = max(0.0, min(1.0, importance))
        lit = _sql_id_literal(memory_id)
        with self._lock:
            try:
                at = self._table.to_arrow()
                filt = at.filter(pc.equal(at.column("id"), pa.scalar(memory_id)))
                if filt.num_rows == 0:
                    return False
                row = filt.slice(0, 1)
                mr = _record_from_table(row, 0)
                self._table.delete(f"id = '{lit}'")
                vec = row.column("vector")[0].as_py()
                self._table.add(
                    [
                        {
                            "id": memory_id,
                            "timestamp": mr.timestamp.isoformat(),
                            "category": mr.category,
                            "content": mr.content,
                            "importance": imp,
                            "last_recall": mr.last_recall.isoformat(),
                            "recall_count": mr.recall_count,
                            "decay_rate": mr.decay_rate,
                            "emotional_valence": mr.emotional_valence,
                            "arousal": mr.arousal,
                            "vector": vec,
                        }
                    ]
                )
                return True
            except Exception as e:
                logger.warning("lance update_importance failed: %s", e)
                return False

    def delete_memory(self, memory_id: str) -> bool:
        lit = _sql_id_literal(memory_id)
        with self._lock:
            try:
                at = self._table.to_arrow()
                if memory_id not in set(at.column("id").to_pylist()):
                    return False
                self._table.delete(f"id = '{lit}'")
            except Exception as e:
                logger.warning("delete_memory failed: %s", e)
                return False
        if self._graph:
            self._graph.remove_node(memory_id)
        return True

    def consolidate(self) -> None:
        """Слить записи с одинаковым текстом (после ``strip``), оставив максимальный ``importance``."""
        try:
            with self._lock:
                at = self._table.to_arrow()
        except Exception as e:
            logger.warning("consolidate: read failed %s", e)
            return
        if at.num_rows <= 1:
            return
        rows = [_record_from_table(at, i) for i in range(at.num_rows)]
        groups: dict[str, list[MemoryRecord]] = {}
        for rec in rows:
            groups.setdefault(rec.content.strip(), []).append(rec)
        to_drop: list[str] = []
        for _key, recs in groups.items():
            if len(recs) < 2:
                continue
            recs.sort(key=lambda r: (-r.importance, r.timestamp.isoformat()))
            keeper = recs[0]
            for dup in recs[1:]:
                to_drop.append(dup.id)
                if self._graph:
                    self._graph.repoint(dup.id, keeper.id)
        if not to_drop:
            return
        with self._lock:
            for did in to_drop:
                try:
                    self._table.delete(f"id = '{_sql_id_literal(did)}'")
                except Exception as e:
                    logger.warning("consolidate delete %s: %s", did, e)
        logger.info("consolidate: удалено %d дублей по содержимому", len(to_drop))
