"""Точка входа операций песочницы для парсера тегов и MainLoop."""

from __future__ import annotations

import logging
from pathlib import Path

from iskra.core.config import SandboxConfig
from iskra.memory.protocol import MemoryStore
from iskra.sandbox import file_ops
from iskra.sandbox.python_runner import run_python_file, run_python_inline

logger = logging.getLogger("iskra.sandbox.manager")


class SandboxManager:
    def __init__(self, cfg: SandboxConfig) -> None:
        self._cfg = cfg
        self._root = Path(cfg.path)

    def ensure_root(self) -> None:
        if self._cfg.enabled:
            self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def extensions_ok(self) -> frozenset[str]:
        return frozenset(x.lower() for x in self._cfg.files.allowed_extensions)

    async def write_file(self, filename: str, content: str, *, memory_store: MemoryStore) -> str:
        if not self._cfg.files.enabled:
            return "[sandbox] WRITE_FILE: файлы отключены в конфиге"
        try:
            file_ops.write_text(
                self._root,
                filename,
                content,
                allowed_ext=self.extensions_ok(),
            )
            summary = f"[sandbox] WRITE_FILE OK {filename!r}"
            memory_store.store(self._cfg.memory_category, summary, 0.55)
            return summary
        except Exception as e:
            logger.warning("sandbox WRITE_FILE: %s", e)
            msg = f"[sandbox] WRITE_FILE error: {e}"
            memory_store.store(self._cfg.memory_category, msg, 0.4)
            return msg

    async def read_file(self, filename: str, *, memory_store: MemoryStore) -> str:
        if not self._cfg.files.enabled:
            return "[sandbox] READ_FILE: файлы отключены в конфиге"
        try:
            text = file_ops.read_text(
                self._root,
                filename,
                allowed_ext=self.extensions_ok(),
                max_bytes=self._cfg.files.max_file_size_bytes,
            )
            body = f"[sandbox] READ_FILE {filename!r}\n---\n{text[:8000]}"
            if len(text) > 8000:
                body += "\n[… содержимое обрезано для памяти …]"
            memory_store.store(self._cfg.memory_category, body, 0.55)
            return body[:12000]
        except Exception as e:
            logger.warning("sandbox READ_FILE: %s", e)
            msg = f"[sandbox] READ_FILE error: {e}"
            memory_store.store(self._cfg.memory_category, msg, 0.4)
            return msg

    async def list_files(self, *, memory_store: MemoryStore) -> str:
        if not self._cfg.files.enabled:
            return "[sandbox] LIST_FILES: файлы отключены в конфиге"
        try:
            names = file_ops.list_files(self._root, recursive=self._cfg.files.list_recursive)
            body = "[sandbox] LIST_FILES:\n" + "\n".join(names[:500])
            if len(names) > 500:
                body += f"\n[… всего файлов: {len(names)}]"
            memory_store.store(self._cfg.memory_category, body, 0.45)
            return body
        except Exception as e:
            logger.warning("sandbox LIST_FILES: %s", e)
            msg = f"[sandbox] LIST_FILES error: {e}"
            memory_store.store(self._cfg.memory_category, msg, 0.4)
            return msg

    async def run_python_code(self, code: str, *, memory_store: MemoryStore) -> str:
        if not self._cfg.python.enabled:
            return "[sandbox] Python отключён в конфиге"
        py = self._cfg.python
        rc, out = await run_python_inline(
            interpreter=py.interpreter,
            cwd=self._root.resolve(),
            code=code,
            timeout_seconds=float(py.timeout_seconds),
            max_output_bytes=py.max_output_bytes,
        )
        body = f"[sandbox] PYTHON_CODE rc={rc}\n---\n{out}"
        memory_store.store(self._cfg.memory_category, body, 0.65)
        return body[:12000]

    async def run_python_file(self, filename: str, *, memory_store: MemoryStore) -> str:
        if not self._cfg.python.enabled:
            return "[sandbox] Python отключён в конфиге"
        py = self._cfg.python
        rc, out = await run_python_file(
            interpreter=py.interpreter,
            cwd=self._root.resolve(),
            script_relative=filename,
            timeout_seconds=float(py.timeout_seconds),
            max_output_bytes=py.max_output_bytes,
        )
        body = f"[sandbox] RUN_PYTHON {filename!r} rc={rc}\n---\n{out}"
        memory_store.store(self._cfg.memory_category, body, 0.65)
        return body[:12000]
