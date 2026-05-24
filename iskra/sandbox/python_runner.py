"""Запуск Python в каталоге песочницы (async subprocess)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger("iskra.sandbox.python")


OUTPUT_TRUNCATED_MARKER = "\n\n[… stdout/stderr усечён по лимиту]\n"


async def run_python_inline(
    *,
    interpreter: str,
    cwd: Path,
    code: str,
    timeout_seconds: float,
    max_output_bytes: int,
) -> tuple[int, str]:
    cwd.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        interpreter,
        "-c",
        code,
        cwd=str(cwd.resolve()),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -9, f"[sandbox] timeout {timeout_seconds}s\n"

    rc = int(proc.returncode or 0)
    raw = out_b.decode("utf-8", errors="replace") if out_b else ""
    encoded = raw.encode("utf-8")
    if len(encoded) <= max_output_bytes:
        return rc, raw
    chunk = encoded[: max_output_bytes - len(OUTPUT_TRUNCATED_MARKER.encode("utf-8"))]
    trimmed = chunk.decode("utf-8", errors="replace") + OUTPUT_TRUNCATED_MARKER
    return rc, trimmed


async def run_python_file(
    *,
    interpreter: str,
    cwd: Path,
    script_relative: str,
    timeout_seconds: float,
    max_output_bytes: int,
) -> tuple[int, str]:
    from iskra.sandbox.file_ops import resolve_under_root

    scr = resolve_under_root(cwd, script_relative)
    if scr.suffix.lower() != ".py":
        return 1, "[sandbox] RUN_PYTHON: только .py файлы\n"
    cwd.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        interpreter,
        str(scr),
        cwd=str(cwd.resolve()),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -9, f"[sandbox] timeout {timeout_seconds}s ({script_relative})\n"

    rc = int(proc.returncode or 0)
    raw = out_b.decode("utf-8", errors="replace") if out_b else ""
    encoded = raw.encode("utf-8")
    if len(encoded) <= max_output_bytes:
        return rc, raw
    chunk = encoded[: max_output_bytes - len(OUTPUT_TRUNCATED_MARKER.encode("utf-8"))]
    trimmed = chunk.decode("utf-8", errors="replace") + OUTPUT_TRUNCATED_MARKER
    return rc, trimmed
