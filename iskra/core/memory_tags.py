"""Парсинг и исполнение тегов памяти и веб-поиска в тексте LLM / входящего файла (см. docs/CONFIG_SCHEMA.md)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from uuid import UUID

from iskra.core.config import AgencyConfig
from iskra.memory.protocol import MemoryStore

logger = logging.getLogger("iskra.memory_tags")

_TAG_LINE = re.compile(
    r"^\[(MEMORY_REQUEST|MEMORY_UPDATE|MEMORY_SAVE|MEMORY_DELETE)\]\s*(.*)\s*$",
    re.IGNORECASE,
)

_WEB_SEARCH_LINE = re.compile(r"^\[WEB_SEARCH\]\s*(.*)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class MemoryRequestTag:
    query: str


@dataclass(frozen=True)
class MemoryUpdateTag:
    memory_id: str
    importance: float | None = None
    link_add: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemorySaveTag:
    content: str
    importance: float | None


@dataclass(frozen=True)
class MemoryDeleteTag:
    memory_id: str


MemoryTagOp = MemoryRequestTag | MemoryUpdateTag | MemorySaveTag | MemoryDeleteTag


def _split_fields(segment: str) -> list[tuple[str, str]]:
    """Разбор ``key: value`` с учётом кавычек в значениях."""
    segment = segment.strip()
    if not segment:
        return []
    out: list[tuple[str, str]] = []
    i = 0
    n = len(segment)
    while i < n:
        while i < n and segment[i] in " \t":
            i += 1
        if i >= n:
            break
        colon = segment.find(":", i)
        if colon < 0:
            break
        key = segment[i:colon].strip()
        j = colon + 1
        while j < n and segment[j] in " \t":
            j += 1
        if j >= n:
            out.append((key, ""))
            break
        if segment[j] == '"':
            j += 1
            buf: list[str] = []
            while j < n:
                c = segment[j]
                if c == "\\" and j + 1 < n:
                    buf.append(segment[j + 1])
                    j += 2
                    continue
                if c == '"':
                    j += 1
                    break
                buf.append(c)
                j += 1
            val = "".join(buf)
            out.append((key, val))
            while j < n and segment[j] in " \t":
                j += 1
            if j < n and segment[j] == ",":
                j += 1
            i = j
            continue
        buf2: list[str] = []
        while j < n and segment[j] != ",":
            buf2.append(segment[j])
            j += 1
        raw = "".join(buf2).strip()
        out.append((key, raw))
        if j < n and segment[j] == ",":
            j += 1
        i = j
    return out


def _parse_uuid(s: str) -> str | None:
    s = s.strip().strip('"')
    try:
        return str(UUID(s))
    except ValueError:
        return None


def _parse_float(s: str) -> float | None:
    try:
        return float(s.strip())
    except ValueError:
        return None


def parse_line(line: str) -> MemoryTagOp | None:
    m = _TAG_LINE.match(line.strip())
    if not m:
        return None
    kind = m.group(1).upper()
    fields = {k: v for k, v in _split_fields(m.group(2))}
    if kind == "MEMORY_REQUEST":
        q = fields.get("query")
        if q is None:
            logger.warning("MEMORY_REQUEST without query")
            return None
        return MemoryRequestTag(query=q)
    if kind == "MEMORY_UPDATE":
        mid = fields.get("id")
        if not mid:
            logger.warning("MEMORY_UPDATE without id")
            return None
        uid = _parse_uuid(mid)
        if uid is None:
            logger.warning("MEMORY_UPDATE invalid id: %s", mid)
            return None
        imp = fields.get("importance")
        imp_f = _parse_float(imp) if imp is not None else None
        link_add: list[str] = []
        link_raw = fields.get("links")
        if link_raw:
            for part in link_raw.split(","):
                u = _parse_uuid(part)
                if u:
                    link_add.append(u)
        return MemoryUpdateTag(memory_id=uid, importance=imp_f, link_add=tuple(link_add))
    if kind == "MEMORY_SAVE":
        content = fields.get("content")
        if not content:
            logger.warning("MEMORY_SAVE without content")
            return None
        imp = fields.get("importance")
        imp_f = _parse_float(imp) if imp is not None else None
        return MemorySaveTag(content=content, importance=imp_f)
    if kind == "MEMORY_DELETE":
        mid = fields.get("id")
        if not mid:
            logger.warning("MEMORY_DELETE without id")
            return None
        uid = _parse_uuid(mid)
        if uid is None:
            logger.warning("MEMORY_DELETE invalid id: %s", mid)
            return None
        return MemoryDeleteTag(memory_id=uid)
    return None


def parse_memory_tags(text: str) -> list[MemoryTagOp]:
    ops: list[MemoryTagOp] = []
    for line in text.splitlines():
        op = parse_line(line)
        if op is not None:
            ops.append(op)
    return ops


def strip_tag_lines(text: str) -> str:
    lines_out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if _TAG_LINE.match(s) or _WEB_SEARCH_LINE.match(s):
            continue
        lines_out.append(line)
    return "\n".join(lines_out)


def parse_web_search_queries(text: str) -> list[str]:
    """Строки ``[WEB_SEARCH] …``: полный хвост или поля ``query:`` / ``запрос:`` / ``исследование:``."""
    out: list[str] = []
    for line in text.splitlines():
        m = _WEB_SEARCH_LINE.match(line.strip())
        if not m:
            continue
        rest = (m.group(1) or "").strip()
        if not rest:
            continue
        fields = _split_fields(rest)
        fld = {k.strip().lower(): v for k, v in fields}
        q = fld.get("query") or fld.get("запрос") or fld.get("исследование")
        if q:
            out.append(q.strip())
        else:
            out.append(rest)
    return out


def apply_memory_tags(
    store: MemoryStore,
    ops: list[MemoryTagOp],
    agency: AgencyConfig,
    *,
    default_category: str,
    recall_n: int = 5,
) -> None:
    """Исполнить теги: L0 — только REQUEST; L1 — только предложения SAVE/UPDATE в лог (ядро не мутирует память); L2 — SAVE/UPDATE/links + пол ``importance`` не ниже ``l2_importance_floor``; L3 — + ``MEMORY_DELETE``."""
    for op in ops:
        if isinstance(op, MemoryRequestTag):
            recalled = store.recall(category=None, n=recall_n, context=op.query, state=None)
            logger.info(
                "MEMORY_REQUEST query=%r -> %d записей",
                op.query[:80],
                len(recalled),
            )
            continue
        if isinstance(op, MemoryDeleteTag):
            if agency.level < 3:
                logger.info("agency L%d: MEMORY_DELETE только при level >= 3", agency.level)
                continue
            ok = store.delete_memory(op.memory_id)
            logger.info("MEMORY_DELETE id=%s -> %s", op.memory_id, ok)
            continue
        if isinstance(op, MemorySaveTag):
            if agency.level < 1:
                logger.info("agency L0: пропуск MEMORY_SAVE")
                continue
            imp = op.importance if op.importance is not None else 0.7
            if agency.level == 1:
                logger.info(
                    "agency L1 suggest (не исполнено): MEMORY_SAVE content=%r importance=%s",
                    op.content[:500],
                    imp,
                )
                continue
            mid = store.store(default_category, op.content, imp)
            if mid:
                logger.info("MEMORY_SAVE -> id=%s", mid)
            continue
        if isinstance(op, MemoryUpdateTag):
            if agency.level < 1:
                logger.info("agency L0: пропуск MEMORY_UPDATE")
                continue
            if agency.level == 1:
                logger.info(
                    "agency L1 suggest (не исполнено): MEMORY_UPDATE id=%s importance=%s links=%s",
                    op.memory_id,
                    op.importance,
                    list(op.link_add) if op.link_add else (),
                )
                continue
            did = False
            if op.importance is not None:
                imp = op.importance
                if agency.level == 2:
                    imp = max(imp, agency.l2_importance_floor)
                ok = store.update_importance(op.memory_id, imp)
                logger.info(
                    "MEMORY_UPDATE id=%s importance=%s -> %s",
                    op.memory_id,
                    imp,
                    ok,
                )
                did = True
            if op.link_add:
                store.link_memories(op.memory_id, list(op.link_add))
                logger.info(
                    "MEMORY_UPDATE id=%s links=%s",
                    op.memory_id,
                    len(op.link_add),
                )
                did = True
            if not did:
                logger.warning("MEMORY_UPDATE без importance и links — пропуск")
