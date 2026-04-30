"""Персистентный граф связей между записями памяти (NetworkX, JSON рядом с Lance)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("iskra.memory.graph")


class MemoryGraphSidecar:
    """Неориентированный граф UUID → UUID.

    Файл JSON: ``{"edges": [...]}``. Элемент — ``[a, b]`` (вес 1) или ``[a, b, w]`` (вес ``w > 0``).
    Повторный ``link`` на то же ребро **усиливает** вес (до ``max_edge_weight``).
    """

    def __init__(
        self,
        path: Path,
        *,
        link_increment: float = 1.0,
        max_edge_weight: float = 1000.0,
    ) -> None:
        try:
            import networkx as nx_module
        except ImportError as e:
            raise ImportError(
                "Граф памяти требует networkx. Установите: pip install iskra[memory]"
            ) from e

        self._nx = nx_module
        self._path = path
        self._link_inc = float(link_increment)
        self._max_w = float(max_edge_weight)
        self._g = nx_module.Graph()
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("memory graph: не прочитать %s: %s", self._path, e)
            return
        for edge in raw.get("edges", []):
            if isinstance(edge, (list, tuple)) and len(edge) >= 2:
                a, b = str(edge[0]), str(edge[1])
                if a == b:
                    continue
                w = float(edge[2]) if len(edge) >= 3 else 1.0
                if w <= 0:
                    continue
                w = min(self._max_w, w)
                if self._g.has_edge(a, b):
                    w0 = float(self._g[a][b].get("weight", 1.0))
                    self._g[a][b]["weight"] = min(self._max_w, w0 + w)
                else:
                    self._g.add_edge(a, b, weight=w)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        edges: list[list[object]] = []
        for u, v, data in self._g.edges(data=True):
            w = float(data.get("weight", 1.0))
            if abs(w - 1.0) < 1e-9:
                edges.append([u, v])
            else:
                edges.append([u, v, w])
        self._path.write_text(json.dumps({"edges": edges}, indent=2), encoding="utf-8")

    def _add_or_strengthen(self, a: str, b: str, delta: float) -> None:
        d = min(self._max_w, max(delta, 1e-9))
        if self._g.has_edge(a, b):
            w0 = float(self._g[a][b].get("weight", 1.0))
            self._g[a][b]["weight"] = min(self._max_w, w0 + d)
        else:
            self._g.add_edge(a, b, weight=d)

    def link(self, source_id: str, target_ids: list[str]) -> None:
        for t in target_ids:
            if t and t != source_id:
                self._add_or_strengthen(source_id, t, self._link_inc)
        self.save()

    def neighbors(self, node_id: str) -> list[str]:
        if node_id not in self._g:
            return []
        return list(self._g.neighbors(node_id))

    def neighbors_by_weight(self, node_id: str) -> list[str]:
        """Соседи по убыванию веса ребра (для recall_graph_extra)."""
        if node_id not in self._g:
            return []
        pairs: list[tuple[str, float]] = []
        for nb in self._g.neighbors(node_id):
            w = float(self._g[node_id][nb].get("weight", 1.0))
            pairs.append((nb, w))
        pairs.sort(key=lambda x: (-x[1], x[0]))
        return [nb for nb, _ in pairs]

    def has_node(self, node_id: str) -> bool:
        return self._g.has_node(node_id)

    def remove_node(self, node_id: str) -> None:
        if node_id in self._g:
            self._g.remove_node(node_id)
            self.save()

    def repoint(self, old_id: str, new_id: str) -> None:
        """Переназначить все рёбра с ``old_id`` на ``new_id``, узел ``old_id`` удалить."""
        if old_id == new_id or old_id not in self._g:
            return
        # Ребро old_id—new_id (если было) отбрасываем: узлы сливаются в new_id.
        for nb in list(self._g.neighbors(old_id)):
            if nb == new_id:
                continue
            w_old = float(self._g[old_id][nb].get("weight", 1.0))
            if self._g.has_edge(new_id, nb):
                w_ex = float(self._g[new_id][nb].get("weight", 1.0))
                self._g[new_id][nb]["weight"] = min(self._max_w, w_old + w_ex)
            else:
                self._g.add_edge(new_id, nb, weight=min(self._max_w, w_old))
        self._g.remove_node(old_id)
        self.save()
