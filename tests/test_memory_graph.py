"""Персистентный граф памяти (networkx)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import networkx  # noqa: F401
except ImportError:
    pytest.skip("networkx not installed", allow_module_level=True)

from iskra.memory.memory_graph import MemoryGraphSidecar


def _edge_pairs(edges: list) -> set[frozenset[str]]:
    out: set[frozenset[str]] = set()
    for e in edges:
        if isinstance(e, (list, tuple)) and len(e) >= 2:
            out.add(frozenset((str(e[0]), str(e[1]))))
    return out


def test_graph_save_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "g.json"
    g1 = MemoryGraphSidecar(p)
    g1.link("a", ["b", "c"])
    del g1
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert _edge_pairs(raw["edges"]) >= {frozenset(("a", "b")), frozenset(("a", "c"))}
    g2 = MemoryGraphSidecar(p)
    assert set(g2.neighbors("a")) >= {"b", "c"}


def test_graph_repeated_link_strengthens(tmp_path: Path) -> None:
    p = tmp_path / "gw.json"
    g = MemoryGraphSidecar(p, link_increment=2.0, max_edge_weight=100.0)
    g.link("x", ["y"])
    g.link("x", ["y"])
    assert g.neighbors_by_weight("x") == ["y"]
    raw = json.loads(p.read_text(encoding="utf-8"))
    trip = [e for e in raw["edges"] if set(e[:2]) == {"x", "y"}][0]
    assert len(trip) == 3 and float(trip[2]) == pytest.approx(4.0)


def test_graph_weighted_json_load(tmp_path: Path) -> None:
    p = tmp_path / "gj.json"
    p.write_text(
        json.dumps({"edges": [["p", "q", 7.5]]}),
        encoding="utf-8",
    )
    g = MemoryGraphSidecar(p)
    assert g.neighbors_by_weight("p") == ["q"]


def test_neighbors_by_weight_order(tmp_path: Path) -> None:
    p = tmp_path / "ord.json"
    g = MemoryGraphSidecar(p, link_increment=1.0, max_edge_weight=100.0)
    g.link("s", ["weak"])
    g.link("s", ["strong"])
    g.link("s", ["strong"])
    g.link("s", ["strong"])
    assert g.neighbors_by_weight("s") == ["strong", "weak"]
