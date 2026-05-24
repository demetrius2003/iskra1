"""Операции с файлами только под корнем песочницы."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("iskra.sandbox.files")


class SandboxPathError(ValueError):
    """Путь выходит за пределы ``sandbox.path``."""


def resolve_under_root(root: Path, filename: str) -> Path:
    root_r = root.resolve()
    rel = filename.strip().replace("\\", "/").strip("/")
    if not rel or ".." in Path(rel).parts:
        raise SandboxPathError(f"invalid sandbox filename: {filename!r}")
    cand = (root_r / rel).resolve()
    try:
        cand.relative_to(root_r)
    except ValueError:
        raise SandboxPathError(f"path escapes sandbox: {filename!r}") from None
    return cand


def ext_allowed(path: Path, allowed: frozenset[str]) -> bool:
    suf = path.suffix.lower()
    return suf in allowed


def write_text(root: Path, filename: str, content: str, *, allowed_ext: frozenset[str]) -> None:
    path = resolve_under_root(root, filename)
    if not ext_allowed(path, allowed_ext):
        raise SandboxPathError(f"extension not allowed: {path.suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("sandbox: записан файл %s", path.relative_to(root.resolve()))


def read_text(root: Path, filename: str, *, allowed_ext: frozenset[str], max_bytes: int) -> str:
    path = resolve_under_root(root, filename)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if not ext_allowed(path, allowed_ext):
        raise SandboxPathError(f"extension not allowed: {path.suffix}")
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"file too large ({len(data)} bytes > {max_bytes})")
    return data.decode("utf-8", errors="replace")


def list_files(root: Path, *, recursive: bool) -> list[str]:
    root_r = root.resolve()
    if not root_r.is_dir():
        return []
    out: list[str] = []
    if recursive:
        for p in root_r.rglob("*"):
            if p.is_file():
                try:
                    out.append(str(p.relative_to(root_r)).replace("\\", "/"))
                except ValueError:
                    continue
    else:
        for p in sorted(root_r.iterdir()):
            if p.is_file():
                out.append(p.name)
    return out
