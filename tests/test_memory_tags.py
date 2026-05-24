"""Парсинг тегов памяти."""

import pytest

from iskra.core.config import AgencyConfig, MemoryConfig, MemoryV2Config
from iskra.core.memory_tags import (
    MemorySaveTag,
    MemoryUpdateTag,
    apply_memory_tags,
    parse_memory_tags,
    parse_web_search_queries,
    strip_tag_lines,
)
from iskra.memory.sqlite_store import SQLiteMemoryStore


def _sqlite_mem(tmp_path, name: str) -> SQLiteMemoryStore:
    cfg = MemoryConfig(
        backend="sqlite",
        settings={"db_path": str(tmp_path / name)},
        v2=MemoryV2Config(enabled=False),
    )
    return SQLiteMemoryStore(cfg)


def test_parse_request_update_save() -> None:
    text = """intro line
[MEMORY_REQUEST] query: "hello, world"
[MEMORY_UPDATE] id: 550e8400-e29b-41d4-a716-446655440000, importance: 0.9
[MEMORY_SAVE] content: "note", importance: 0.5
tail"""
    ops = parse_memory_tags(text)
    assert len(ops) == 3
    assert ops[0].query == "hello, world"
    assert isinstance(ops[1], MemoryUpdateTag)
    assert ops[1].memory_id == "550e8400-e29b-41d4-a716-446655440000"
    assert ops[1].importance == 0.9
    assert ops[1].link_add == ()
    assert isinstance(ops[2], MemorySaveTag)
    assert ops[2].content == "note"
    assert ops[2].importance == 0.5


def test_parse_update_links() -> None:
    u1 = "550e8400-e29b-41d4-a716-446655440000"
    u2 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    ops = parse_memory_tags(f"[MEMORY_UPDATE] id: {u1}, links: {u2}")
    assert len(ops) == 1
    assert ops[0].link_add == (u2,)


def test_parse_memory_delete() -> None:
    u = "550e8400-e29b-41d4-a716-446655440000"
    ops = parse_memory_tags(f"[MEMORY_DELETE] id: {u}")
    assert len(ops) == 1
    assert ops[0].memory_id == u


def test_agency_l2_importance_floor(tmp_path) -> None:
    store = _sqlite_mem(tmp_path, "mf.db")
    mid = store.store("t", "x", 0.9)
    ops = parse_memory_tags(f"[MEMORY_UPDATE] id: {mid}, importance: 0.02")
    apply_memory_tags(
        store,
        ops,
        AgencyConfig(level=2, l2_importance_floor=0.25),
        default_category="t",
    )
    rec = store.recall(category="t", n=1)
    assert rec[0].importance == pytest.approx(0.25)


def test_agency_l3_delete(tmp_path) -> None:
    store = _sqlite_mem(tmp_path, "md.db")
    mid = store.store("t", "bye", 0.5)
    ops = parse_memory_tags(f"[MEMORY_DELETE] id: {mid}")
    apply_memory_tags(store, ops, AgencyConfig(level=2), default_category="t")
    assert store.count() == 1
    apply_memory_tags(store, ops, AgencyConfig(level=3), default_category="t")
    assert store.count() == 0


def test_strip_tag_lines_removes_sandbox_markup() -> None:
    raw = (
        "intro\n"
        '[WRITE_FILE] filename: "x.txt" content: "y"\n'
        "[PYTHON_CODE]\nprint(1)\n[/PYTHON_CODE]\n"
        "visible\n"
        "[LIST_FILES]\n"
        "tail"
    )
    out = strip_tag_lines(raw).strip()
    assert "WRITE_FILE" not in out
    assert "PYTHON_CODE" not in out
    assert "LIST_FILES" not in out
    assert "visible" in out


def test_strip_tag_lines() -> None:
    raw = "a\n[MEMORY_SAVE] content: \"x\"\nb"
    assert strip_tag_lines(raw).strip() == "a\nb"


def test_strip_web_search_lines() -> None:
    raw = "a\n[WEB_SEARCH] x\nb"
    assert strip_tag_lines(raw).strip() == "a\nb"


def test_parse_web_search_queries_plain_and_fields() -> None:
    text = """intro
[WEB_SEARCH] парадоксы Кантора
[WEB_SEARCH] query: "неполнота"
tail"""
    assert parse_web_search_queries(text) == ["парадоксы Кантора", "неполнота"]


def test_parse_web_search_queries_russian_key() -> None:
    assert parse_web_search_queries('[WEB_SEARCH] запрос: "Гёдель"') == ["Гёдель"]


def test_parse_web_search_queries_issledovanie_key() -> None:
    assert parse_web_search_queries(
        '[WEB_SEARCH] исследование: "современные открытия майя"'
    ) == ["современные открытия майя"]


def test_apply_tags_agency_l0(tmp_path) -> None:
    store = _sqlite_mem(tmp_path, "m.db")
    store.store("t", "base", 0.5)
    ops = parse_memory_tags('[MEMORY_SAVE] content: "new", importance: 0.8')
    apply_memory_tags(store, ops, AgencyConfig(level=0), default_category="x")
    assert store.count() == 1


def test_apply_tags_agency_l1_save(tmp_path) -> None:
    store = _sqlite_mem(tmp_path, "m2.db")
    ops = parse_memory_tags('[MEMORY_SAVE] content: "new", importance: 0.8')
    apply_memory_tags(store, ops, AgencyConfig(level=1), default_category="tagged")
    assert store.count() == 0


def test_apply_tags_agency_l2_save(tmp_path) -> None:
    store = _sqlite_mem(tmp_path, "m3.db")
    ops = parse_memory_tags('[MEMORY_SAVE] content: "new", importance: 0.8')
    apply_memory_tags(store, ops, AgencyConfig(level=2), default_category="tagged")
    assert store.count() == 1
    rec = store.recall(category="tagged", n=1)
    assert rec[0].content == "new"
