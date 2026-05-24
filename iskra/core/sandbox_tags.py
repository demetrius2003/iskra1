"""Парсинг и исполнение тегов песочницы в ответе LLM (docs/TZ_ISKRA_0.7.0.md)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from iskra.core.memory_tags import split_tag_fields
from iskra.memory.protocol import MemoryStore
from iskra.sandbox.sandbox_manager import SandboxManager

logger = logging.getLogger("iskra.sandbox.tags")

_PYTHON_BLOCK = re.compile(r"\[PYTHON_CODE\]\s*(.*?)\s*\[/PYTHON_CODE\]", re.IGNORECASE | re.DOTALL)

_LINE_WRITE = re.compile(r"^\[WRITE_FILE\]\s*(.*)\s*$", re.IGNORECASE)
_LINE_READ = re.compile(r"^\[READ_FILE\]\s*(.*)\s*$", re.IGNORECASE)
_LINE_LIST = re.compile(r"^\[LIST_FILES\]\s*$", re.IGNORECASE)
_LINE_RUN = re.compile(r"^\[RUN_PYTHON\]\s*(.*)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class SandboxWriteOp:
    filename: str
    content: str


@dataclass(frozen=True)
class SandboxReadOp:
    filename: str


@dataclass(frozen=True)
class SandboxListOp:
    pass


@dataclass(frozen=True)
class SandboxRunPythonOp:
    filename: str


@dataclass(frozen=True)
class SandboxInlinePythonOp:
    code: str


SandboxOp = (
    SandboxWriteOp
    | SandboxReadOp
    | SandboxListOp
    | SandboxRunPythonOp
    | SandboxInlinePythonOp
)


def strip_sandbox_markup(text: str) -> str:
    """Удалить блоки PYTHON_CODE и одиночные строки sandbox-тегов из текста для вывода."""
    s = _PYTHON_BLOCK.sub("", text)
    lines_out: list[str] = []
    for line in s.splitlines():
        st = line.strip()
        if _PYTHON_BLOCK.search(st):
            continue
        if (
            _LINE_WRITE.match(st)
            or _LINE_READ.match(st)
            or _LINE_LIST.match(st)
            or _LINE_RUN.match(st)
            or st.upper().startswith("[PYTHON_CODE]")
            or st.upper().startswith("[/PYTHON_CODE]")
        ):
            continue
        lines_out.append(line)
    return "\n".join(lines_out)


def parse_sandbox_tags(text: str) -> list[SandboxOp]:
    ops: list[SandboxOp] = []

    for m in _PYTHON_BLOCK.finditer(text):
        code = (m.group(1) or "").strip()
        if code:
            ops.append(SandboxInlinePythonOp(code=code))

    for line in text.splitlines():
        st = line.strip()
        m = _LINE_WRITE.match(st)
        if m:
            fld = {k.strip().lower(): v for k, v in split_tag_fields(m.group(1))}
            fn = fld.get("filename") or fld.get("file")
            ct = fld.get("content")
            if fn and ct is not None:
                ops.append(SandboxWriteOp(filename=fn.strip(), content=ct))
            else:
                logger.warning("[WRITE_FILE] без filename или content")
            continue
        m = _LINE_READ.match(st)
        if m:
            fld = {k.strip().lower(): v for k, v in split_tag_fields(m.group(1))}
            fn = fld.get("filename") or fld.get("file")
            if fn:
                ops.append(SandboxReadOp(filename=fn.strip()))
            else:
                logger.warning("[READ_FILE] без filename")
            continue
        if _LINE_LIST.match(st):
            ops.append(SandboxListOp())
            continue
        m = _LINE_RUN.match(st)
        if m:
            fld = {k.strip().lower(): v for k, v in split_tag_fields(m.group(1))}
            fn = fld.get("filename") or fld.get("file")
            if fn:
                ops.append(SandboxRunPythonOp(filename=fn.strip()))
            else:
                logger.warning("[RUN_PYTHON] без filename")
            continue
    return ops


async def apply_sandbox_tags(
    ops: list[SandboxOp],
    *,
    manager: SandboxManager,
    memory_store: MemoryStore,
    max_ops: int,
) -> None:
    """Исполняет до ``max_ops`` операций подряд."""
    if max_ops < 1:
        return
    for i, op in enumerate(ops[:max_ops]):
        try:
            if isinstance(op, SandboxWriteOp):
                await manager.write_file(op.filename, op.content, memory_store=memory_store)
            elif isinstance(op, SandboxReadOp):
                await manager.read_file(op.filename, memory_store=memory_store)
            elif isinstance(op, SandboxListOp):
                await manager.list_files(memory_store=memory_store)
            elif isinstance(op, SandboxRunPythonOp):
                await manager.run_python_file(op.filename, memory_store=memory_store)
            elif isinstance(op, SandboxInlinePythonOp):
                await manager.run_python_code(op.code, memory_store=memory_store)
        except Exception as e:
            logger.warning("sandbox op #%d failed: %s", i, e)
        if i + 1 >= max_ops:
            if len(ops) > max_ops:
                logger.info("sandbox: лимит max_tag_ops_per_tick=%d, пропуск остальных", max_ops)
            break
